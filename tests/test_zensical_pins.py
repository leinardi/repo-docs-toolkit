"""Every place that names the Zensical version the toolkit is tested with agrees on it.

Dependabot bumps tools/docs; this test then fails until docstool's KNOWN_ZENSICAL, the skill's
shipped asset and its text move with it (skills/zensical-site/references/upgrade-and-audit.md).
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

import re
import tomllib

from conftest import DOCSTOOL, REPO_ROOT, load_module

docstool = load_module("docstool_pins", DOCSTOOL)
KNOWN = docstool.KNOWN_ZENSICAL


def _pyproject_pin(rel: str) -> str:
    data = tomllib.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))
    pins = [str(d).split("==", 1)[1] for d in data["project"]["dependencies"] if str(d).startswith("zensical==")]
    assert len(pins) == 1, f"{rel} must pin zensical with == exactly once"
    return pins[0]


def test_the_docs_project_and_the_shipped_asset_pin_known_zensical() -> None:
    assert _pyproject_pin("tools/docs/pyproject.toml") == KNOWN
    assert _pyproject_pin("skills/zensical-site/assets/tools/docs/pyproject.toml") == KNOWN


def test_the_lock_resolves_known_zensical() -> None:
    lock = tomllib.loads((REPO_ROOT / "tools/docs/uv.lock").read_text(encoding="utf-8"))
    versions = [p["version"] for p in lock["package"] if p["name"] == "zensical"]
    assert versions == [KNOWN]


def test_the_skill_text_names_known_zensical() -> None:
    for rel in ("skills/zensical-site/SKILL.md", "skills/zensical-site/references/config.md"):
        pins = set(re.findall(r"zensical==([\w.]+)", (REPO_ROOT / rel).read_text(encoding="utf-8")))
        assert pins == {KNOWN}, f"{rel} names zensical {sorted(pins)}, docstool knows {KNOWN}"
