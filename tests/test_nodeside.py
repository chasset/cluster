"""Tests de la lecture PURE de l'état node-side (nestor/nodeside.py, ADR 0081 étape 3).

Pur : sorties brutes d'un nœud → faits structurés. Aucun nœud, aucun cluster.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor.nodeside import (  # noqa: E402
    assemble_nodeside,
    classify_hardening,
    parse_cni,
    parse_cri,
    parse_disks,
)


class ParseCri(unittest.TestCase):
    def test_containerd_version_line(self):
        out = "containerd github.com/containerd/containerd v1.7.27 abc123"
        self.assertEqual(parse_cri(out), "containerd 1.7.27")

    def test_version_without_v_prefix(self):
        self.assertEqual(parse_cri("containerd 2.0.5 commit"), "containerd 2.0.5")

    def test_unreadable_is_none(self):
        self.assertIsNone(parse_cri(""))
        self.assertIsNone(parse_cri("command not found"))


class ParseCni(unittest.TestCase):
    def test_cilium_recognized(self):
        self.assertEqual(parse_cni("05-cilium.conflist"), "cilium")

    def test_calico_recognized(self):
        self.assertEqual(parse_cni("10-calico.conflist\n"), "calico")

    def test_unknown_is_none(self):
        self.assertIsNone(parse_cni(""))
        self.assertIsNone(parse_cni("99-loopback.conf"))


class ParseDisks(unittest.TestCase):
    def test_name_size_pairs(self):
        out = "vda   40G\nvdb   10G\nvdc   10G\n"
        pairs = [(d.name, d.size) for d in parse_disks(out)]
        self.assertEqual(pairs, [("vda", "40G"), ("vdb", "10G"), ("vdc", "10G")])

    def test_order_preserved_and_blank_ignored(self):
        out = "vdb 10G\n\nvda 40G\n"
        self.assertEqual([d.name for d in parse_disks(out)], ["vdb", "vda"])

    def test_empty_is_no_disks(self):
        self.assertEqual(parse_disks(""), [])


class ClassifyHardening(unittest.TestCase):
    def test_both_active_is_hardened(self):
        self.assertEqual(classify_hardening("active", "active"), "hardened")

    def test_both_inactive_is_plain(self):
        self.assertEqual(classify_hardening("inactive", "inactive"), "plain")

    def test_one_active_is_partial(self):
        self.assertEqual(classify_hardening("active", "inactive"), "partial")
        self.assertEqual(classify_hardening("inactive", "active"), "partial")

    def test_unknown_or_empty(self):
        self.assertEqual(classify_hardening("unknown", "active"), "unknown")
        self.assertEqual(classify_hardening("", ""), "unknown")

    def test_failed_unit_treated_as_not_active(self):
        # systemctl is-active peut rendre `failed` → traité comme non actif (→ plain ici).
        self.assertEqual(classify_hardening("failed", "inactive"), "plain")


class AssembleNodeside(unittest.TestCase):
    def test_full_node(self):
        ns = assemble_nodeside(
            cri_version="containerd github.com/... v1.7.27 x",
            cni_listing="05-cilium.conflist",
            lsblk="vda 40G\nvdb 10G\n",
            auditd="active",
            fail2ban="active",
        )
        self.assertEqual(ns.cri, "containerd 1.7.27")
        self.assertEqual(ns.cni, "cilium")
        self.assertEqual([d.name for d in ns.disks], ["vda", "vdb"])
        self.assertEqual(ns.hardening, "hardened")

    def test_partial_probes_tolerated(self):
        # un nœud qui ne répond qu'à lsblk : les autres champs restent None, pas d'erreur.
        ns = assemble_nodeside(lsblk="vda 40G\n")
        self.assertIsNone(ns.cri)
        self.assertIsNone(ns.cni)
        self.assertIsNone(ns.hardening)  # unknown → None
        self.assertEqual(len(ns.disks), 1)


if __name__ == "__main__":
    unittest.main()
