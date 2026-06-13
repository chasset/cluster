"""Modèle de données d'une topologie (ADR 0056 §1).

Chargement + validation minimale de `topology.yaml`. Pas de pydantic à ce
palier (P0-P1) : un dataclass + des dérivations pures suffisent ; la validation
de schéma riche viendra en P2 (graphe de dépendances de profil). On reste sur
la stdlib + pyyaml (ADR 0049 : pas de dépendance avant le besoin).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml


class TopologyError(ValueError):
    """topology.yaml invalide (champ manquant, rôle inconnu, incohérence)."""


VALID_ROLES = {"control", "worker", "storage"}
VALID_TARGET_KINDS = {"prod", "lima"}
# Modes du point d'entrée HA devant les CP (ADR 0047/0055). kube-vip-arp =
# bare-metal/local (pod statique, annonce ARP) ; kube-vip-lb = via LB-IPAM ;
# external = LB fourni par le terrain (cloud, ADR 0040).
VALID_LB_MODES = {"kube-vip-arp", "kube-vip-lb", "external"}


@dataclass
class Node:
    name: str
    roles: list[str]
    ansible_host: str | None = None
    disks: list[str] | None = None

    def has_role(self, role: str) -> bool:
        return role in self.roles


@dataclass
class Topology:
    """Vue typée d'un topology.yaml. Les dérivations (listes control/worker…)
    sont des PROPRIÉTÉS pures, testables sans I/O."""

    catalog: dict[str, Any]
    nodes: list[Node]
    network: dict[str, Any] = field(default_factory=dict)
    exposition: dict[str, Any] = field(default_factory=dict)
    storage: dict[str, Any] = field(default_factory=dict)
    hardening: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, Any] | None = None
    target_kind: str = "prod"

    # ── Dérivations pures (le cœur de la génération sans état) ──────────────
    @property
    def control_nodes(self) -> list[str]:
        """Noms des nœuds portant le rôle `control`, dans l'ordre déclaré."""
        return [n.name for n in self.nodes if n.has_role("control")]

    @property
    def worker_nodes(self) -> list[str]:
        """Noms des nœuds portant le rôle `worker` (et PAS `control`), ordre déclaré.

        Un nœud hyperconvergé (control+worker) est un control-plane qui schedule ;
        dans l'inventaire Ansible il vit dans le groupe `control` (le détaint le
        rend schedulable, ADR 0007). Le groupe `workers` ne liste donc que les
        nœuds worker-PURS — sinon double appartenance et drift d'inventaire.
        """
        return [n.name for n in self.nodes if n.has_role("worker") and not n.has_role("control")]

    @property
    def is_ha_control_plane(self) -> bool:
        """> 1 control-plane → exige un control_plane_lb (VIP), ADR 0047/0055."""
        return len(self.control_nodes) > 1


def _parse_node(raw: dict[str, Any]) -> Node:
    if "name" not in raw:
        raise TopologyError(f"nœud sans `name` : {raw!r}")
    roles = raw.get("roles") or []
    if not roles:
        raise TopologyError(f"nœud `{raw['name']}` sans `roles`")
    unknown = set(roles) - VALID_ROLES
    if unknown:
        raise TopologyError(
            f"nœud `{raw['name']}` : rôle(s) inconnu(s) {sorted(unknown)} "
            f"(valides : {sorted(VALID_ROLES)})"
        )
    return Node(
        name=raw["name"],
        roles=list(roles),
        ansible_host=raw.get("ansible_host"),
        disks=raw.get("disks"),
    )


def topology_from_dict(data: dict[str, Any]) -> Topology:
    """Construit une Topology depuis un dict (pur, testable sans fichier)."""
    if "nodes" not in data or not data["nodes"]:
        raise TopologyError("topology sans `nodes`")
    nodes = [_parse_node(n) for n in data["nodes"]]
    target_kind = data.get("target_kind", "prod")
    if target_kind not in VALID_TARGET_KINDS:
        raise TopologyError(
            f"target_kind `{target_kind}` invalide (valides : {sorted(VALID_TARGET_KINDS)})"
        )
    topo = Topology(
        catalog=data.get("catalog", {}),
        nodes=nodes,
        network=data.get("network", {}) or {},
        exposition=data.get("exposition", {}) or {},
        storage=data.get("storage", {}) or {},
        hardening=data.get("hardening", {}) or {},
        resources=data.get("resources"),
        target_kind=target_kind,
    )
    # Cohérence HA : > 1 CP exige un control_plane_lb déclaré (ADR 0047/0055).
    lb = topo.network.get("control_plane_lb")
    if topo.is_ha_control_plane and not lb:
        raise TopologyError(
            f"{len(topo.control_nodes)} control-planes mais aucun `network.control_plane_lb` "
            "(VIP requise dès > 1 CP — ADR 0047/0055)"
        )
    # Si un control_plane_lb est déclaré, son `mode` doit être connu (sinon le delta
    # d'outillage — kube-vip vs external — n'est pas dérivable, ADR 0047/0055).
    if lb is not None:
        mode = lb.get("mode") if isinstance(lb, dict) else None
        if mode not in VALID_LB_MODES:
            raise TopologyError(
                f"`network.control_plane_lb.mode` = {mode!r} inconnu "
                f"(valides : {sorted(VALID_LB_MODES)} — ADR 0047/0055)"
            )
    return topo


def load_topology(path: str) -> Topology:
    """Charge un topology.yaml depuis un fichier."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise TopologyError(
            f"{path} : racine YAML attendue = mapping, obtenu {type(data).__name__}"
        )
    return topology_from_dict(data)
