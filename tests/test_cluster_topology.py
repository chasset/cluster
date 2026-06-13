"""Tests de l'outil déclaratif cluster_topology (ADR 0056 / ADR 0017).

unittest (stdlib). Deux niveaux :
  - fonctions PURES (dérivations control/worker, validation) sur des dicts injectés ;
  - l'INVARIANT BYTE-IDENTIQUE (P1) : render(topology.example.yaml) ==
    bootstrap/hosts.example.yaml, octet pour octet (ADR 0056 §3).

Lancé par `python3 -m unittest discover tests` (cible `test:python` + CI).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cluster_topology import load_topology, render_prod_inventory  # noqa: E402
from cluster_topology.model import (  # noqa: E402
    TopologyError,
    topology_from_dict,
)

_ROOT = os.path.join(os.path.dirname(__file__), "..")


def _base(**over):
    """Un topology dict minimal valide, surchargeable."""
    d = {
        "catalog": {"topology": "multi-node-3"},
        "nodes": [
            {"name": "cp1", "roles": ["control"]},
            {"name": "node1", "roles": ["worker"]},
        ],
        "target_kind": "prod",
    }
    d.update(over)
    return d


class Derivations(unittest.TestCase):
    def test_control_and_worker_lists_in_order(self):
        t = topology_from_dict(
            _base(
                nodes=[
                    {"name": "cp1", "roles": ["control"]},
                    {"name": "node1", "roles": ["worker"]},
                    {"name": "node2", "roles": ["worker"]},
                ]
            )
        )
        self.assertEqual(t.control_nodes, ["cp1"])
        self.assertEqual(t.worker_nodes, ["node1", "node2"])

    def test_hyperconverged_node_is_control_not_worker(self):
        # un nœud control+worker (hyperconvergence) vit dans le groupe control,
        # PAS dans workers (sinon double appartenance, ADR 0007).
        t = topology_from_dict(
            _base(
                nodes=[
                    {"name": "n1", "roles": ["control", "worker", "storage"]},
                    {"name": "n2", "roles": ["worker"]},
                ],
                # 1 seul control-plane ici → pas de control_plane_lb requis.
            )
        )
        self.assertEqual(t.control_nodes, ["n1"])
        self.assertEqual(t.worker_nodes, ["n2"])
        self.assertNotIn("n1", t.worker_nodes)

    def test_ha_detection(self):
        single = topology_from_dict(_base())
        self.assertFalse(single.is_ha_control_plane)


class Validation(unittest.TestCase):
    def test_unknown_role_rejected(self):
        with self.assertRaises(TopologyError):
            topology_from_dict(_base(nodes=[{"name": "x", "roles": ["master"]}]))

    def test_node_without_roles_rejected(self):
        with self.assertRaises(TopologyError):
            topology_from_dict(_base(nodes=[{"name": "x", "roles": []}]))

    def test_no_nodes_rejected(self):
        with self.assertRaises(TopologyError):
            topology_from_dict(_base(nodes=[]))

    def test_bad_target_kind_rejected(self):
        with self.assertRaises(TopologyError):
            topology_from_dict(_base(target_kind="staging"))

    def test_multi_cp_without_lb_rejected(self):
        # > 1 control-plane SANS control_plane_lb = invalide (VIP requise, 0047/0055)
        with self.assertRaises(TopologyError):
            topology_from_dict(
                _base(
                    nodes=[
                        {"name": "cp1", "roles": ["control"]},
                        {"name": "cp2", "roles": ["control"]},
                    ]
                )
            )

    def test_multi_cp_with_lb_accepted(self):
        t = topology_from_dict(
            _base(
                nodes=[
                    {"name": "cp1", "roles": ["control"]},
                    {"name": "cp2", "roles": ["control"]},
                    {"name": "cp3", "roles": ["control"]},
                ],
                network={"control_plane_lb": {"mode": "kube-vip-arp"}},
            )
        )
        self.assertTrue(t.is_ha_control_plane)
        self.assertEqual(t.control_nodes, ["cp1", "cp2", "cp3"])


class ByteExactInvariant(unittest.TestCase):
    """P1 : le profil prod générique régénère hosts.example.yaml à l'octet."""

    def test_prod_inventory_is_byte_identical(self):
        topo = load_topology(os.path.join(_ROOT, "topology.example.yaml"))
        generated = render_prod_inventory(topo)
        with open(os.path.join(_ROOT, "bootstrap", "hosts.example.yaml"), encoding="utf-8") as f:
            expected = f.read()
        self.assertEqual(
            generated,
            expected,
            "le générateur ne reproduit plus bootstrap/hosts.example.yaml à l'octet "
            "(invariant P1, ADR 0056 §3) — éditer le template, pas le fichier généré",
        )


if __name__ == "__main__":
    unittest.main()
