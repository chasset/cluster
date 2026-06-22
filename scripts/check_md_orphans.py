#!/usr/bin/env python3
"""Garde-fou ADR 0029 — tout Markdown versionné est atteignable depuis la doc.

Atteignable = présent dans le sidebar Starlight OU cible (transitive) d'un lien
Markdown depuis une page elle-même atteignable. Sort en code 1 s'il reste un
orphelin.

Atteignabilité = parcours en largeur (BFS) :
  racines = entrées `link:` de la sidebar (docs/astro.config.mjs, ADR 0089)
  arêtes  = liens Markdown `](cible)` entre fichiers versionnés

Usage : python3 scripts/check_md_orphans.py   (via `pnpm lint:docs-orphans`)

La logique (résolution de liens + BFS) est isolée dans des fonctions pures
testées par tests/test_check_md_orphans.py (ADR 0017 : tout script de logique
est testé). Python plutôt que bash : parcours de graphe + chemins relatifs.
"""

from __future__ import annotations

import os
import posixpath
import re
import subprocess
import sys
from collections import deque
from collections.abc import Callable, Iterable

# Non rendus par le site Astro (artefacts de build + README racine hors doc) +
# contenu généré sous src/content/docs/docs/ (copie de docs/ par le script de
# migration : on raisonne sur les SOURCES docs/*.md, pas sur les copies).
EXCLUDE_RE = re.compile(
    r"node_modules/|\.github/|CHANGELOG\.md|LICENSE\.md|"
    r"docs/dist/|docs/\.astro/|docs/src/content/docs/docs/|^README\.md$"
)
LINK_RE = re.compile(r"link:\s*['\"]([^'\"]+)['\"]")
MD_LINK_RE = re.compile(r"\]\(([^)]+)\)")


def sidebar_link_to_file(link: str, files: set[str]) -> str | None:
    """Résout une entrée `link:` de la sidebar Starlight vers un fichier SOURCE.

    Les liens sont des URL servies (sans base, ex. /docs/manifeste/, /bootstrap/
    RUNBOOK/) qu'on re-mappe vers le fichier source réel. La home `/` correspond
    à docs/index.md (ancienne home VitePress, transposée).
    """
    link = link.split("#", 1)[0].strip("/")
    if link == "":  # home `/`
        return "docs/index.md" if "docs/index.md" in files else None
    # /docs/manifeste/ → docs/manifeste.md ; /storage/ceph/ → storage/ceph/README.md
    candidates = [
        link + ".md",
        link + "/README.md",
        link + "/index.md",  # index de dossier copié sous docs/
    ]
    return next((c for c in candidates if c in files), None)


def resolve_md_link(target: str, from_dir: str, files: set[str]) -> str | None:
    """Résout un lien Markdown `](target)` vers un fichier source, ou None.

    Gère trois formes (post-migration Astro, ADR 0089) :
    - URL absolue du site `/cluster/<x>/` (réécrite par migrate_docs_to_astro) →
      re-mappée vers le fichier source ;
    - lien relatif `../x.md` (encore présent dans les fichiers non réécrits) ;
    - lien absolu `/x` historique. Les liens GitHub (https://github.com/...) et
      externes sont ignorés (le code n'est pas une page).
    """
    target = target.split()[0].split("#", 1)[0] if target.split() else ""
    if not target or target.startswith(("http://", "https://", "mailto:")):
        return None
    # URL du site Astro : /cluster/<slug>/ → on retombe sur le mapping sidebar
    if target.startswith("/cluster/"):
        return sidebar_link_to_file(target.removeprefix("/cluster"), files)
    base = (
        target[1:]
        if target.startswith("/")
        else posixpath.normpath(posixpath.join(from_dir, target))
    )
    candidates = [
        base,
        base + ".md",
        base.rstrip("/") + "/README.md",
        posixpath.join(base, "README.md"),
    ]
    return next((c for c in (x.removeprefix("./") for x in candidates) if c in files), None)


def find_orphans(
    all_files: Iterable[str],
    sidebar_links: Iterable[str],
    read_file: Callable[[str], str],
) -> list[str]:
    """Retourne les fichiers Markdown non atteignables, triés.

    Fonction pure : `read_file(path)` est injecté (le contenu, ou "" si illisible),
    ce qui rend le BFS testable sans toucher au disque.
    """
    files = set(all_files)
    roots = [f for f in (sidebar_link_to_file(link, files) for link in sidebar_links) if f]

    seen: set[str] = set(roots)
    queue: deque[str] = deque(roots)
    while queue:
        current = queue.popleft()
        from_dir = posixpath.dirname(current)
        for match in MD_LINK_RE.finditer(read_file(current)):
            resolved = resolve_md_link(match.group(1), from_dir, files)
            if resolved and resolved not in seen:
                seen.add(resolved)
                queue.append(resolved)

    return sorted(f for f in files if f not in seen)


def _git_markdown_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "*.md"], capture_output=True, text=True, check=True
    ).stdout
    return [f for f in out.splitlines() if f and not EXCLUDE_RE.search(f)]


def _read_safe(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def main() -> int:
    repo_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    os.chdir(repo_root)

    config = "docs/astro.config.mjs"
    if not os.path.isfile(config):
        print(f"check-md-orphans: {config} introuvable", file=sys.stderr)
        return 2

    all_files = _git_markdown_files()
    sidebar_links = LINK_RE.findall(_read_safe(config))
    orphans = find_orphans(all_files, sidebar_links, _read_safe)

    if orphans:
        print(
            f"check-md-orphans: {len(orphans)} fichier(s) Markdown orphelin(s) (ADR 0029) :",
            file=sys.stderr,
        )
        for orphan in orphans:
            print(f"  - {orphan}", file=sys.stderr)
        print(
            "\nRendez-les atteignables : entrée sidebar (docs/astro.config.mjs) "
            "ou lien depuis une page liée.",
            file=sys.stderr,
        )
        return 1

    print(f"check-md-orphans: OK — {len(all_files)} fichiers Markdown tous atteignables.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
