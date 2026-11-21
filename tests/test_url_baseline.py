"""check --save-baseline / --baseline: routes, redirects and anchors of built sites."""

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

import json
from pathlib import Path
from typing import Any

from conftest import docstool_code, docstool_json, git, make_repo
from test_site_build import build, prebuilt

OLD = {
    "index.html": "<h1 id='home'>Home</h1>",
    "guide/index.html": "<h1 id='guide'>Guide</h1><h2 id='install'>Install</h2><h2 id='usage'>Usage</h2>",
    "gone/index.html": "<h1 id='gone'>Gone</h1>",
    "chain/index.html": "<h1 id='chain'>Chain</h1>",
    "loop/index.html": "<h1>Loop</h1>",
    "plugin/index.html": "<h1 id='generated'>Made by a plugin</h1>",
    "anchored/index.html": "<h1 id='anchored'>A</h1><h2 id='old-anchor'>Old</h2>",
    "dangle/index.html": "<h1 id='dangle'>Dangle</h1>",
}
REFRESH = '<meta http-equiv="refresh" content="0; url={}">'
NEW = {
    "index.html": "<h1 id='home'>Home</h1>",
    "guide/index.html": "<h1 id='guide'>Guide</h1><h2 id='install'>Install</h2>",
    "chain/index.html": REFRESH.format("../hop/"),
    "hop/index.html": REFRESH.format("../guide/"),
    "loop/index.html": REFRESH.format("../loop2/"),
    "loop2/index.html": REFRESH.format("../loop/"),
    "anchored/index.html": "<h1 id='anchored'>A</h1>",
    "dangle/index.html": REFRESH.format("../nowhere/"),
    "redirect.json": json.dumps({"anchored/#old-anchor": "guide/#install"}),
}


def built(tmp_path: Path, name: str, pages: dict[str, str]) -> tuple[Path, Path]:
    repo = make_repo("clean", tmp_path / name)
    prebuilt(repo, pages)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "prebuilt")
    out = tmp_path / f"{name}-site"
    code, report = build(repo, out)
    assert code == 0, report
    return repo, out


def compare(tmp_path: Path) -> dict[str, Any]:
    old_repo, old = built(tmp_path, "old", OLD)
    code, _ = docstool_json(old_repo, "check", "--built", str(old), "--save-baseline", str(tmp_path / "urls.json"))
    assert code == 0
    new_repo, new = built(tmp_path, "new", NEW)
    _, report = docstool_json(new_repo, "check", "--built", str(new), "--baseline", str(tmp_path / "urls.json"))
    return report


def test_built_baselines_find_every_lost_route_and_anchor(tmp_path: Path) -> None:
    report = compare(tmp_path)
    got = {(f["check"], f["message"].split(" ")[0]) for f in report["findings"] if f["file"].endswith("urls.json")}
    assert got == {
        ("route-missing", "/gone/"),
        ("route-missing", "/plugin/"),
        ("redirect-chain", "/chain/"),
        ("redirect-loop", "/loop/:"),
        ("fragment-lost", "/guide/:"),
        ("redirect-dangling", "/dangle/:"),
    }
    assert {r["input"]: r["state"] for r in report["coverage"]}["url_baseline"] == "complete"


def test_source_derived_baseline_is_partial(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    code, report = docstool_json(repo, "check", "--save-baseline", str(tmp_path / "urls.json"))
    assert code == 0
    assert {r["input"]: r["state"] for r in report["coverage"]}["url_baseline"] == "partial"
    routes = json.loads((tmp_path / "urls.json").read_text(encoding="utf-8"))["routes"]
    assert set(routes) == {"", "guide/", "reference/"}


def test_baseline_needs_built(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    assert docstool_code(repo, "check", "--baseline", str(tmp_path / "urls.json")) == 2


def test_unknown_build_dependencies_make_preservation_partial(tmp_path: Path) -> None:
    old_repo, old = built(tmp_path, "old", OLD)
    assert docstool_json(old_repo, "check", "--built", str(old), "--save-baseline", str(tmp_path / "urls.json"))[0] == 0
    new_repo = make_repo("clean", tmp_path / "new")
    prebuilt(new_repo, OLD)
    config = new_repo / "zensical.toml"
    config.write_text(config.read_text(encoding="utf-8") + "\n[project.plugins.some-plugin]\n", encoding="utf-8")
    git(new_repo, "add", "-A")
    git(new_repo, "commit", "-q", "-m", "plugin")
    assert build(new_repo, tmp_path / "new-site")[0] == 0
    code, report = docstool_json(new_repo, "check", "--built", str(tmp_path / "new-site"), "--baseline", str(tmp_path / "urls.json"))
    assert code == 3
    assert {r["input"]: r["state"] for r in report["coverage"]}["url_baseline"] == "partial"
    # and a baseline saved from such a build is partial at once
    code, report = docstool_json(new_repo, "check", "--built", str(tmp_path / "new-site"), "--save-baseline", str(tmp_path / "partial.json"))
    assert {r["input"]: r["state"] for r in report["coverage"]}["url_baseline"] == "partial"
    assert json.loads((tmp_path / "partial.json").read_text(encoding="utf-8"))["dependencies"] == "partial"
