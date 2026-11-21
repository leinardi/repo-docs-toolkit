"""docstool site-audit: what Zensical ignores, misses or does differently."""

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

import shutil
from pathlib import Path

from conftest import docstool_json, git, make_repo


def checks(repo: Path) -> set[str]:
    code, report = docstool_json(repo, "site-audit")
    assert code == 1
    return {f["check"] for f in report["findings"]}


def test_zensical_site_planted_problems(tmp_path: Path) -> None:
    got = checks(make_repo("zensical-site", tmp_path))
    assert got == {"extension-missing", "internal-published", "ci-build", "lock", "site-url", "slugify", "feature-conflict", "feature-noop"}


def test_mkdocs_site_planted_problems(tmp_path: Path) -> None:
    got = checks(make_repo("mkdocs-site", tmp_path))
    assert {"hooks", "plugin-unsupported", "feature-noop", "yaml-env", "yaml-python-name", "extension-missing", "slugify"} <= got


def test_the_clean_site_only_lacks_a_lock_and_ci(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / "zensical-requirements.txt").write_text("zensical==0.1.3 \\\n    --hash=sha256:00\n", encoding="utf-8")
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "docs.yaml").write_text("jobs:\n  b:\n    steps:\n      - run: zensical build --strict\n", encoding="utf-8")
    code, report = docstool_json(repo, "site-audit")
    assert code == 0, report["findings"]


def test_a_uv_project_lock_pins_zensical(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    docs = repo / "tools" / "docs"
    docs.mkdir(parents=True)
    (docs / "pyproject.toml").write_text('[project]\nname = "docs"\nversion = "0"\ndependencies = ["zensical==0.1.3"]\n', encoding="utf-8")
    lock = (
        '[[package]]\nname = "zensical"\nversion = "{}"\nsource = {{ registry = "https://pypi.org/simple" }}\n'
        'wheels = [\n    {{ url = "https://files.pythonhosted.org/z.whl", hash = "sha256:00" }},\n]\n'
    )
    (docs / "uv.lock").write_text(lock.format("0.1.3"), encoding="utf-8")
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "docs.yaml").write_text(
        "jobs:\n  b:\n    steps:\n      - run: uv run --project tools/docs --locked zensical build --strict --clean\n", encoding="utf-8"
    )
    code, report = docstool_json(repo, "site-audit")
    assert code == 0, report["findings"]
    assert report["data"]["locks"] == {"tools/docs/uv.lock": "0.1.3"}
    # another version in the lock is reported against the one docstool was checked with
    (docs / "uv.lock").write_text(lock.format("0.2.0"), encoding="utf-8")
    _, report = docstool_json(repo, "site-audit")
    assert [(f["check"], f["file"]) for f in report["findings"]] == [("zensical-version", "tools/docs/uv.lock")]
    # a git source carries no hashes: nothing is pinned, and the requirement is reported instead
    (docs / "uv.lock").write_text(
        '[[package]]\nname = "zensical"\nversion = "0.1.3"\nsource = { git = "https://github.com/zensical/zensical" }\n', encoding="utf-8"
    )
    _, report = docstool_json(repo, "site-audit")
    assert report["data"]["locks"] == {}
    assert "lock" in {f["check"] for f in report["findings"]}


def test_dotted_pymdownx_keys_are_hoisted(tmp_path: Path) -> None:
    repo = make_repo("zensical-site", tmp_path)
    config = repo / "zensical.toml"
    text = config.read_text(encoding="utf-8").replace(
        "pymdownx.superfences = {}",
        'pymdownx.superfences.custom_fences = [{ name = "mermaid", class = "mermaid", format = "pymdownx.superfences.fence_code_format" }]\npymdownx.tabbed.alternate_style = true',
    )
    config.write_text(text, encoding="utf-8")
    _, report = docstool_json(repo, "site-audit")
    assert "extension-missing" not in {f["check"] for f in report["findings"]}


def commit_all(repo: Path) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change")


def test_an_unpinned_requirement_is_reported_at_its_line(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / "zensical-requirements.in").write_text("# the docs toolchain\nzensical>=0.1.3\n", encoding="utf-8")
    commit_all(repo)
    _, report = docstool_json(repo, "site-audit")
    lock = [f for f in report["findings"] if f["check"] == "lock"]
    assert [(f["file"], f["line"]) for f in lock] == [("zensical-requirements.in", 2)]
    assert "zensical>=0.1.3" in lock[0]["message"]


def test_deprecated_validation_and_a_missing_internal_exclusion(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    config = repo / "zensical.toml"
    text = config.read_text(encoding="utf-8").replace('exclude_docs = """\ninternal/\n"""\n', "")
    config.write_text(text + "\n[project.validation]\ninvalid_links = true\nunused_footnotes = true\n", encoding="utf-8")
    shutil.rmtree(repo / "docs" / "internal", ignore_errors=True)
    commit_all(repo)
    _, report = docstool_json(repo, "site-audit")
    got = {(f["check"], f["severity"]) for f in report["findings"]}
    assert {("validation-deprecated", "P3"), ("exclude-internal", "P3")} <= got
    assert "internal-published" not in {check for check, _ in got}


def test_slug_uses_the_site_style_by_default(tmp_path: Path) -> None:
    repo = make_repo("mkdocs-site", tmp_path)
    _, report = docstool_json(repo, "slug", "Security & Operations")
    row = report["data"]["slugs"][0]
    assert (row["github"], row["site"], row["style"]) == ("security--operations", "security-operations", "python-markdown")
    _, report = docstool_json(repo, "slug", "--style", "pymdownx-lower", "Security & Operations")
    assert report["data"]["slugs"][0]["site"] == "security--operations"


def test_slug_with_an_unknown_site_slugify_is_incomplete_not_guessed(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    config = repo / "zensical.toml"
    config.write_text(config.read_text(encoding="utf-8").replace('"pymdownx.slugs.slugify"', '"my_project.slugs.slugify"'), encoding="utf-8")
    code, report = docstool_json(repo, "slug", "Security & Operations")
    assert code == 3
    row = report["data"]["slugs"][0]
    assert (row["github"], row["site"], row["style"]) == ("security--operations", None, "unknown")
    # an explicit --style is the caller's answer: complete again
    code, report = docstool_json(repo, "slug", "--style", "pymdownx-lower", "Security & Operations")
    assert code == 0
