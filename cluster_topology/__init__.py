"""cluster_topology — outil déclaratif des topologies (ADR 0056).

`topology.yaml` est la source de vérité unique d'une topologie ; ce paquet en
DÉRIVE, SANS ÉTAT, les entrées que les outils consomment déjà (inventaire
Ansible aujourd'hui ; group_vars de profil et table de nœuds Lima ensuite).
Ansible reste le moteur de convergence (ADR 0056 §7) — l'outil ne réimplémente
jamais la convergence ni un état réconcilié.

Palier P0-P1 (plan-modele-declaratif) : modéliser (`topology.example.yaml`) +
générer l'inventaire prod BYTE-IDENTIQUE à `bootstrap/hosts.example.yaml`. La
logique (chargement, dérivation, rendu) est pure et testée
(tests/test_cluster_topology.py, ADR 0017).
"""

from cluster_topology.generator import render_prod_inventory
from cluster_topology.model import Topology, load_topology

__all__ = ["Topology", "load_topology", "render_prod_inventory"]
