"""One version, two files: the dev pins must not drift apart.

``pytest`` is pinned twice -- in ``requirements-dev.txt``, which is what ``make test`` and CI
install, and in the ``additional_dependencies`` of the mypy hooks in
``.pre-commit-config.yaml``, which is what gives mypy the ``py.typed`` marker it needs to see
``@fixture`` and ``@parametrize`` as typed.

Each Dependabot ecosystem rewrites only its own copy: ``pip`` the requirements file,
``pre-commit`` the hooks' ``additional_dependencies``. Without this check one half could merge
green with mypy type-checking the tests against a different pytest than the one CI runs -- a
silent difference that surfaces later as stub errors nobody can reproduce locally. With it, the
halves must land together, which is why ``.github/dependabot.yml`` puts both ecosystems in one
multi-ecosystem group.

This module is the check; ``make sync-pins`` (``scripts/sync_pins.py``) is the fix. Both read
the files through the same functions, so a green run here means that command has nothing left
to do.
"""

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

import pytest
from conftest import REPO_ROOT, load_module

sync_pins = load_module("sync_pins", REPO_ROOT / "scripts" / "sync_pins.py")
hook_pins, requirement_pins, sync = sync_pins.hook_pins, sync_pins.requirement_pins, sync_pins.sync

REQUIREMENTS = REPO_ROOT / "requirements-dev.txt"
PRE_COMMIT = REPO_ROOT / ".pre-commit-config.yaml"


def test_every_dev_dependency_is_pinned_exactly() -> None:
    """A floating dev dependency makes a CI failure depend on the day it ran."""
    pins = requirement_pins(REQUIREMENTS.read_text(encoding="utf-8"))
    assert pins, "requirements-dev.txt parsed as empty -- the pin regex has rotted, not the file"
    assert "pytest" in pins


def test_the_duplicated_pin_is_still_duplicated() -> None:
    """Guards the parsing.

    Without this, a rename or a reformat that empties one side would leave the drift test with
    nothing to compare, and it would pass by vacuum. If the duplication is genuinely gone --
    no hook installs pytest any more -- delete this module rather than relax it.
    """
    shared = {name for _, name, _ in hook_pins(PRE_COMMIT.read_text(encoding="utf-8"))} & set(
        requirement_pins(REQUIREMENTS.read_text(encoding="utf-8"))
    )
    assert "pytest" in shared, "pytest is no longer pinned in both files; see this test's docstring"


def test_no_hook_disagrees_with_another_hook() -> None:
    """Two hooks pinning the same package to different versions is drift within one file."""
    versions: dict[str, set[str]] = {}
    for _, name, version in hook_pins(PRE_COMMIT.read_text(encoding="utf-8")):
        versions.setdefault(name, set()).add(version)
    for name, pinned in versions.items():
        assert len(pinned) == 1, f"{name} is pinned to {sorted(pinned)} by different hooks in .pre-commit-config.yaml"


def test_no_pin_drifts_between_the_two_files() -> None:
    _, changes = sync(REQUIREMENTS.read_text(encoding="utf-8"), PRE_COMMIT.read_text(encoding="utf-8"))
    assert not changes, (
        ".pre-commit-config.yaml disagrees with requirements-dev.txt: " + "; ".join(changes) + ". Run `make sync-pins` and commit the result."
    )


REQUIREMENTS_SAMPLE = "# a comment\npytest==9.9.9\npytest-xdist==3.8.0\n"

PRE_COMMIT_SAMPLE = """repos:
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.19.0
    hooks:
      - id: mypy
        additional_dependencies:
          # pytest ships py.typed
          - pytest==9.0.2
      - id: mypy
        alias: mypy-json-output
        additional_dependencies:
          - pytest==9.0.2  # trailing comment
  - repo: local
    hooks:
      - id: prettier-yaml
        additional_dependencies: ["prettier@3.7.4"]
"""


def test_sync_rewrites_every_copy_of_a_bumped_pin() -> None:
    updated, changes = sync(REQUIREMENTS_SAMPLE, PRE_COMMIT_SAMPLE)
    assert len(changes) == 2, changes
    assert "pytest==9.0.2" not in updated
    assert updated.count("pytest==9.9.9") == 2


def test_sync_touches_nothing_but_the_version() -> None:
    """Indentation and trailing comments survive: prettier and yamllint both read this file."""
    updated, _ = sync(REQUIREMENTS_SAMPLE, PRE_COMMIT_SAMPLE)
    assert "          - pytest==9.9.9\n" in updated
    assert "          - pytest==9.9.9  # trailing comment\n" in updated
    assert updated.splitlines()[0] == "repos:"
    assert len(updated.splitlines()) == len(PRE_COMMIT_SAMPLE.splitlines())


def test_sync_leaves_alone_what_the_requirements_file_does_not_pin() -> None:
    """An npm pin has no counterpart to sync against, and neither does an unlisted package."""
    updated, changes = sync("pytest==9.0.2\n", PRE_COMMIT_SAMPLE)
    assert not changes
    assert updated == PRE_COMMIT_SAMPLE
    assert 'additional_dependencies: ["prettier@3.7.4"]' in updated


def test_a_requirement_that_is_not_an_exact_pin_is_refused() -> None:
    """Silently skipping it would sync a version this file does not actually name."""
    with pytest.raises(ValueError, match="not an exact pin"):
        requirement_pins("pytest>=9.0.2\n")
