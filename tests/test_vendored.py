"""The vendored docstool.py copies and scripts/sync-vendored.py."""

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

import pytest
from conftest import DOCSTOOL, REPO_ROOT, load_module, run_script

SYNC = REPO_ROOT / "scripts" / "sync-vendored.py"
sync = load_module("sync_vendored", SYNC)


def test_every_skill_that_runs_docstool_has_an_identical_copy() -> None:
    canonical = DOCSTOOL.read_bytes()
    for copy in sync.COPIES:
        path = REPO_ROOT / copy
        assert not path.is_symlink(), f"{copy} is a symlink; claude plugin validate does not follow them"
        assert path.read_bytes() == canonical, f"{copy} differs from {sync.CANONICAL}; run make sync-vendored"


def test_the_copies_cover_every_skill_with_a_scripts_dir() -> None:
    skills_with_docstool = {p.relative_to(REPO_ROOT) for p in REPO_ROOT.glob("skills/*/scripts/docstool.py")}
    assert skills_with_docstool == {sync.CANONICAL, *sync.COPIES}


def test_the_site_copies_match_their_source() -> None:
    for source, copy in sync.SITE_COPIES:
        path = REPO_ROOT / copy
        assert not path.is_symlink(), f"{copy} is a symlink"
        assert path.read_bytes() == (REPO_ROOT / source).read_bytes(), f"{copy} differs from {source}; run make sync-vendored"


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    for source, copy in sync.pairs():
        for rel in (source, copy):
            dest = tmp_path / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / source, dest)
    return tmp_path


def test_check_passes_on_identical_copies(tree: Path) -> None:
    result = run_script(SYNC, "--check", "--root", str(tree))
    assert result.returncode == 0, result.stderr


def test_check_fails_on_an_edited_copy_and_names_it(tree: Path) -> None:
    edited = tree / sync.COPIES[0]
    edited.write_text(edited.read_text(encoding="utf-8") + "# local edit\n", encoding="utf-8")
    result = run_script(SYNC, "--check", "--root", str(tree))
    assert result.returncode == 1
    assert str(sync.COPIES[0]) in result.stderr
    assert str(sync.COPIES[1]) not in result.stderr


def test_check_fails_on_a_missing_copy(tree: Path) -> None:
    (tree / sync.COPIES[1]).unlink()
    assert run_script(SYNC, "--check", "--root", str(tree)).returncode == 1


def test_check_fails_on_a_symlinked_copy(tree: Path) -> None:
    copy = tree / sync.COPIES[0]
    copy.unlink()
    copy.symlink_to(tree / sync.CANONICAL)
    assert run_script(SYNC, "--check", "--root", str(tree)).returncode == 1


def test_sync_rewrites_stale_copies_and_replaces_symlinks(tree: Path) -> None:
    (tree / sync.COPIES[0]).write_text("stale\n", encoding="utf-8")
    link = tree / sync.COPIES[1]
    link.unlink()
    link.symlink_to(tree / sync.CANONICAL)
    result = run_script(SYNC, "--root", str(tree))
    assert result.returncode == 0, result.stderr
    canonical = (tree / sync.CANONICAL).read_bytes()
    for copy in sync.COPIES:
        assert not (tree / copy).is_symlink()
        assert (tree / copy).read_bytes() == canonical
    assert run_script(SYNC, "--check", "--root", str(tree)).returncode == 0


def test_check_fails_on_an_edited_site_copy_and_sync_restores_it(tree: Path) -> None:
    source, copy = sync.SITE_COPIES[0]
    (tree / copy).write_text("/* local edit */\n", encoding="utf-8")
    result = run_script(SYNC, "--check", "--root", str(tree))
    assert result.returncode == 1
    assert str(copy) in result.stderr
    assert run_script(SYNC, "--root", str(tree)).returncode == 0
    assert (tree / copy).read_bytes() == (tree / source).read_bytes()


def test_a_missing_site_source_is_a_usage_error(tree: Path) -> None:
    (tree / sync.SITE_COPIES[0][0]).unlink()
    assert run_script(SYNC, "--check", "--root", str(tree)).returncode == 2


def test_a_missing_canonical_file_is_a_usage_error(tmp_path: Path) -> None:
    assert run_script(SYNC, "--check", "--root", str(tmp_path)).returncode == 2
