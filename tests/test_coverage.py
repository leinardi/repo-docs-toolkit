"""Fail-closed coverage: what docstool cannot analyse is reported, never passed as clean."""

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

from pathlib import Path
from typing import Any

from conftest import DOCSTOOL, docstool_json, git, make_repo, run_script
from test_plan import ART, conserve_repo, write_plan
from test_site_build import build, prebuilt

ANCHORED_YAML = "site_name: x\nnav: &nav\n  - Home: index.md\nextra: *nav\n"


def states(report: dict[str, Any]) -> dict[str, str]:
    return {r["input"]: r["state"] for r in report["coverage"]}


def test_no_site_config_is_not_applicable_and_complete(tmp_path: Path) -> None:
    repo = make_repo("rust-cli", tmp_path)
    (repo / "zensical.toml").unlink()
    code, report = docstool_json(repo, "check", "--scope", "repo")
    assert states(report)["nav"] == "not_applicable"
    assert code in (0, 1)


def test_binary_files_are_excluded_not_partial(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / "font.woff2").write_bytes(b"wOF2\x00\x01")
    (repo / "blob.dat").write_bytes(b"\x00\x01\x02")
    (repo / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "binaries")
    code, report = docstool_json(repo, "inventory")
    assert states(report)["couplings"] == "complete"
    assert code == 0
    # tracked images and fonts never block a restructure
    write_plan(repo, {"keep": [{"paths": ["docs/"]}]})
    code, report = docstool_json(repo, "plan", "validate")
    assert code == 0, report["findings"]
    assert states(report)["couplings"] == "complete"


def test_unsupported_yaml_blocks_check_and_plan(tmp_path: Path) -> None:
    repo = make_repo("mkdocs-site", tmp_path)
    (repo / "mkdocs.yml").write_text(ANCHORED_YAML, encoding="utf-8")
    code, report = docstool_json(repo, "check")
    assert code == 3
    code, report = docstool_json(repo, "check", "--allow-partial")
    assert code in (0, 1)
    text = run_script(DOCSTOOL, "check", "--root", str(repo), "--allow-partial")
    assert text.returncode in (0, 1)
    assert "PARTIAL: " in text.stdout.split("\n")[0]
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "anchors")
    write_plan(repo, {"keep": [{"paths": ["docs/"]}]}, meta={"site_config": "mkdocs.yml"})
    for action in (("validate",), ("apply", "--write")):
        code, report = docstool_json(repo, "plan", *action)
        assert code == 3, (action, report["findings"])
        assert {r["input"]: r["state"] for r in report["coverage"]}["config"] != "complete"


def test_undecodable_text_blocks_plan_apply(tmp_path: Path) -> None:
    repo = make_repo("messy-docs", tmp_path)
    (repo / "notes.txt").write_bytes(b"caf\xe9 docs/release.md\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "notes")
    write_plan(repo, {"move": [{"from": "docs/release.md", "to": "docs/guide/release.md"}], "keep": [{"paths": ["docs/"]}]}, ["docs/release.md"])
    code, report = docstool_json(repo, "plan", "validate")
    assert code == 3
    assert "plan-coverage" in {f["check"] for f in report["findings"]}
    code, report = docstool_json(repo, "plan", "apply", "--write")
    assert code == 3
    assert (repo / "docs" / "release.md").exists()


def test_a_source_derived_baseline_makes_verify_partial(tmp_path: Path) -> None:
    repo = conserve_repo(tmp_path)
    prebuilt(repo, {"index.html": "<h1 id='clean'>Clean</h1>", "guide/index.html": "<h2 id='install'>Install</h2>"})
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "prebuilt")
    assert docstool_json(repo, "check", "--save-baseline", str(tmp_path / "urls.json"))[0] in (0, 1)
    assert build(repo, tmp_path / "site")[0] == 0
    code, report = docstool_json(repo, "plan", "verify", "--urls", str(tmp_path / "urls.json"), "--built", str(tmp_path / "site"))
    assert code == 3
    assert states(report)["url_baseline"] == "partial"
    assert "partially verified" in next(r["reason"] for r in report["coverage"] if r["input"] == "url_baseline")
    assert (repo / ART / "blocks.json").is_file()
