"""Regressions found by the gx52 end-to-end trial (P7): plan, verify, inventory and readme."""

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
import re
import stat
from pathlib import Path
from typing import Any

from conftest import DOCSTOOL, docstool_json, git, load_module, make_repo
from test_plan import ART, approve, write_plan

STATUS = "Historical: the notes of the first design session, kept as written. The current design is in the UI page, which the code cites."

FILES = {
    "docs/ui.md": "# UI\n\n## Views\n\nThe views.\n",
    "docs/analysis.md": "# Analysis\n\n## Six\n\nSection six.\n",
    # a plain-text citation that still resolves once both files sit in docs/internal/, and a link
    # whose text wraps, so its destination is on the line after the one it starts on
    "docs/roadmap.md": '# Roadmap\n\nThe screens are in ui.md, "Views".\n\nThe [sixth section of the\nanalysis](analysis.md#six) explains it.\n',
    # archived with a status line, and edited by a [[reference]] on its original line 5
    "docs/notes.md": "# Notes\n\nFirst session.\n\nThe screens moved to docs/ui.md later.\n",
    "src/app.rs": '// The views (docs/ui.md, "Views").\nfn main() {}\n',
    ".markdownlint-cli2.yaml": "config:\n  line-length:\n    line_length: 60\n",
}

PLAN: dict[str, list[dict[str, Any]]] = {
    "move": [
        {"from": "docs/ui.md", "to": "docs/internal/ui.md", "redirect_to": "docs/index.md"},
        {"from": "docs/roadmap.md", "to": "docs/internal/roadmap.md", "redirect_to": "docs/index.md"},
        {"from": "docs/analysis.md", "to": "docs/internal/history/analysis.md", "redirect_to": "docs/index.md"},
    ],
    "archive": [{"from": "docs/notes.md", "to": "docs/internal/history/notes.md", "status": STATUS, "redirect_to": "docs/index.md"}],
    "reference": [
        {"file": "src/app.rs", "line": 1, "old": "docs/ui.md", "new": "docs/internal/ui.md"},
        {"file": "docs/notes.md", "line": 5, "old": "docs/ui.md", "new": "docs/internal/ui.md"},
    ],
    "keep": [{"paths": ["docs/index.md", "docs/guide.md", "docs/reference.md", "docs/internal/"]}],
}
SOURCES = ["docs/ui.md", "docs/roadmap.md", "docs/analysis.md", "docs/notes.md", "src/app.rs"]


def trial_repo(tmp_path: Path) -> Path:
    repo = make_repo("clean", tmp_path)
    for rel, text in FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "trial")
    write_plan(repo, PLAN, SOURCES)
    return repo


def test_comoved_citations_and_wrapped_links_need_no_reference(tmp_path: Path) -> None:
    code, report = docstool_json(trial_repo(tmp_path), "plan", "validate")
    assert code == 0, report["findings"]


def test_reference_edits_on_an_archived_file_apply_and_verify(tmp_path: Path) -> None:
    repo = trial_repo(tmp_path)
    approve(repo)
    code, report = docstool_json(repo, "plan", "apply", "--write")
    assert code == 0, report["findings"]
    notes = (repo / "docs/internal/history/notes.md").read_text(encoding="utf-8").split("\n")
    assert "The screens moved to docs/internal/ui.md later." in notes
    status = [line for line in notes if line.startswith(">")]
    # wrapped at the repository's markdownlint line length, every line still a quote
    assert len(status) > 1 and all(len(line) <= 60 for line in status), status
    assert (repo / "src/app.rs").read_text(encoding="utf-8").startswith('// The views (docs/internal/ui.md, "Views").')
    # the [[reference]] edits are the plan's own: verify does not call the edited blocks lost
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 0, report["findings"]


def test_inventory_skips_the_restructure_artifacts(tmp_path: Path) -> None:
    repo = trial_repo(tmp_path)
    approve(repo)
    assert docstool_json(repo, "plan", "apply", "--write")[0] == 0
    git(repo, "add", "-A")
    _, report = docstool_json(repo, "inventory")
    assert not [f for f in report["findings"] if f["file"].startswith(ART)], report["findings"]


TABLE = "| Code | Control |\n| --- | --- |\n| 288 | Trigger |\n| 289 | Fire |\n| 290 | A |\n"


def test_identical_rows_match_the_copy_that_stayed(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    # the same table in a page that stays and in a spike that moves to a path sorting before it
    (repo / "docs/protocol.md").write_text("# Protocol\n\n## Buttons\n\n" + TABLE, encoding="utf-8")
    (repo / "docs/spike.md").write_text("# Spike\n\n## Buttons\n\n" + TABLE.replace("| 289 | Fire |\n", "") + "| 289 | Fire |\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "tables")
    plan: dict[str, list[dict[str, Any]]] = {
        "move": [{"from": "docs/spike.md", "to": "docs/internal/research/spike.md", "redirect_to": "docs/index.md"}],
        "keep": [{"paths": ["docs/index.md", "docs/guide.md", "docs/reference.md", "docs/protocol.md", "docs/internal/"]}],
    }
    write_plan(repo, plan, ["docs/spike.md"])
    approve(repo)
    assert docstool_json(repo, "plan", "apply", "--write")[0] == 0
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 0, report["findings"]


def test_a_reviewed_mapping_places_a_moved_warning(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    readme = repo / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\n## Access\n\nNever run it as root.\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "warning")
    write_plan(repo, {"keep": [{"paths": ["docs/"]}]})
    # the README section moves into a new page by hand, as a README rewrite does
    readme.write_text(readme.read_text(encoding="utf-8").replace("\n## Access\n\nNever run it as root.\n", ""), encoding="utf-8")
    (repo / "docs/start.md").write_text("# Start\n\n## Access\n\nNever run it as root.\n", encoding="utf-8")
    code, report = docstool_json(repo, "plan", "verify")
    assert "context-lost" in {f["check"] for f in report["findings"]}, report["findings"]
    blocks = json.loads((repo / ART / "blocks.json").read_text(encoding="utf-8"))["blocks"]
    digest = next(b["hash"] for b in blocks if b["file"] == "README.md" and b["text"] == "Never run it as root.")
    (repo / ART / "mappings.toml").write_text(
        f'[[rewritten]]\nid = "m1"\nblocks = ["{digest}"]\nto = "docs/start.md"\nheading = "Access"\n', encoding="utf-8"
    )
    code, report = docstool_json(repo, "plan", "approve", "--mappings", "--by", "Owner")
    assert code == 0, report["findings"]
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 0, report["findings"]


def test_apply_keeps_the_executable_bit(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    for rel, text in FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    script = repo / "scripts/release.sh"
    script.parent.mkdir()
    script.write_text('#!/bin/sh\n# The release (docs/ui.md, "Views").\n', encoding="utf-8")
    script.chmod(0o755)
    (repo / "docs/ui.md").chmod(0o755)  # a moved file keeps its mode too
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "trial")
    plan = {**PLAN, "reference": [*PLAN["reference"], {"file": "scripts/release.sh", "line": 2, "old": "docs/ui.md", "new": "docs/internal/ui.md"}]}
    write_plan(repo, plan, [*SOURCES, "scripts/release.sh"])
    approve(repo)
    code, report = docstool_json(repo, "plan", "apply", "--write")
    assert code == 0, report["findings"]
    assert "docs/internal/ui.md" in script.read_text(encoding="utf-8")
    assert stat.S_IMODE(script.stat().st_mode) == 0o755
    assert stat.S_IMODE((repo / "docs/internal/ui.md").stat().st_mode) == 0o755
    assert os.access(script, os.X_OK)


def test_a_comoved_heading_citation_renamed_by_an_anchor_is_reported(tmp_path: Path) -> None:
    repo = trial_repo(tmp_path)
    write_plan(repo, {**PLAN, "anchor": [{"file": "docs/ui.md", "from": "views", "to": "screens"}]}, SOURCES)
    code, report = docstool_json(repo, "plan", "validate")
    assert code == 1
    assert ("plan-inbound", "docs/roadmap.md") in {(f["check"], f["file"]) for f in report["findings"]}, report["findings"]


def test_a_wrapped_status_line_never_starts_a_block() -> None:
    module = load_module("docstool_status", DOCSTOOL)
    status = "Historical: kept as written - 1. the plan, + 2. the spikes, # 3 notes > 4 and - more - items + to - wrap"
    for width in range(40, 90):
        note = [line for line in module._status_line("# Title\n\nBody.\n", status, width).split("\n") if line.startswith(">")]
        assert note[0].startswith("> **Status:**")
        assert not any(re.match(r"^> (?:[-+*]\s|\d+[.)]\s|#|>)", line) for line in note[1:]), (width, note)
