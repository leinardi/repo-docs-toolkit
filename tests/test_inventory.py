"""docstool inventory: couplings, freezes, regions, enum headings, duplicates, lifecycle."""

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

from conftest import docstool_json, git, make_repo

GOLDEN = Path(__file__).parent / "golden" / "messy-docs-couplings.json"


def couplings(report: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        ({k: c[k] for k in ("source", "line", "kind", "ref", "target", "detail", "status")} for c in report["data"]["couplings"]),
        key=lambda c: (c["source"], c["line"], c["ref"], c["detail"]),
    )


def test_messy_docs_couplings_match_the_golden_file(tmp_path: Path) -> None:
    repo = make_repo("messy-docs", tmp_path)
    _, report = docstool_json(repo, "inventory")
    got = couplings(report)
    assert got == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_messy_docs_findings_are_the_citations_check_cannot_see(tmp_path: Path) -> None:
    repo = make_repo("messy-docs", tmp_path)
    code, report = docstool_json(repo, "inventory")
    assert code == 1
    assert sorted((f["check"], f["file"], f["line"], f["severity"]) for f in report["findings"]) == [
        ("coupling-bold-label", "src/device.rs", 2, "P2"),
        ("coupling-missing", ".agents/skills/review/SKILL.md", 8, "P3"),
        ("coupling-missing", "src/device.rs", 3, "P1"),
        ("coupling-missing", "src/device.rs", 4, "P1"),
    ]


def test_frozen_paths_come_from_code_tests_and_ci(tmp_path: Path) -> None:
    repo = make_repo("messy-docs", tmp_path)
    _, report = docstool_json(repo, "inventory")
    frozen = report["data"]["frozen"]
    assert set(frozen) == {"docs/protocol.md", "docs/release.md"}
    assert "tests/docs_test.rs:2" in frozen["docs/protocol.md"]["path"]
    assert set(frozen["docs/protocol.md"]["headings"]) == {"udev rule", "section 5"}


def test_lifecycle_duplicates_and_census(tmp_path: Path) -> None:
    repo = make_repo("messy-docs", tmp_path)
    _, report = docstool_json(repo, "inventory")
    files = report["data"]["files"]
    assert files["docs/roadmap.md"]["lifecycle"]["hint"] == "record"
    assert files["docs/protocol.md"]["lifecycle"]["hint"] == "living"
    assert files["docs/internal/notes.md"]["published"] is False
    exact = report["data"]["duplicates"]["exact"]
    kinds = sorted((group["kind"], tuple(group["occurrences"])) for group in exact)
    assert ("code", ("CONTRIBUTING.md:5", "README.md:5")) in kinds
    assert ("paragraph", ("RELEASING.md:5", "docs/release.md:5")) in kinds
    root = report["data"]["root"]["files"]
    assert root["CHANGELOG.md"] == ["CHANGELOG.md"]
    assert root["SECURITY.md"] == []


def test_generated_regions_enum_headings_and_blob_urls(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / "docs" / "troubleshooting.md").write_text(
        "# Troubleshooting\n\n## Refusals\n\n### busy\n\nx\n\n### unknown-model\n\nx\n\n### no-backend\n\nx\n\n"
        "<!-- BEGIN GENERATED: edit models.yaml -->\n| a |\n| --- |\n<!-- END GENERATED -->\n",
        encoding="utf-8",
    )
    (repo / "src").mkdir()
    (repo / "src" / "refusal.go").write_text(
        'package refusal\n\nconst (\n\tBusy = "busy"\n\tUnknown = "unknown-model"\n\tNone = "no-backend"\n)\n'
        'const docs = "https://github.com/example/clean/blob/main/"\n'
        'const page = "https://github.com/example/clean/blob/main/docs/troubleshooting.md#busy"\n',
        encoding="utf-8",
    )
    _, report = docstool_json(repo, "inventory")
    groups = report["data"]["enum_headings"]
    assert [(g["file"], g["parent"], g["count"]) for g in groups] == [("docs/troubleshooting.md", "Refusals", 3)]
    assert report["data"]["files"]["docs/troubleshooting.md"]["generated_regions"][0]["start"] == 17
    refs = {(c["ref"], c["status"]) for c in report["data"]["couplings"] if c["source"] == "src/refusal.go"}
    assert refs == {("blob-base", "runtime"), ("blob", "ok"), ("anchor", "ok")}
    assert "docs/troubleshooting.md" in report["data"]["frozen"]


def test_urls_built_at_run_time_are_couplings(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / "web").mkdir()
    (repo / "web" / "links.ts").write_text(
        'const REPOSITORY = "https://github.com/example/clean"\n'
        "const DOCS = `${REPOSITORY}/blob/main/docs`\n"
        "export const install = `${DOCS}/guide.md#install`\n"
        "export const gone = `${DOCS}/guide.md#gone`\n",
        encoding="utf-8",
    )
    _, report = docstool_json(repo, "inventory")
    refs = sorted((c["line"], c["ref"], c["target"], c["status"]) for c in report["data"]["couplings"] if c["source"] == "web/links.ts")
    assert refs == [
        (2, "blob", "docs", "ok"),
        (3, "anchor", "docs/guide.md", "ok"),
        (3, "blob", "docs/guide.md", "ok"),
        (4, "anchor", "docs/guide.md", "missing"),
        (4, "blob", "docs/guide.md", "ok"),
    ]
    assert ("coupling-missing", "web/links.ts", 4) in {(f["check"], f["file"], f["line"]) for f in report["findings"]}
    assert "web/links.ts:3" in report["data"]["frozen"]["docs/guide.md"]["path"]


def test_a_path_no_commit_held_is_an_unverified_lead(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / "docs" / "old.md").write_text("# Old\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "add old")
    (repo / "docs" / "old.md").unlink()
    (repo / "tools").mkdir()
    (repo / "tools" / "gen.py").write_text('OLD = open("docs/old.md")\nOTHER = open("docs/never.md")\n', encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "remove old")
    _, report = docstool_json(repo, "inventory")
    got = {(f["line"], f["severity"], f["confidence"]) for f in report["findings"] if f["file"] == "tools/gen.py"}
    assert got == {(1, "P1", "verified"), (2, "P3", "unverified")}


def test_pre_commit_regexes_that_name_docs_are_couplings(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / ".pre-commit-config.yaml").write_text(
        "repos:\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: docs-test\n"
        "        name: docs test\n"
        "        entry: 'true'\n"
        "        language: system\n"
        "        files: ^docs/(guide|reference)\\.md$\n"
        "      - id: all-md\n"
        "        name: md\n"
        "        entry: 'true'\n"
        "        language: system\n"
        "        files: \\.md$\n"
        "        exclude: ^docs/old-notes\\.md$\n",
        encoding="utf-8",
    )
    _, report = docstool_json(repo, "inventory")
    regex = sorted((c["line"], c["target"], c["status"]) for c in report["data"]["couplings"] if c["ref"] == "regex")
    assert regex == [(8, "docs/guide.md", "ok"), (8, "docs/reference.md", "ok"), (14, "docs/old-notes.md", "missing")]
    assert "docs/guide.md" in report["data"]["frozen"]
    assert ("coupling-missing", ".pre-commit-config.yaml", 14, "P2") in {
        (f["check"], f["file"], f["line"], f["severity"]) for f in report["findings"]
    }


def test_pre_commit_regexes_are_read_line_by_line_past_unsupported_yaml(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / ".pre-commit-config.yaml").write_text(
        "repos:\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: docs-test\n"
        "        args: [\n"
        "          --x,\n"
        "        ]\n"
        "        files: '^docs/guide\\.md$'\n",
        encoding="utf-8",
    )
    code, report = docstool_json(repo, "inventory")
    assert {(c["target"], c["status"]) for c in report["data"]["couplings"] if c["ref"] == "regex"} == {("docs/guide.md", "ok")}
    assert {r["input"]: r["state"] for r in report["coverage"]}["couplings"] == "complete"
    (repo / ".pre-commit-config.yaml").write_text("repos: [\n]\nfiles: |\n  ^docs/\n", encoding="utf-8")
    code, report = docstool_json(repo, "inventory")
    assert {r["input"]: r["state"] for r in report["coverage"]}["couplings"] == "partial"
    assert code == 3


def test_blocks_baseline_is_written(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    out = tmp_path / "blocks.json"
    code, _ = docstool_json(repo, "inventory", "--blocks", str(out))
    assert code == 0
    blocks = json.loads(out.read_text(encoding="utf-8"))["blocks"]
    code_blocks = [b for b in blocks if b["type"] == "code"]
    assert {b["info"] for b in code_blocks} == {"sh", "markdown"}
    assert all(len(b["hash"]) == 16 for b in blocks)
    assert {"file", "line", "type", "depth", "position", "heading_path", "text"} <= set(blocks[0])


def test_unreadable_text_file_makes_couplings_partial(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / "notes.txt").write_bytes(b"caf\xe9 docs/guide.md\n")
    (repo / "image.png").write_bytes(b"\x89PNG\x00\x00")
    code, report = docstool_json(repo, "inventory")
    rows = {r["input"]: r for r in report["coverage"]}
    assert rows["couplings"]["state"] == "partial"
    assert "notes.txt (undecodable)" in rows["couplings"]["reason"]
    assert "image.png" not in rows["couplings"]["reason"]
    assert code == 3


def test_no_site_config_is_not_applicable(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / "zensical.toml").unlink()
    code, report = docstool_json(repo, "inventory")
    states = {r["input"]: r["state"] for r in report["coverage"]}
    assert states["config"] == states["nav"] == states["exclude_docs"] == "not_applicable"
    assert code == 0
