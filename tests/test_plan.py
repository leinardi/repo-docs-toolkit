"""docstool plan: validate, approve, apply, recovery and content conservation."""

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

import hashlib
import json
import subprocess
import tomllib
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from conftest import DOCSTOOL, GIT_ENV, docstool_code, docstool_json, git, load_module, make_repo, run_script
from test_site_build import build, prebuilt

ART = "docs/internal/restructure"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(repo: Path) -> dict[str, str]:
    """Every file outside .git and the restructure artifacts, with its hash."""
    return {
        p.relative_to(repo).as_posix(): sha(p)
        for p in sorted(repo.rglob("*"))
        if p.is_file() and ".git" not in p.relative_to(repo).parts and not p.relative_to(repo).as_posix().startswith(ART)
    }


def directories(repo: Path) -> set[str]:
    """Every directory outside .git and the restructure artifacts: a rollback removes the ones it made."""
    return {
        p.relative_to(repo).as_posix()
        for p in repo.rglob("*")
        if p.is_dir() and ".git" not in p.relative_to(repo).parts and not p.relative_to(repo).as_posix().startswith(ART)
    }


def head(repo: Path) -> str:
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True, env=GIT_ENV).stdout.strip()


def toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    return json.dumps(value)


def write_plan(repo: Path, entries: dict[str, list[dict[str, Any]]], sources: list[str] | None = None, meta: dict[str, Any] | None = None) -> Path:
    """A plan.toml whose [meta.sources] hashes the given files as they are now."""
    blocks = repo / ART / "blocks.json"
    blocks.parent.mkdir(parents=True, exist_ok=True)
    if not blocks.exists():
        code, _ = docstool_json(repo, "inventory", "--blocks", str(blocks))
        assert code in (0, 1, 3), code
    hashed = sorted({*(sources or []), f"{ART}/blocks.json", "zensical.toml"})
    fields: dict[str, Any] = {
        "schema": 1,
        "base_commit": head(repo),
        "docs_dir": "docs",
        "site_config": "zensical.toml",
        "blocks": f"{ART}/blocks.json",
    }
    fields.update(meta or {})
    if fields["site_config"] != "zensical.toml":
        hashed = sorted({*hashed, str(fields["site_config"])} - {"zensical.toml"})
    lines = ["[meta]"] + [f"{key} = {toml_value(value)}" for key, value in fields.items()]
    lines.append("")
    lines.append("[meta.sources]")
    lines += [f'"{rel}" = "{sha(repo / rel)}"' for rel in hashed if (repo / rel).is_file()]
    for kind, items in entries.items():
        for item in items:
            lines += ["", f"[[{kind}]]"]
            lines += [f"{k} = {toml_value(v)}" for k, v in item.items()]
    path = repo / ART / "plan.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


MESSY_PLAN: dict[str, list[dict[str, Any]]] = {
    "archive": [
        {
            "from": "docs/roadmap.md",
            "to": "docs/internal/archive/roadmap.md",
            "status": "Finished in October 2026; kept as written.",
            "redirect_to": "docs/protocol.md",
        }
    ],
    "move": [{"from": "docs/release.md", "to": "docs/guide/release.md"}],
    "reference": [{"file": "src/device.rs", "line": 3, "old": "docs/release.md", "new": "docs/guide/release.md"}],
    "keep": [{"paths": ["docs/protocol.md", "docs/internal/"]}],
}
MESSY_SOURCES = ["docs/roadmap.md", "docs/release.md", "src/device.rs", "RELEASING.md"]


def messy(tmp_path: Path) -> Path:
    repo = make_repo("messy-docs", tmp_path)
    write_plan(repo, MESSY_PLAN, MESSY_SOURCES)
    return repo


def approve(repo: Path) -> None:
    code, report = docstool_json(repo, "plan", "approve", "--by", "Owner")
    assert code == 0, report["findings"]


def broken(repo: Path) -> set[tuple[str, str]]:
    _, report = docstool_json(repo, "check")
    return {(f["check"], f["message"]) for f in report["findings"] if f["check"].startswith("broken")}


def test_plan_round_trip_on_messy_docs(tmp_path: Path) -> None:
    repo = messy(tmp_path)
    planted = broken(repo)
    code, report = docstool_json(repo, "plan", "validate")
    assert code == 0, report["findings"]
    assert report["data"]["approval"] == "missing"
    code, report = docstool_json(repo, "plan", "apply")
    assert code == 0
    assert "dry run" in report["data"]["state"]
    assert {op["path"] for op in report["data"]["operations"]} >= {
        "docs/roadmap.md",
        "docs/guide/release.md",
        "RELEASING.md",
        "zensical.toml",
        "src/device.rs",
    }
    before = snapshot(repo)
    assert snapshot(repo) == before
    approve(repo)
    code, report = docstool_json(repo, "plan", "apply", "--write")
    assert code == 0, report["findings"]
    assert not (repo / "docs/release.md").exists()
    assert (repo / "docs/guide/release.md").read_text(encoding="utf-8").count("](../internal/notes.md)") == 1
    assert "docs/guide/release.md" in (repo / "RELEASING.md").read_text(encoding="utf-8")
    assert "docs/guide/release.md" in (repo / "src/device.rs").read_text(encoding="utf-8").split("\n")[2]
    archived = (repo / "docs/internal/archive/roadmap.md").read_text(encoding="utf-8")
    assert "> **Status:** Finished in October 2026; kept as written." in archived
    config = (repo / "zensical.toml").read_text(encoding="utf-8")
    assert '"roadmap.md" = "protocol.md"' in config
    assert '"release.md" = "guide/release.md"' in config
    assert not any((repo / ART / name).exists() for name in (".apply-journal.json", ".staging", ".backups"))
    assert (repo / ART / "apply-log.json").is_file()
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 0, report["findings"]
    assert report["data"]["conservation"]["unaccounted"] == 0
    assert broken(repo) == planted
    code, report = docstool_json(repo, "plan", "apply", "--write")
    assert code == 0
    assert report["data"]["state"] == "already applied, nothing to do"


def test_mixed_state_refuses_with_each_paths_state(tmp_path: Path) -> None:
    repo = messy(tmp_path)
    approve(repo)
    assert docstool_json(repo, "plan", "apply", "--write")[0] == 0
    git(repo, "show", "HEAD:RELEASING.md")
    original = subprocess.run(["git", "-C", str(repo), "show", "HEAD:RELEASING.md"], capture_output=True, check=True, env=GIT_ENV).stdout
    (repo / "RELEASING.md").write_bytes(original)
    code, report = docstool_json(repo, "plan", "apply", "--write")
    assert code == 1
    states = {f["file"]: f["message"] for f in report["findings"] if f["check"] == "plan-mixed"}
    assert "pre-image" in states["RELEASING.md"]
    assert "post-image" in states["docs/guide/release.md"]


def test_the_shipped_example_plan_validates(tmp_path: Path) -> None:
    example = Path(DOCSTOOL).parents[1] / "assets" / "restructure-plan.example.toml"
    repo = make_repo("messy-docs", tmp_path)
    blocks = repo / ART / "blocks.json"
    blocks.parent.mkdir(parents=True)
    assert docstool_json(repo, "inventory", "--blocks", str(blocks))[0] in (0, 1)
    lines = []
    for raw in example.read_text(encoding="utf-8").split("\n"):
        line = raw.replace("<base commit>", head(repo))
        if line.endswith('= "<sha256>"'):
            line = line.replace("<sha256>", sha(repo / line.split('"')[1]))
        lines.append(line)
    (repo / ART / "plan.toml").write_text("\n".join(lines), encoding="utf-8")
    code, report = docstool_json(repo, "plan", "validate")
    assert code == 0, report["findings"]
    code, report = docstool_json(repo, "plan", "apply")
    assert code == 0, report["findings"]
    assert {op["path"] for op in report["data"]["operations"]} >= {"docs/internal/release.md", "docs/internal/history/roadmap.md", "src/device.rs"}


@pytest.mark.parametrize(
    ("mutate", "check"),
    [
        (lambda repo: (repo / "docs/release.md").write_text("# Release\n\nchanged\n", encoding="utf-8"), "plan-stale"),
        (
            lambda repo: (repo / ART / "plan.toml").write_text(
                (repo / ART / "plan.toml").read_text(encoding="utf-8").replace("kept as written", "kept"), encoding="utf-8"
            ),
            "plan-approval",
        ),
    ],
)
def test_stale_input_and_edited_plan_refuse(tmp_path: Path, mutate: Callable[[Path], None], check: str) -> None:
    repo = messy(tmp_path)
    approve(repo)
    mutate(repo)
    before = snapshot(repo)
    code, report = docstool_json(repo, "plan", "apply", "--write")
    assert code == 1
    assert check in {f["check"] for f in report["findings"]}
    assert snapshot(repo) == before


def test_head_not_descending_from_base_refuses(tmp_path: Path) -> None:
    repo = make_repo("messy-docs", tmp_path)
    git(repo, "checkout", "-q", "-b", "other")
    (repo / "x.txt").write_text("x\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "other")
    write_plan(repo, MESSY_PLAN, MESSY_SOURCES)
    git(repo, "checkout", "-q", "main")
    git(repo, "commit", "-q", "--allow-empty", "-m", "diverge")
    code, report = docstool_json(repo, "plan", "validate")
    assert code == 1
    assert "plan-base" in {f["check"] for f in report["findings"]}


@pytest.mark.parametrize(
    ("entry", "check"),
    [
        ({"move": [{"from": "docs/release.md", "to": "docs/../release.md"}]}, "plan-path"),
        ({"move": [{"from": "docs/release.md", "to": "/tmp/release.md"}]}, "plan-path"),
        ({"move": [{"from": "docs/release.md", "to": "docs/linked/release.md"}]}, "plan-path"),
        ({"move": [{"from": "docs/release.md", "to": "docs/Protocol.md"}]}, "plan-collision"),
        ({"move": [{"from": "docs/release.md", "to": "docs/protocol.md"}]}, "plan-collision"),
        ({"move": [{"from": "docs/release.md", "to": "src/release.md"}]}, "plan-path"),
        ({"move": [{"from": "docs/protocol.md", "to": "docs/guide/protocol.md"}]}, "plan-frozen"),
        ({"delete": [{"path": "docs/release.md", "approved": True, "proof": "duplicate"}]}, "plan-delete"),
        ({"decision": [{"id": "D1", "question": "Publish the notes?", "answer": ""}]}, "plan-decision"),
    ],
)
def test_validate_rules_refuse(tmp_path: Path, entry: dict[str, list[dict[str, Any]]], check: str) -> None:
    repo = make_repo("messy-docs", tmp_path)
    (repo / "elsewhere").mkdir()
    (repo / "docs" / "linked").symlink_to("../elsewhere")
    entries = {"keep": [{"paths": ["docs/"]}], **entry}
    write_plan(repo, entries, ["docs/release.md", "docs/protocol.md"])
    code, report = docstool_json(repo, "plan", "validate")
    assert code == 1
    assert check in {f["check"] for f in report["findings"]}, report["findings"]
    assert not (repo / "elsewhere" / "release.md").exists()


def test_uncovered_doc_and_missing_reference_are_reported(tmp_path: Path) -> None:
    repo = make_repo("messy-docs", tmp_path)
    write_plan(repo, {"move": [{"from": "docs/release.md", "to": "docs/guide/release.md"}]}, ["docs/release.md"])
    _, report = docstool_json(repo, "plan", "validate")
    found = {(f["check"], f["file"]) for f in report["findings"]}
    assert ("plan-uncovered", "docs/plan.toml") not in found
    assert any(c == "plan-uncovered" for c, _ in found)
    assert ("plan-frozen", "src/device.rs") in found


def test_dirty_touched_file_refuses(tmp_path: Path) -> None:
    repo = messy(tmp_path)
    approve(repo)
    (repo / "RELEASING.md").write_text((repo / "RELEASING.md").read_text(encoding="utf-8") + "\nlocal edit\n", encoding="utf-8")
    code, report = docstool_json(repo, "plan", "apply", "--write")
    assert code == 1
    assert {f["check"] for f in report["findings"]} & {"plan-dirty", "plan-stale"}
    assert (repo / "docs/release.md").exists()


def test_redirects_reparse_and_unapproved_apply_refuses(tmp_path: Path) -> None:
    repo = messy(tmp_path)
    code, report = docstool_json(repo, "plan", "apply", "--write")
    assert code == 1
    assert "plan-approval" in {f["check"] for f in report["findings"]}
    assert (repo / "docs/release.md").exists()


def _run_main(module: Any, repo: Path, *args: str) -> int:
    return int(module.main([*args, "--root", str(repo), "--format", "json"]))


def _post_state(tmp_path: Path) -> dict[str, str]:
    reference = messy(tmp_path / "reference")
    approve(reference)
    assert docstool_json(reference, "plan", "apply", "--write")[0] == 0
    return snapshot(reference)


def _count_ops(repo: Path) -> int:
    _, report = docstool_json(repo, "plan", "apply")
    return len(report["data"]["operations"])


def test_failure_at_every_operation_rolls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    probe = messy(tmp_path / "probe")
    total = _count_ops(probe)
    assert total >= 5
    for k in range(total):
        repo = messy(tmp_path / f"k{k}")
        approve(repo)
        before, dirs_before = snapshot(repo), directories(repo)
        module = load_module(f"docstool_fail_{k}", DOCSTOOL)
        state = {"n": 0, "k": k, "real": module._apply_one}

        def failing(root: Any, art: Any, index: int, entry: Any, state: dict[str, Any] = state) -> None:
            # the k-th operation's write, rename or unlink fails
            if state["n"] == state["k"]:
                raise OSError("injected failure")
            state["n"] += 1
            state["real"](root, art, index, entry)

        monkeypatch.setattr(module, "_apply_one", failing)
        code = _run_main(module, repo, "plan", "apply", "--write")
        monkeypatch.undo()
        capsys.readouterr()
        assert code == 2
        assert snapshot(repo) == before, k
        assert directories(repo) == dirs_before, k
        assert not (repo / ART / ".apply-journal.json").exists()


def test_failure_after_a_change_rolls_it_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    repo = messy(tmp_path)
    approve(repo)
    before = snapshot(repo)
    module = load_module("docstool_journal_fail", DOCSTOOL)
    real = module._write_journal
    calls = {"n": 0}

    def failing(art: Any, journal: Any) -> None:
        calls["n"] += 1
        if calls["n"] == 3:  # the plan, op 0 done, then op 1 done fails after op 1 changed the tree
            raise OSError("disk full")
        real(art, journal)

    monkeypatch.setattr(module, "_write_journal", failing)
    assert _run_main(module, repo, "plan", "apply", "--write") == 2
    capsys.readouterr()
    assert snapshot(repo) == before
    assert not any((repo / ART / n).exists() for n in (".apply-journal.json", ".staging", ".backups"))


class Crash(BaseException):
    pass


@pytest.mark.parametrize("point", ["before-change", "after-change", "after-done"])
def test_crash_points_resume_and_rollback(tmp_path: Path, point: str, capsys: pytest.CaptureFixture[str]) -> None:
    post = _post_state(tmp_path)
    total = _count_ops(messy(tmp_path / "probe"))
    for k in range(total):
        for recovery in ("resume", "rollback"):
            repo = messy(tmp_path / f"{point}-{k}-{recovery}")
            approve(repo)
            before = snapshot(repo)
            module = load_module(f"docstool_crash_{point}_{k}_{recovery}", DOCSTOOL)

            def hook(name: str, index: int, k: int = k) -> None:
                if name == point and index == k:
                    raise Crash

            setattr(module, "_CRASH_HOOK", hook)  # noqa: B010 - the module is loaded by path, so mypy cannot see it
            with pytest.raises(Crash):
                _run_main(module, repo, "plan", "apply", "--write")
            capsys.readouterr()
            assert (repo / ART / ".apply-journal.json").exists()
            code, report = docstool_json(repo, "plan", "apply", "--write")
            assert code == 1
            assert "plan-journal" in {f["check"] for f in report["findings"]}
            code, report = docstool_json(repo, "plan", recovery)
            assert code == 0, report["findings"]
            assert snapshot(repo) == (post if recovery == "resume" else before), (point, k, recovery)
            assert not (repo / ART / ".apply-journal.json").exists()


@pytest.mark.parametrize("point", ["log-tmp", "after-log", "after-staging", "after-backups"])
def test_finalisation_crashes_recover(tmp_path: Path, point: str, capsys: pytest.CaptureFixture[str]) -> None:
    post = _post_state(tmp_path)
    repo = messy(tmp_path / point)
    approve(repo)
    module = load_module(f"docstool_final_{point}", DOCSTOOL)

    def hook(name: str, index: int) -> None:
        if name == point:
            raise Crash

    setattr(module, "_CRASH_HOOK", hook)  # noqa: B010 - the module is loaded by path, so mypy cannot see it
    with pytest.raises(Crash):
        _run_main(module, repo, "plan", "apply", "--write")
    capsys.readouterr()
    code, report = docstool_json(repo, "plan", "resume")
    assert code == 0, report["findings"]
    assert snapshot(repo) == post
    assert not any((repo / ART / n).exists() for n in (".apply-journal.json", ".staging", ".backups", "apply-log.json.tmp"))
    code, report = docstool_json(repo, "plan", "apply", "--write")
    assert code == 0
    assert report["data"]["state"] == "already applied, nothing to do"


def test_edit_after_crash_is_a_conflict(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = messy(tmp_path)
    approve(repo)
    module = load_module("docstool_conflict", DOCSTOOL)

    def hook(name: str, index: int) -> None:
        if name == "after-done" and index == 1:
            raise Crash

    setattr(module, "_CRASH_HOOK", hook)  # noqa: B010 - the module is loaded by path, so mypy cannot see it
    with pytest.raises(Crash):
        _run_main(module, repo, "plan", "apply", "--write")
    capsys.readouterr()
    journal = json.loads((repo / ART / ".apply-journal.json").read_text(encoding="utf-8"))
    edited = repo / journal["ops"][0]["path"]
    edited.parent.mkdir(parents=True, exist_ok=True)
    edited.write_text("edited by hand\n", encoding="utf-8")
    for action in ("resume", "rollback"):
        code, report = docstool_json(repo, "plan", action)
        assert code == 1
        assert "plan-conflict" in {f["check"] for f in report["findings"]}
        assert edited.read_text(encoding="utf-8") == "edited by hand\n"


def test_log_with_a_path_reverted_by_hand_is_a_conflict(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = messy(tmp_path)
    approve(repo)
    module = load_module("docstool_logconflict", DOCSTOOL)

    def hook(name: str, index: int) -> None:
        if name == "after-log":
            raise Crash

    setattr(module, "_CRASH_HOOK", hook)  # noqa: B010 - the module is loaded by path, so mypy cannot see it
    with pytest.raises(Crash):
        _run_main(module, repo, "plan", "apply", "--write")
    capsys.readouterr()
    (repo / "RELEASING.md").write_bytes(
        subprocess.run(["git", "-C", str(repo), "show", "HEAD:RELEASING.md"], capture_output=True, check=True, env=GIT_ENV).stdout
    )
    code, report = docstool_json(repo, "plan", "resume")
    assert code == 1
    assert "plan-conflict" in {f["check"] for f in report["findings"]}


# --- verify: content conservation ---------------------------------------------------------------

CONSERVE = """# Guide

## Install

!!! warning
    Back up the device first.

1. Unplug it.
2. Flash it.
3. Plug it in.

~~~sh
make flash
	echo tab
~~~

Never flash over USB hubs.

Same line.

Same line.

## Other

**Do not** skip the check.
"""


def conserve_repo(tmp_path: Path) -> Path:
    repo = make_repo("clean", tmp_path)
    (repo / "docs" / "flash.md").write_text(CONSERVE, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "flash")
    write_plan(repo, {"keep": [{"paths": ["docs/"]}]})
    return repo


def edit(repo: Path, old: str, new: str) -> None:
    path = repo / "docs" / "flash.md"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_verify_passes_on_an_untouched_tree(tmp_path: Path) -> None:
    repo = conserve_repo(tmp_path)
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 0, report["findings"]


@pytest.mark.parametrize(
    ("old", "new", "check"),
    [
        ("!!! warning\n    Back up the device first.\n\n", "", "block-unaccounted"),
        ("1. Unplug it.\n2. Flash it.", "1. Flash it.\n2. Unplug it.", "order-changed"),
        ("\techo tab", "    echo tab", "block-unaccounted"),
        ("Same line.\n\nSame line.\n", "Same line.\n", "block-unaccounted"),
        ("Never flash over USB hubs.\n\n", "", "context-lost"),
        ("**Do not** skip", "Do not skip", "block-unaccounted"),
    ],
)
def test_conservation_negatives_fail_verify(tmp_path: Path, old: str, new: str, check: str) -> None:
    repo = conserve_repo(tmp_path)
    edit(repo, old, new)
    if check == "context-lost":
        edit(repo, "## Other\n", "## Other\n\nNever flash over USB hubs.\n")
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 1
    assert check in {f["check"] for f in report["findings"]}, report["findings"]


def test_rewritten_mapping_needs_a_valid_receipt(tmp_path: Path) -> None:
    repo = conserve_repo(tmp_path)
    blocks = json.loads((repo / ART / "blocks.json").read_text(encoding="utf-8"))["blocks"]
    target = next(b for b in blocks if b["text"] == "Never flash over USB hubs.")
    edit(repo, "Never flash over USB hubs.", "Never flash through a USB hub.")
    mappings = repo / ART / "mappings.toml"
    mappings.write_text(f'[[rewritten]]\nid = "m1"\nblocks = ["{target["hash"]}"]\nto = "docs/flash.md"\nheading = "Install"\n', encoding="utf-8")
    plan_before = (repo / ART / "plan.toml").read_bytes()
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 1
    assert "mapping-unreviewed" in {f["check"] for f in report["findings"]}
    code, report = docstool_json(repo, "plan", "approve", "--mappings", "--by", "Owner")
    assert code == 0, report["findings"]
    assert report["data"]["review"][0]["before"] == ["Never flash over USB hubs."]
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 0, report["findings"]
    assert (repo / ART / "plan.toml").read_bytes() == plan_before
    edit(repo, "Never flash through a USB hub.", "Flash anywhere.")
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 1
    assert "receipt-invalid" in {f["check"] for f in report["findings"]}
    edit(repo, "Flash anywhere.", "Never flash through a USB hub.")
    assert docstool_json(repo, "plan", "verify")[0] == 0
    mappings.write_text(mappings.read_text(encoding="utf-8") + 'note = "changed"\n', encoding="utf-8")
    code, report = docstool_json(repo, "plan", "verify")
    assert "receipt-invalid" in {f["check"] for f in report["findings"]}


def test_split_moves_a_section_and_its_anchors(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / "docs" / "big.md").write_text(
        "# Big\n\nSee [opts](#options).\n\n## Options\n\nText [back](#big).\n\n### Sub\n\nMore.\n\n## Tail\n\nEnd.\n", encoding="utf-8"
    )
    (repo / "docs" / "index.md").write_text((repo / "docs" / "index.md").read_text(encoding="utf-8") + "\n[o](big.md#options)\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "big")
    write_plan(
        repo,
        {
            "split": [{"from": "docs/big.md", "heading": "Options", "to": "docs/options.md"}],
            "keep": [{"paths": ["docs/index.md", "docs/guide.md", "docs/reference.md", "docs/internal/"]}],
        },
        ["docs/big.md"],
    )
    approve(repo)
    code, report = docstool_json(repo, "plan", "apply", "--write")
    assert code == 0, report["findings"]
    moved = (repo / "docs" / "options.md").read_text(encoding="utf-8")
    assert moved.startswith("# Options")
    assert "## Sub" in moved
    assert "[back](big.md#big)" in moved
    assert "[o](options.md#options)" in (repo / "docs" / "index.md").read_text(encoding="utf-8")
    assert "[opts](options.md#options)" in (repo / "docs" / "big.md").read_text(encoding="utf-8")
    assert '"big.md#options" = "options.md#options"' in (repo / "zensical.toml").read_text(encoding="utf-8")
    code, report = docstool_json(repo, "check")
    assert [f for f in report["findings"] if f["check"].startswith("broken")] == []


def test_split_then_verify_accounts_for_every_block(tmp_path: Path) -> None:
    # a split promotes the moved headings; conservation and section context must follow them
    repo = make_repo("clean", tmp_path)
    (repo / "docs" / "big.md").write_text(
        "# Big\n\n## Options\n\nNever set both flags.\n\n### Sub\n\n- one\n- two\n\n## Tail\n\nEnd.\n", encoding="utf-8"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "big")
    write_plan(
        repo,
        {
            "split": [{"from": "docs/big.md", "heading": "Options", "to": "docs/options.md"}],
            "keep": [{"paths": ["docs/index.md", "docs/guide.md", "docs/reference.md", "docs/internal/"]}],
        },
        ["docs/big.md"],
    )
    approve(repo)
    assert docstool_json(repo, "plan", "apply", "--write")[0] == 0
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 0, report["findings"]
    assert report["data"]["conservation"]["unaccounted"] == 0


SECTIONS = "# Setup\n\n## Linux\n\n### Install\n\nNever run it as root.\n\n## Windows\n\n### Install\n\nPlain.\n"


@pytest.mark.parametrize("where", ["sibling", "other-file"])
def test_sensitive_block_moved_between_same_named_sections_loses_context(tmp_path: Path, where: str) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / "docs" / "setup.md").write_text(SECTIONS, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "setup")
    write_plan(repo, {"keep": [{"paths": ["docs/"]}]})
    assert docstool_json(repo, "plan", "verify")[0] == 0
    if where == "sibling":
        text = SECTIONS.replace("Never run it as root.\n\n", "").replace("Plain.\n", "Plain.\n\nNever run it as root.\n")
        (repo / "docs" / "setup.md").write_text(text, encoding="utf-8")
    else:
        (repo / "docs" / "setup.md").write_text(SECTIONS.replace("Never run it as root.\n\n", ""), encoding="utf-8")
        (repo / "docs" / "other.md").write_text("# Setup\n\n## Linux\n\n### Install\n\nNever run it as root.\n", encoding="utf-8")
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 1
    assert "context-lost" in {f["check"] for f in report["findings"]}, report["findings"]


def test_a_failure_while_staging_changes_nothing_and_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = messy(tmp_path)
    approve(repo)
    before, dirs_before = snapshot(repo), directories(repo)
    module = load_module("docstool_stage_fail", DOCSTOOL)
    real = module._fsync_write
    calls = {"n": 0}

    def failing(path: Path, data: bytes) -> None:
        calls["n"] += 1
        if calls["n"] == 3:
            raise OSError("no space left on device")
        real(path, data)

    monkeypatch.setattr(module, "_fsync_write", failing)
    assert _run_main(module, repo, "plan", "apply", "--write") == 2
    monkeypatch.undo()
    assert "nothing was changed" in capsys.readouterr().err
    assert snapshot(repo) == before
    assert directories(repo) == dirs_before
    assert not any((repo / ART / n).exists() for n in (".apply-journal.json", ".staging", ".backups"))
    # staging left by a run killed before its journal: apply refuses, resume clears it, apply then works
    (repo / ART / ".staging").mkdir()
    (repo / ART / ".staging" / "0").write_bytes(b"half")
    assert docstool_code(repo, "plan", "apply", "--write") == 2
    code, report = docstool_json(repo, "plan", "resume")
    assert code == 0, report["findings"]
    assert "stopped before changing anything" in report["data"]["state"]
    assert snapshot(repo) == before
    assert docstool_json(repo, "plan", "apply", "--write")[0] == 0


def test_a_plan_outside_the_root_is_refused(tmp_path: Path) -> None:
    repo = messy(tmp_path / "repo")
    outside = tmp_path / "x"
    outside.mkdir()
    (outside / "plan.toml").write_bytes((repo / ART / "plan.toml").read_bytes())
    for given in ("../x/plan.toml", str(outside / "plan.toml"), "docs/../../x/plan.toml"):
        for action in ("validate", "approve"):
            assert docstool_code(repo, "plan", action, "--plan", given, "--by", "Owner") == 2, (given, action)
    assert "[approval]" not in (outside / "plan.toml").read_text(encoding="utf-8")
    assert docstool_json(repo, "plan", "validate", "--plan", str(repo / ART / "plan.toml"))[0] == 0


def test_a_dropped_mapping_needs_proof(tmp_path: Path) -> None:
    repo = conserve_repo(tmp_path)
    blocks = json.loads((repo / ART / "blocks.json").read_text(encoding="utf-8"))["blocks"]
    target = next(b for b in blocks if b["text"] == "Same line.")
    edit(repo, "Same line.\n\nSame line.\n", "Same line.\n")
    mappings = repo / ART / "mappings.toml"
    mappings.write_text(f'[[dropped]]\nid = "d1"\nblocks = ["{target["hash"]}"]\n', encoding="utf-8")
    code, report = docstool_json(repo, "plan", "approve", "--mappings", "--by", "Owner")
    assert code == 1
    assert "mapping-invalid" in {f["check"] for f in report["findings"]}
    assert not (repo / ART / "review-receipts.json").exists()
    mappings.write_text(mappings.read_text(encoding="utf-8") + 'proof = "an exact duplicate of the line above"\n', encoding="utf-8")
    assert docstool_json(repo, "plan", "approve", "--mappings", "--by", "Owner")[0] == 0
    assert docstool_json(repo, "plan", "verify")[0] == 0


def test_rewrites_and_promotion_respect_fence_length_and_character() -> None:
    module = load_module("docstool_fences", DOCSTOOL)
    lines = ["````md", "```", "# inside", "[x](a.md)", "```", "````", "~~~", "```", "# tilde inside", "~~~", "## real"]
    assert module._promote(lines, 1) == [*lines[:-1], "# real"]
    text = "\n".join(lines) + "\n[y](a.md)\n"
    rewritten = module._rewrite_links(text, "docs", "docs", "docs/x.md", "docs/x.md", {"docs/a.md": "docs/b.md"}, {})
    assert "[x](a.md)" in rewritten
    assert "[y](b.md)" in rewritten


def test_text_dry_run_lists_operations_and_verify_names_the_unchecked_urls(tmp_path: Path) -> None:
    repo = messy(tmp_path)
    result = run_script(DOCSTOOL, "plan", "apply", "--root", str(repo))
    assert result.returncode == 0, result.stderr
    assert "Operations (" in result.stdout
    assert "docs/guide/release.md" in result.stdout
    assert "Redirects added (" in result.stdout
    _, report = docstool_json(repo, "plan", "verify")
    row = next(r for r in report["coverage"] if r["input"] == "url_baseline")
    assert row["state"] == "partial"
    assert "--urls" in row["reason"]


def test_blocks_baseline_creates_its_directory(tmp_path: Path) -> None:
    repo = make_repo("messy-docs", tmp_path)
    target = repo / "docs" / "internal" / "restructure" / "blocks.json"
    assert not target.parent.exists()
    assert docstool_json(repo, "inventory", "--blocks", str(target))[0] in (0, 1)
    assert target.is_file()


def test_links_outside_the_docs_are_rewritten_only_when_declared(tmp_path: Path) -> None:
    repo = make_repo("messy-docs", tmp_path)
    write_plan(repo, MESSY_PLAN, [s for s in MESSY_SOURCES if s != "RELEASING.md"])
    code, report = docstool_json(repo, "plan", "validate")
    assert code == 1
    inbound = [f for f in report["findings"] if f["check"] == "plan-inbound"]
    assert [(f["file"], f["line"]) for f in inbound] == [("RELEASING.md", 3)]
    assert docstool_json(repo, "plan", "apply")[0] == 1  # refused: validate fails
    # declared: bound to the approval, so editing it afterwards makes the plan stale
    write_plan(repo, MESSY_PLAN, MESSY_SOURCES)
    assert docstool_json(repo, "plan", "validate")[0] == 0
    releasing = repo / "RELEASING.md"
    releasing.write_text(releasing.read_text(encoding="utf-8") + "\nmore\n", encoding="utf-8")
    code, report = docstool_json(repo, "plan", "validate")
    assert ("plan-stale", "RELEASING.md") in {(f["check"], f["file"]) for f in report["findings"]}


def reference_repo(tmp_path: Path) -> tuple[Path, str]:
    """A plan with a [[reference]] edit outside the docs, applied; returns the repo and the block's hash."""
    repo = make_repo("clean", tmp_path)
    (repo / "NOTES.md").write_text("# Notes\n\nRead old/path before you start.\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "notes")
    write_plan(
        repo,
        {"keep": [{"paths": ["docs/"]}], "reference": [{"file": "NOTES.md", "line": 3, "old": "old/path", "new": "new/path"}]},
        ["NOTES.md"],
    )
    approve(repo)
    assert docstool_json(repo, "plan", "apply", "--write")[0] == 0
    blocks = json.loads((repo / ART / "blocks.json").read_text(encoding="utf-8"))["blocks"]
    return repo, next(b["hash"] for b in blocks if b["file"] == "NOTES.md" and "old/path" in b["text"])


def test_a_reviewed_mapping_covers_a_block_with_a_reference_edit(tmp_path: Path) -> None:
    repo, digest = reference_repo(tmp_path)
    (repo / "NOTES.md").write_text("# Notes\n\nStart by reading new/path.\n", encoding="utf-8")
    (repo / ART / "mappings.toml").write_text(
        f'[[rewritten]]\nid = "m1"\nblocks = ["{digest}"]\nto = "NOTES.md"\nheading = "Notes"\n', encoding="utf-8"
    )
    assert docstool_json(repo, "plan", "approve", "--mappings", "--by", "Owner")[0] == 0
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 0, report["findings"]
    (repo / ART / "review-receipts.json").write_text('{"receipts": []}', encoding="utf-8")
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 1
    assert {"block-unaccounted", "mapping-unreviewed"} <= {f["check"] for f in report["findings"]}


def split_repo(tmp_path: Path, **extra: Any) -> Path:
    repo = make_repo("clean", tmp_path)
    (repo / "docs" / "mixed.md").write_text("# Mixed\n\nIntro.\n\n## Old notes\n\nHistory text.\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "mixed")
    split = {"from": "docs/mixed.md", "heading": "Old notes", "to": "docs/internal/history/old-notes.md", **extra}
    write_plan(repo, {"keep": [{"paths": ["docs/"]}], "split": [split]}, ["docs/mixed.md"])
    return repo


def test_a_split_can_write_a_status_line(tmp_path: Path) -> None:
    repo = split_repo(tmp_path, status="Historical notes, superseded by the guide.")
    approve(repo)
    code, report = docstool_json(repo, "plan", "apply", "--write")
    assert code == 0, report["findings"]
    moved = (repo / "docs/internal/history/old-notes.md").read_text(encoding="utf-8")
    assert moved == "# Old notes\n\n> **Status:** Historical notes, superseded by the guide.\n\nHistory text.\n"
    assert "Status" not in (repo / "docs/mixed.md").read_text(encoding="utf-8")
    code, report = docstool_json(repo, "plan", "verify")
    assert not {"block-unaccounted"} & {f["check"] for f in report["findings"]}


def test_a_split_without_status_writes_none(tmp_path: Path) -> None:
    repo = split_repo(tmp_path)
    approve(repo)
    assert docstool_json(repo, "plan", "apply", "--write")[0] == 0
    assert "Status" not in (repo / "docs/internal/history/old-notes.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("status", ["", "   ", 3])
def test_a_split_refuses_a_blank_or_non_string_status(tmp_path: Path, status: Any) -> None:
    repo = split_repo(tmp_path, status=status)
    code, report = docstool_json(repo, "plan", "validate")
    assert code == 1
    assert any(f["check"] == "plan-entry" and "status" in f["message"] for f in report["findings"])


@pytest.mark.parametrize(
    ("section", "expected"),
    [
        ("## Old notes\nHistory text.\n", "# Old notes\n\n> **Status:** Old.\n\nHistory text.\n"),
        ("Old notes\n---\n\n```sh\n# install deps\n```\n", "Old notes\n---\n\n> **Status:** Old.\n\n```sh\n# install deps\n```\n"),
        ("Old notes\n---\n\nHistory text.\n", "Old notes\n---\n\n> **Status:** Old.\n\nHistory text.\n"),
        (" ## Old notes\nHistory text.\n", " ## Old notes\n\n> **Status:** Old.\n\nHistory text.\n"),
    ],
)
def test_a_split_status_sits_under_the_real_title(tmp_path: Path, section: str, expected: str) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / "docs" / "mixed.md").write_text(f"# Mixed\n\nIntro.\n\n{section}", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "mixed")
    split = {"from": "docs/mixed.md", "heading": "Old notes", "to": "docs/internal/history/old-notes.md", "status": "Old."}
    write_plan(repo, {"keep": [{"paths": ["docs/"]}], "split": [split]}, ["docs/mixed.md"])
    approve(repo)
    code, report = docstool_json(repo, "plan", "apply", "--write")
    assert code == 0, report["findings"]
    assert (repo / "docs/internal/history/old-notes.md").read_text(encoding="utf-8") == expected


def test_an_archive_status_skips_a_fenced_comment_and_front_matter() -> None:
    module = load_module("docstool_status", DOCSTOOL)
    text = "---\ntitle: x\n# yaml comment\n---\n\nIntro.\n\n```sh\n# not a title\n```\n"
    assert module._status_line(text, "Old.") == "---\ntitle: x\n# yaml comment\n---\n> **Status:** Old.\n\n\nIntro.\n\n```sh\n# not a title\n```\n"
    assert module._status_line("Title\n===\nBody.\n", "Old.") == "Title\n===\n\n> **Status:** Old.\n\nBody.\n"


def no_site_repo(tmp_path: Path) -> Path:
    """A repository with no site config, a block baseline and a source URL baseline."""
    repo = make_repo("clean", tmp_path)
    (repo / "zensical.toml").unlink()
    (repo / "docs" / "old.md").write_text("# Old\n\nIntro text.\n\n## Details\n\nBody text.\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "no site")
    write_plan(repo, {"keep": [{"paths": ["docs/"]}]})
    docstool_json(repo, "check", "--save-baseline", f"{ART}/urls.json")
    assert json.loads((repo / ART / "urls.json").read_text(encoding="utf-8"))["routes"] == {}
    return repo


def verify_urls(repo: Path) -> tuple[int, dict[str, Any]]:
    return docstool_json(repo, "plan", "verify", "--urls", f"{ART}/urls.json")


def rows(report: dict[str, Any]) -> dict[str, str]:
    return {r["input"]: r["state"] for r in report["coverage"]}


def test_no_site_verify_checks_github_urls_not_site_routes(tmp_path: Path) -> None:
    repo = no_site_repo(tmp_path)
    code, report = verify_urls(repo)
    assert code == 0, report["findings"]
    assert rows(report)["url_baseline"] == "not_applicable"
    assert rows(report)["github_urls"] == "complete"


def test_no_site_verify_without_urls_says_github_is_unchecked(tmp_path: Path) -> None:
    repo = no_site_repo(tmp_path)
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 3
    assert rows(report)["github_urls"] == "partial"


@pytest.mark.parametrize(
    "change",
    [{"routes": None}, {"routes": []}, {"routes": {"a/": {"type": "page", "ids": []}}}, {"kind": "built"}],
)
def test_no_site_verify_refuses_any_other_baseline(tmp_path: Path, change: dict[str, Any]) -> None:
    repo = no_site_repo(tmp_path)
    path = repo / ART / "urls.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(change)
    path.write_text(json.dumps(data), encoding="utf-8")
    assert docstool_code(repo, "plan", "verify", "--urls", f"{ART}/urls.json") == 2


def test_no_site_verify_refuses_a_baseline_with_no_routes_key(tmp_path: Path) -> None:
    repo = no_site_repo(tmp_path)
    path = repo / ART / "urls.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["routes"]
    path.write_text(json.dumps(data), encoding="utf-8")
    assert docstool_code(repo, "plan", "verify", "--urls", f"{ART}/urls.json") == 2


@pytest.mark.parametrize("built", [False, True])
@pytest.mark.parametrize("github", [None, [], {"docs/old.md": "details"}, {"docs/old.md": [1]}])
def test_a_malformed_github_table_is_refused_with_or_without_built(tmp_path: Path, built: bool, github: Any) -> None:
    repo = no_site_repo(tmp_path)
    path = repo / ART / "urls.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["github"] = github
    path.write_text(json.dumps(data), encoding="utf-8")
    extra = ["--built", str(tmp_path / "unused")] if built else []
    result = run_script(DOCSTOOL, "plan", "verify", "--urls", f"{ART}/urls.json", *extra, "--root", str(repo), "--format", "json")
    assert result.returncode == 2
    assert "github table" in result.stderr


def test_a_site_added_later_still_compares_the_github_urls(tmp_path: Path) -> None:
    repo = no_site_repo(tmp_path)
    git(repo, "checkout", "-q", "HEAD~1", "--", "zensical.toml")
    page = repo / "docs" / "old.md"
    page.write_text(page.read_text(encoding="utf-8").replace("## Details", "## More"), encoding="utf-8")
    prebuilt(repo, {"index.html": "<h1 id='home'>Home</h1>"})
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "site")
    out = tmp_path / "site"
    code, built_report = build(repo, out)
    assert code == 0, built_report
    code, report = docstool_json(repo, "plan", "verify", "--urls", f"{ART}/urls.json", "--built", str(out))
    assert code == 3  # a source baseline leaves url_baseline partial
    assert rows(report)["url_baseline"] == "partial"
    assert rows(report)["github_urls"] == "complete"
    assert "github-url-lost" in {f["check"] for f in report["findings"]}


def test_a_page_loss_entry_does_not_excuse_anchors_of_a_surviving_page(tmp_path: Path) -> None:
    repo = no_site_repo(tmp_path)
    page = repo / "docs" / "old.md"
    page.write_text(page.read_text(encoding="utf-8").replace("## Details", "## More"), encoding="utf-8")
    entry = '[[github_loss]]\nid = "g1"\npath = "docs/old.md"\npage = true\nreason = "owner decision"\n'
    (repo / ART / "mappings.toml").write_text(entry, encoding="utf-8")
    assert docstool_json(repo, "plan", "approve", "--mappings", "--by", "Owner")[0] == 0
    code, report = verify_urls(repo)
    assert code == 1
    assert "github-url-lost" in {f["check"] for f in report["findings"]}


def test_a_page_loss_entry_accepts_a_missing_page(tmp_path: Path) -> None:
    repo = no_site_repo(tmp_path)
    old = repo / "docs" / "old.md"
    (repo / "docs" / "new.md").write_text(old.read_text(encoding="utf-8"), encoding="utf-8")
    old.unlink()
    entry = '[[github_loss]]\nid = "g1"\npath = "docs/old.md"\npage = true\nreason = "owner moved it"\n'
    (repo / ART / "mappings.toml").write_text(entry, encoding="utf-8")
    assert docstool_json(repo, "plan", "approve", "--mappings", "--by", "Owner")[0] == 0
    code, report = verify_urls(repo)
    assert code == 0, report["findings"]


def test_a_renamed_github_anchor_needs_a_reviewed_loss(tmp_path: Path) -> None:
    repo = no_site_repo(tmp_path)
    page = repo / "docs" / "old.md"
    page.write_text(page.read_text(encoding="utf-8").replace("## Details", "## More"), encoding="utf-8")
    code, report = verify_urls(repo)
    assert code == 1
    assert [f["check"] for f in report["findings"]] == ["github-url-lost"]
    mappings = repo / ART / "mappings.toml"
    entry = '[[github_loss]]\nid = "g1"\npath = "docs/old.md"\nanchors = ["details"]\nreason = "owner renamed it"\n'
    mappings.write_text(entry, encoding="utf-8")
    assert verify_urls(repo)[0] == 1  # not reviewed yet
    assert docstool_json(repo, "plan", "approve", "--mappings", "--by", "Owner")[0] == 0
    code, report = verify_urls(repo)
    assert code == 0, report["findings"]
    mappings.write_text(entry.replace("owner renamed it", "changed"), encoding="utf-8")
    assert "receipt-invalid" in {f["check"] for f in verify_urls(repo)[1]["findings"]}


@pytest.mark.parametrize("stub", [False, True])
def test_a_moved_page_loses_its_github_url_even_with_a_stub(tmp_path: Path, stub: bool) -> None:
    repo = no_site_repo(tmp_path)
    old = repo / "docs" / "old.md"
    (repo / "docs" / "new.md").write_text(old.read_text(encoding="utf-8"), encoding="utf-8")
    if stub:
        old.write_text("# Old\n\nThis page moved to [New](new.md).\n", encoding="utf-8")
    else:
        old.unlink()
    code, report = verify_urls(repo)
    assert code == 1
    lost = [f for f in report["findings"] if f["check"] == "github-url-lost"]
    assert len(lost) == 1
    assert ("#details" in lost[0]["message"]) is stub


@pytest.mark.parametrize(
    "entry",
    [
        'path = "docs/old.md"\nanchors = ["details"]\nreason = "  "\n',
        'path = "docs/old.md"\nreason = "x"\n',
        'anchors = ["details"]\nreason = "x"\n',
        'path = "docs/old.md"\npage = "yes"\nreason = "x"\n',
    ],
)
def test_a_malformed_github_loss_cannot_be_approved(tmp_path: Path, entry: str) -> None:
    repo = no_site_repo(tmp_path)
    (repo / ART / "mappings.toml").write_text(f'[[github_loss]]\nid = "g1"\n{entry}', encoding="utf-8")
    code, report = docstool_json(repo, "plan", "approve", "--mappings", "--by", "Owner")
    assert code == 1
    assert "mapping-invalid" in {f["check"] for f in report["findings"]}


def test_a_github_loss_cannot_excuse_content(tmp_path: Path) -> None:
    repo = no_site_repo(tmp_path)
    blocks = json.loads((repo / ART / "blocks.json").read_text(encoding="utf-8"))["blocks"]
    digest = next(b["hash"] for b in blocks if b["text"] == "Body text.")
    entry = f'[[github_loss]]\nid = "g1"\nblocks = ["{digest}"]\npath = "docs/old.md"\npage = true\nreason = "x"\n'
    (repo / ART / "mappings.toml").write_text(entry, encoding="utf-8")
    code, report = docstool_json(repo, "plan", "approve", "--mappings", "--by", "Owner")
    assert code == 1
    assert "mapping-invalid" in {f["check"] for f in report["findings"]}


def label_repo(tmp_path: Path, page: str, extra: dict[str, list[dict[str, Any]]] | None = None) -> Path:
    repo = make_repo("clean", tmp_path)
    (repo / "docs" / "old.md").write_text("# Old\n\nOld body.\n", encoding="utf-8")
    (repo / "docs" / "page.md").write_text(page, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "labels")
    entries: dict[str, list[dict[str, Any]]] = {
        "keep": [{"paths": ["docs/"]}],
        "move": [{"from": "docs/old.md", "to": "docs/guide/new.md"}],
        **(extra or {}),
    }
    write_plan(repo, entries, ["docs/old.md", "docs/page.md"])
    approve(repo)
    code, report = docstool_json(repo, "plan", "apply", "--write")
    assert code == 0, report["findings"]
    return repo


def test_a_label_that_spells_the_old_path_moves_with_the_link(tmp_path: Path) -> None:
    page = "# Page\n\nSee [`docs/old.md`](old.md), [old.md](old.md) and [the guide](old.md).\n"
    repo = label_repo(tmp_path, page)
    text = (repo / "docs" / "page.md").read_text(encoding="utf-8")
    assert "[`docs/guide/new.md`](guide/new.md), [guide/new.md](guide/new.md) and [the guide](guide/new.md)" in text
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 0, report["findings"]


@pytest.mark.parametrize(
    "line",
    ["![old.md](old.md)", "[docs/old.md and more](old.md)"],
)
def test_other_labels_stay(tmp_path: Path, line: str) -> None:
    repo = label_repo(tmp_path, f"# Page\n\n{line}\n")
    text = (repo / "docs" / "page.md").read_text(encoding="utf-8")
    assert "guide/new.md" not in text.split("](")[0]


def test_labels_in_code_stay(monkeypatch: pytest.MonkeyPatch) -> None:
    # validate refuses a real plan whose docs quote a moved path in code, so this calls the rewrite itself
    module = load_module("docstool_labels", DOCSTOOL)
    monkeypatch.setattr(module, "_link_rewritable", lambda _context, _rel: True)
    context = SimpleNamespace(plan=module.Plan("plan.toml", "", {}, "."), site=module.Site())
    moves = {"docs/old.md": "docs/guide/new.md"}
    for text in ("`[old.md](old.md)` in code\n", "```md\n[old.md](old.md)\n```\n"):
        assert module._planned_lines(context, "docs/page.md", text, moves) == text
    assert module._planned_lines(context, "docs/page.md", "[old.md](old.md)\n", moves) == "[guide/new.md](old.md)\n"


def test_a_heading_label_keeps_its_anchor_and_context(tmp_path: Path) -> None:
    page = "# Page\n\n## [old.md](old.md)\n\nNever do this here.\n\nSee [page](page.md#oldmd).\n"
    repo = label_repo(tmp_path, page)
    text = (repo / "docs" / "page.md").read_text(encoding="utf-8")
    assert "## [old.md](guide/new.md)" in text
    assert "page.md#oldmd" in text or "#oldmd" in text
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 0, report["findings"]


def test_the_dry_run_names_heading_labels_it_leaves(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / "docs" / "old.md").write_text("# Old\n\nOld body.\n", encoding="utf-8")
    (repo / "docs" / "page.md").write_text("# Page\n\n## [old.md](old.md)\n\nText.\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "labels")
    write_plan(repo, {"keep": [{"paths": ["docs/"]}], "move": [{"from": "docs/old.md", "to": "docs/guide/new.md"}]}, ["docs/old.md", "docs/page.md"])
    result = run_script(DOCSTOOL, "plan", "apply", "--root", str(repo))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Link labels that spell an old path, left for you (1):" in result.stdout
    assert "docs/page.md:3 (heading" in result.stdout


def test_a_reference_edit_in_a_multiline_block_replaces_its_own_line(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / "NOTES.md").write_text("# Notes\n\nThe old/path stays here,\nand the old/path moves.\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "notes")
    write_plan(
        repo, {"keep": [{"paths": ["docs/"]}], "reference": [{"file": "NOTES.md", "line": 4, "old": "old/path", "new": "new/path"}]}, ["NOTES.md"]
    )
    approve(repo)
    assert docstool_json(repo, "plan", "apply", "--write")[0] == 0
    assert (repo / "NOTES.md").read_text(encoding="utf-8") == "# Notes\n\nThe old/path stays here,\nand the new/path moves.\n"
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 0, report["findings"]


@pytest.mark.parametrize("delete_second", [False, True])
def test_an_edit_that_splits_a_block_has_no_expected_hash(tmp_path: Path, delete_second: bool) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / "NOTES.md").write_text("# Notes\n\nFirst half. SPLIT Second half.\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "notes")
    write_plan(repo, {"keep": [{"paths": ["docs/"]}], "reference": [{"file": "NOTES.md", "line": 3, "old": " SPLIT ", "new": "\n\n"}]}, ["NOTES.md"])
    approve(repo)
    assert docstool_json(repo, "plan", "apply", "--write")[0] == 0
    if delete_second:
        (repo / "NOTES.md").write_text("# Notes\n\nFirst half.\n", encoding="utf-8")
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 1
    assert "block-unaccounted" in {f["check"] for f in report["findings"]}


def test_a_label_follows_a_fragment_into_a_split_section(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / "docs" / "old.md").write_text("# Old\n\nOld body.\n\n## Part\n\nPart body.\n", encoding="utf-8")
    (repo / "docs" / "page.md").write_text("# Page\n\n[docs/old.md](old.md#part), [old.md](old.md#part), [old.md](old.md)\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "labels")
    entries: dict[str, list[dict[str, Any]]] = {
        "keep": [{"paths": ["docs/"]}],
        "move": [{"from": "docs/old.md", "to": "docs/guide/new.md"}],
        "split": [{"from": "docs/old.md", "heading": "Part", "to": "docs/part.md"}],
    }
    write_plan(repo, entries, ["docs/old.md", "docs/page.md"])
    approve(repo)
    code, report = docstool_json(repo, "plan", "apply", "--write")
    assert code == 0, report["findings"]
    text = (repo / "docs" / "page.md").read_text(encoding="utf-8")
    assert "[docs/part.md](part.md#part), [part.md](part.md#part), [guide/new.md](guide/new.md)" in text
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 0, report["findings"]


def test_a_heading_label_after_a_multiline_reference_edit_stays(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / "docs" / "old.md").write_text("# Old\n\nOld body.\n", encoding="utf-8")
    (repo / "NOTES.md").write_text("# Notes\n\nFirst. SPLIT Second.\n\n## [docs/old.md](docs/old.md)\n\nBody.\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "notes")
    entries: dict[str, list[dict[str, Any]]] = {
        "keep": [{"paths": ["docs/"]}],
        "move": [{"from": "docs/old.md", "to": "docs/guide/new.md"}],
        "reference": [{"file": "NOTES.md", "line": 3, "old": " SPLIT ", "new": "\n\n"}],
    }
    write_plan(repo, entries, ["docs/old.md", "NOTES.md"])
    result = run_script(DOCSTOOL, "plan", "apply", "--root", str(repo))
    assert "NOTES.md:7 (heading" in result.stdout, result.stdout
    approve(repo)
    assert docstool_json(repo, "plan", "apply", "--write")[0] == 0
    assert "## [docs/old.md](docs/guide/new.md)" in (repo / "NOTES.md").read_text(encoding="utf-8")


def test_multiline_setext_and_reference_style_labels_are_held(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module("docstool_held", DOCSTOOL)
    monkeypatch.setattr(module, "_link_rewritable", lambda _context, _rel: True)
    context = SimpleNamespace(plan=module.Plan("plan.toml", "", {}, "."), site=module.Site())
    moves = {"docs/old.md": "docs/guide/new.md"}
    held: list[str] = []
    setext = "Intro\n[old.md](old.md)\nmore\n---\n"
    assert module._planned_lines(context, "docs/page.md", setext, moves, held) == setext
    assert held == ["docs/page.md:2 (heading: the label sets its anchor)"]
    held.clear()
    reference = "See [old.md][ref].\n\n[ref]: old.md\n"
    assert module._planned_lines(context, "docs/page.md", reference, moves, held) == reference
    assert held == ["docs/page.md:1 (reference-style link)"]


def test_a_moved_page_with_a_label_in_a_split_section_uses_the_new_directory(tmp_path: Path) -> None:
    page = "# Page\n\nIntro.\n\n## Part\n\nSee [old.md](old.md).\n"
    repo = label_repo(tmp_path, page, {"split": [{"from": "docs/page.md", "heading": "Part", "to": "docs/archive/part.md"}]})
    assert "[../guide/new.md](../guide/new.md)" in (repo / "docs" / "archive" / "part.md").read_text(encoding="utf-8")
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 0, report["findings"]


def scaffold(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run_script(DOCSTOOL, "plan", "mappings", "--root", str(repo), *args)


def repeated_repo(tmp_path: Path) -> Path:
    repo = make_repo("clean", tmp_path)
    (repo / "docs" / "same.md").write_text("# Same\n\nSame text.\n\nMiddle.\n\nSame text.\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "same")
    write_plan(repo, {"keep": [{"paths": ["docs/"]}]})
    return repo


def test_block_unaccounted_names_the_hash(tmp_path: Path) -> None:
    repo = repeated_repo(tmp_path)
    blocks = json.loads((repo / ART / "blocks.json").read_text(encoding="utf-8"))["blocks"]
    digest = next(b["hash"] for b in blocks if b["text"] == "Middle.")
    (repo / "docs" / "same.md").write_text("# Same\n\nSame text.\n\nSame text.\n", encoding="utf-8")
    _, report = docstool_json(repo, "plan", "verify")
    finding = next(f for f in report["findings"] if f["check"] == "block-unaccounted")
    assert f"block hash: {digest}" in finding["evidence"]


def test_the_default_scaffold_output_is_toml_and_cannot_be_approved_unfilled(tmp_path: Path) -> None:
    repo = repeated_repo(tmp_path)
    (repo / "docs" / "same.md").write_text("# Same\n\nSame text.\n\nSame text.\n", encoding="utf-8")
    result = scaffold(repo)
    assert result.returncode == 0, result.stderr
    data = tomllib.loads(result.stdout)
    assert [e["to"] for e in data["rewritten"]] == [""]
    assert not result.stdout.startswith("docstool")
    (repo / ART / "mappings.toml").write_text(result.stdout, encoding="utf-8")
    code, report = docstool_json(repo, "plan", "approve", "--mappings", "--by", "Owner")
    assert code == 1
    assert "mapping-invalid" in {f["check"] for f in report["findings"]}
    assert not (repo / ART / "review-receipts.json").exists()


def test_the_scaffold_keeps_a_second_missing_copy_of_a_mapped_hash(tmp_path: Path) -> None:
    repo = repeated_repo(tmp_path)
    blocks = json.loads((repo / ART / "blocks.json").read_text(encoding="utf-8"))["blocks"]
    digest = next(b["hash"] for b in blocks if b["text"] == "Same text.")
    (repo / "docs" / "same.md").write_text("# Same\n\nMiddle.\n", encoding="utf-8")
    assert [e["blocks"] for e in tomllib.loads(scaffold(repo).stdout)["rewritten"]] == [[digest], [digest]]
    (repo / ART / "mappings.toml").write_text(f'[[rewritten]]\nid = "m1"\nblocks = ["{digest}"]\nto = "docs/same.md"\n', encoding="utf-8")
    entries = tomllib.loads(scaffold(repo).stdout)["rewritten"]
    assert [e["blocks"] for e in entries] == [[digest]]
    assert entries[0]["id"] != "m1"


@pytest.mark.parametrize("damage", [lambda b: b.append(3), lambda b: b[0].pop("hash"), lambda b: b[0].update(line="x")])
def test_a_damaged_baseline_gives_no_scaffold(tmp_path: Path, damage: Callable[[list[Any]], None]) -> None:
    repo = repeated_repo(tmp_path)
    path = repo / ART / "blocks.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    damage(data["blocks"])
    path.write_text(json.dumps(data), encoding="utf-8")
    result = scaffold(repo)
    assert result.returncode == 3
    assert result.stdout == ""
    assert "conservation_baseline" in result.stderr
    assert docstool_code(repo, "plan", "verify") == 3


@pytest.mark.parametrize(
    "content",
    [
        b"rewritten = [1]\n",
        b'[[rewritten]]\nid = "m1"\nblocks = 1\n',
        b'[[rewritten]]\nid = "m1"\nblocks = "abc"\n',
        b'[[rewritten]]\nid = "m1"\nblocks = [["a"]]\n',
        b"# \xff not utf-8\n",
    ],
)
def test_malformed_mappings_are_refused(tmp_path: Path, content: bytes) -> None:
    repo = repeated_repo(tmp_path)
    (repo / ART / "mappings.toml").write_bytes(content)
    assert scaffold(repo).returncode == 2
    assert docstool_code(repo, "plan", "verify") == 2


@pytest.mark.parametrize("name", ["plan.toml", "blocks.json", "mappings.toml", "review-receipts.json", "new.toml"])
def test_the_scaffold_never_writes_a_file(tmp_path: Path, name: str) -> None:
    repo = repeated_repo(tmp_path)
    (repo / ART / "mappings.toml").write_text("", encoding="utf-8")
    (repo / ART / "review-receipts.json").write_text('{"receipts": []}', encoding="utf-8")
    before = {p.name: p.read_bytes() for p in (repo / ART).iterdir()}
    result = scaffold(repo, "--out", str(repo / ART / name))
    assert result.returncode == 2
    assert result.stdout == ""
    assert {p.name: p.read_bytes() for p in (repo / ART).iterdir()} == before


def test_the_scaffold_as_json(tmp_path: Path) -> None:
    repo = repeated_repo(tmp_path)
    (repo / "docs" / "same.md").write_text("# Same\n\nSame text.\n\nSame text.\n", encoding="utf-8")
    code, report = docstool_json(repo, "plan", "mappings")
    assert code == 0
    assert report["findings"] == []
    assert len(tomllib.loads(report["data"]["mappings_toml"])["rewritten"]) == 1


def test_the_scaffold_lists_github_losses_with_urls(tmp_path: Path) -> None:
    repo = no_site_repo(tmp_path)
    page = repo / "docs" / "old.md"
    page.write_text(page.read_text(encoding="utf-8").replace("## Details", "## More"), encoding="utf-8")
    assert "GitHub URLs were not compared" in scaffold(repo).stdout
    result = scaffold(repo, "--urls", f"{ART}/urls.json")
    assert result.returncode == 0, result.stderr
    losses = tomllib.loads(result.stdout)["github_loss"]
    assert [(e["path"], e["anchors"], e["reason"]) for e in losses] == [("docs/old.md", ["details"], "")]
    (repo / ART / "mappings.toml").write_text(result.stdout, encoding="utf-8")
    assert docstool_json(repo, "plan", "approve", "--mappings", "--by", "Owner")[0] == 1
    assert "github_loss" not in tomllib.loads(scaffold(repo, "--urls", f"{ART}/urls.json").stdout)


def test_a_scaffold_comment_stays_on_one_line(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / "docs" / "code.md").write_text('# Code\n\n```sh\nfirst\n[[rewritten]]\nid = "x"\n```\n', encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "code")
    write_plan(repo, {"keep": [{"paths": ["docs/"]}]})
    (repo / "docs" / "code.md").write_text("# Code\n", encoding="utf-8")
    entries = tomllib.loads(scaffold(repo).stdout)["rewritten"]
    assert len(entries) == 1
    assert entries[0]["id"] == "m1"


def wrap_repo(tmp_path: Path, limit: int = 50, page: bytes | None = None) -> Path:
    repo = make_repo("clean", tmp_path)
    (repo / ".markdownlint.yaml").write_text(f"MD013:\n  line_length: {limit}\n", encoding="utf-8")
    (repo / "docs" / "old.md").write_text("# Old\n\nBody.\n", encoding="utf-8")
    long_before = "An old line that was already much longer than the limit, before this plan."
    (repo / "docs" / "page.md").write_text(
        f"# Page\n\nSee the [old page](old.md) for it all.\n\n[old page](old.md) is here and also more.\n\n{long_before}\n\n[a](old.md)\n",
        encoding="utf-8",
    )
    if page is not None:
        (repo / "docs" / "page.md").write_bytes(page)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "wrap")
    target = "docs/guide/some/deeply/nested/place/new.md"
    write_plan(repo, {"keep": [{"paths": ["docs/"]}], "move": [{"from": "docs/old.md", "to": target}]}, ["docs/old.md", "docs/page.md"])
    return repo


def test_the_default_dry_run_shows_wrap_warnings(tmp_path: Path) -> None:
    repo = wrap_repo(tmp_path)
    result = run_script(DOCSTOOL, "plan", "apply", "--root", str(repo))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Wrap warnings: apply pushes 2 lines past the markdownlint line_length (MD013 defaults" in result.stdout
    assert "docs/page.md:3 (" in result.stdout
    assert "docs/page.md:5 (" in result.stdout
    assert "docs/page.md:7 (" not in result.stdout
    assert "docs/page.md:9 (" not in result.stdout
    capped = run_script(DOCSTOOL, "plan", "apply", "--root", str(repo), "--max", "1")
    assert "... 1 more (raise --max or use --format json)" in capped.stdout
    code, report = docstool_json(repo, "plan", "apply")
    assert code == 0
    assert len(report["data"]["wrap_warnings"]) == 2


def wrap_lines(repo: Path) -> list[int]:
    code, report = docstool_json(repo, "plan", "apply")
    assert code == 0, report["findings"]
    return [w["line"] for w in report["data"].get("wrap_warnings", [])]


def test_wrap_warnings_follow_md013(tmp_path: Path) -> None:
    page = (
        "# Page\n\n"
        "A line already well past the limit before [old page](old.md) and more.\n\n"
        "See the [old page](old.md) for it all.\n\n"
        "Short words then the last token [x](old.md)\n\n"
        "[old page](old.md) [old page](old.md)\n\n"
        "[ref]: old.md\n"
    )
    assert wrap_lines(wrap_repo(tmp_path, page=page.encode())) == [5]


def test_wrap_warnings_read_crlf_files(tmp_path: Path) -> None:
    module = load_module("docstool_wrap", DOCSTOOL)
    (tmp_path / "page.md").write_bytes(b"```sh\r\ncode\r\n```\r\n\r\nSee the [old page](old.md) for it all.\r\n")
    tree = module.VirtualTree(tmp_path)
    tree.write("page.md", b"```sh\r\ncode\r\n```\r\n\r\nSee the [old page](guide/some/deeply/nested/new.md) for it all.\r\n")
    assert [w["line"] for w in module._wrap_warnings(tree, 50, {})] == [5]


def test_no_wrap_warnings_without_a_lint_limit(tmp_path: Path) -> None:
    repo = wrap_repo(tmp_path)
    (repo / ".markdownlint.yaml").unlink()
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "no lint")
    target = "docs/guide/some/deeply/nested/place/new.md"
    (repo / ART / "blocks.json").unlink()
    write_plan(repo, {"keep": [{"paths": ["docs/"]}], "move": [{"from": "docs/old.md", "to": target}]}, ["docs/old.md", "docs/page.md"])
    assert "Wrap warnings" not in run_script(DOCSTOOL, "plan", "apply", "--root", str(repo)).stdout


# --- plan rebase: the same plan on a newer upstream ---------------------------------------------


def remote_pair(tmp_path: Path, extra: dict[str, str] | None = None) -> tuple[Path, Path]:
    """A work repository with docs/flash.md (and extra files), and the bare origin it fetches."""
    repo = make_repo("clean", tmp_path)
    (repo / "docs" / "flash.md").write_text(CONSERVE, encoding="utf-8")
    for rel, text in (extra or {}).items():
        (repo / rel).write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "flash")
    remote = tmp_path / "origin.git"
    git(tmp_path, "clone", "-q", "--bare", str(repo), str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "fetch", "-q", "origin")
    return repo, remote


def push_upstream(tmp_path: Path, remote: Path, change: Callable[[Path], object], reset: bool = False) -> None:
    """Someone else changes the docs upstream; with reset, on a history that drops the last commit."""
    upstream = tmp_path / "upstream"
    if not upstream.exists():
        git(tmp_path, "clone", "-q", str(remote), str(upstream))
    if reset:
        git(upstream, "reset", "-q", "--hard", "HEAD~1")
    change(upstream)
    git(upstream, "add", "-A")
    git(upstream, "commit", "-q", "-m", "upstream edit")
    git(upstream, "push", "-q", "--force", "origin", "main")


def to_upstream(repo: Path) -> None:
    """Drop the local work: the tree becomes origin/main, with the untracked plan artifacts kept."""
    git(repo, "fetch", "-q", "origin")
    git(repo, "switch", "-q", "--detach", "origin/main")


def everything(repo: Path) -> dict[str, str]:
    """Every file under the repository, .git included: a dry run must leave all of them alone."""
    return {p.relative_to(repo).as_posix(): sha(p) for p in sorted(repo.rglob("*")) if p.is_file()}


def rebase(repo: Path, *args: str, onto: str = "origin/main") -> tuple[int, dict[str, Any]]:
    return docstool_json(repo, "plan", "rebase", "--onto", onto, *args)


def refusals(report: dict[str, Any]) -> list[str]:
    return [f["message"] for f in report["findings"] if f["check"] == "plan-rebase"]


def reword_and_add(upstream: Path) -> None:
    path = upstream / "docs" / "flash.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace("Never flash over USB hubs.", "Never flash through a USB hub.")
    text = text.replace("## Other\n", "## Other\n\nCharge the battery to half first.\n")
    path.write_text(text, encoding="utf-8")


def approved_upstream_plan(tmp_path: Path, extra: dict[str, str] | None = None, **plan: Any) -> tuple[Path, Path]:
    """An approved, unapplied plan written on the old base; upstream has since reworded and added."""
    repo, remote = remote_pair(tmp_path, extra)
    write_plan(repo, plan.get("entries", {"keep": [{"paths": ["docs/"]}]}), plan.get("sources"))
    approve(repo)
    push_upstream(tmp_path, remote, reword_and_add)
    to_upstream(repo)
    return repo, remote


def test_rebase_carries_the_plan_onto_upstream_and_protects_what_upstream_added(tmp_path: Path) -> None:
    repo, _ = approved_upstream_plan(tmp_path)
    before = everything(repo)
    code, report = rebase(repo)
    assert code == 0, report["findings"]
    assert everything(repo) == before, "the dry run wrote something"
    assert report["data"]["state"].startswith("dry run")
    [delta] = report["data"]["upstream"]
    assert delta["file"] == "docs/flash.md"
    assert delta["plan_source"] is False  # covered by keep: protected by the baseline, not moved
    assert [r["new"]["text"] for r in delta["reworded"]] == ["Never flash through a USB hub."]
    assert [b["text"] for b in delta["added"]] == ["Charge the battery to half first."]
    assert delta["removed"] == []
    assert report["data"]["decisions"] == "unchanged since the approval"
    assert report["data"]["writes"] == sorted([f"{ART}/blocks.json", f"{ART}/plan.toml"])
    text = run_script(DOCSTOOL, "plan", "rebase", "--onto", "origin/main", "--root", str(repo)).stdout
    assert "docs/flash.md (not in the plan's sources): 1 added, 0 removed, 1 reworded" in text, text
    assert "  + line " in text and "Charge the battery to half first." in text, text
    assert "decisions: unchanged since the approval" in text, text

    code, report = rebase(repo, "--write")
    assert code == 0, report["findings"]
    assert report["data"]["approval"] == "stale"
    meta = tomllib.loads((repo / ART / "plan.toml").read_text(encoding="utf-8"))["meta"]
    assert meta["base_commit"] == head(repo)
    assert meta["sources"][f"{ART}/blocks.json"] == sha(repo / ART / "blocks.json")
    blocks = json.loads((repo / ART / "blocks.json").read_text(encoding="utf-8"))["blocks"]
    assert any(b["text"] == "Charge the battery to half first." for b in blocks)
    assert docstool_json(repo, "plan", "validate")[0] == 0
    approve(repo)
    assert docstool_json(repo, "plan", "apply", "--write")[0] == 0
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 0, report["findings"]
    # A replay of the old restructure that loses the paragraph upstream added is caught.
    edit(repo, "Charge the battery to half first.\n\n", "")
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 1
    assert "block-unaccounted" in {f["check"] for f in report["findings"]}


def _local_branch(repo: Path) -> str:
    git(repo, "branch", "-q", "upstream-copy", "origin/main")
    return "upstream-copy"


def _commit(repo: Path) -> str:
    return head(repo)


def _intermediate_commit(repo: Path) -> str:
    # touches neither the docs layout nor the plan artifacts, and is still not upstream
    (repo / "NOTES.txt").write_text("local\n", encoding="utf-8")
    git(repo, "add", "NOTES.txt")
    git(repo, "commit", "-q", "-m", "local")
    return "origin/main"


def _old_base(repo: Path) -> str:
    git(repo, "switch", "-q", "--detach", "HEAD@{1}")
    return "origin/main"


def _dirty(repo: Path) -> str:
    (repo / "docs" / "guide.md").write_text("# Guide\n\nEdited locally.\n", encoding="utf-8")
    return "origin/main"


def _applied(repo: Path) -> str:
    (repo / ART / "apply-log.json").write_text("{}\n", encoding="utf-8")
    return "origin/main"


@pytest.mark.parametrize(
    ("prepare", "says"),
    [
        (_local_branch, "refs/heads/upstream-copy, not a fetched upstream branch"),
        (_commit, "is a commit, not a fetched upstream branch"),
        (_intermediate_commit, "is not origin/main"),
        (_old_base, "is not origin/main"),
        (_dirty, "docs/guide.md: the working tree is not clean"),
        (_applied, "apply-log.json exists"),
    ],
)
def test_rebase_refuses_and_writes_nothing(tmp_path: Path, prepare: Callable[[Path], str], says: str) -> None:
    repo, _ = approved_upstream_plan(tmp_path)
    onto = prepare(repo)
    before = everything(repo)
    code, report = rebase(repo, "--write", onto=onto)
    assert code == 1
    assert any(says in message for message in refusals(report)), refusals(report)
    assert everything(repo) == before


def test_rebase_refuses_a_base_that_upstream_rewrote_away(tmp_path: Path) -> None:
    repo, remote = remote_pair(tmp_path)
    write_plan(repo, {"keep": [{"paths": ["docs/"]}]})
    push_upstream(tmp_path, remote, lambda upstream: (upstream / "docs" / "new.md").write_text("# New\n", encoding="utf-8"), reset=True)
    to_upstream(repo)
    before = everything(repo)
    code, report = rebase(repo, "--write")
    assert code == 1
    assert any("is not an ancestor of origin/main" in message for message in refusals(report)), refusals(report)
    assert everything(repo) == before


def test_rebase_refuses_a_reference_edit_whose_file_changed_upstream(tmp_path: Path) -> None:
    notes = {"NOTES.md": "# Notes\n\nRead old/path before you start.\n"}
    entries: dict[str, list[dict[str, Any]]] = {
        "keep": [{"paths": ["docs/"]}],
        "reference": [{"file": "NOTES.md", "line": 3, "old": "old/path", "new": "new/path"}],
    }
    repo, remote = remote_pair(tmp_path, notes)
    write_plan(repo, entries, ["NOTES.md"])
    approve(repo)

    def insert(upstream: Path) -> None:
        path = upstream / "NOTES.md"
        path.write_text("<!-- moved -->\n" + path.read_text(encoding="utf-8"), encoding="utf-8")

    push_upstream(tmp_path, remote, insert)
    to_upstream(repo)
    before = everything(repo)
    code, report = rebase(repo, "--write")
    assert code == 1
    [message] = refusals(report)
    assert message.startswith("[[reference]] #1 edits NOTES.md at line 3"), message
    assert everything(repo) == before


def test_rebase_reports_decisions_edited_after_the_approval(tmp_path: Path) -> None:
    repo, _ = approved_upstream_plan(tmp_path)
    plan = repo / ART / "plan.toml"
    plan.write_text(plan.read_text(encoding="utf-8").replace('paths = ["docs/"]', 'paths = ["docs/", "docs/internal/"]'), encoding="utf-8")
    code, report = rebase(repo)
    assert code == 1
    assert report["data"]["decisions"] == "changed since the approval"
    assert report["data"]["decisions_sha256"] != report["data"]["approved_decisions_sha256"]
    assert "plan-decisions" in {f["check"] for f in report["findings"]}
    assert not refusals(report)


def _move_within(upstream: Path) -> None:
    path = upstream / "docs" / "flash.md"
    text = path.read_text(encoding="utf-8").replace("!!! warning\n    Back up the device first.\n\n", "")
    path.write_text(text.replace("## Other\n\n", "## Other\n\n!!! warning\n    Back up the device first.\n\n"), encoding="utf-8")


def _move_across(upstream: Path) -> None:
    path = upstream / "docs" / "flash.md"
    path.write_text(path.read_text(encoding="utf-8").replace("!!! warning\n    Back up the device first.\n\n", ""), encoding="utf-8")
    (upstream / "docs" / "safety.md").write_text("# Safety\n\n!!! warning\n    Back up the device first.\n", encoding="utf-8")


@pytest.mark.parametrize("move", [_move_within, _move_across])
def test_a_warning_upstream_moved_is_protected_where_it_now_is(tmp_path: Path, move: Callable[[Path], None]) -> None:
    repo, remote = remote_pair(tmp_path)
    write_plan(repo, {"keep": [{"paths": ["docs/"]}]})
    approve(repo)
    push_upstream(tmp_path, remote, move)
    to_upstream(repo)
    assert rebase(repo, "--write")[0] == 0
    approve(repo)
    assert docstool_json(repo, "plan", "apply", "--write")[0] == 0
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 0, report["findings"]
    # a re-apply that drops the warning from its new place
    page = repo / "docs" / ("flash.md" if move is _move_within else "safety.md")
    page.write_text(page.read_text(encoding="utf-8").replace("!!! warning\n    Back up the device first.\n", ""), encoding="utf-8")
    code, report = docstool_json(repo, "plan", "verify")
    assert code == 1
    assert "block-unaccounted" in {f["check"] for f in report["findings"]}


def test_rebase_reports_what_upstream_broke_in_the_plan_and_writes_nothing(tmp_path: Path) -> None:
    mixed = {"docs/mixed.md": "# Mixed\n\nIntro.\n\n## Old notes\n\nHistory text.\n"}
    split = {"from": "docs/mixed.md", "heading": "Old notes", "to": "docs/internal/history/old-notes.md", "status": "Superseded."}
    repo, remote = remote_pair(tmp_path, mixed)
    write_plan(repo, {"keep": [{"paths": ["docs/"]}], "split": [split]}, ["docs/mixed.md"])
    approve(repo)

    def rename_heading(upstream: Path) -> None:
        path = upstream / "docs" / "mixed.md"
        path.write_text(path.read_text(encoding="utf-8").replace("## Old notes", "## Earlier notes"), encoding="utf-8")

    push_upstream(tmp_path, remote, rename_heading)
    to_upstream(repo)
    before = everything(repo)
    code, report = rebase(repo, "--write")
    assert code == 1
    assert not refusals(report)
    assert any(f["severity"] == "Blocking" and "Old notes" in f["message"] for f in report["findings"]), report["findings"]
    assert "does not validate" in report["data"]["state"]
    [delta] = report["data"]["upstream"]
    assert delta["plan_source"] is True
    assert everything(repo) == before


def test_rebase_rewrites_the_inventory_the_plan_names(tmp_path: Path) -> None:
    repo, remote = remote_pair(tmp_path)
    inventory = f"{ART}/inventory.json"
    (repo / ART).mkdir(parents=True)
    assert run_script(DOCSTOOL, "inventory", "--root", str(repo), "--format", "json", "--out", str(repo / inventory)).returncode in (0, 1)
    write_plan(repo, {"keep": [{"paths": ["docs/"]}]}, [inventory], {"inventory": inventory})
    approve(repo)
    push_upstream(tmp_path, remote, lambda upstream: (upstream / "docs" / "safety.md").write_text("# Safety\n\nUnplug first.\n", encoding="utf-8"))
    to_upstream(repo)
    assert "docs/safety.md" not in json.loads((repo / inventory).read_text(encoding="utf-8"))["data"]["files"]
    code, report = rebase(repo, "--write")
    assert code == 0, report["findings"]
    assert sorted(report["data"]["writes"]) == sorted([f"{ART}/blocks.json", inventory, f"{ART}/plan.toml"])
    written = (repo / inventory).read_text(encoding="utf-8")
    assert "docs/safety.md" in json.loads(written)["data"]["files"]
    # byte for byte what inventory --format json writes for the same tree
    assert written == run_script(DOCSTOOL, "inventory", "--root", str(repo), "--format", "json").stdout
    meta = tomllib.loads((repo / ART / "plan.toml").read_text(encoding="utf-8"))["meta"]
    assert meta["sources"][inventory] == sha(repo / inventory)
    code, report = docstool_json(repo, "plan", "validate")
    assert code == 0, report["findings"]


def test_rebase_refuses_to_write_a_partial_inventory(tmp_path: Path) -> None:
    repo, remote = remote_pair(tmp_path)
    inventory = f"{ART}/inventory.json"
    (repo / ART).mkdir(parents=True)
    run_script(DOCSTOOL, "inventory", "--root", str(repo), "--format", "json", "--out", str(repo / inventory))
    write_plan(repo, {"keep": [{"paths": ["docs/"]}]}, [inventory], {"inventory": inventory})
    push_upstream(tmp_path, remote, lambda upstream: (upstream / "docs" / "latin1.md").write_bytes(b"# Caf\xe9\n"))
    to_upstream(repo)
    before = everything(repo)
    code, report = rebase(repo, "--write")
    assert code == 3  # the unreadable page leaves the markdown coverage incomplete: never clean
    assert any("is incomplete (" in message and "markdown" in message for message in refusals(report)), refusals(report)
    assert everything(repo) == before


def test_an_unrelated_removal_and_addition_are_not_a_rewording(tmp_path: Path) -> None:
    repo, remote = remote_pair(tmp_path)
    write_plan(repo, {"keep": [{"paths": ["docs/"]}]})

    def replace(upstream: Path) -> None:
        path = upstream / "docs" / "flash.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace("Never flash over USB hubs.", "Firmware images live in the releases page."), encoding="utf-8"
        )

    push_upstream(tmp_path, remote, replace)
    to_upstream(repo)
    code, report = rebase(repo)
    assert code == 0, report["findings"]
    [delta] = report["data"]["upstream"]
    assert delta["reworded"] == []
    assert [b["text"] for b in delta["removed"]] == ["Never flash over USB hubs."]
    assert [b["text"] for b in delta["added"]] == ["Firmware images live in the releases page."]


@pytest.mark.parametrize("command", ["rebase", "approve"])
def test_a_planted_temp_symlink_is_never_written_through(tmp_path: Path, command: str) -> None:
    repo, _ = approved_upstream_plan(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("precious\n", encoding="utf-8")
    if command == "rebase":
        (repo / ART / "blocks.json.tmp").symlink_to(outside)
        code = docstool_code(repo, "plan", "rebase", "--onto", "origin/main", "--write")
    else:
        (repo / ART / "plan.toml.tmp").symlink_to(outside)
        code = docstool_code(repo, "plan", "approve", "--by", "Owner")
    assert code == 2
    assert outside.read_text(encoding="utf-8") == "precious\n"


def test_rebase_needs_onto_and_onto_needs_rebase(tmp_path: Path) -> None:
    repo, _ = approved_upstream_plan(tmp_path)
    assert docstool_code(repo, "plan", "rebase") == 2
    assert docstool_code(repo, "plan", "validate", "--onto", "origin/main") == 2
