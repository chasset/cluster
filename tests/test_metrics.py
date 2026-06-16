"""Tests de l'exposition des métriques (nestor/metrics.py, P6).

unittest stdlib, pur (Run construit en mémoire). Vérifie qu'on LIT et met en forme
les métriques consignées sans en dériver de nouvelles.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor.history import Run  # noqa: E402
from nestor.metrics import format_metrics, metrics_of  # noqa: E402


def _run(**over):
    base = {
        "id": "2026-06-08T16-ceph-abc",
        "date": "2026-06-08T16:20:49Z",
        "profil": "ceph",
        "topologie": "multi-node-3",
        "total_s": 759,
        "phases": {"up": 165, "bootstrap": 399, "ceph": 189, "sc": 6},
        "metriques": {"cpu_core_s": 272, "ram_peak_mib": 7606, "ram_mean_mib": 7489},
    }
    base.update(over)
    return Run(**base)


class MetricsOf(unittest.TestCase):
    def test_extracts_consigned_values(self):
        rm = metrics_of(_run())
        self.assertEqual(rm.objectif, "ceph / multi-node-3")
        self.assertEqual(rm.total_s, 759)
        self.assertEqual(rm.cpu_core_s, 272)
        self.assertEqual(rm.ram_peak_mib, 7606)
        self.assertTrue(rm.has_metrics)

    def test_absent_metrics_block(self):
        rm = metrics_of(_run(metriques={}))
        self.assertIsNone(rm.cpu_core_s)
        self.assertFalse(rm.has_metrics)


class FormatMetrics(unittest.TestCase):
    def test_durations_and_resources(self):
        out = format_metrics(metrics_of(_run()))
        self.assertIn("12m39s", out)  # 759 s = 12m39s (parité metro_fmt_dur)
        self.assertIn("cpu_core_s=272", out)
        self.assertIn("ram_peak=7606 MiB", out)
        self.assertIn("ceph 3m09s", out)  # 189 s

    def test_no_metrics_message(self):
        out = format_metrics(metrics_of(_run(metriques={})))
        self.assertIn("non échantillonnées", out)

    def test_missing_total_is_question_mark(self):
        out = format_metrics(metrics_of(_run(total_s=None)))
        self.assertIn("durée totale  : ?", out)


if __name__ == "__main__":
    unittest.main()
