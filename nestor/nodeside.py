"""Lecture PURE de l'état NODE-SIDE d'un nœud (ADR 0081 étape 3).

`discover` lit, via la brique node_exec (façade I/O), des sorties brutes d'un nœud
(`containerd --version`, `lsblk`, `systemctl is-active`, conf CNI) que l'API Kubernetes
NE PORTE PAS. Ce module les PARSE en faits structurés — aucun I/O, aucun nœud : la façade
collecte les octets, ici on ne fait que les interpréter. C'est le portage en données
structurées du `sed`/`grep` dispersé (detect_hardening_state, gate disques de
run-phases.sh) — ADR 0049 : Python pour la logique, pas du grappillage shell.

Faits exposés (NodeSide) : runtime CRI, CNI, disques bruts, durcissement. `discover`
les attache au nœud reconstruit (les sondes manquantes de l'ADR 0074).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Disk:
    """Disque brut d'un nœud (nom + taille), pour le profil stockage (Ceph veut des bruts)."""

    name: str
    size: str


@dataclass
class NodeSide:
    """État node-side d'un nœud, dérivé du réel (PUR). Champs None/[] si non sondé/illisible."""

    cri: str | None = None  # ex. "containerd 1.7.27"
    cni: str | None = None  # ex. "cilium" | "calico" | None
    disks: list[Disk] = field(default_factory=list)  # disques bruts (lsblk)
    hardening: str | None = None  # "hardened" | "plain" | "partial" | None (inconnu)


def parse_cri(version_output: str) -> str | None:
    """`containerd --version` → "containerd <semver>", ou None si illisible (PUR).

    Format containerd : `containerd github.com/containerd/containerd v1.7.27 <commit>`.
    On extrait le `vX.Y.Z` (le `v` optionnel). Tolérant : ligne vide/inattendue → None."""
    m = re.search(r"\bv?(\d+\.\d+\.\d+)\b", version_output or "")
    return f"containerd {m.group(1)}" if m else None


def parse_cni(cni_listing: str) -> str | None:
    """Conf CNI active (`ls /etc/cni/net.d` ou contenu) → nom du CNI, ou None (PUR).

    On reconnaît les CNI au nom de fichier/plugin : `cilium`, `calico`, `flannel`. Le banc
    pose Cilium (cni.sh). Inconnu/vide → None (on ne devine pas)."""
    text = (cni_listing or "").lower()
    for cni in ("cilium", "calico", "flannel"):
        if cni in text:
            return cni
    return None


def parse_disks(lsblk_output: str) -> list[Disk]:
    """`lsblk -dno NAME,SIZE` → liste de `Disk` (PUR). Une ligne `NAME SIZE` par disque.

    On garde l'ORDRE et on ignore les lignes vides/malformées. Pas de filtrage ici (le
    profil — quels disques sont « data » — est une décision en aval) : on RAPPORTE le réel."""
    disks: list[Disk] = []
    for line in (lsblk_output or "").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            disks.append(Disk(name=parts[0], size=parts[1]))
    return disks


def classify_hardening(auditd: str, fail2ban: str) -> str:
    """État de durcissement DÉRIVÉ de `systemctl is-active` des deux unités (PUR, ADR 0065).

    Calque `classify_hardening_signal` (rollback-lib bats) : les deux `active` → "hardened" ;
    les deux inactifs/absents → "plain" ; un seul → "partial" (incohérent) ; signal vide/
    inconnu → "unknown" (l'appelant décide). Robuste aux valeurs `inactive`/`failed`/``."""
    a, f = (auditd or "").strip(), (fail2ban or "").strip()
    if a == "unknown" or f == "unknown" or (not a and not f):
        return "unknown"
    a_on, f_on = a == "active", f == "active"
    if a_on and f_on:
        return "hardened"
    if not a_on and not f_on:
        return "plain"
    return "partial"


def assemble_nodeside(
    *,
    cri_version: str = "",
    cni_listing: str = "",
    lsblk: str = "",
    auditd: str = "",
    fail2ban: str = "",
) -> NodeSide:
    """Compose un `NodeSide` depuis les sorties brutes d'un nœud (PUR, ADR 0081 étape 3).

    Chaque sonde est indépendante et tolérante : une sortie vide → champ None/[]/unknown,
    jamais une erreur (un nœud peut ne pas répondre à une commande sans invalider le reste)."""
    hard = classify_hardening(auditd, fail2ban)
    return NodeSide(
        cri=parse_cri(cri_version),
        cni=parse_cni(cni_listing),
        disks=parse_disks(lsblk),
        hardening=None if hard == "unknown" else hard,
    )
