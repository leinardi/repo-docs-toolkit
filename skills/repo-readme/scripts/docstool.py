#!/usr/bin/env python3
"""docstool: the repo-docs-toolkit documentation checker.

Run it in isolated mode, as every SKILL.md says: `python3 -I <skill-dir>/scripts/docstool.py <command>`.
Standard library only, Python 3.11 or newer.

The canonical copy is skills/repo-docs/scripts/docstool.py; the copies in the zensical-site and
repo-readme skills are byte-identical (scripts/sync-vendored.py writes and checks them), so each
skill works on its own.
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

if sys.version_info < (3, 11):  # noqa: UP036 - the check is for users running an older python3
    sys.exit("docstool needs Python 3.11 or newer")

# The version of docstool's command line and JSON output. It changes when a command, a flag or an
# output field changes, independently of the plugin version in .claude-plugin/plugin.json.
__version__ = "0.1.0"

# Exit codes shared by every command.
EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
EXIT_INCOMPLETE = 3


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser; each command is a subparser of the `command` destination."""
    parser = argparse.ArgumentParser(
        prog="docstool",
        description="Check documentation against the repository it describes.",
    )
    parser.add_argument("--version", action="version", version=f"docstool {__version__}")
    parser.add_subparsers(dest="command", metavar="<command>")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_usage(sys.stderr)
        print("docstool: error: no command given", file=sys.stderr)
        return EXIT_USAGE
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
