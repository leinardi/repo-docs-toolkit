"""docstool readme: the README rules and drift against the homepage."""

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


def test_good_readme_passes_with_its_homepage(tmp_path: Path) -> None:
    repo = make_repo("readme-good", tmp_path)
    code, report = docstool_json(repo, "readme", "--home", "docs/index.md")
    assert code == 0, report["findings"]
    assert 50 <= report["data"]["readme"]["lines"] <= 100


def test_bad_readme_planted_faults(tmp_path: Path) -> None:
    repo = make_repo("readme-bad", tmp_path)
    code, report = docstool_json(repo, "readme", "--home", "docs/index.md")
    assert code == 1
    got = {(f["check"], f["severity"]) for f in report["findings"]}
    assert got == {
        ("readme-picture", "P1"),
        ("broken-anchor", "P1"),
        ("readme-drift", "P2"),
        ("readme-h1", "P2"),
        ("readme-alt", "P2"),
        ("readme-registry-image", "P2"),
        ("readme-badges", "P2"),
        ("readme-length", "P3"),
        ("readme-badges", "P3"),
        ("readme-emoji", "P3"),
        ("readme-license", "P3"),
        ("readme-alerts", "P3"),
    }
    drift = sorted(f["message"] for f in report["findings"] if f["check"] == "readme-drift")
    assert len(drift) == 3


def test_drift_both_directions(tmp_path: Path) -> None:
    repo = make_repo("readme-good", tmp_path)
    home = repo / "docs" / "index.md"
    home.write_text(home.read_text(encoding="utf-8").replace("**Honest**", "**Careful**"), encoding="utf-8")
    _, report = docstool_json(repo, "readme", "--home", "docs/index.md")
    files = {(f["file"], f["message"].split("'")[1]) for f in report["findings"] if f["check"] == "readme-drift"}
    assert files == {("README.md", "Careful"), ("docs/index.md", "Honest")}


def test_missing_readme_is_failed_coverage(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    code, _ = docstool_json(repo, "readme", "--file", "NOPE.md")
    assert code == 3
