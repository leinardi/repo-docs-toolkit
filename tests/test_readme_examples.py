"""The repo-readme example READMEs: they pass docstool readme against the landing example homepages."""

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
import shutil
from pathlib import Path
from typing import Any

import pytest
from conftest import LANDING_EXAMPLES, SKILLS_DIR, ZENSICAL_SITE, docstool_json, git

README_EXAMPLES = SKILLS_DIR / "repo-readme" / "assets" / "examples"


def example_repo(name: str, tmp_path: Path) -> Path:
    """A repository made of a landing example's site and the matching example README."""
    repo = tmp_path / name
    shutil.copytree(ZENSICAL_SITE / "assets" / "landing-examples" / name, repo)
    shutil.copy2(README_EXAMPLES / name / "README.md", repo / "README.md")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "example")
    return repo


def readme_report(repo: Path) -> tuple[int, dict[str, Any]]:
    return docstool_json(repo, "readme", "--home", "docs/index.md")


@pytest.mark.parametrize("name", LANDING_EXAMPLES)
def test_example_readme_is_clean_and_in_budget(name: str, tmp_path: Path) -> None:
    code, report = readme_report(example_repo(name, tmp_path))
    assert code == 0, report["findings"]
    assert 50 <= report["data"]["readme"]["lines"] <= 150
    assert report["data"]["readme"]["features"] == report["data"]["home"]["features"]
    assert report["data"]["readme"]["install"] == report["data"]["home"]["install"]


def test_drift_is_reported_in_both_directions(tmp_path: Path) -> None:
    repo = example_repo("cli", tmp_path)
    readme = repo / "README.md"
    text = readme.read_text(encoding="utf-8")
    # The README renames a feature: the homepage card is missing from the README, and the README's
    # new title is missing from the homepage.
    readme.write_text(text.replace("**No collisions:**", "**Collision checks:**"), encoding="utf-8")
    code, report = readme_report(repo)
    assert code == 1
    files = {f["file"] for f in report["findings"] if f["check"] == "readme-drift"}
    assert files == {"README.md", "docs/index.md"}
    messages = " ".join(f["message"] for f in report["findings"])
    assert "'No collisions'" in messages and "'Collision checks'" in messages


@pytest.mark.parametrize(
    ("old", "new", "what"),
    [
        ("Rename thousands of files safely, with a preview of every change.", "Rename files safely.", "tagline"),
        ("cargo install ferrule", "cargo install --locked ferrule", "install block"),
    ],
)
def test_tagline_and_install_drift(tmp_path: Path, old: str, new: str, what: str) -> None:
    repo = example_repo("cli", tmp_path)
    readme = repo / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    code, report = readme_report(repo)
    assert code == 1
    assert any(f["check"] == "readme-drift" and what in f["message"] for f in report["findings"]), report["findings"]


def test_the_code_of_conduct_asset_is_the_covenant_with_its_reporting_note() -> None:
    text = (SKILLS_DIR / "repo-readme" / "assets" / "CODE_OF_CONDUCT.contributor-covenant.md").read_text(encoding="utf-8")
    assert text.startswith("# Contributor Covenant 3.0 Code of Conduct\n")
    assert "[NOTE: describe your means of reporting here.]" in text
    assert "licensed under CC BY-SA 4.0" in text


def test_cards_without_recognisable_titles_make_the_home_input_partial(tmp_path: Path) -> None:
    repo = example_repo("cli", tmp_path)
    home = repo / "docs" / "index.md"
    home.write_text(re.sub(r"^    \*\*(.+?)\*\*$", r"    \1", home.read_text(encoding="utf-8"), flags=re.MULTILINE), encoding="utf-8")
    code, report = readme_report(repo)
    assert code == 3
    assert {r["input"]: r["state"] for r in report["coverage"]}["home"] == "partial"


def test_an_unverified_todo_is_reported(tmp_path: Path) -> None:
    repo = example_repo("cli", tmp_path)
    readme = repo / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace("Licensed under the [MIT License](LICENSE).", "TODO(verify: the licence)"), encoding="utf-8"
    )
    _, report = readme_report(repo)
    assert [f["check"] for f in report["findings"] if f["severity"] == "P2"] == ["readme-todo"]


def test_one_untitled_card_makes_the_home_input_partial(tmp_path: Path) -> None:
    repo = example_repo("cli", tmp_path)
    home = repo / "docs" / "index.md"
    home.write_text(home.read_text(encoding="utf-8").replace("    **No collisions**", "    No collisions, ever."), encoding="utf-8")
    code, report = readme_report(repo)
    assert code == 3
    assert "1 feature cards" in {r["input"]: r["reason"] for r in report["coverage"]}["home"]


def test_bullets_inside_a_card_are_not_cards(tmp_path: Path) -> None:
    repo = example_repo("cli", tmp_path)
    home = repo / "docs" / "index.md"
    text = home.read_text(encoding="utf-8").replace(
        "    Two files that would end up with the same name stop the run before anything is renamed.\n",
        "    Two files that would end up with the same name stop the run before anything is renamed.\n\n    - **Note:** case-only renames count too.\n    - plain sub-bullet\n",
    )
    assert "**Note:**" in text
    home.write_text(text, encoding="utf-8")
    code, report = readme_report(repo)
    assert code == 0, report["findings"]
    assert report["data"]["home"]["features"] == ["Preview first", "Undo the last run", "No collisions", "Fast on big trees"]


@pytest.mark.parametrize("name", LANDING_EXAMPLES)
def test_example_readme_names_no_missing_command(name: str, tmp_path: Path) -> None:
    _, report = docstool_json(example_repo(name, tmp_path), "drift", "--scope", "repo")
    assert [f for f in report["findings"] if f["file"] == "README.md"] == []


def test_a_tagline_wrapped_over_two_lines_is_read_whole(tmp_path: Path) -> None:
    # a repository with a line-length rule wraps the header's <strong> tagline
    repo = example_repo("cli", tmp_path)
    readme = repo / "README.md"
    tagline = "Rename thousands of files safely, with a preview of every change."
    text = readme.read_text(encoding="utf-8")
    assert f"<strong>{tagline}</strong>" in text
    readme.write_text(
        text.replace(f"<strong>{tagline}</strong>", "<strong>Rename thousands of files safely,\nwith a preview of every change.</strong>"),
        encoding="utf-8",
    )
    code, report = readme_report(repo)
    assert code == 0, report["findings"]
    assert report["data"]["readme"]["tagline"] == report["data"]["home"]["tagline"]
