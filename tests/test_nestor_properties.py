"""Property-based testing des fonctions PURES de `nestor` (ADR 0087).

Hypothesis génère des entrées variées (chaînes arbitraires, listes de
provisioners, entiers aux bornes) et vérifie des INVARIANTS — pas des sorties
figées. C'est le « fuzzing » défendable de ce dépôt d'IaC (Scorecard `Fuzzing`) :
il cible les fonctions qui parsent/classent une entrée externe non fiable
(sorties de `run-phases.sh`, provisioners de StorageClass lus du cluster) et les
dérivations à invariant net (verdicts de santé, clamps de replicas).

`unittest` + `@given` : ramassé par `python -m unittest discover -s tests`
(ci.yml) — aucune bascule pytest (ADR 0087). PUR : aucun subprocess, aucun banc.
"""

import os
import sys
import unittest

from hypothesis import given
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor.discover import (  # noqa: E402
    ABSENT,
    DEGRADE,
    SAIN,
    classify_backend_drift,
    classify_health,
    detect_backend,
)
from nestor.facts import parse_facts  # noqa: E402
from nestor.model import TopologyError  # noqa: E402
from nestor.profile import storage_params  # noqa: E402
from nestor.scale import target_replicas  # noqa: E402

_VERDICTS = {SAIN, DEGRADE, ABSENT}
_KNOWN_FACT_KEYS = {"CP_IP", "L2_IFACE", "VIP", "VIP_IFACE"}

# Lignes ressemblant à la VRAIE sortie de `run-phases.sh facts` (clé connue ou
# bruit) — du `st.text()` brut ne produit quasi jamais de ligne `KEY=VALUE`
# valide, donc l'idempotence ne serait testée que sur le dict vide. On fabrique
# des sorties réalistes : des lignes de contrat mêlées à des logs parasites.
_fact_values = st.text(alphabet=st.characters(blacklist_characters="\n="), max_size=15).filter(
    lambda v: v == v.strip()
)  # valeurs déjà strippées (parse_facts strippe)
_contract_lines = st.fixed_dictionaries({k: _fact_values for k in _KNOWN_FACT_KEYS}).map(
    lambda d: [f"{k}={v}" for k, v in d.items()]
)
_noise_lines = st.lists(
    st.text(alphabet=st.characters(blacklist_characters="\n"), max_size=20), max_size=4
)
# Fragments de provisioners reconnus + bruit, pour fabriquer des listes réalistes.
_SC_TOKENS = ["rook-ceph", "rbd.csi.ceph.com", "rancher.io/local-path", "local-path", "noise", ""]
_sc_lists = st.lists(st.sampled_from(_SC_TOKENS), max_size=6)


class ParseFactsProperties(unittest.TestCase):
    """`facts.parse_facts` — parse la sortie KEY=VALUE du contrat de banc."""

    @given(st.text())
    def test_never_raises_on_arbitrary_text(self, stdout):
        # Robustesse : une sortie bavarde/binaire ne doit jamais faire lever.
        parse_facts(stdout)

    @given(st.text())
    def test_keys_subset_of_contract(self, stdout):
        # Seules les clés connues du contrat sont retenues — jamais de bruit.
        self.assertTrue(set(parse_facts(stdout)) <= _KNOWN_FACT_KEYS)

    @given(st.text())
    def test_idempotent_on_rerendered_output(self, stdout):
        # Re-rendre le dict parsé en KEY=VALUE puis reparser donne le même dict
        # (le parsing d'une sortie « propre » est un point fixe).
        once = parse_facts(stdout)
        rerendered = "\n".join(f"{k}={v}" for k, v in once.items())
        self.assertEqual(parse_facts(rerendered), once)

    @given(_contract_lines, _noise_lines)
    def test_extracts_real_contract_lines_amid_noise(self, contract, noise):
        # Sur une sortie RÉALISTE (lignes de contrat mêlées de logs), parse_facts
        # extrait exactement les clés connues — le bruit est ignoré. Sans cette
        # stratégie ciblée, du texte aléatoire ne produit jamais de ligne valide
        # et l'invariant ne serait vérifié que sur le dict vide.
        lines = noise + contract  # bruit AVANT (les vraies lignes priment au parse)
        parsed = parse_facts("\n".join(lines))
        self.assertEqual(set(parsed), _KNOWN_FACT_KEYS)


class DetectBackendProperties(unittest.TestCase):
    """`discover.detect_backend` — déduit le backend des provisioners de SC."""

    @given(_sc_lists)
    def test_result_in_known_set(self, provisioners):
        # Le backend déduit est toujours l'un des deux backends du socle.
        self.assertIn(detect_backend(provisioners), {"ceph", "local-path"})

    @given(_sc_lists)
    def test_ceph_marker_wins(self, provisioners):
        # Un provisioner ceph présent ⇒ ceph, même mêlé à du local-path (ceph
        # prime, cf. docstring : un cluster ceph garde souvent local-path).
        self.assertEqual(detect_backend([*provisioners, "rbd.csi.ceph.com"]), "ceph")

    @given(_sc_lists)
    def test_default_is_local_path(self, provisioners):
        # Aucun signal reconnu (que du bruit) ⇒ défaut local-path, jamais ceph.
        noise = [p for p in provisioners if "ceph" not in p and "local-path" not in p]
        self.assertEqual(detect_backend(noise), "local-path")


class ClassifyBackendDriftProperties(unittest.TestCase):
    """`discover.classify_backend_drift` — CIBLE BUG (logique de contradiction).

    Ne signale un drift QUE sur un signal reconnu contredisant le déclaré ; sinon
    None. La subtilité (asymétrie ceph/local-path) en fait la fonction la plus à
    risque — Hypothesis cherche ici activement une entrée qui casse l'invariant.
    """

    @given(st.text(max_size=12), _sc_lists)
    def test_never_raises_and_result_shape(self, declared, provisioners):
        # Pour TOUT backend déclaré (même absurde) et TOUTE liste de SC : ne lève
        # jamais, et le résultat est None ou un backend reconnu (jamais autre).
        result = classify_backend_drift(declared, provisioners)
        self.assertIn(result, {None, "ceph", "local-path"})

    @given(st.sampled_from(["ceph", "local-path", "unknown"]))
    def test_no_signal_means_no_drift(self, declared):
        # Cluster vide / injoignable (aucune SC reconnue) ⇒ pas de drift
        # affirmable, quel que soit le déclaré (on ne confond pas vide et réel).
        self.assertIsNone(classify_backend_drift(declared, ["noise", ""]))

    @given(_sc_lists)
    def test_ceph_present_contradicts_non_ceph(self, provisioners):
        # Des SC ceph résiduelles alors que le déclaré n'est pas ceph ⇒ drift=ceph
        # (le cas vécu #356 : bascule ceph→local-path, rook-ceph orphelin).
        self.assertEqual(classify_backend_drift("local-path", [*provisioners, "rook-ceph"]), "ceph")

    @given(st.sampled_from(["ceph", "local-path", "unknown"]), _sc_lists)
    def test_drift_differs_from_declared_when_set(self, declared, provisioners):
        # Un drift signalé contredit TOUJOURS le déclaré (sinon ce n'est pas un
        # drift) — invariant transverse aux deux branches.
        result = classify_backend_drift(declared, provisioners)
        if result is not None:
            self.assertNotEqual(result, declared)


class ClassifyHealthProperties(unittest.TestCase):
    """`discover.classify_health` — agrège des sondes en verdicts de santé."""

    @given(
        nodes_ready=st.integers(min_value=0, max_value=20),
        nodes_total=st.integers(min_value=0, max_value=20),
        workloads_degraded=st.lists(st.text(max_size=10), max_size=5),
        pvc_pending=st.integers(min_value=0, max_value=20),
        pvc_total=st.integers(min_value=0, max_value=20),
        osds_up=st.one_of(st.none(), st.integers(min_value=0, max_value=50)),
        osds_expected=st.one_of(st.none(), st.integers(min_value=0, max_value=50)),
    )
    def test_all_verdicts_in_known_set(self, **kw):
        # Quelles que soient les sondes, chaque verdict ∈ {sain, dégradé, absent}.
        items = classify_health(**kw)
        self.assertTrue(items, "le bilan n'est jamais vide")
        for item in items:
            self.assertIn(item.verdict, _VERDICTS)

    @given(
        nodes_total=st.integers(min_value=1, max_value=20),
        pvc_total=st.integers(min_value=0, max_value=20),
        pvc_pending=st.integers(min_value=0, max_value=20),
    )
    def test_all_nodes_ready_is_healthy(self, nodes_total, pvc_total, pvc_pending):
        # nodes_ready == nodes_total > 0 ⇒ dimension « nœuds » saine.
        items = classify_health(
            nodes_ready=nodes_total,
            nodes_total=nodes_total,
            pvc_total=pvc_total,
            pvc_pending=pvc_pending,
        )
        nodes = next(i for i in items if i.dimension == "nœuds")
        self.assertEqual(nodes.verdict, SAIN)


class StorageParamsProperties(unittest.TestCase):
    """`profile.storage_params` — dérive les paramètres fins d'un backend."""

    _EXPECTED_KEYS = {"storage_class", "s3_backing", "s3_endpoint", "argocd_apply_gateway"}

    @given(st.sampled_from(["ceph", "local-path"]))
    def test_known_backend_returns_expected_keys(self, backend):
        # Backend valide ⇒ dict avec exactement les 4 clés du contrat de profil.
        self.assertEqual(set(storage_params(backend)), self._EXPECTED_KEYS)

    @given(st.sampled_from(["ceph", "local-path"]))
    def test_returns_fresh_copy(self, backend):
        # Le retour est une COPIE : muter le dict rendu ne contamine pas l'appel
        # suivant (sinon une dérivation polluerait la constante partagée).
        storage_params(backend)["storage_class"] = "MUTATED"
        self.assertNotEqual(storage_params(backend)["storage_class"], "MUTATED")

    @given(st.text())
    def test_unknown_backend_raises(self, backend):
        # Tout backend hors {ceph, local-path} ⇒ TopologyError (jamais un dict).
        if backend in {"ceph", "local-path"}:
            return  # filtré : ces deux-là sont valides
        with self.assertRaises(TopologyError):
            storage_params(backend)


class TargetReplicasProperties(unittest.TestCase):
    """`scale.target_replicas` — clamp `max(1, min(workers, plafond))`."""

    @given(
        workers_ready=st.integers(min_value=0, max_value=100),
        max_replicas=st.integers(min_value=1, max_value=100),
    )
    def test_clamped_between_one_and_max(self, workers_ready, max_replicas):
        # Jamais 0 (un service ne se coupe pas), jamais > plafond, jamais >
        # workers Ready (pas de pod Pending faute de nœud).
        result = target_replicas(workers_ready, max_replicas)
        self.assertGreaterEqual(result, 1)
        self.assertLessEqual(result, max_replicas)
        self.assertLessEqual(result, max(workers_ready, 1))


if __name__ == "__main__":
    unittest.main()
