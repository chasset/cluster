"""Tests du garde-fou check-md-orphans (ADR 0029 / ADR 0017 : logique testée).

unittest (stdlib) — pas de dépendance. Les fonctions testées sont pures : le
contenu des fichiers est injecté via un dict, donc aucun accès disque/git.

Lancé par `python3 -m unittest discover tests` (cible `test:python` + CI).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from check_md_orphans import (  # noqa: E402
    find_orphans,
    resolve_md_link,
    sidebar_link_to_file,
)


class SidebarLinkToFile(unittest.TestCase):
    def setUp(self):
        self.files = {
            "docs/index.md",
            "docs/demarrage.md",
            "bench/README.md",
            "bootstrap/RUNBOOK.md",
        }

    def test_root_maps_to_home(self):
        # `/` = home Starlight = docs/index.md (ancienne home VitePress, ADR 0089)
        self.assertEqual(sidebar_link_to_file("/", self.files), "docs/index.md")

    def test_page_link_adds_md(self):
        # liens Starlight avec trailing slash : /docs/demarrage/ → docs/demarrage.md
        self.assertEqual(sidebar_link_to_file("/docs/demarrage/", self.files), "docs/demarrage.md")

    def test_dir_link_maps_to_readme(self):
        self.assertEqual(sidebar_link_to_file("/bench/", self.files), "bench/README.md")

    def test_strips_anchor(self):
        self.assertEqual(
            sidebar_link_to_file("/bootstrap/RUNBOOK#init", self.files), "bootstrap/RUNBOOK.md"
        )

    def test_unknown_returns_none(self):
        self.assertIsNone(sidebar_link_to_file("/inexistant", self.files))


class ResolveMdLink(unittest.TestCase):
    def setUp(self):
        self.files = {"docs/a.md", "docs/sub/b.md", "platform/README.md", "README.md"}

    def test_relative_sibling(self):
        self.assertEqual(resolve_md_link("b.md", "docs/sub", self.files), "docs/sub/b.md")

    def test_relative_parent(self):
        self.assertEqual(resolve_md_link("../a.md", "docs/sub", self.files), "docs/a.md")

    def test_dir_resolves_to_readme(self):
        self.assertEqual(resolve_md_link("../platform/", "docs", self.files), "platform/README.md")

    def test_absolute_site_link(self):
        self.assertEqual(resolve_md_link("/README.md", "docs/sub", self.files), "README.md")

    def test_external_ignored(self):
        self.assertIsNone(resolve_md_link("https://example.org", "docs", self.files))

    def test_anchor_only_ignored(self):
        self.assertIsNone(resolve_md_link("#section", "docs", self.files))

    def test_unknown_target_returns_none(self):
        self.assertIsNone(resolve_md_link("nope.md", "docs", self.files))


class FindOrphans(unittest.TestCase):
    # Racine sidebar `/` = docs/index.md (home Starlight, ADR 0089).
    def test_reachable_via_sidebar_and_transitive_link(self):
        files = ["docs/index.md", "docs/guide.md", "docs/deep.md"]
        contents = {
            "docs/index.md": "voir [guide](guide.md)",
            "docs/guide.md": "puis [deep](deep.md)",
            "docs/deep.md": "feuille",
        }
        # docs/index.md est racine sidebar ; guide et deep sont atteints par liens.
        orphans = find_orphans(files, ["/"], lambda p: contents.get(p, ""))
        self.assertEqual(orphans, [])

    def test_detects_orphan(self):
        files = ["docs/index.md", "orphan.md"]
        contents = {"docs/index.md": "rien ne pointe vers l'orphelin"}
        orphans = find_orphans(files, ["/"], lambda p: contents.get(p, ""))
        self.assertEqual(orphans, ["orphan.md"])

    def test_orphan_linked_only_from_other_orphan_stays_orphan(self):
        # b est lié depuis a, mais a lui-même n'est atteignable par personne.
        files = ["docs/index.md", "a.md", "b.md"]
        contents = {"docs/index.md": "seul", "a.md": "[b](b.md)", "b.md": "x"}
        orphans = find_orphans(files, ["/"], lambda p: contents.get(p, ""))
        self.assertEqual(orphans, ["a.md", "b.md"])

    def test_cycle_does_not_loop_forever(self):
        # a/b sous docs/ : les liens relatifs se résolvent depuis docs/index.md.
        files = ["docs/index.md", "docs/a.md", "docs/b.md"]
        contents = {
            "docs/index.md": "[a](a.md)",
            "docs/a.md": "[b](b.md)",
            "docs/b.md": "[a](a.md)",
        }
        orphans = find_orphans(files, ["/"], lambda p: contents.get(p, ""))
        self.assertEqual(orphans, [])

    def test_empty_sidebar_all_orphan(self):
        files = ["docs/index.md", "x.md"]
        orphans = find_orphans(files, [], lambda p: "")
        self.assertEqual(orphans, ["docs/index.md", "x.md"])

    def test_resolves_cluster_site_url(self):
        # Lien réécrit en URL du site Astro (/cluster/...) → re-mappé à la source.
        files = ["docs/index.md", "CODE_OF_CONDUCT.md"]
        contents = {"docs/index.md": "voir [CoC](/cluster/CODE_OF_CONDUCT/)"}
        orphans = find_orphans(files, ["/"], lambda p: contents.get(p, ""))
        self.assertEqual(orphans, [])


if __name__ == "__main__":
    unittest.main()
