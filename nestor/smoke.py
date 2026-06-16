"""Smoke-test de réversibilité (P6, ADR 0056 §8.7).

Éprouve l'apply ET le rollback (rejoint le rollback-par-phase,
[ADR 0054](../decisions/0054-rollback-par-phase-banc.md)) par le cycle le plus
simple : **créer** un objet k8s (un Namespace jetable) → **vérifier présent** →
**détruire** → **vérifier détruit**. Si chaque étape réussit, le cluster honore
la création comme la suppression : il est *réversible*.

C'est le SEUL module qui importe le client `kubernetes` (couche d'exécution
isolée, même patron que `runner.py` pour ansible-runner — frontière pur/I-O,
ADR 0017). Import LOCAL : la lib n'est chargée que lorsqu'on touche réellement le
cluster, et un `ImportError` se mappe en erreur d'usage. Les tests _stubbent_
`_core_v1` (l'accès au client) : aucun cluster en CI ; la preuve réelle passe par
un run de banc consigné (ADR 0034/0052).

Aucune convergence réimplémentée : on crée/lit/supprime et on consomme le verdict
exposé par l'API (le Namespace est-il présent ? a-t-il disparu ?), point.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_DEFAULT_NS_PREFIX = "topology-smoke"
# Délai max par appel API, en (connexion, lecture) secondes : un cluster
# injoignable doit ÉCHOUER VITE (message clair), jamais bloquer indéfiniment (le
# client kubernetes n'a pas de timeout par défaut). On désactive aussi les retries
# (sinon le timeout est multiplié par le nombre de tentatives).
_REQUEST_TIMEOUT = (5, 10)
# Attente de la disparition réelle après delete (Terminating → 404). Un namespace
# vide disparaît en < 1 s en général ; on laisse une marge.
_DELETE_WAIT_S = 30
_POLL_INTERVAL_S = 1


def _now() -> float:
    """Horloge monotone (testable)."""
    import time

    return time.monotonic()


@dataclass
class SmokeStep:
    nom: str
    ok: bool
    detail: str = ""


@dataclass
class SmokeResult:
    """Verdict du smoke-test. `reversible` = toutes les étapes ont réussi."""

    namespace: str
    steps: list[SmokeStep] = field(default_factory=list)

    @property
    def reversible(self) -> bool:
        return bool(self.steps) and all(s.ok for s in self.steps)


class SmokeUnavailable(RuntimeError):
    """Client `kubernetes` introuvable ou cluster injoignable (mappé en usage)."""


def _core_v1():
    """Client CoreV1Api configuré (import LOCAL ; in-cluster ou kubeconfig).

    Point d'injection unique pour les tests (monkeypatch). Mappe un ImportError ou
    une erreur de config en SmokeUnavailable (message actionnable).
    """
    try:
        from kubernetes import client, config
    except ImportError as exc:  # pragma: no cover - dépendance épinglée
        raise SmokeUnavailable("client kubernetes introuvable — `uv sync`") from exc
    try:
        config.load_kube_config()
    except Exception:  # noqa: BLE001 - fallback in-cluster si pas de kubeconfig local
        try:
            config.load_incluster_config()
        except Exception as exc:  # noqa: BLE001
            raise SmokeUnavailable(
                "aucune configuration kubernetes (ni kubeconfig local ni in-cluster)"
            ) from exc
    # Couper les retries : sans ça, un timeout de connexion est retenté plusieurs
    # fois et le smoke-test bloque bien au-delà de _REQUEST_TIMEOUT.
    cfg = client.Configuration.get_default_copy()
    cfg.retries = 0
    return client.CoreV1Api(client.ApiClient(cfg))


def _ns_exists(api, name: str) -> bool:
    """Le namespace existe-t-il ? (lecture ; 404 → absent)."""
    from kubernetes.client.exceptions import ApiException

    try:
        api.read_namespace(name, _request_timeout=_REQUEST_TIMEOUT)
        return True
    except ApiException as exc:
        if exc.status == 404:
            return False
        raise


def _wait_gone(api, name: str, *, timeout_s: int, sleep, clock=_now) -> bool:
    """Attend la disparition RÉELLE du namespace (404), jusqu'à `timeout_s`.

    La suppression d'un namespace k8s n'est PAS instantanée : il passe en
    `Terminating` quelques secondes (finalizers) avant de disparaître. Vérifier
    l'absence juste après `delete` donne un faux « encore présent ». On poll donc
    jusqu'au 404 confirmé (ou expiration). `sleep`/`clock` sont injectés (test sans
    attente réelle ni horloge murale).
    """
    deadline = clock() + timeout_s
    while True:
        if not _ns_exists(api, name):
            return True
        if clock() >= deadline:
            return False
        sleep(_POLL_INTERVAL_S)


def run_smoke(namespace: str | None = None, *, api=None, sleep=None, clock=_now) -> SmokeResult:
    """Cycle créer → vérifier présent → détruire → vérifier détruit (réversibilité).

    `namespace` : nom de l'objet jetable (défaut : préfixe générique). `api` :
    client injectable (tests) ; None → `_core_v1()` réel. `sleep` : fonction
    d'attente injectable (tests → no-op). Renvoie un SmokeResult.

    Notes de robustesse (issues de la revue) :
    - on **attend** la disparition réelle du namespace (`Terminating` → 404),
      jusqu'à `_DELETE_WAIT_S`, plutôt qu'un check immédiat qui serait un faux
      négatif sur un vrai cluster ;
    - si la suppression ÉCHOUE, le namespace **fuit** sur le cluster (verdict
      `reversible=False` signalé) — à nettoyer à la main (`kubectl delete ns …`).
    """
    import time

    from kubernetes import client as k8s
    from kubernetes.client.exceptions import ApiException
    from urllib3.exceptions import HTTPError

    ns = namespace or _DEFAULT_NS_PREFIX
    api = api or _core_v1()
    sleep = sleep or time.sleep
    result = SmokeResult(namespace=ns)

    # 1. Créer. Un cluster injoignable (timeout/connexion) → SmokeUnavailable (code
    # 2 usage), pas un faux verdict « non réversible » : on n'a rien pu tester.
    try:
        api.create_namespace(
            k8s.V1Namespace(metadata=k8s.V1ObjectMeta(name=ns)),
            _request_timeout=_REQUEST_TIMEOUT,
        )
        result.steps.append(SmokeStep("créer", True, f"namespace {ns} créé"))
    except ApiException as exc:
        if exc.status is None or exc.status == 0:
            raise SmokeUnavailable(f"cluster injoignable : {exc.reason}") from exc
        result.steps.append(SmokeStep("créer", False, f"échec création : {exc.reason}"))
        return result
    except HTTPError as exc:  # timeout / connexion refusée (urllib3)
        raise SmokeUnavailable(f"cluster injoignable : {exc}") from exc

    # 2. Vérifier présent. Créé mais introuvable = anomalie infra (webhook, race) :
    # on s'arrête là — inutile de « détruire » un objet déjà absent (diagnostic faux).
    present = _ns_exists(api, ns)
    result.steps.append(
        SmokeStep("vérifier présent", present, "présent" if present else "absent !")
    )
    if not present:
        return result

    # 3. Détruire.
    try:
        api.delete_namespace(ns, _request_timeout=_REQUEST_TIMEOUT)
        result.steps.append(SmokeStep("détruire", True, f"suppression de {ns} demandée"))
    except ApiException as exc:
        result.steps.append(SmokeStep("détruire", False, f"échec suppression : {exc.reason}"))
        return result

    # 4. Vérifier détruit — on ATTEND le 404 réel (Terminating → disparu), pas un
    # check immédiat (faux négatif sur un vrai cluster).
    gone = _wait_gone(api, ns, timeout_s=_DELETE_WAIT_S, sleep=sleep, clock=clock)
    result.steps.append(
        SmokeStep(
            "vérifier détruit",
            gone,
            "détruit" if gone else f"encore présent après {_DELETE_WAIT_S}s (Terminating bloqué ?)",
        )
    )
    return result
