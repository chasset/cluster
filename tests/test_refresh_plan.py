"""Tests du plan de refresh (cluster_topology/refresh_plan.py, ADR 0076).

Pur : dicts en entrée (topo déclarée + réel sondé), RefreshPlan en sortie. Aucun
cluster, aucun subprocess — la collecte (kubectl, via discover) est à la façade.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cluster_topology.refresh_plan import (  # noqa: E402
    NodeChange,
    format_plan,
    plan_refresh,
)


def _plan(**over):
    base = dict(
        declared_nodes=[{"name": "node1", "roles": ["control", "worker"]}],
        declared_layers=["dataops"],
        declared_backend="local-path",
        real_nodes=[{"name": "node1", "roles": ["control", "worker"]}],
        real_layers=["dataops"],
        real_backend="local-path",
    )
    base.update(over)
    return plan_refresh(**base)


class Additions(unittest.TestCase):
    def test_new_node_is_proposed(self):
        p = _plan(
            real_nodes=[
                {"name": "node1", "roles": ["control", "worker"]},
                {"name": "node2", "roles": ["worker"]},
            ]
        )
        self.assertEqual(p.nodes_to_add, [NodeChange("node2", ["worker"])])
        self.assertTrue(p.has_additions)

    def test_new_layer_is_proposed(self):
        p = _plan(real_layers=["dataops", "monitoring"])
        self.assertEqual(p.layers_to_add, ["monitoring"])

    def test_backend_change_detected(self):
        p = _plan(real_backend="ceph")
        self.assertEqual(p.backend_change, ("local-path", "ceph"))

    def test_backend_none_proposes_nothing(self):
        # Cluster injoignable / SC indétectable → real_backend None → pas de proposition.
        p = _plan(real_backend=None)
        self.assertIsNone(p.backend_change)

    def test_identical_real_and_declared_is_empty(self):
        p = _plan()
        self.assertFalse(p.has_additions)
        self.assertFalse(p.has_signals)


class Absences(unittest.TestCase):
    """Déclaré mais absent du réel : SIGNALÉ, jamais retiré en v1 (ADR 0076 §3)."""

    def test_declared_node_absent_is_signaled_not_added(self):
        p = _plan(real_nodes=[])  # node1 déclaré, aucun réel
        self.assertEqual(p.nodes_absent, ["node1"])
        self.assertFalse(p.has_additions)  # une absence ne s'APPLIQUE pas
        self.assertTrue(p.has_signals)  # mais elle se SIGNALE

    def test_declared_layer_absent_is_signaled(self):
        p = _plan(real_layers=[])  # dataops déclaré, absent du réel
        self.assertEqual(p.layers_absent, ["dataops"])
        self.assertFalse(p.has_additions)


class Format(unittest.TestCase):
    def test_format_marks_additions_and_absences(self):
        p = plan_refresh(
            declared_nodes=[{"name": "node1", "roles": ["control"]}],
            declared_layers=["dataops"],
            declared_backend="local-path",
            real_nodes=[
                {"name": "node1", "roles": ["control"]},
                {"name": "node2", "roles": ["worker"]},
            ],
            real_layers=["monitoring"],  # dataops absent, monitoring nouveau
            real_backend="ceph",
        )
        lines = "\n".join(format_plan(p))
        self.assertIn("+ nœud `node2`", lines)
        self.assertIn("+ couche `monitoring`", lines)
        self.assertIn("~ storage.backend : `local-path` → `ceph`", lines)
        self.assertIn("- couche `dataops` déclarée mais ABSENTE", lines)
        self.assertIn("non retiré", lines)  # garde-fou ADR 0076 §3 visible


if __name__ == "__main__":
    unittest.main()
