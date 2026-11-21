"""docstool site-build: fresh output, a stamp of the inputs, staleness, and one real Zensical build."""

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
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import DOCSTOOL, docstool_code, docstool_json, git, load_module, make_repo, run_script

FAKEGEN = Path(__file__).parent / "fakegen.py"
GEN = f"{sys.executable} {FAKEGEN}"


def prebuilt(repo: Path, pages: dict[str, str]) -> None:
    for rel, text in pages.items():
        path = repo / "prebuilt" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def build(repo: Path, out: Path, *extra: str) -> tuple[int, dict[str, Any]]:
    result = run_script(DOCSTOOL, "site-build", "--root", str(repo), "--out", str(out), "--generator-cmd", GEN, "--format", "json", *extra)
    return result.returncode, json.loads(result.stdout) if result.stdout else {"stderr": result.stderr}


def site_repo(tmp_path: Path) -> Path:
    repo = make_repo("clean", tmp_path)
    prebuilt(repo, {"index.html": "<h1 id='clean'>Clean</h1>"})
    config = repo / "zensical.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "[project.markdown_extensions.attr_list]", 'extra_css = ["assets/extra.css"]\n\n[project.markdown_extensions.attr_list]'
        )
        + '\n[project.markdown_extensions."pymdownx.snippets"]\nbase_path = ["."]\n',
        encoding="utf-8",
    )
    (repo / "docs" / "assets" / "extra.css").write_text("a {}\n", encoding="utf-8")
    (repo / "includes").mkdir()
    (repo / "includes" / "outer.md").write_text('--8<-- "includes/inner.md"\n', encoding="utf-8")
    (repo / "includes" / "inner.md").write_text("inner\n", encoding="utf-8")
    guide = repo / "docs" / "guide.md"
    guide.write_text(guide.read_text(encoding="utf-8") + '\n--8<-- "README.md"\n\n--8<-- "includes/outer.md"\n', encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "site")
    return repo


def test_build_writes_a_stamp_with_every_input(tmp_path: Path) -> None:
    repo = site_repo(tmp_path)
    code, report = build(repo, tmp_path / "out")
    assert code == 0, report
    stamp = json.loads((tmp_path / "out" / ".docstool-build.json").read_text(encoding="utf-8"))
    assert {"zensical.toml", "docs/guide.md", "docs/assets/extra.css", "README.md", "includes/outer.md", "includes/inner.md"} <= set(stamp["inputs"])
    assert not any(k.startswith("docs/internal/") for k in stamp["inputs"])
    assert stamp["dependencies"] == "complete"
    assert (tmp_path / "out" / "index.html").is_file()
    assert not (repo / "site").exists()


@pytest.mark.parametrize(
    ("rel", "stale"),
    [
        ("README.md", True),
        ("includes/inner.md", True),
        ("docs/assets/extra.css", True),
        ("docs/internal/receipts.json", False),
        ("docs/internal/README.md", True),
    ],
)
def test_stamp_staleness(tmp_path: Path, rel: str, stale: bool) -> None:
    repo = site_repo(tmp_path)
    if rel == "docs/internal/README.md":
        # without exclude_docs, docs/internal/ is published and so a build input
        config = repo / "zensical.toml"
        config.write_text(config.read_text(encoding="utf-8").replace('exclude_docs = """\ninternal/\n"""\n', ""), encoding="utf-8")
    assert build(repo, tmp_path / "out")[0] == 0
    path = repo / rel
    path.write_text((path.read_text(encoding="utf-8") if path.exists() else "") + "changed\n", encoding="utf-8")
    assert (docstool_code(repo, "check", "--built", str(tmp_path / "out")) == 2) is stale


def test_ref_build_leaves_the_working_tree_alone(tmp_path: Path) -> None:
    repo = site_repo(tmp_path)
    (repo / "docs" / "guide.md").write_text("# Uncommitted\n", encoding="utf-8")
    before = {p: p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts}
    code, report = build(repo, tmp_path / "out", "--ref", "HEAD")
    assert code == 0, report
    assert {p: p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts} == before
    stamp = json.loads((tmp_path / "out" / ".docstool-build.json").read_text(encoding="utf-8"))
    assert stamp["commit"] and stamp["ref"] == "HEAD"
    assert "Uncommitted" not in json.dumps(stamp)


def test_failures_leave_no_stamp(tmp_path: Path) -> None:
    repo = site_repo(tmp_path)
    (repo / "FAIL").write_text("", encoding="utf-8")
    code, _ = build(repo, tmp_path / "out")
    assert code == 2
    assert not (tmp_path / "out" / ".docstool-build.json").exists()
    (tmp_path / "busy").mkdir()
    (tmp_path / "busy" / "x").write_text("", encoding="utf-8")
    assert build(repo, tmp_path / "busy")[0] == 2


def test_missing_generator_gives_the_install_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    repo = site_repo(tmp_path)
    module = load_module("docstool_nogen", DOCSTOOL)
    monkeypatch.setattr(module.shutil, "which", lambda name: None)
    code = module.main(["site-build", "--root", str(repo), "--out", str(tmp_path / "out")])
    assert code == 2
    assert "pip install zensical==0.1.3" in capsys.readouterr().err


def test_check_refuses_unstamped_or_edited_output(tmp_path: Path) -> None:
    repo = site_repo(tmp_path)
    (tmp_path / "plain").mkdir()
    assert docstool_code(repo, "check", "--built", str(tmp_path / "plain")) == 2
    assert build(repo, tmp_path / "out")[0] == 0
    (tmp_path / "out" / "index.html").write_text("edited", encoding="utf-8")
    assert docstool_code(repo, "check", "--built", str(tmp_path / "out")) == 2


def test_unknown_plugin_or_hooks_make_dependencies_partial(tmp_path: Path) -> None:
    repo = site_repo(tmp_path)
    config = repo / "zensical.toml"
    config.write_text(config.read_text(encoding="utf-8") + "\n[project.plugins.some-plugin]\n", encoding="utf-8")
    code, report = build(repo, tmp_path / "out")
    assert code == 0, report
    assert report["data"]["dependencies"] == "partial"


def test_mkdocs_hooks_make_dependencies_partial(tmp_path: Path) -> None:
    repo = make_repo("mkdocs-site", tmp_path)
    assert "hooks:" in (repo / "mkdocs.yml").read_text(encoding="utf-8")
    prebuilt(repo, {"index.html": "<h1 id='home'>Home</h1>"})
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "prebuilt")
    code, report = build(repo, tmp_path / "out", "--generator", "mkdocs")
    assert code == 0, report
    stamp = json.loads((tmp_path / "out" / ".docstool-build.json").read_text(encoding="utf-8"))
    assert stamp["dependencies"] == "partial"
    assert any(d.startswith("hooks") for d in stamp["unknown_dependencies"])


@pytest.mark.zensical
def test_a_real_zensical_build(tmp_path: Path) -> None:
    if shutil.which("zensical") is None:
        if os.environ.get("DOCSTOOL_REQUIRE_ZENSICAL"):
            pytest.fail("zensical is not installed but DOCSTOOL_REQUIRE_ZENSICAL is set")
        pytest.skip("zensical is not installed")
    repo = make_repo("clean", tmp_path)
    result = run_script(DOCSTOOL, "site-build", "--root", str(repo), "--out", str(tmp_path / "out"), "--format", "json")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "out" / "guide" / "index.html").is_file()
    code, report = docstool_json(repo, "check", "--built", str(tmp_path / "out"), "--save-baseline", str(tmp_path / "urls.json"))
    assert code == 0, report["findings"]
    routes = json.loads((tmp_path / "urls.json").read_text(encoding="utf-8"))["routes"]
    assert "install" in routes["guide/"]["ids"]


def _real_build(repo: Path, out: Path) -> None:
    result = run_script(DOCSTOOL, "site-build", "--root", str(repo), "--out", str(out), "--format", "json")
    assert result.returncode == 0, result.stderr


@pytest.mark.zensical
def test_real_zensical_anchor_redirects_preserve_fragments(tmp_path: Path) -> None:
    # Zensical 0.1.3 writes anchor redirects only to redirect.json, keyed "page/#anchor"; check follows them
    if shutil.which("zensical") is None:
        if os.environ.get("DOCSTOOL_REQUIRE_ZENSICAL"):
            pytest.fail("zensical is not installed but DOCSTOOL_REQUIRE_ZENSICAL is set")
        pytest.skip("zensical is not installed")
    repo = make_repo("clean", tmp_path)
    _real_build(repo, tmp_path / "old")
    assert docstool_json(repo, "check", "--built", str(tmp_path / "old"), "--save-baseline", str(tmp_path / "urls.json"))[0] == 0
    guide = repo / "docs" / "guide.md"
    guide.write_text(guide.read_text(encoding="utf-8").replace("## Install", "## Setup"), encoding="utf-8")
    config = repo / "zensical.toml"
    plain = config.read_text(encoding="utf-8")
    config.write_text(plain + '\n[project.plugins.redirects.redirect_maps]\n"guide.md#install" = "guide.md#setup"\n', encoding="utf-8")
    _real_build(repo, tmp_path / "new")
    assert json.loads((tmp_path / "new" / "redirect.json").read_text(encoding="utf-8")) == {"guide/#install": "guide/#setup"}
    _, report = docstool_json(repo, "check", "--built", str(tmp_path / "new"), "--baseline", str(tmp_path / "urls.json"))
    # README.md still links the old anchor (a source finding); the built site loses no URL or fragment
    assert [f for f in report["findings"] if f["file"].endswith("urls.json")] == []
    assert {r["input"]: r["state"] for r in report["coverage"]}["url_baseline"] == "complete"
    config.write_text(plain, encoding="utf-8")
    _real_build(repo, tmp_path / "bare")
    _, report = docstool_json(repo, "check", "--built", str(tmp_path / "bare"), "--baseline", str(tmp_path / "urls.json"))
    assert "fragment-lost" in {f["check"] for f in report["findings"]}
