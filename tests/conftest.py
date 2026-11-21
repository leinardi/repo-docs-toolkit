"""Shared helpers for the test suite."""

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

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
DOCSTOOL = SKILLS_DIR / "repo-docs" / "scripts" / "docstool.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures"
# Fixed identity and dates, so a fixture's history is the same on every machine.
GIT_ENV = {
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.org",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.org",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def load_module(name: str, path: Path) -> ModuleType:
    """Import a script by path, the way it cannot import itself under python3 -I."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses look the module up in sys.modules while the class body runs.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_script(path: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a script exactly as the skills document it: python3 -I <path> <args>."""
    return subprocess.run([sys.executable, "-I", str(path), *args], capture_output=True, text=True, check=False, cwd=cwd)


def git(repo: Path, *args: str) -> str:
    env = {**os.environ, **GIT_ENV}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=env).stdout


def make_repo(fixture: str, tmp_path: Path) -> Path:
    """Copy a fixture into tmp_path and commit it as a fresh git repository."""
    dest = tmp_path / fixture
    shutil.copytree(FIXTURES / fixture, dest)
    git(dest, "init", "-q", "-b", "main")
    git(dest, "add", "-A")
    git(dest, "commit", "-q", "-m", "fixture")
    return dest


def docstool_json(repo: Path, *args: str) -> tuple[int, dict[str, Any]]:
    """Run docstool with --format json in repo and return (exit code, parsed report)."""
    result = run_script(DOCSTOOL, *args, "--root", str(repo), "--format", "json")
    assert result.stdout, result.stderr
    return result.returncode, json.loads(result.stdout)
