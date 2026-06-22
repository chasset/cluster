"""Tests de nestor/prod_target.py (ADR 0090 / ADR 0017 : logique pure testée).

Aucun I/O cluster : on teste la résolution kubeconfig, la décision de rapatriement,
le message de confirmation et le parsing de réponse — tout pur.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from nestor.prod_target import (  # noqa: E402
    TargetConfirmation,
    default_kubeconfig_path,
    is_affirmative,
    needs_repatriation,
    resolve_kubeconfig,
)


class DefaultPath(unittest.TestCase):
    def test_convention_per_stack(self):
        self.assertEqual(default_kubeconfig_path("dirqual"), "~/.kube/dirqual.config")


class ResolveKubeconfig(unittest.TestCase):
    def test_env_wins(self):
        # KUBECONFIG exporté = intention explicite → prime sur tout (ADR 0053/0090).
        got = resolve_kubeconfig(
            env_kubeconfig="/tmp/k", declared="~/.kube/dirqual.config", stack="dirqual"
        )
        self.assertEqual(got, "/tmp/k")

    def test_declared_when_no_env(self):
        got = resolve_kubeconfig(
            env_kubeconfig=None, declared="~/.kube/dirqual.config", stack="dirqual"
        )
        self.assertEqual(got, "~/.kube/dirqual.config")

    def test_default_when_nothing(self):
        got = resolve_kubeconfig(env_kubeconfig=None, declared=None, stack="dirqual")
        self.assertEqual(got, "~/.kube/dirqual.config")


class Confirmation(unittest.TestCase):
    def test_prompt_shows_endpoint_and_nodes(self):
        c = TargetConfirmation(
            stack="dirqual", endpoint="https://10.67.2.11:6443", nodes=["dirqual1", "dirqual2"]
        )
        msg = c.prompt()
        self.assertIn("dirqual", msg)
        self.assertIn("10.67.2.11", msg)
        self.assertIn("dirqual1", msg)
        self.assertTrue(c.reachable)

    def test_prompt_handles_unreachable(self):
        c = TargetConfirmation(stack="dirqual", endpoint=None, nodes=[])
        msg = c.prompt()
        self.assertIn("aucun nœud", msg)
        self.assertFalse(c.reachable)


class NeedsRepatriation(unittest.TestCase):
    def test_absent_file_needs_repatriation(self):
        self.assertTrue(
            needs_repatriation(kubeconfig_path="/nope/absent.config", reaches_api=False)
        )

    def test_present_but_unreachable_needs_repatriation(self):
        # Fichier présent mais API injoignable (forward mort / cluster down) → rapatrier.
        self.assertTrue(needs_repatriation(kubeconfig_path=__file__, reaches_api=False))

    def test_present_and_reachable_ok(self):
        self.assertFalse(needs_repatriation(kubeconfig_path=__file__, reaches_api=True))


class Affirmative(unittest.TestCase):
    def test_yes_variants(self):
        for a in ("y", "Y", "yes", "o", "OUI", " oui "):
            self.assertTrue(is_affirmative(a), a)

    def test_default_no(self):
        for a in ("", "n", "non", "nope", "maybe"):
            self.assertFalse(is_affirmative(a), a)


if __name__ == "__main__":
    unittest.main()
