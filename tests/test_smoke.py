"""Tests du smoke-test de réversibilité (nestor/smoke.py, P6).

On injecte un FAUX client (`api=`) : aucun cluster réel, aucun réseau en CI. La
preuve réelle d'un smoke-test passe par un run de banc (ADR 0034/0052). On couvre
le cycle nominal (réversible) et les échecs (création/suppression KO, cluster
absent → SmokeUnavailable).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor import smoke  # noqa: E402


class _ApiExc(Exception):
    """Imite kubernetes.client.exceptions.ApiException (status + reason)."""

    def __init__(self, status, reason="boom"):
        self.status = status
        self.reason = reason
        super().__init__(reason)


# smoke.py importe ApiException localement ; on patche le symbole pour que nos
# fausses exceptions soient reconnues comme telles.
import kubernetes.client.exceptions as _kexc  # noqa: E402


class FakeApi:
    """Cluster en mémoire : un set de namespaces ; create/read/delete réversibles."""

    def __init__(
        self,
        *,
        fail_create=False,
        fail_delete=False,
        leak_on_delete=False,
        absent_after_create=False,
        terminating_reads=0,
    ):
        self.namespaces = set()
        self.fail_create = fail_create
        self.fail_delete = fail_delete
        self.leak_on_delete = leak_on_delete
        # Simule une anomalie « créé mais introuvable » à la relecture.
        self.absent_after_create = absent_after_create
        # Simule le Terminating : N relectures « encore présent » après delete
        # avant de disparaître (404). 0 = disparition immédiate.
        self.terminating_reads = terminating_reads
        self._deleted = None

    def create_namespace(self, body, _request_timeout=None):
        if self.fail_create:
            raise _kexc.ApiException(status=409, reason="AlreadyExists")
        self.namespaces.add(body.metadata.name)

    def read_namespace(self, name, _request_timeout=None):
        if self.absent_after_create and name in self.namespaces:
            # « présent » selon le set, mais l'API répond 404 (race/webhook).
            raise _kexc.ApiException(status=404, reason="NotFound")
        if self._deleted == name and self.terminating_reads > 0:
            self.terminating_reads -= 1
            return object()  # encore en Terminating
        if name not in self.namespaces:
            raise _kexc.ApiException(status=404, reason="NotFound")
        return object()

    def delete_namespace(self, name, _request_timeout=None):
        if self.fail_delete:
            raise _kexc.ApiException(status=500, reason="Internal")
        self._deleted = name
        if not self.leak_on_delete:
            self.namespaces.discard(name)


def _no_sleep(_):
    """sleep injecté no-op : le poll de _wait_gone n'attend pas en test."""


def _fast_clock():
    """Horloge factice qui bondit de 10 s à chaque appel : le poll de _wait_gone
    atteint son deadline en quelques itérations, sans attente réelle."""
    t = {"v": 0.0}

    def tick():
        t["v"] += 10.0
        return t["v"]

    return tick


class SmokeNominal(unittest.TestCase):
    def test_full_cycle_is_reversible(self):
        api = FakeApi()
        res = smoke.run_smoke("topo-smoke-x", api=api, sleep=_no_sleep)
        self.assertTrue(res.reversible)
        self.assertEqual(
            [s.nom for s in res.steps],
            ["créer", "vérifier présent", "détruire", "vérifier détruit"],
        )
        self.assertTrue(all(s.ok for s in res.steps))
        self.assertNotIn("topo-smoke-x", api.namespaces)  # bien nettoyé

    def test_default_namespace(self):
        res = smoke.run_smoke(api=FakeApi(), sleep=_no_sleep)
        self.assertEqual(res.namespace, "topology-smoke")

    def test_terminating_then_gone_is_reversible(self):
        # L'objet reste en Terminating 3 relectures puis disparaît → réversible
        # (le poll _wait_gone attend le 404 réel, pas un check immédiat).
        api = FakeApi(terminating_reads=3)
        res = smoke.run_smoke("x", api=api, sleep=_no_sleep)
        self.assertTrue(res.reversible)
        self.assertTrue(res.steps[-1].ok)


class SmokeFailures(unittest.TestCase):
    def test_create_failure_stops_and_not_reversible(self):
        res = smoke.run_smoke("x", api=FakeApi(fail_create=True), sleep=_no_sleep)
        self.assertFalse(res.reversible)
        self.assertEqual(res.steps[0].nom, "créer")
        self.assertFalse(res.steps[0].ok)
        self.assertEqual(len(res.steps), 1)  # on s'arrête à l'échec de création

    def test_created_but_absent_stops_before_delete(self):
        # Créé mais introuvable (anomalie infra) → on s'arrête à « vérifier présent »
        # sans tenter de détruire un objet déjà absent (diagnostic franc).
        res = smoke.run_smoke("x", api=FakeApi(absent_after_create=True), sleep=_no_sleep)
        self.assertFalse(res.reversible)
        self.assertEqual([s.nom for s in res.steps], ["créer", "vérifier présent"])
        self.assertFalse(res.steps[-1].ok)

    def test_delete_failure_not_reversible(self):
        res = smoke.run_smoke("x", api=FakeApi(fail_delete=True), sleep=_no_sleep)
        self.assertFalse(res.reversible)
        noms = [s.nom for s in res.steps]
        self.assertIn("détruire", noms)
        self.assertFalse(next(s for s in res.steps if s.nom == "détruire").ok)

    def test_leak_on_delete_is_not_reversible(self):
        # suppression "réussie" mais l'objet reste indéfiniment → étape 4 échoue
        # après le timeout d'attente (horloge factice : pas d'attente réelle).
        res = smoke.run_smoke(
            "x", api=FakeApi(leak_on_delete=True), sleep=_no_sleep, clock=_fast_clock()
        )
        self.assertFalse(res.reversible)
        self.assertFalse(res.steps[-1].ok)


class SmokeUnavailable(unittest.TestCase):
    def test_unconfigured_cluster_raises(self):
        # _core_v1 lève SmokeUnavailable si pas de config — on simule via stub.
        orig = smoke._core_v1

        def boom():
            raise smoke.SmokeUnavailable("aucune configuration kubernetes")

        smoke._core_v1 = boom
        self.addCleanup(setattr, smoke, "_core_v1", orig)
        with self.assertRaises(smoke.SmokeUnavailable):
            smoke.run_smoke("x")  # api=None → appelle _core_v1


if __name__ == "__main__":
    unittest.main()
