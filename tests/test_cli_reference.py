"""docs/reference/docstool.md documents every docstool subcommand, option and choice."""

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

import argparse
import re

import pytest
from conftest import DOCSTOOL, REPO_ROOT, load_module

REFERENCE = REPO_ROOT / "docs" / "reference" / "docstool.md"
docstool = load_module("docstool_cli_reference", DOCSTOOL)

# The options every subcommand shares, documented once under "## Common options".
COMMON = {"--root", "--format", "--out", "--max", "--fail-on"}


def _subcommands() -> dict[str, argparse.ArgumentParser]:
    parser = docstool.build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    raise AssertionError("docstool has no subcommands")


def _sections() -> dict[str, str]:
    text = REFERENCE.read_text(encoding="utf-8")
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts), 2)}


def _documented(action: argparse.Action) -> list[str]:
    """The names a reader looks for: the option strings, or the positional's name."""
    return [s for s in action.option_strings if s != "-h"] or [action.dest]


SUBCOMMANDS = _subcommands()


def test_every_subcommand_has_a_section() -> None:
    missing = sorted(set(SUBCOMMANDS) - set(_sections()))
    assert not missing, f"docs/reference/docstool.md has no section for: {missing}"


def test_the_reference_names_no_subcommand_docstool_lacks() -> None:
    known = set(SUBCOMMANDS) | {"Common options", "Exit codes", "What docstool writes"}
    extra = sorted(set(_sections()) - known)
    assert not extra, f"docs/reference/docstool.md documents what docstool does not have: {extra}"


@pytest.mark.parametrize("name", sorted(SUBCOMMANDS))
def test_every_option_and_choice_is_documented(name: str) -> None:
    sections = _sections()
    section, common = sections.get(name, ""), sections["Common options"]
    for action in SUBCOMMANDS[name]._actions:
        if action.help == argparse.SUPPRESS or "-h" in action.option_strings:
            continue
        shared = set(action.option_strings) & COMMON and not (name == "site-build" and "--out" in action.option_strings)
        where = common if shared else section
        for label in _documented(action):
            assert f"`{label}`" in where, f"{name}: {label} is not documented"
            if shared:
                assert f"`{label}`" in section, f"{name}: the common option {label} is not listed"
        for choice in action.choices or ():
            assert f"`{choice}`" in where, f"{name} {_documented(action)[0]}: the choice {choice} is not documented"


# Placeholders the Values column uses for free-form values; anything else in backticks is a choice.
PLACEHOLDERS = {"DIR", "PATH", "N", "REF", "NAME", "#rrggbb", "TEXT …"}


def _rows(section: str) -> list[list[str]]:
    rows = []
    for line in section.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split(" | ")]
        if line.startswith("| `") and len(cells) == 4:
            rows.append(cells)
    return rows


def _actions_by_label(parser: argparse.ArgumentParser) -> dict[str, argparse.Action]:
    return {label: action for action in parser._actions for label in _documented(action)}


@pytest.mark.parametrize("name", ["Common options", *sorted(SUBCOMMANDS)])
def test_every_documented_option_choice_and_default_exists(name: str) -> None:
    """The other direction: a row the reference keeps after docstool dropped or changed it fails."""
    parser = SUBCOMMANDS["check" if name == "Common options" else name]
    actions = _actions_by_label(parser)
    for option, values, default, _ in _rows(_sections()[name]):
        labels = re.findall(r"`([^`]+)`", option)
        assert labels, f"{name}: unreadable option cell {option!r}"
        action = actions.get(labels[0])
        assert action is not None, f"{name}: {labels[0]} is documented but docstool has no such option"
        assert set(labels) <= set(_documented(action)), f"{name}: {option} names options docstool does not group"
        choices = [v for v in re.findall(r"`([^`]+)`", values) if v not in PLACEHOLDERS]
        assert set(choices) <= set(map(str, action.choices or ())), f"{name} {labels[0]}: documents choices {choices}"
        documented_default = re.findall(r"`([^`]+)`", default)
        actual = action.default if action.default not in (None, False) else None
        assert documented_default == ([str(actual)] if actual is not None else []), f"{name} {labels[0]}: default"


def test_the_top_level_version_flag_is_documented() -> None:
    assert "--version" in REFERENCE.read_text(encoding="utf-8")
