"""Diff RÉEL ↔ DÉCLARATION pour `nestor refresh` (ADR 0076).

`refresh` matérialise une évolution VOULUE du réel dans `topology.yaml` (nœud/couche
ajoutés délibérément), bornée par l'ADR 0046 (jamais blanchir une dérive en silence :
diff + confirmation). Ce module est PUR : il CLASSE un écart déjà sondé (topo déclarée
+ réel réduit par la façade via les sondes de `discover`) en un PLAN d'ajustement
lisible. Il N'ÉCRIT rien — la fusion (édition texte du fichier) et la collecte
(kubectl, via `discover`) restent à la façade (ADR 0049/0074 §6).

Périmètre v1 (ADR 0076 §2) — dimensions OBSERVABLES ET DÉCLARATIVES :
- **nœuds & rôles** : un nœud réel Ready absent de la déclaration → proposé à l'ajout ;
- **couches montées** : une couche dont le signal d'infra est présent mais hors
  `layers:` → proposée à l'ajout ;
- **backend de stockage** : backend réel (StorageClass) ≠ `storage.backend` déclaré → signalé.

HORS périmètre (ADR 0076 §2) : le **scale** (runtime, ADR 0072 — pas une dimension
déclarative). La **suppression** (déclaré mais absent) est SIGNALÉE séparément mais
n'est PAS appliquée en v1 (réservée à `--prune`, ADR 0076 §3) — une absence peut être
une panne (ADR 0046), jamais retirée sur la seule foi du réel.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NodeChange:
    """Un nœud réel à AJOUTER à la déclaration (présent sur le cluster, pas déclaré)."""

    name: str
    roles: list[str]


@dataclass(frozen=True)
class RefreshPlan:
    """Plan d'ajustement réel→déclaration (PUR, sans I/O). Listes vides = rien à faire.

    AJOUTS (le réel est en AVANCE sur la déclaration — évolution voulue à matérialiser) :
    - `nodes_to_add` : nœuds réels Ready absents de `nodes:` ;
    - `layers_to_add` : couches saines absentes de `layers:` ;
    - `backend_change` : (déclaré, réel) si le backend réel diffère, sinon None.

    SIGNALÉS, NON appliqués en v1 (ADR 0076 §3 — défaut prudent, réservé à --prune) :
    - `nodes_absent` : déclarés mais SANS nœud réel (détruit ? panne ?) ;
    - `layers_absent` : déclarées mais signal d'infra ABSENT du réel.
    """

    nodes_to_add: list[NodeChange] = field(default_factory=list)
    layers_to_add: list[str] = field(default_factory=list)
    backend_change: tuple[str, str] | None = None
    nodes_absent: list[str] = field(default_factory=list)
    layers_absent: list[str] = field(default_factory=list)

    @property
    def has_additions(self) -> bool:
        """Y a-t-il quelque chose à MATÉRIALISER (le geste appliqué par refresh) ?"""
        return bool(self.nodes_to_add or self.layers_to_add or self.backend_change)

    @property
    def has_signals(self) -> bool:
        """Y a-t-il quelque chose à SIGNALER (ajouts OU absences) ? (rien → topo à jour)"""
        return self.has_additions or bool(self.nodes_absent or self.layers_absent)


def plan_refresh(
    *,
    declared_nodes: list[dict],
    declared_layers: list[str],
    declared_backend: str,
    real_nodes: list[dict],
    real_layers: list[str],
    real_backend: str | None,
) -> RefreshPlan:
    """Calcule le plan d'ajustement réel→déclaration (PUR, ADR 0076 §2).

    `declared_*` : ce que `topology.yaml` déclare (nodes = [{name, roles}], layers, backend).
    `real_*` : ce que la façade a sondé du cluster (mêmes formes ; `real_backend` None si
    indétectable — cluster injoignable / aucune SC reconnue → on ne PROPOSE rien dessus).

    Règles :
    - un nœud réel dont le `name` n'est pas déclaré → `nodes_to_add` (rôles du réel) ;
    - un nœud déclaré sans équivalent réel → `nodes_absent` (signalé, pas retiré) ;
    - une couche réelle hors `layers:` → `layers_to_add` ; déclarée mais absente du réel
      → `layers_absent` ;
    - backend réel ≠ déclaré (et détectable) → `backend_change=(déclaré, réel)`.
    On compare les nœuds par NOM (clé stable) ; les rôles d'un nœud déjà déclaré ne sont
    pas « corrigés » en v1 (un changement de rôle est un geste plus délicat — futur).
    """
    declared_names = {n.get("name") for n in declared_nodes}
    real_by_name = {n.get("name"): n for n in real_nodes}

    nodes_to_add = [
        NodeChange(name=n["name"], roles=list(n.get("roles") or []))
        for n in real_nodes
        if n.get("name") not in declared_names
    ]
    nodes_absent = [n.get("name") for n in declared_nodes if n.get("name") not in real_by_name]

    declared_layer_set = set(declared_layers)
    real_layer_set = set(real_layers)
    layers_to_add = [layer for layer in real_layers if layer not in declared_layer_set]
    layers_absent = [layer for layer in declared_layers if layer not in real_layer_set]

    backend_change: tuple[str, str] | None = None
    if real_backend is not None and real_backend != declared_backend:
        backend_change = (declared_backend, real_backend)

    return RefreshPlan(
        nodes_to_add=nodes_to_add,
        layers_to_add=layers_to_add,
        backend_change=backend_change,
        nodes_absent=[n for n in nodes_absent if n is not None],
        layers_absent=layers_absent,
    )


def format_plan(plan: RefreshPlan) -> list[str]:
    """Rend le plan en lignes de diff lisibles (préfixe `+` ajout, `~` change, `-` absent).

    PUR (renvoie des chaînes, n'imprime pas — la façade choisit le flux/couleur). Les
    absences sont préfixées `-` mais marquées « signalé, non retiré » : ADR 0076 §3 (on
    n'efface pas une intention déclarée sur la foi d'une absence)."""
    lines: list[str] = []
    for nc in plan.nodes_to_add:
        roles = ",".join(nc.roles) or "—"
        lines.append(f"  + nœud `{nc.name}` (rôles : {roles})")
    for layer in plan.layers_to_add:
        lines.append(f"  + couche `{layer}`")
    if plan.backend_change:
        declared, real = plan.backend_change
        lines.append(f"  ~ storage.backend : `{declared}` → `{real}`")
    for name in plan.nodes_absent:
        lines.append(f"  - nœud `{name}` déclaré mais ABSENT du réel (signalé, non retiré)")
    for layer in plan.layers_absent:
        lines.append(f"  - couche `{layer}` déclarée mais ABSENTE du réel (signalé, non retiré)")
    return lines
