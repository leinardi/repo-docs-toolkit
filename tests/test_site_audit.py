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

from pathlib import Path

from conftest import docstool_json, make_repo


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
