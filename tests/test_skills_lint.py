"""Lint for the shipped skills: frontmatter, size, references and the docstool commands they name."""

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
import shlex
from pathlib import Path

import pytest
from conftest import DOCSTOOL, SKILLS_DIR, load_module

docstool = load_module("docstool", DOCSTOOL)

SKILLS = sorted(p.parent for p in SKILLS_DIR.glob("*/SKILL.md"))
# The plan's size targets for each SKILL.md body, with a margin; a skill routes to references
# rather than growing past these.
MAX_SKILL_LINES = {"repo-docs": 200, "zensical-site": 170, "repo-readme": 150}
NAME_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
LINK_RE = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
FENCE_RE = re.compile(r"^(`{3,}|~{3,})[^\n]*\n(.*?)^\1[ \t]*$", re.MULTILINE | re.DOTALL)
CODE_SPAN_RE = re.compile(r"(`+)(.+?)\1", re.DOTALL)


def frontmatter(text: str) -> dict[str, str]:
    """Parse the flat YAML frontmatter the skills use: plain, quoted or folded/literal scalars."""
    lines = text.splitlines()
    assert lines and lines[0] == "---", "SKILL.md must start with a --- frontmatter block"
    end = lines.index("---", 1)
    fields: dict[str, str] = {}
    i = 1
    while i < end:
        match = re.fullmatch(r"([A-Za-z_][\w-]*):\s*(.*)", lines[i])
        assert match, f"unexpected frontmatter line {i + 1}: {lines[i]!r}"
        key, value = match.groups()
        i += 1
        if value in {">", ">-", "|", "|-"}:
            block = []
            while i < end and (lines[i].startswith(" ") or not lines[i]):
                block.append(lines[i].strip())
                i += 1
            value = (" " if value.startswith(">") else "\n").join(block).strip()
        assert key not in fields, f"duplicate frontmatter key {key}"
        fields[key] = value.strip("\"'")
    return fields


def subcommands() -> set[str]:
    parser = docstool.build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def global_options() -> dict[str, bool]:
    """Map each top-level docstool option to whether it takes a value."""
    options: dict[str, bool] = {}
    for action in docstool.build_parser()._actions:
        for flag in action.option_strings:
            options[flag] = action.nargs != 0
    return options


def code_texts(markdown: str) -> list[str]:
    """Return the fenced blocks and code spans of a Markdown text: where commands are written."""
    texts = [m.group(2) for m in FENCE_RE.finditer(markdown)]
    prose = FENCE_RE.sub("", markdown)
    texts += [m.group(2) for m in CODE_SPAN_RE.finditer(prose)]
    return texts


def is_docstool(token: str) -> bool:
    return token in {"docstool", "docstool.py"} or token.endswith("/docstool.py")


def docstool_invocations(markdown: str) -> list[tuple[str | None, list[str]]]:
    """Return (command, unknown options) for every docstool invocation in the code of a text.

    The command is the first word after docstool (or a path ending in docstool.py) and its global
    options; None when only options follow (`docstool --version`) or the text uses a placeholder
    such as <command>. Backslash line continuations are joined first.
    """
    options = global_options()
    found: list[tuple[str | None, list[str]]] = []
    for text in code_texts(markdown):
        for line in re.sub(r"\\\n", " ", text).splitlines():
            try:
                tokens = shlex.split(line)
            except ValueError:
                tokens = line.split()
            for i, token in enumerate(tokens):
                if not is_docstool(token):
                    continue
                unknown: list[str] = []
                j = i + 1
                while j < len(tokens) and tokens[j].startswith("-"):
                    flag = tokens[j].split("=", 1)[0]
                    if flag not in options:
                        unknown.append(flag)
                    j += 2 if options.get(flag) and "=" not in tokens[j] else 1
                command = tokens[j] if j < len(tokens) else None
                if command is not None and not re.fullmatch(r"[a-z][a-z-]*", command):
                    command = None
                found.append((command, unknown))
    return found


def test_there_are_exactly_the_three_planned_skills() -> None:
    assert [p.name for p in SKILLS] == ["repo-docs", "repo-readme", "zensical-site"]


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_frontmatter_is_portable(skill: Path) -> None:
    fields = frontmatter((skill / "SKILL.md").read_text(encoding="utf-8"))
    assert set(fields) == {"name", "description"}, "only name and description are portable across agents"
    assert fields["name"] == skill.name
    assert NAME_RE.fullmatch(fields["name"])
    assert len(fields["name"]) <= 64
    description = fields["description"]
    assert len(description) <= 1024, f"description is {len(description)} characters"
    assert "Use when" in description, "the description must say when to use the skill"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_skill_body_stays_short(skill: Path) -> None:
    lines = (skill / "SKILL.md").read_text(encoding="utf-8").splitlines()
    assert len(lines) <= MAX_SKILL_LINES[skill.name]


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_no_symlinks_in_a_skill(skill: Path) -> None:
    links = [p for p in skill.rglob("*") if p.is_symlink()]
    assert not links, f"claude plugin validate does not follow symlinks: {links}"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_relative_links_resolve(skill: Path) -> None:
    for md in skill.rglob("*.md"):
        # A link inside a fenced block is an example for the reader to adapt, not a link.
        for target in LINK_RE.findall(FENCE_RE.sub("", md.read_text(encoding="utf-8"))):
            if "://" in target or target.startswith("mailto:"):
                continue
            assert (md.parent / target).exists(), f"{md.relative_to(SKILLS_DIR)} links to missing {target}"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_references_are_agent_shaped(skill: Path) -> None:
    for ref in sorted((skill / "references").glob("*.md")):
        lines = ref.read_text(encoding="utf-8").splitlines()
        body = [line for line in lines if line.strip() and not line.startswith("#")]
        assert body and body[0].startswith("Read this when"), f"{ref.name} must open with 'Read this when'"
        if len(lines) > 100:
            assert any(re.fullmatch(r"#+\s+Contents", line) for line in lines), f"{ref.name} is long and needs a Contents list"


def invocation_problems(markdown: str) -> list[str]:
    known = subcommands()
    problems = []
    for command, unknown in docstool_invocations(markdown):
        problems += [f"unknown option {flag}" for flag in unknown]
        if command is not None and command not in known:
            problems.append(f"unknown command {command}")
    return problems


def test_every_docstool_command_named_in_the_skills_exists() -> None:
    for md in sorted(SKILLS_DIR.rglob("*.md")):
        problems = invocation_problems(md.read_text(encoding="utf-8"))
        assert not problems, f"{md.relative_to(SKILLS_DIR)}: {problems}"


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("Run `docstool chekc`.", ["unknown command chekc"]),
        ("```sh\npython3 -I skills/repo-docs/scripts/docstool.py --version chekc\n```\n", ["unknown command chekc"]),
        ("```sh\npython3 -I <skill-dir>/scripts/docstool.py --bogus 1 chekc\n```\n", ["unknown option --bogus"]),
        ("```console\n$ python3 -I scripts/docstool.py \\\n    chekc --root .\n```\n", ["unknown command chekc"]),
        ("~~~\ndocstool chekc\n~~~\n", ["unknown command chekc"]),
    ],
)
def test_the_command_check_rejects_planted_mistakes(markdown: str, expected: list[str]) -> None:
    assert invocation_problems(markdown) == expected


@pytest.mark.parametrize(
    "markdown",
    [
        "docstool reports findings in prose, which is not a command.",
        "Run `python3 -I <skill-dir>/scripts/docstool.py <command>`.",
        "`docstool --version` prints the version.",
    ],
)
def test_the_command_check_accepts_prose_placeholders_and_options(markdown: str) -> None:
    assert invocation_problems(markdown) == []


def test_the_frontmatter_parser_reads_folded_descriptions() -> None:
    text = "---\nname: x\ndescription: >-\n  one\n  two\n---\n"
    assert frontmatter(text) == {"name": "x", "description": "one two"}
