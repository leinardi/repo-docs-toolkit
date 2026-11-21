#!/usr/bin/env python3
"""Keep the vendored copies of docstool.py byte-identical to the canonical one.

Each skill must work on its own (claude.ai, OpenCode and `npx skills` install skills one by one, and
`python3 -I` cannot import from another directory), so docstool.py is vendored into every skill
that runs it. The canonical copy is skills/repo-docs/scripts/docstool.py.

The plugin's own site uses the landing page stylesheet as shipped. Zensical reads extra_css from
docs/ or custom_dir, and the asset sits in neither (custom_dir is the skill's assets/overrides/), so
docs/stylesheets/home.css is a copy of the skill's asset, kept the same way.

    scripts/sync-vendored.py          write the copies from the canonical file
    scripts/sync-vendored.py --check  list the copies that differ; exit 1 if any does
"""

#
# MIT License
#
# Copyright (c) 2026 Roberto Leinardi
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL = Path("skills/repo-docs/scripts/docstool.py")
COPIES = (
    Path("skills/zensical-site/scripts/docstool.py"),
    Path("skills/repo-readme/scripts/docstool.py"),
)
# (source, copy) pairs outside the docstool copies.
SITE_COPIES = ((Path("skills/zensical-site/assets/stylesheets/home.css"), Path("docs/stylesheets/home.css")),)


def pairs() -> tuple[tuple[Path, Path], ...]:
    """Every (source, copy) pair this script keeps identical."""
    return tuple((CANONICAL, copy) for copy in COPIES) + SITE_COPIES


def stale_copies(root: Path) -> list[Path]:
    """Return the copies that are missing, symlinks, or differ from their source."""
    stale = []
    for source, copy in pairs():
        path = root / copy
        if path.is_symlink() or not path.is_file() or path.read_bytes() != (root / source).read_bytes():
            stale.append(copy)
    return stale


def write_copies(root: Path) -> list[Path]:
    """Write every stale copy from its source and return the ones written."""
    written = stale_copies(root)
    sources = {copy: source for source, copy in pairs()}
    for copy in written:
        path = root / copy
        if path.is_symlink():
            path.unlink()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((root / sources[copy]).read_bytes())
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--check", action="store_true", help="only report copies that differ")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root: Path = args.root
    for source in dict.fromkeys(source for source, _ in pairs()):
        if not (root / source).is_file():
            print(f"sync-vendored: {source} not found under {root}", file=sys.stderr)
            return 2
    if args.check:
        stale = stale_copies(root)
        if stale:
            print("These copies differ from their source; run make sync-vendored:", file=sys.stderr)
            for copy in stale:
                print(f"  {copy}", file=sys.stderr)
            return 1
        print(f"Vendored copies: {len(pairs())} copies match their source.")
        return 0
    for copy in write_copies(root):
        print(f"wrote {copy}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
