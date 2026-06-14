"""Tests de l'orchestration du socle k8s (cluster_topology/bootstrap.py).

unittest stdlib, I/O INJECTÉE (launch/run_cni stubés) — aucun subprocess, aucun banc.
Vérifie la séquence ordonnée des 6 playbooks, les extravars, et le fail-fast.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cluster_topology.bootstrap import (  # noqa: E402
    BootstrapError,
    bootstrap_extravars,
    bootstrap_playbooks,
    run_bootstrap,
)


class _FakeResult:
    def __init__(self, rc=0, status="successful"):
        self.rc = rc
        self.status = status


class Sequence(unittest.TestCase):
    def test_six_playbooks_in_dependency_order(self):
        # Transcription fidèle de bootstrap_node_sequence (lib.sh).
        self.assertEqual(
            bootstrap_playbooks(),
            [
                "checks.yaml",
                "cri.yaml",
                "kubeadm.yaml",
                "control-planes.yaml",
                "initialisation.yaml",
                "join-workers.yaml",
            ],
        )

    def test_playbooks_list_is_a_copy(self):
        # Copie défensive : muter le retour ne touche pas la source de vérité.
        bootstrap_playbooks().append("intrus.yaml")
        self.assertNotIn("intrus.yaml", bootstrap_playbooks())


class Extravars(unittest.TestCase):
    def test_control_plane_ip(self):
        self.assertEqual(bootstrap_extravars("10.0.0.5"), {"control_plane_ip": "10.0.0.5"})


class RunBootstrap(unittest.TestCase):
    def test_launches_six_playbooks_then_cni(self):
        launched = []

        def launch(pb, extravars):
            launched.append((pb, extravars))
            return _FakeResult(rc=0)

        cni_called = []

        def run_cni():
            cni_called.append(1)
            return 0

        result = run_bootstrap("10.0.0.5", launch=launch, run_cni=run_cni)
        self.assertTrue(result.built)
        # Les 6 playbooks dans l'ordre, chacun avec control_plane_ip.
        self.assertEqual([pb for pb, _ in launched], bootstrap_playbooks())
        self.assertTrue(all(e == {"control_plane_ip": "10.0.0.5"} for _, e in launched))
        # CNI posée APRÈS les playbooks.
        self.assertEqual(cni_called, [1])
        # Une étape par playbook + cni.
        self.assertEqual(len(result.steps), 7)
        self.assertTrue(all(s.ok for s in result.steps))

    def test_fail_fast_on_playbook_error(self):
        # Le 3e playbook échoue → BootstrapError, les suivants NE sont PAS lancés.
        launched = []

        def launch(pb, extravars):
            launched.append(pb)
            return _FakeResult(rc=0 if len(launched) < 3 else 2)

        with self.assertRaises(BootstrapError):
            run_bootstrap("10.0.0.5", launch=launch, run_cni=lambda: 0)
        # checks, cri, kubeadm tentés ; control-planes/init/join PAS lancés.
        self.assertEqual(launched, ["checks.yaml", "cri.yaml", "kubeadm.yaml"])

    def test_cni_failure_raises(self):
        with self.assertRaises(BootstrapError):
            run_bootstrap("10.0.0.5", launch=lambda *a, **k: _FakeResult(rc=0), run_cni=lambda: 1)


if __name__ == "__main__":
    unittest.main()
