#!/usr/bin/env python3
"""docstool: the repo-docs-toolkit documentation checker.

Run it in isolated mode, as every SKILL.md says: `python3 -I <skill-dir>/scripts/docstool.py <command>`.
Standard library only, Python 3.11 or newer.

The canonical copy is skills/repo-docs/scripts/docstool.py; the copies in the zensical-site and
repo-readme skills are byte-identical (scripts/sync-vendored.py writes and checks them), so each
skill works on its own.

docstool never runs project code, never sends repository content over the network, runs only
read-only git commands, and writes only the files a command documents (`--out`, `--blocks`).
Every run reports a coverage table next to its findings: an input it could not analyse makes the
run incomplete (exit 3) instead of clean.
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

import argparse
import hashlib
import html
import io
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urljoin

if sys.version_info < (3, 11):  # noqa: UP036 - the check is for users running an older python3
    sys.exit("docstool needs Python 3.11 or newer")

import tomllib

# The version of docstool's command line and JSON output. It changes when a command, a flag or an
# output field changes, independently of the plugin version in .claude-plugin/plugin.json.
__version__ = "0.1.0"

# Exit codes shared by every command.
EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
EXIT_INCOMPLETE = 3

SEVERITIES = ("Blocking", "P0", "P1", "P2", "P3")
CONFIDENCES = ("verified", "likely", "unverified")
COMPLETE_STATES = ("complete", "not_applicable")

# Text files larger than this are not scanned; the couplings row then says which.
MAX_TEXT_BYTES = 8 * 1024 * 1024
# Known binary formats, excluded from text scans without lowering coverage.
BINARY_EXTENSIONS = frozenset(
    [
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".avif",
        ".ico",
        ".icns",
        ".bmp",
        ".tif",
        ".tiff",
        ".psd",
        ".xcf",
        ".svgz",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".eot",
        ".pdf",
        ".zip",
        ".gz",
        ".tgz",
        ".bz2",
        ".xz",
        ".zst",
        ".7z",
        ".rar",
        ".tar",
        ".jar",
        ".whl",
        ".so",
        ".dylib",
        ".dll",
        ".exe",
        ".a",
        ".o",
        ".class",
        ".pyc",
        ".wasm",
        ".bin",
        ".dat",
        ".db",
        ".sqlite",
        ".mp3",
        ".mp4",
        ".ogg",
        ".wav",
        ".flac",
        ".webm",
        ".mov",
        ".avi",
        ".mkv",
        ".flatpak",
        ".deb",
        ".rpm",
        ".apk",
        ".gpg",
        ".der",
        ".p12",
        ".keystore",
    ]
)
MARKDOWN_EXTENSIONS = (".md", ".markdown")
NUL_BYTE = b"\0"
# Heuristic thresholds: near-duplicate shingle overlap, ticked share of a finished checklist, and
# the share of link-only paragraphs that makes a page an index.
NEAR_DUPLICATE = 0.6
TICKED_RATIO = 0.9
INDEX_LINK_RATIO = 0.6


class UsageError(Exception):
    """A problem with the command line or its inputs: exit 2."""


# ---------------------------------------------------------------------------------------------
# Findings, coverage and output
# ---------------------------------------------------------------------------------------------


@dataclass
class Finding:
    check: str
    severity: str
    confidence: str
    file: str
    line: int
    message: str
    evidence: list[str] = field(default_factory=list)
    suggestion: str = ""
    id: str = ""


@dataclass
class CoverageRow:
    input: str
    state: str
    reason: str = ""

    @property
    def complete(self) -> bool:
        return self.state in COMPLETE_STATES


@dataclass
class Report:
    command: str
    root: str
    coverage: list[CoverageRow] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)


def severity_rank(severity: str) -> int:
    return SEVERITIES.index(severity)


def finalize(report: Report, required: Iterable[str], fail_on: str, allow_partial: bool) -> tuple[int, list[str]]:
    """Number the findings and return the exit code and the incomplete required inputs."""
    report.findings.sort(key=lambda f: (severity_rank(f.severity), f.file, f.line, f.check, f.message))
    for number, finding in enumerate(report.findings, 1):
        finding.id = f"F{number}"
    rows = {row.input: row for row in report.coverage}
    incomplete = [name for name in required if name in rows and not rows[name].complete]
    failing = [f for f in report.findings if severity_rank(f.severity) <= severity_rank(fail_on)]
    if incomplete and not allow_partial:
        return EXIT_INCOMPLETE, incomplete
    return (EXIT_FINDINGS if failing else EXIT_OK), incomplete


def render_text(report: Report, incomplete: list[str], limit: int) -> str:
    counts = Counter(f.severity for f in report.findings)
    summary = ", ".join(f"{s}: {counts[s]}" for s in SEVERITIES if counts[s]) or "none"
    state = "PARTIAL: " + ", ".join(incomplete) + " incomplete" if incomplete else "coverage complete"
    # rows this command does not require can still be partial; say so in the summary line too
    others = [r.input for r in report.coverage if not r.complete and r.input not in incomplete]
    if others:
        state += "; not required but partial: " + ", ".join(others)
    out = [f"docstool {report.command}: {len(report.findings)} findings ({summary}); {state}", "", "Coverage:"]
    width = max((len(r.input) for r in report.coverage), default=8)
    out += [f"  {r.input:<{width}}  {r.state:<14}  {r.reason}".rstrip() for r in report.coverage]
    for key, value in report.data.items():
        if isinstance(value, (str, int, float)):
            out.append(f"{key}: {value}")
    if report.findings:
        out += ["", "Findings:"]
        for finding in report.findings[:limit]:
            where = f"{finding.file}:{finding.line}" if finding.line else finding.file
            out.append(f"  {finding.id} [{finding.severity}][{finding.confidence}] {finding.check} {where}: {finding.message}")
            out += [f"      evidence: {e}" for e in finding.evidence[:3]]
            if finding.suggestion:
                out.append(f"      fix: {finding.suggestion}")
        if len(report.findings) > limit:
            out.append(f"  ... {len(report.findings) - limit} more (raise --max or use --format json)")
    return "\n".join(out) + "\n"


def render_json(report: Report, incomplete: list[str]) -> str:
    counts = Counter(f.severity for f in report.findings)
    payload = {
        "tool": "docstool",
        "version": __version__,
        "command": report.command,
        "root": report.root,
        "summary": {"findings": len(report.findings), "by_severity": dict(counts), "incomplete": incomplete},
        "coverage": [asdict(r) for r in report.coverage],
        "findings": [asdict(f) for f in report.findings],
        "data": report.data,
    }
    return json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=False) + "\n"


# ---------------------------------------------------------------------------------------------
# Repository access: tracked files, text reading, read-only git
# ---------------------------------------------------------------------------------------------


def git(root: Path, *args: str) -> str | None:
    """Run a read-only git command; return its stdout, or None when git fails."""
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", "replace")


class Repo:
    """The files of a repository: tracked plus untracked-but-not-ignored, as git sees them."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        if not self.root.is_dir():
            raise UsageError(f"--root {root} is not a directory")
        listing = git(self.root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
        self.is_git = listing is not None
        if listing is None:
            names = [p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file() and ".git" not in p.parts]
        else:
            names = [n for n in listing.split("\0") if n]
        if listing is None:
            names += [p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_symlink() and ".git" not in p.parts]
        self.files = sorted({n for n in names if (self.root / n).is_file() and not (self.root / n).is_symlink()})
        # Symlinks are not scanned (their in-repository targets are, at their own path), but
        # links through them resolve: rel -> the in-root target, or None when it leaves the root.
        self.symlinks: dict[str, str | None] = {}
        for name in sorted(set(names)):
            if (self.root / name).is_symlink():
                try:
                    real = (self.root / name).resolve(strict=True).relative_to(self.root).as_posix()
                except (OSError, ValueError, RuntimeError):
                    self.symlinks[name] = None
                else:
                    self.symlinks[name] = real
        self.file_set = frozenset(self.files)
        self.lower_map: dict[str, list[str]] = defaultdict(list)
        for name in self.files:
            self.lower_map[name.lower()].append(name)
        self.dirs = frozenset(str(PurePosixPath(n).parent) for n in self.files) | {"."}
        self.all_dirs = frozenset(d for n in self.files for d in _parents(n))
        self._text: dict[str, tuple[str | None, str]] = {}
        self._history: tuple[frozenset[str] | None] | None = None

    def text(self, rel: str) -> tuple[str | None, str]:
        """Return (text, status); status is ok, binary, too_large, undecodable or missing."""
        if rel in self._text:
            return self._text[rel]
        path = self.root / rel
        result: tuple[str | None, str]
        if not path.is_file():
            result = (None, "missing")
        elif PurePosixPath(rel).suffix.lower() in BINARY_EXTENSIONS:
            result = (None, "binary")
        elif path.stat().st_size > MAX_TEXT_BYTES:
            result = (None, "too_large")
        else:
            data = path.read_bytes()
            if NUL_BYTE in data[:8192]:
                result = (None, "binary")
            else:
                try:
                    result = (data.decode("utf-8-sig"), "ok")
                except UnicodeDecodeError:
                    result = (None, "undecodable")
        self._text[rel] = result
        return result

    def markdown_files(self) -> list[str]:
        return [n for n in self.files if n.lower().endswith(MARKDOWN_EXTENSIONS)]

    def exists(self, rel: str) -> bool:
        if rel in self.file_set or rel in self.all_dirs:
            return True
        real = self.realpath(rel)
        return real is not None and real != rel and (real in self.file_set or real in self.all_dirs or real == ".")

    def realpath(self, rel: str) -> str | None:
        """Follow in-repository symlinks in rel; None when one leaves the root or dangles."""
        for _ in range(40):
            parts = PurePosixPath(rel).parts
            for index in range(len(parts)):
                prefix = "/".join(parts[: index + 1])
                if prefix in self.symlinks:
                    target = self.symlinks[prefix]
                    if target is None:
                        return None
                    rest = "/".join(parts[index + 1 :])
                    rel = (target if target != "." else "") + ("/" if rest and target != "." else "") + rest or "."
                    break
            else:
                return rel
        return None

    def canonical(self, rel: str) -> str:
        return self.realpath(rel) or rel

    def ever_tracked(self) -> frozenset[str] | None:
        """Every path any commit reachable from a ref has held (read-only), or None outside git."""
        if not self.is_git:
            return None
        if self._history is None:
            out = git(self.root, "log", "--all", "--format=", "--name-only", "--no-renames", "-z")
            self._history = (frozenset(p.strip("\n") for p in out.split("\0") if p.strip("\n")),) if out is not None else (None,)
        return self._history[0]

    def remote_url(self) -> str | None:
        """The GitHub https URL of the origin remote, when there is one."""
        out = git(self.root, "remote", "get-url", "origin") if self.is_git else None
        if not out:
            return None
        url = out.strip()
        match = re.match(r"(?:git@|ssh://git@|https?://)(?:www\.)?github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url)
        return f"https://github.com/{match.group(1)}/{match.group(2)}" if match else None


def _parents(rel: str) -> list[str]:
    parts = PurePosixPath(rel).parts[:-1]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def normalize_path(base_dir: str, target: str) -> str | None:
    """Join a relative link target to a repo-relative directory; None when it leaves the repo."""
    parts: list[str] = [] if base_dir in ("", ".") else base_dir.split("/")
    if target.startswith("/"):
        parts = []
    for piece in target.split("/"):
        if piece in ("", "."):
            continue
        if piece == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(piece)
    return "/".join(parts) if parts else "."


# ---------------------------------------------------------------------------------------------
# Slugs: GitHub's and the site generator's
# ---------------------------------------------------------------------------------------------

SHORTCODE_RE = re.compile(r":[a-z0-9_+-]+:")
ATTR_LIST_RE = re.compile(r"\s*\{:?\s*([^{}]*)\}\s*$")
INLINE_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)|!\[[^\]]*\]\[[^\]]*\]")
INLINE_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)|\[([^\]]*)\]\[[^\]]*\]")
CODE_SPAN_RE = re.compile(r"(`+)(.+?)\1")
TAG_RE = re.compile(r"<[^>]*>")
EMPHASIS_RES = (
    re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1"),
    re.compile(r"~~(?=\S)(.+?)(?<=\S)~~"),
    re.compile(r"\*(?=\S)(.+?)(?<=\S)\*"),
    re.compile(r"(?<![\w\\])_(?=\S)(.+?)(?<=\S)_(?!\w)"),
)


def heading_plain_text(raw: str) -> str:
    """The text a renderer gives a heading: markup removed, code kept, emoji shortcodes gone."""
    spans: list[str] = []

    def keep_code(match: re.Match[str]) -> str:
        spans.append(match.group(2).strip() if match.group(2).strip() else match.group(2))
        return f"\0{len(spans) - 1}\0"

    text = CODE_SPAN_RE.sub(keep_code, raw)
    text = INLINE_IMAGE_RE.sub("", text)
    text = INLINE_LINK_RE.sub(lambda m: m.group(1) if m.group(1) is not None else m.group(2), text)
    text = TAG_RE.sub("", text)
    for pattern in EMPHASIS_RES:
        text = pattern.sub(lambda m: m.group(m.lastindex or 1), text)
    text = SHORTCODE_RE.sub("", text)
    text = re.sub(r"\\([!-/:-@\[-`{-~])", r"\1", text)
    text = html.unescape(text)
    text = re.sub(r"\0(\d+)\0", lambda m: spans[int(m.group(1))], text)
    return text.strip()


def github_slug_base(text: str) -> str:
    """github-slugger: lowercase, keep letters, marks, numbers, connectors, spaces and hyphens."""
    kept = []
    for ch in text.lower():
        category = unicodedata.category(ch)
        if ch in " -" or category[0] in "LMN" or category == "Pc":
            kept.append(ch)
    return "".join(kept).replace(" ", "-")


class GithubSlugger:
    """GitHub's anchors for one document: duplicates get -1, -2 and skip taken ids."""

    def __init__(self) -> None:
        self.occurrences: dict[str, int] = {}

    def slug(self, text: str) -> str:
        original = result = github_slug_base(text)
        while result in self.occurrences:
            self.occurrences[original] += 1
            result = f"{original}-{self.occurrences[original]}"
        self.occurrences[result] = 0
        return result


IDCOUNT_RE = re.compile(r"^(.*)_([0-9]+)$")


def site_slug_base(text: str, style: str) -> str:
    """The site generator's toc slugify for a style docstool knows."""
    if style.startswith("pymdownx-"):
        case = style.removeprefix("pymdownx-")
        slug = TAG_RE.sub("", unicodedata.normalize("NFC", text)).strip()
        if case == "lower":
            slug = slug.lower()
        elif case == "lower-ascii":
            slug = re.sub(r"[A-Z]", lambda m: m.group(0).lower(), slug)
        elif case == "fold":
            slug = slug.casefold()
        return re.sub(r"[^\w\- ]", "", slug).replace(" ", "-")
    unicode_ok = style == "python-markdown-unicode"
    value = text
    if not unicode_ok:
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value)


def unique_site_id(slug: str, used: set[str]) -> str:
    """Python-Markdown's toc.unique: a taken id gets _1, _2, ..."""
    while slug in used or not slug:
        match = IDCOUNT_RE.match(slug)
        slug = f"{match.group(1)}_{int(match.group(2)) + 1}" if match else f"{slug}_1"
    used.add(slug)
    return slug


GITHUB_STYLES = ("pymdownx-lower",)


# ---------------------------------------------------------------------------------------------
# Markdown scanner
# ---------------------------------------------------------------------------------------------

FENCE_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
ATX_RE = re.compile(r"^ {0,3}(#{1,6})(?=[ \t]|$)[ \t]*(.*?)(?:[ \t]+#+)?[ \t]*$")
SETEXT_RE = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
LIST_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[-*+]|\d{1,9}[.)])(?:[ \t]+(?P<rest>.*)|$)")
TASK_RE = re.compile(r"^\[([ xX\-])\][ \t]")
TABLE_DELIM_RE = re.compile(r"^[ \t]*\|?[ \t]*:?-+:?[ \t]*(\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$")
HR_RE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
REF_DEF_RE = re.compile(r"^ {0,3}\[([^\]]+)\]:[ \t]*(<[^>]*>|\S+)")
ADMONITION_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<kind>!!!|\?\?\?\+?)[ \t]+(?P<type>[\w-]+)(?P<title>.*)$")
ALERT_RE = re.compile(r"^[ \t]*>[ \t]*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]", re.IGNORECASE)
TABS_RE = re.compile(r'^[ \t]*===\+?[ \t]+"')
SNIPPET_RE = re.compile(r"""^[ \t]*;?--8<--[ \t]+(["'])(?P<path>[^"']+)\1""")
NUMBER_RE = re.compile(r"^(?P<num>\d+(?:\.\d+)*)\.?(?=\s|$)")
LINK_RE = re.compile(
    r"(?P<img>!?)\[(?P<text>(?:[^\[\]\\]|\\.|\[(?:[^\[\]\\]|\\.)*\])*)\]"
    r"\(\s*(?P<dest><[^>\n]*>|(?:[^\s()\\]|\\.|\((?:[^\s()\\]|\\.)*\))*)(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)"
)
REF_LINK_RE = re.compile(r"(?P<img>!?)\[(?P<text>(?:[^\[\]\\]|\\.|\[[^\[\]]*\])*)\]\[(?P<label>[^\]]*)\]")
SHORTCUT_RE = re.compile(r"(?<![\]\\])\[(?P<label>[^\[\]\n]+)\](?![\[(:])")
AUTOLINK_RE = re.compile(r"<((?:https?|ftp|mailto):[^\s<>]+)>")
HTML_ATTR_RE = re.compile(r"""<(?P<tag>[a-zA-Z][\w-]*)\b[^>]*?\b(?P<attr>href|src|srcset)\s*=\s*(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)')""")
HTML_ID_RE = re.compile(r"""<[a-zA-Z][\w-]*\b[^>]*?\b(?:id|name)\s*=\s*(?:"([^"]+)"|'([^']+)')""")
BOLD_LABEL_RE = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])?[ \t]*(?:\*\*|__)([^*_]+?)(?:\*\*|__)")
GENERATED_RE = re.compile(r"\b(BEGIN|END)[ _-]?GENERATED\b|\b(?:DO NOT EDIT|generated by|auto-?generated)\b", re.IGNORECASE)
BANNER_RE = re.compile(r"kept as written|not updated as the code changes|\bhistorical\b|\bsuperseded\b|\barchived?\b", re.IGNORECASE)


def mask_code_spans(line: str) -> str:
    """Blank out inline code spans so their content is never read as links."""
    return CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), line)


def normalize_label(label: str) -> str:
    return " ".join(label.split()).casefold()


@dataclass
class Heading:
    level: int
    text: str
    raw: str
    line: int
    gh_slug: str = ""
    site_slug: str = ""
    explicit_id: str | None = None
    number: str | None = None
    parent: int = -1


@dataclass
class Link:
    kind: str
    target: str
    line: int
    text: str = ""


@dataclass
class Block:
    type: str
    text: str
    line: int
    heading_path: list[str]
    depth: int = 0
    position: int = 0
    info: str = ""


@dataclass
class MarkdownDoc:
    path: str
    lines: list[str]
    front_matter: Any = None
    front_matter_error: str | None = None
    headings: list[Heading] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    html_ids: set[str] = field(default_factory=set)
    ref_defs: dict[str, tuple[str, int]] = field(default_factory=dict)
    ref_uses: list[tuple[str, int]] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    features: Counter[str] = field(default_factory=Counter)
    regions: list[tuple[int, int, str]] = field(default_factory=list)
    banners: list[tuple[int, str]] = field(default_factory=list)
    bold_labels: dict[str, int] = field(default_factory=dict)
    code_blocks: list[tuple[str, str, int]] = field(default_factory=list)
    tasks: Counter[str] = field(default_factory=Counter)
    snippets: list[tuple[str, int]] = field(default_factory=list)
    odd_tasks: list[int] = field(default_factory=list)

    def anchors(self, site: bool = False) -> set[str]:
        if site:
            return {h.site_slug for h in self.headings} | self.html_ids
        return {h.gh_slug for h in self.headings} | self.html_ids


class _BlockBuilder:
    """Collects the typed blocks of a document for the content-conservation baseline."""

    def __init__(self, doc: MarkdownDoc) -> None:
        self.doc = doc
        self.para: list[str] = []
        self.para_line = 0
        self.para_depth = 0
        self.para_kind = "paragraph"
        self.positions: Counter[tuple[int, int]] = Counter()

    def heading_path(self) -> list[str]:
        path: list[str] = []
        index = len(self.doc.headings) - 1
        if index < 0:
            return path
        current: int = index
        while current >= 0:
            path.append(self.doc.headings[current].text)
            current = self.doc.headings[current].parent
        return list(reversed(path))

    def add(self, kind: str, text: str, line: int, depth: int = 0, info: str = "") -> None:
        key = (len(self.doc.headings), depth)
        position = self.positions[key]
        self.positions[key] += 1
        self.doc.blocks.append(Block(kind, text, line, self.heading_path(), depth, position, info))

    def flush(self) -> None:
        if self.para:
            self.add(self.para_kind, " ".join(" ".join(p.split()) for p in self.para), self.para_line, self.para_depth)
        self.para = []
        self.para_kind = "paragraph"


def parse_markdown(path: str, text: str, site_style: str | None = None, attr_list: bool = True) -> MarkdownDoc:
    """Scan a Markdown document: headings, links, anchors, blocks, features and markers."""
    lines = text.split("\n")
    doc = MarkdownDoc(path=path, lines=lines)
    builder = _BlockBuilder(doc)
    start = _front_matter(doc)
    if start:
        builder.add("front-matter", "\n".join(lines[:start]), 1)
    # The prose of the document, line for line: code, comments and front matter are blanked, so
    # links are found in one pass even when their text wraps onto the next line.
    prose = ["" if i < start else line for i, line in enumerate(lines)]
    fence: tuple[str, int] | None = None
    fence_lines: list[str] = []
    fence_info = ""
    fence_line = 0
    fence_indent = 0
    in_comment = False
    region_start: tuple[int, str] | None = None
    list_indents: list[int] = []
    in_table = False
    in_quote: list[str] = []
    quote_line = 0
    quote_kind = "quote"
    admonition: tuple[int, str, int] | None = None
    admonition_lines: list[str] = []
    prev_blank = True
    indented: list[str] = []
    indented_line = 0
    tabs_indent: int | None = None

    def end_indented() -> None:
        nonlocal indented
        while indented and not indented[-1].strip():
            indented.pop()
        if indented:
            content = "\n".join(indented)
            doc.code_blocks.append(("", content, indented_line))
            builder.add("code", content, indented_line)
            doc.features["indented-code"] += 1
        indented = []

    def end_quote() -> None:
        nonlocal in_quote
        if in_quote:
            builder.add(quote_kind, " ".join(" ".join(q.split()) for q in in_quote), quote_line)
            in_quote = []

    def end_admonition() -> None:
        nonlocal admonition, admonition_lines
        if admonition is not None:
            body = " ".join(" ".join(a.split()) for a in admonition_lines if a.strip())
            builder.add(f"admonition:{admonition[1]}", body, admonition[0])
        admonition = None
        admonition_lines = []

    for number, raw_line in enumerate(lines[start:], start + 1):
        line = raw_line
        stripped = line.strip()
        # Fenced code: the content is kept byte for byte and never scanned for links.
        if fence is not None:
            match = re.match(r"^[ \t]*(`+|~+)[ \t]*$", line)
            if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= fence[1]:
                content = "\n".join(_dedent(fence_lines, fence_indent))
                doc.code_blocks.append((fence_info, content, fence_line))
                builder.add("code", content, fence_line, len(list_indents), fence_info)
                fence = None
            else:
                fence_lines.append(line)
            prose[number - 1] = ""
            continue
        if in_comment:
            _markers(doc, line, number)
            if "-->" in line:
                in_comment = False
                prose[number - 1] = line[line.index("-->") + 3 :]
            else:
                prose[number - 1] = ""
            continue
        open_fence = FENCE_RE.match(line)
        if open_fence and not (open_fence.group("fence")[0] == "`" and "`" in open_fence.group("info")):
            builder.flush()
            end_quote()
            fence = (open_fence.group("fence")[0], len(open_fence.group("fence")))
            fence_info = open_fence.group("info").strip()
            fence_line = number
            fence_lines = []
            fence_indent = len(open_fence.group("indent").expandtabs(4))
            prose[number - 1] = ""
            if fence_indent == 0 and prev_blank:
                list_indents = []
            prev_blank = False
            if admonition is not None and fence_indent <= admonition[2]:
                end_admonition()
            doc.features["code-fence" if fence[0] == "`" else "tilde-fence"] += 1
            if fence_info.split(" ", 1)[0] == "mermaid":
                doc.features["mermaid"] += 1
            continue
        # HTML comments: generated-region markers live here; their content is not prose.
        if "<!--" in line:
            _markers(doc, line, number)
            marker = GENERATED_RE.search(line)
            if marker and marker.group(1):
                if marker.group(1).upper() == "BEGIN":
                    region_start = (number, stripped)
                elif region_start is not None:
                    doc.regions.append((region_start[0], number, region_start[1]))
                    region_start = None
            if "-->" not in line[line.index("<!--") :]:
                in_comment = True
            line = re.sub(r"<!--.*?(-->|$)", "", line)
            prose[number - 1] = line
            stripped = line.strip()
            if not stripped:
                continue
        _markers(doc, line, number)
        if not stripped and indented:
            indented.append("")
            prev_blank = True
            continue
        if not stripped:
            builder.flush()
            end_quote()
            in_table = False
            prev_blank = True
            if admonition is not None:
                admonition_lines.append("")
            continue
        indent = len(line) - len(line.lstrip(" \t"))
        if prev_blank and indent == 0 and not LIST_RE.match(line):
            list_indents = []
        if admonition is not None:
            if indent > admonition[2]:
                admonition_lines.append(line)
                prev_blank = False
                continue
            end_admonition()
        # Indented code (CommonMark): four columns, not inside a list, a quote, a paragraph or
        # the indented body of a content tab.
        columns = len(line.expandtabs(4)) - len(line.expandtabs(4).lstrip(" "))
        if tabs_indent is not None and columns <= tabs_indent:
            tabs_indent = None
        if columns >= 4 and (indented or (prev_blank and not builder.para)) and not list_indents and not in_quote and tabs_indent is None:
            if not indented:
                builder.flush()
                indented_line = number
            indented.append(_strip_code_indent(line))
            prose[number - 1] = ""
            prev_blank = False
            continue
        end_indented()
        masked = mask_code_spans(line)
        # Headings
        atx = ATX_RE.match(line)
        setext = SETEXT_RE.match(line)
        if atx and not in_table:
            builder.flush()
            end_quote()
            list_indents = []
            _add_heading(doc, len(atx.group(1)), atx.group(2), number)
            prev_blank = False
            continue
        if setext and builder.para and not list_indents and not in_quote:
            text_lines = builder.para
            builder.para = []
            _add_heading(doc, 1 if setext.group(1)[0] == "=" else 2, " ".join(t.strip() for t in text_lines), builder.para_line)
            prev_blank = False
            continue
        if HR_RE.match(line):
            builder.flush()
            prev_blank = False
            continue
        ref = REF_DEF_RE.match(line)
        if ref and not in_table:
            doc.ref_defs[normalize_label(ref.group(1))] = (ref.group(2).strip("<>"), number)
            doc.links.append(Link("refdef", ref.group(2).strip("<>"), number, ref.group(1)))
            builder.flush()
            builder.add("refdef", stripped, number)
            continue
        snippet = SNIPPET_RE.match(line)
        if snippet:
            doc.snippets.append((snippet.group("path"), number))
            doc.features["snippet"] += 1
        adm = ADMONITION_RE.match(line)
        if adm:
            builder.flush()
            end_quote()
            admonition = (number, adm.group("type").lower(), len(adm.group("indent")))
            admonition_lines = [adm.group("title").strip().strip('"')]
            doc.features["admonition"] += 1
            continue
        if TABS_RE.match(line):
            doc.features["content-tabs"] += 1
            tabs_indent = columns
        if stripped.startswith(">"):
            builder.flush()
            if not in_quote:
                quote_line = number
                alert = ALERT_RE.match(line)
                quote_kind = f"alert:{alert.group(1).lower()}" if alert else "quote"
                if alert:
                    doc.features["github-alert"] += 1
            in_quote.append(re.sub(r"^[ \t]*>[ \t]?", "", line))
            continue
        end_quote()
        # Tables: a row followed by a delimiter row starts one; every row is a block.
        if "|" in masked and (in_table or (number < len(lines) and TABLE_DELIM_RE.match(lines[number]) and not TABLE_DELIM_RE.match(line))):
            if not in_table:
                builder.flush()
                doc.features["table"] += 1
            in_table = True
            if not TABLE_DELIM_RE.match(line):
                cells = [" ".join(c.split()) for c in masked_cells(line)]
                builder.add("table-row", " | ".join(cells), number)
            continue
        item = LIST_RE.match(line)
        if item and (prev_blank or list_indents or not builder.para):
            builder.flush()
            item_indent = len(item.group("indent").expandtabs(4))
            while list_indents and list_indents[-1] > item_indent:
                list_indents.pop()
            if not list_indents or list_indents[-1] < item_indent:
                list_indents.append(item_indent)
            rest = item.group("rest") or ""
            task = TASK_RE.match(rest)
            if task:
                doc.tasks[task.group(1).lower()] += 1
                if task.group(1) == "-":
                    doc.odd_tasks.append(number)
            bold = BOLD_LABEL_RE.match(line)
            if bold:
                doc.bold_labels.setdefault(heading_plain_text(bold.group(1)).rstrip(":.").strip(), number)
            # The item stays open: its lazy and indented continuation lines belong to it.
            builder.para = [rest]
            builder.para_line = number
            builder.para_depth = len(list_indents)
            builder.para_kind = "list-item"
            prev_blank = False
            continue
        if list_indents and indent == 0 and prev_blank:
            list_indents = []
        if stripped.startswith("<") and not builder.para:
            doc.features["html"] += 1
        bold = BOLD_LABEL_RE.match(line)
        if bold and not builder.para:
            doc.bold_labels.setdefault(heading_plain_text(bold.group(1)).rstrip(":.").strip(), number)
        if not builder.para:
            builder.para_line = number
            builder.para_depth = len(list_indents)
        builder.para.append(line)
        prev_blank = False
    builder.flush()
    end_quote()
    end_admonition()
    if fence is not None:
        content = "\n".join(_dedent(fence_lines, fence_indent))
        doc.code_blocks.append((fence_info, content, fence_line))
        builder.add("code", content, fence_line, len(list_indents), fence_info)
    end_indented()
    if region_start is not None:
        doc.regions.append((region_start[0], len(lines), region_start[1] + " (no END marker)"))
    _scan_prose(doc, prose)
    _assign_slugs(doc, site_style, attr_list)
    return doc


def masked_cells(line: str) -> list[str]:
    cells = re.split(r"(?<!\\)\|", line.strip())
    if cells and not cells[0].strip():
        cells = cells[1:]
    if cells and not cells[-1].strip():
        cells = cells[:-1]
    return cells


def _strip_code_indent(line: str) -> str:
    """An indented code line minus its four columns of indentation (one tab or up to four spaces)."""
    if line.startswith("\t"):
        return line[1:]
    strip = 0
    while strip < 4 and strip < len(line) and line[strip] == " ":
        strip += 1
    return line[strip:]


def _dedent(lines: list[str], indent: int) -> list[str]:
    """Remove up to indent leading spaces (the fence's own indentation); every other byte is kept."""
    out = []
    for line in lines:
        strip = 0
        while strip < indent and strip < len(line) and line[strip] == " ":
            strip += 1
        out.append(line[strip:])
    return out


def _front_matter(doc: MarkdownDoc) -> int:
    """Parse a leading --- YAML block; return the index of the first body line."""
    if not doc.lines or doc.lines[0].strip() != "---":
        return 0
    for index in range(1, len(doc.lines)):
        if doc.lines[index].strip() in ("---", "..."):
            try:
                doc.front_matter = yaml_load("\n".join(doc.lines[1:index]))
            except YamlError as error:
                doc.front_matter_error = str(error)
            doc.features["front-matter"] += 1
            return index + 1
    return 0


def _markers(doc: MarkdownDoc, line: str, number: int) -> None:
    """Record a status banner (kept as written, historical, superseded) near the top of a file."""
    if number <= 40 and BANNER_RE.search(line) and (not doc.banners or doc.banners[-1][0] != number):
        doc.banners.append((number, line.strip()[:160]))


def _add_heading(doc: MarkdownDoc, level: int, raw: str, number: int) -> None:
    explicit = None
    attrs = ATTR_LIST_RE.search(raw)
    text_raw = raw
    if attrs and "#" in attrs.group(1):
        match = re.search(r"#([\w-]+)", attrs.group(1))
        explicit = match.group(1) if match else None
        text_raw = raw[: attrs.start()]
    text = heading_plain_text(text_raw)
    num = NUMBER_RE.match(text)
    parent = len(doc.headings) - 1
    while parent >= 0 and doc.headings[parent].level >= level:
        parent = doc.headings[parent].parent
    doc.headings.append(Heading(level, text, raw, number, explicit_id=explicit, number=num.group("num") if num else None, parent=parent))


def _assign_slugs(doc: MarkdownDoc, site_style: str | None, attr_list: bool) -> None:
    slugger = GithubSlugger()
    used = {h.explicit_id for h in doc.headings if h.explicit_id and attr_list} | set(doc.html_ids)
    for heading in doc.headings:
        # GitHub renders an attribute list literally, so it is part of the GitHub slug; so does a
        # site without the attr_list extension.
        heading.gh_slug = slugger.slug(heading_plain_text(heading.raw))
        if heading.explicit_id and attr_list:
            heading.site_slug = heading.explicit_id
        else:
            text = heading.text if attr_list else heading_plain_text(heading.raw)
            heading.site_slug = unique_site_id(site_slug_base(text, site_style or "pymdownx-lower"), used)


MULTILINE_CODE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`)((?:[^`\n]|\n(?![ \t]*\n)|(?!\1)`+)+?)(?<!`)\1(?!`)")


def _scan_prose(doc: MarkdownDoc, prose: list[str]) -> None:
    """Record links, images, reference uses, HTML targets and HTML anchors in the prose."""
    text = "\n".join(prose)
    masked = MULTILINE_CODE_SPAN_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    masked = masked.replace("\\[", "  ").replace("\\]", "  ")
    starts = [0]
    for index, ch in enumerate(masked):
        if ch == "\n":
            starts.append(index + 1)

    def line_of(offset: int) -> int:
        low, high = 0, len(starts) - 1
        while low < high:
            mid = (low + high + 1) // 2
            if starts[mid] <= offset:
                low = mid
            else:
                high = mid - 1
        return low + 1

    _scan_inline(doc, masked, line_of)


def _scan_inline(doc: MarkdownDoc, masked: str, line_of: Any) -> None:
    """Find the inline constructs of masked prose; line_of maps an offset to its line."""
    for match in LINK_RE.finditer(masked):
        dest = match.group("dest").strip()
        dest = dest[1:-1] if dest.startswith("<") and dest.endswith(">") else dest
        text = " ".join(match.group("text").split())
        doc.links.append(Link("image" if match.group("img") else "link", dest, line_of(match.start()), text))
    without_inline = LINK_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), masked)
    for match in REF_LINK_RE.finditer(without_inline):
        label = match.group("label") or match.group("text")
        doc.ref_uses.append((normalize_label(label), line_of(match.start())))
    without_refs = REF_LINK_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), without_inline)
    for match in SHORTCUT_RE.finditer(without_refs):
        doc.ref_uses.append(("?" + normalize_label(match.group("label")), line_of(match.start())))
    for match in AUTOLINK_RE.finditer(masked):
        doc.links.append(Link("autolink", match.group(1), line_of(match.start())))
    for match in HTML_ATTR_RE.finditer(masked):
        value = match.group("dq") if match.group("dq") is not None else match.group("sq") or ""
        number = line_of(match.start())
        if match.group("attr") == "srcset":
            for candidate in value.split(","):
                if candidate.strip():
                    doc.links.append(Link("html-src", candidate.strip().split()[0], number))
        else:
            doc.links.append(Link("html-src" if match.group("attr") == "src" else "html-href", value, number))
    for match in HTML_ID_RE.finditer(masked):
        doc.html_ids.add(match.group(1) or match.group(2))


# ---------------------------------------------------------------------------------------------
# YAML subset (mkdocs.yml, front matter): no guessing, unsupported constructs raise
# ---------------------------------------------------------------------------------------------


class YamlError(Exception):
    def __init__(self, message: str, line: int, path: list[str]) -> None:
        where = ".".join(path) or "<root>"
        super().__init__(f"line {line}, at {where}: {message}")
        self.line = line
        self.key_path = list(path)


@dataclass
class Tagged:
    """A tagged YAML value such as !!python/name:x or !ENV [VAR, default]."""

    tag: str
    value: Any


@dataclass
class _Line:
    indent: int
    text: str
    number: int


def _strip_comment(text: str) -> str:
    quote = ""
    for index, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"" and (index == 0 or text[index - 1] in " [{,:"):
            quote = ch
        elif ch == "#" and (index == 0 or text[index - 1] in " \t"):
            return text[:index].rstrip()
    return text.rstrip()


KEY_RE = re.compile(
    r"""^(?P<key>"(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^\s"'#\-?:,\[\]{}&*!|>%@`](?:[^:#]|(?<=\S)\#)*?|-[^\s:](?:[^:#]|(?<=\S)\#)*?)[ \t]*:(?:[ \t]+(?P<rest>.*)|$)"""
)


def yaml_load(text: str) -> Any:
    """Parse the YAML subset docstool supports; raise YamlError for anything else."""
    raw = text.split("\n")
    lines: list[_Line] = []
    index = 0
    while index < len(raw):
        line = raw[index]
        number = index + 1
        index += 1
        if line.strip() in ("---",) and not lines:
            continue
        if line.strip() in ("---", "..."):
            if any(r.strip() and not r.strip().startswith("#") for r in raw[index:]):
                raise YamlError("multi-document files are not supported", number, [])
            break
        if "\t" in line[: len(line) - len(line.lstrip())]:
            raise YamlError("tab indentation", number, [])
        content = _strip_comment(line)
        if not content.strip():
            continue
        lines.append(_Line(len(content) - len(content.lstrip(" ")), content.strip(), number))
        # Block scalars keep their raw lines; mark them so the parser can collect them.
        if re.search(r"(?:^|[:\-][ \t])[|>][+-]?\d*$", content.strip()):
            base = lines[-1].indent
            block: list[str] = []
            while index < len(raw) and (not raw[index].strip() or len(raw[index]) - len(raw[index].lstrip(" ")) > base):
                block.append(raw[index])
                index += 1
            lines[-1] = _Line(lines[-1].indent, lines[-1].text + "\0" + "\n".join(block), number)
    if not lines:
        return None
    value, end = _parse_node(lines, 0, lines[0].indent, [])
    if end < len(lines):
        raise YamlError("unexpected content", lines[end].number, [])
    return value


def _parse_node(lines: list[_Line], index: int, indent: int, path: list[str]) -> tuple[Any, int]:
    line = lines[index]
    if line.text == "-" or line.text.startswith("- "):
        return _parse_sequence(lines, index, line.indent, path)
    if KEY_RE.match(line.text.split("\0", 1)[0]):
        return _parse_mapping(lines, index, line.indent, path)
    value = _parse_inline(line.text, line.number, path)
    return value, index + 1


def _parse_mapping(lines: list[_Line], index: int, indent: int, path: list[str]) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines) and lines[index].indent == indent:
        line = lines[index]
        head = line.text.split("\0", 1)[0]
        match = KEY_RE.match(head)
        if not match:
            if head.startswith("- "):
                break
            raise YamlError("expected a mapping key", line.number, path)
        key = _unquote(match.group("key").strip())
        if key == "<<":
            raise YamlError("merge keys are not supported", line.number, path)
        rest = match.group("rest")
        sub = [*path, key]
        if key in result:
            raise YamlError(f"duplicate key {key!r}", line.number, path)
        if rest is None or rest == "":
            index += 1
            if index < len(lines) and (lines[index].indent > indent or (lines[index].indent == indent and lines[index].text.startswith("- "))):
                result[key], index = _parse_node(lines, index, lines[index].indent, sub)
            else:
                result[key] = None
            continue
        if "\0" in line.text:
            result[key] = _block_scalar(rest, line.text.split("\0", 1)[1], line.number, sub)
            index += 1
            continue
        tag_only = re.fullmatch(r"(!\S*)", rest)
        if tag_only:
            index += 1
            child: Any = None
            if index < len(lines) and lines[index].indent > indent:
                child, index = _parse_node(lines, index, lines[index].indent, sub)
            result[key] = Tagged(tag_only.group(1), child)
            continue
        result[key] = _parse_inline(rest, line.number, sub)
        index += 1
    return result, index


def _parse_sequence(lines: list[_Line], index: int, indent: int, path: list[str]) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines) and lines[index].indent == indent and (lines[index].text == "-" or lines[index].text.startswith("- ")):
        line = lines[index]
        sub = [*path, f"[{len(result)}]"]
        rest = line.text[1:].lstrip(" ")
        if not rest:
            index += 1
            if index < len(lines) and lines[index].indent > indent:
                value, index = _parse_node(lines, index, lines[index].indent, sub)
            else:
                value = None
            result.append(value)
            continue
        offset = indent + (len(line.text) - len(rest))
        lines[index] = _Line(offset, rest, line.number)
        value, index = _parse_node(lines, index, offset, sub)
        result.append(value)
    return result, index


def _block_scalar(indicator: str, body: str, number: int, path: list[str]) -> str:
    if path and path[0] == "nav":
        raise YamlError("block scalars inside nav are not supported", number, path)
    rows = body.split("\n")
    widths = [len(r) - len(r.lstrip(" ")) for r in rows if r.strip()]
    cut = min(widths) if widths else 0
    rows = [r[cut:] for r in rows]
    while rows and not rows[-1].strip():
        rows.pop()
    if indicator.startswith(">"):
        return " ".join(r.strip() for r in rows if r.strip()) + ("" if "-" in indicator else "\n")
    return "\n".join(rows) + ("" if "-" in indicator else "\n")


def _unquote(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] == '"':
        return json.loads(text) if "\\" in text else text[1:-1]
    if len(text) >= 2 and text[0] == text[-1] == "'":
        return text[1:-1].replace("''", "'")
    return text


def _parse_inline(text: str, number: int, path: list[str]) -> Any:
    text = text.strip()
    if text.startswith(("&", "*")):
        raise YamlError("anchors and aliases are not supported", number, path)
    if text.startswith("!"):
        tag, _, rest = text.partition(" ")
        return Tagged(tag, _parse_inline(rest, number, path) if rest.strip() else None)
    if text.startswith(("[", "{")):
        value, end = _parse_flow(text, 0, number, path)
        if text[end:].strip():
            raise YamlError("unexpected text after a flow collection", number, path)
        return value
    if text.startswith(("|", ">")):
        raise YamlError("block scalar without content", number, path)
    if text[0] in "\"'":
        if not (len(text) >= 2 and text[-1] == text[0]):
            raise YamlError("multi-line quoted scalars are not supported", number, path)
        return _unquote(text)
    return _plain_scalar(text)


def _plain_scalar(text: str) -> Any:
    lowered = text.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    if lowered in ("null", "~"):
        return None
    if re.fullmatch(r"[-+]?\d+", text):
        return int(text)
    if re.fullmatch(r"[-+]?(\d+\.\d*|\.\d+)([eE][-+]?\d+)?", text):
        return float(text)
    return text


def _parse_flow(text: str, index: int, number: int, path: list[str]) -> tuple[Any, int]:
    opener = text[index]
    closer = "]" if opener == "[" else "}"
    items: list[Any] = []
    mapping: dict[str, Any] = {}
    index += 1
    while True:
        while index < len(text) and text[index] in " \t":
            index += 1
        if index >= len(text):
            raise YamlError("multi-line flow collections are not supported", number, path)
        if text[index] == closer:
            return (items if opener == "[" else mapping), index + 1
        value, index = _flow_item(text, index, number, path)
        if opener == "{" or (isinstance(value, tuple) and value[0] == "pair"):
            if not (isinstance(value, tuple) and value[0] == "pair"):
                mapping[str(value)] = None
            elif opener == "{":
                mapping[value[1]] = value[2]
            else:
                items.append({value[1]: value[2]})
        else:
            items.append(value)
        while index < len(text) and text[index] in " \t":
            index += 1
        if index < len(text) and text[index] == ",":
            index += 1


def _flow_item(text: str, index: int, number: int, path: list[str]) -> tuple[Any, int]:
    if text[index] in "[{":
        return _parse_flow(text, index, number, path)
    if text[index] in "\"'":
        quote = text[index]
        end = index + 1
        while end < len(text):
            if text[end] == "\\" and quote == '"':
                end += 2
                continue
            if text[end] == quote:
                if quote == "'" and end + 1 < len(text) and text[end + 1] == "'":
                    end += 2
                    continue
                break
            end += 1
        if end >= len(text):
            raise YamlError("multi-line quoted scalars are not supported", number, path)
        scalar: Any = _unquote(text[index : end + 1])
        index = end + 1
    else:
        match = re.compile(r"[^,\[\]{}]*").match(text, index)
        assert match is not None
        token = match.group(0)
        colon = re.search(r":(?:\s|$)", token)
        if colon:
            key = _unquote(token[: colon.start()].strip())
            rest_start = index + colon.end()
            while rest_start < len(text) and text[rest_start] in " \t":
                rest_start += 1
            if rest_start < len(text) and text[rest_start] in "[{\"'":
                value, end_index = _flow_item(text, rest_start, number, path)
            else:
                vmatch = re.compile(r"[^,\[\]{}]*").match(text, rest_start)
                assert vmatch is not None
                value, end_index = _plain_or_tag(vmatch.group(0).strip(), number, path), vmatch.end()
            return ("pair", key, value), end_index
        if token.strip().startswith(("&", "*")):
            raise YamlError("anchors and aliases are not supported", number, path)
        return _plain_or_tag(token.strip(), number, path), match.end()
    while index < len(text) and text[index] in " \t":
        index += 1
    if index < len(text) and text[index] == ":":
        index += 1
        while index < len(text) and text[index] in " \t":
            index += 1
        value, index = _flow_item(text, index, number, path)
        return ("pair", str(scalar), value), index
    return scalar, index


def _plain_or_tag(token: str, number: int, path: list[str]) -> Any:
    if token.startswith("!"):
        tag, _, rest = token.partition(" ")
        return Tagged(tag, _plain_scalar(rest.strip()) if rest.strip() else None)
    return _plain_scalar(token) if token else None


# ---------------------------------------------------------------------------------------------
# gitignore-style patterns (exclude_docs, draft_docs, not_in_nav)
# ---------------------------------------------------------------------------------------------


def _glob_to_regex(glob: str) -> str:
    out = []
    index = 0
    while index < len(glob):
        ch = glob[index]
        if glob.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
            continue
        if glob.startswith("**", index):
            out.append(".*")
            index += 2
            continue
        if ch == "*":
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        elif ch == "[":
            end = glob.find("]", index + 1)
            if end == -1:
                out.append(re.escape(ch))
            else:
                out.append("[" + glob[index + 1 : end].replace("!", "^", 1) + "]")
                index = end
        else:
            out.append(re.escape(ch))
        index += 1
    return "".join(out)


class GitignoreSpec:
    """The gitignore matching Zensical and MkDocs apply to exclude_docs and its siblings."""

    def __init__(self, text: str) -> None:
        self.rules: list[tuple[re.Pattern[str], bool, str]] = []
        for raw in text.splitlines():
            line = raw.rstrip()
            if not line or line.startswith("#"):
                continue
            negate = line.startswith("!")
            pattern = line[1:] if negate else line
            dir_only = pattern.endswith("/")
            pattern = pattern.rstrip("/")
            anchored = "/" in pattern
            pattern = pattern.lstrip("/")
            body = _glob_to_regex(pattern)
            prefix = "^" if anchored else "^(?:.*/)?"
            suffix = "/.*$" if dir_only else "(?:/.*)?$"
            self.rules.append((re.compile(prefix + body + suffix), negate, line))

    def match(self, rel: str) -> bool:
        matched = False
        for regex, negate, _ in self.rules:
            if regex.match(rel):
                matched = not negate
        return matched

    def __bool__(self) -> bool:
        return bool(self.rules)


# ---------------------------------------------------------------------------------------------
# Site configuration: zensical.toml or mkdocs.yml
# ---------------------------------------------------------------------------------------------

# Zensical's built-in plugins (0.1.3); anything else in a config is silently ignored by it.
KNOWN_ZENSICAL = "0.1.3"
# The anchor styles docstool emulates (slug --style; a site's toc.slugify maps to one of them).
SLUG_STYLES = ("pymdownx-lower", "pymdownx-none", "python-markdown", "python-markdown-unicode")
DEFAULT_EXCLUDES = GitignoreSpec(".*\n/templates/\n")
# The extensions Zensical enables when markdown_extensions is absent (zensical/config.py,
# DEFAULT_MARKDOWN_EXTENSIONS); setting the key replaces the whole list.
ZENSICAL_DEFAULT_EXTENSIONS = [
    "abbr",
    "admonition",
    "attr_list",
    "def_list",
    "footnotes",
    "md_in_html",
    "toc",
    "tables",
    "pymdownx.arithmatex",
    "pymdownx.betterem",
    "pymdownx.caret",
    "pymdownx.details",
    "pymdownx.emoji",
    "pymdownx.highlight",
    "pymdownx.inlinehilite",
    "pymdownx.keys",
    "pymdownx.magiclink",
    "pymdownx.mark",
    "pymdownx.smartsymbols",
    "pymdownx.superfences",
    "pymdownx.tabbed",
    "pymdownx.tasklist",
    "pymdownx.tilde",
]


@dataclass
class NavEntry:
    title: str
    target: str
    path: list[str]


@dataclass
class Site:
    config: str | None = None
    kind: str | None = None
    docs_dir: str = "docs"
    exclude: GitignoreSpec = field(default_factory=lambda: GitignoreSpec(""))
    draft: GitignoreSpec = field(default_factory=lambda: GitignoreSpec(""))
    not_in_nav: GitignoreSpec = field(default_factory=lambda: GitignoreSpec(""))
    exclude_text: str = ""
    nav: list[NavEntry] | None = None
    slug_style: str = "python-markdown"
    extensions: dict[str, Any] = field(default_factory=dict)
    plugins: dict[str, Any] = field(default_factory=dict)
    custom_dir: str | None = None
    extra_css: list[str] = field(default_factory=list)
    extra_javascript: list[str] = field(default_factory=list)
    redirects: dict[str, str] = field(default_factory=dict)
    repo_url: str | None = None
    site_url: str | None = None
    edit_uri: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def in_docs(self, rel: str) -> bool:
        return self.docs_dir in (".", rel) or rel.startswith(self.docs_dir + "/")

    def docs_rel(self, rel: str) -> str:
        return rel if self.docs_dir == "." else rel[len(self.docs_dir) + 1 :]

    def published(self, rel: str) -> bool:
        """Whether a file under docs_dir is part of the built site."""
        if self.config is None or not self.in_docs(rel):
            return False
        inner = self.docs_rel(rel)
        return not (DEFAULT_EXCLUDES.match(inner) or self.exclude.match(inner) or self.draft.match(inner))


def _pattern_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(v) for v in value)
    return str(value or "")


def _extensions_from_mkdocs(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in value or []:
        if isinstance(item, str):
            result[item] = {}
        elif isinstance(item, dict):
            for name, options in item.items():
                result[str(name)] = options if options is not None else {}
    return result


def _zensical_extensions(value: Any) -> dict[str, Any]:
    """zensical.toml's extension table with dotted pymdownx/zensical keys hoisted, as Zensical does."""
    if not isinstance(value, dict):
        return {}
    result = dict(value)
    for prefix in ("pymdownx", "zensical"):
        nested = result.pop(prefix, None)
        if not isinstance(nested, dict):
            continue
        for name, options in nested.items():
            if (prefix, name) in (("pymdownx", "blocks"), ("zensical", "extensions")) and isinstance(options, dict):
                for inner, inner_options in options.items():
                    result[f"{prefix}.{name}.{inner}"] = inner_options
            else:
                result[f"{prefix}.{name}"] = options
    return result


def _plugins_from_mkdocs(value: Any) -> dict[str, Any]:
    return _extensions_from_mkdocs(value)


def _slug_style(extensions: dict[str, Any], kind: str, explicit_list: bool) -> str:
    """Name the toc slugify the site uses: pymdownx-<case>, python-markdown(-unicode) or unknown."""
    toc = extensions.get("toc")
    if toc is None:
        # Zensical's default extension list includes toc with Python-Markdown's slugify; an explicit
        # list without toc still gets toc added (zensical/config.py), with the same slugify.
        return "python-markdown"
    slugify = toc.get("slugify") if isinstance(toc, dict) else None
    if slugify is None:
        return "python-markdown"
    if isinstance(slugify, Tagged):
        name = slugify.tag.split(":", 1)[-1]
        kwds = slugify.value.get("kwds", {}) if isinstance(slugify.value, dict) else {}
    elif isinstance(slugify, dict):
        name = str(slugify.get("object", ""))
        kwds = slugify.get("kwds", {}) or {}
    else:
        name = str(slugify)
        kwds = {}
    if name.endswith("pymdownx.slugs.slugify"):
        return f"pymdownx-{kwds.get('case', 'none')}"
    if name.endswith("toc.slugify_unicode"):
        return "python-markdown-unicode"
    if name.endswith("toc.slugify"):
        return "python-markdown"
    return "unknown"


def _flatten_nav(value: Any, path: list[str], out: list[NavEntry], problems: list[str]) -> None:
    if isinstance(value, list):
        for item in value:
            _flatten_nav(item, path, out, problems)
    elif isinstance(value, dict):
        for title, target in value.items():
            if isinstance(target, (list, dict)):
                _flatten_nav(target, [*path, str(title)], out, problems)
            elif isinstance(target, str):
                out.append(NavEntry(str(title), target, path))
            else:
                problems.append(f"nav entry {title!r} has an unsupported value")
    elif isinstance(value, str):
        out.append(NavEntry("", value, path))
    elif value is not None:
        problems.append(f"unsupported nav item {value!r}")


def load_site(repo: Repo, report: Report, prefer_mkdocs: bool = False) -> Site:
    """Read the site config and add the config, nav, exclude_docs, redirects and slug-style rows.

    Zensical reads zensical.toml when both configs exist; prefer_mkdocs reads mkdocs.yml instead,
    for a build with MkDocs (site-build --generator mkdocs)."""
    site = Site()
    if repo.symlinks:
        outside = sorted(name for name, target in repo.symlinks.items() if target is None)
        reason = f"{len(repo.symlinks)} symlinks, not scanned; links through them resolve to their targets, scanned at their own path"
        if outside:
            reason += "; not followed (outside the repository or dangling): " + ", ".join(outside[:10])
        report.coverage.append(CoverageRow("symlinks", "partial" if outside else "complete", reason))
    toml_path, yaml_path = "zensical.toml", "mkdocs.yml"
    if not repo.exists(yaml_path) and repo.exists("mkdocs.yaml"):
        yaml_path = "mkdocs.yaml"
    rows = ("config", "nav", "exclude_docs", "redirects", "slug_style")
    if not repo.exists(toml_path) and not repo.exists(yaml_path):
        site.docs_dir = "docs"
        for name in rows:
            report.coverage.append(CoverageRow(name, "not_applicable", "no zensical.toml or mkdocs.yml"))
        return site
    chosen = toml_path if repo.exists(toml_path) and not (prefer_mkdocs and repo.exists(yaml_path)) else yaml_path
    note = f" (zensical.toml is used; {yaml_path} is ignored by Zensical)" if chosen == toml_path and repo.exists(yaml_path) else ""
    if chosen == yaml_path and repo.exists(toml_path):
        note = f" (read for MkDocs; Zensical would read {toml_path})"
    site.config = chosen
    text, status = repo.text(chosen)
    data: Any = None
    if text is None:
        reason = f"{chosen}: {status}"
    else:
        try:
            if chosen.endswith(".toml"):
                site.kind = "zensical"
                data = tomllib.loads(text).get("project", {})
            else:
                site.kind = "mkdocs"
                data = yaml_load(text)
            reason = ""
        except (tomllib.TOMLDecodeError, YamlError) as error:
            reason = f"{chosen}: {error}"
    if not isinstance(data, dict):
        state = "partial" if text is not None else "failed"
        for name in rows:
            report.coverage.append(CoverageRow(name, state, reason or f"{chosen}: not a mapping"))
        return site
    site.raw = data
    report.coverage.append(CoverageRow("config", "complete", chosen + note))
    site.docs_dir = str(data.get("docs_dir", "docs")).strip("/") or "."
    site.repo_url = data.get("repo_url") if isinstance(data.get("repo_url"), str) else None
    site.site_url = data.get("site_url") if isinstance(data.get("site_url"), str) else None
    site.edit_uri = data.get("edit_uri") if isinstance(data.get("edit_uri"), str) else None
    for key in ("extra_css", "extra_javascript"):
        entries = data.get(key) or []
        values = [e.get("path", "") if isinstance(e, dict) else str(e) for e in entries] if isinstance(entries, list) else []
        setattr(site, key, values)
    theme = data.get("theme") or {}
    if isinstance(theme, dict) and theme.get("custom_dir"):
        site.custom_dir = str(theme["custom_dir"]).strip("/")
    # exclude_docs / draft_docs / not_in_nav
    bad = [k for k in ("exclude_docs", "draft_docs", "not_in_nav") if isinstance(data.get(k), Tagged)]
    if bad:
        report.coverage.append(CoverageRow("exclude_docs", "partial", f"tagged values in {', '.join(bad)}"))
    else:
        site.exclude_text = _pattern_text(data.get("exclude_docs"))
        site.exclude = GitignoreSpec(site.exclude_text)
        site.draft = GitignoreSpec(_pattern_text(data.get("draft_docs")))
        site.not_in_nav = GitignoreSpec(_pattern_text(data.get("not_in_nav")))
        report.coverage.append(CoverageRow("exclude_docs", "complete", "set" if site.exclude else "not set"))
    # nav
    if "nav" in data:
        nav_entries: list[NavEntry] = []
        problems: list[str] = []
        _flatten_nav(data["nav"], [], nav_entries, problems)
        site.nav = nav_entries
        report.coverage.append(CoverageRow("nav", "partial" if problems else "complete", "; ".join(problems) or f"{len(nav_entries)} entries"))
    else:
        report.coverage.append(CoverageRow("nav", "complete", "no explicit nav: built from the folder structure"))
    # extensions and plugins
    if site.kind == "zensical":
        explicit = "markdown_extensions" in data
        site.extensions = _zensical_extensions(data.get("markdown_extensions")) if explicit else {name: {} for name in ZENSICAL_DEFAULT_EXTENSIONS}
        plugins = data.get("plugins") or {}
        site.plugins = dict(plugins) if isinstance(plugins, dict) else {}
    else:
        explicit = True
        site.extensions = _extensions_from_mkdocs(data.get("markdown_extensions"))
        site.plugins = _plugins_from_mkdocs(data.get("plugins"))
    site.slug_style = _slug_style(site.extensions, site.kind or "", explicit)
    slug_reason = "GitHub-compatible" if site.slug_style in GITHUB_STYLES else "differs from GitHub's anchors"
    state = "partial" if site.slug_style == "unknown" else "complete"
    report.coverage.append(CoverageRow("slug_style", state, f"{site.slug_style}: {slug_reason}"))
    # redirects
    redirects = site.plugins.get("redirects")
    maps = redirects.get("redirect_maps") if isinstance(redirects, dict) else None
    if redirects is not None and maps is not None and not isinstance(maps, dict):
        report.coverage.append(CoverageRow("redirects", "partial", "redirect_maps is not a mapping"))
    else:
        site.redirects = {str(k): str(v) for k, v in (maps or {}).items()}
        report.coverage.append(CoverageRow("redirects", "complete", f"{len(site.redirects)} redirects"))
    return site


def snippet_bases(site: Site) -> list[str] | None:
    """The snippet base paths, repo-relative; None when the snippets extension is not enabled."""
    options = site.extensions.get("pymdownx.snippets")
    if options is None:
        return None
    base = options.get("base_path", ["."]) if isinstance(options, dict) else ["."]
    bases = base if isinstance(base, list) else [base]
    config_dir = str(PurePosixPath(site.config or ".").parent)
    return [normalize_path(config_dir, str(b)) or "." for b in bases]


# ---------------------------------------------------------------------------------------------
# Corpus: every Markdown file parsed once
# ---------------------------------------------------------------------------------------------


class Corpus:
    def __init__(self, repo: Repo, site: Site) -> None:
        self.repo = repo
        self.site = site
        self.docs: dict[str, MarkdownDoc] = {}
        self.unreadable: list[str] = []
        attr_list = site.config is None or "attr_list" in site.extensions
        for rel in repo.markdown_files():
            text, status = repo.text(rel)
            if text is None:
                self.unreadable.append(f"{rel} ({status})")
                continue
            self.docs[rel] = parse_markdown(rel, text, site.slug_style if site.config else None, attr_list)
        self.basenames: dict[str, list[str]] = defaultdict(list)
        for rel in self.docs:
            self.basenames[PurePosixPath(rel).name.lower()].append(rel)

    def resolve_doc(self, base_dir: str, token: str) -> str | None:
        """Find the Markdown file a path token names: relative to its file, the root, or by name."""
        for start in (base_dir, ""):
            candidate = normalize_path(start, token)
            if candidate and candidate in self.docs:
                return candidate
        if "/" not in token:
            matches = [m for m in self.basenames.get(token.lower(), []) if self.site.in_docs(m)]
            if len(matches) == 1:
                return matches[0]
        return None


# ---------------------------------------------------------------------------------------------
# Couplings: references to doc paths, headings, sections and anchors from anywhere in the repo
# ---------------------------------------------------------------------------------------------

DOC_PATH_RE = re.compile(r"(?<![\w/@.-])((?:\.\.?/)*(?:[\w@+-][\w.@+-]*/)*[\w@+-][\w.@+-]*\.md)(?:#([\w%~.:-]+))?(?![\w-])")
AFTER_PATH_RE = re.compile(
    r"""^(?:[ \t]*(?:,|:|[ \t][-–—])[ \t]*|[ \t]+)(?:"""
    r"""(?:section|sec\.|§)[ \t]*(?P<num>\d+(?:\.\d+)*)"""
    r"""|"(?P<dq>[^"\n]{2,100})"|'(?P<sq>[^'\n]{2,100})'|[“‘](?P<cq>[^”’\n]{2,100})[”’]|`(?P<bq>[^`\n]{2,100})`"""
    r"""|(?P<uq>[A-Z][\w'’ -]{2,60}?)(?=[).;"`]|$))"""
)
SECTION_RE = re.compile(r"(?:§|\bsection[ \t]+)(\d+(?:\.\d+)*)", re.IGNORECASE)
BLOB_RE = re.compile(
    r"https?://(?:github\.com/(?P<o1>[\w.-]+)/(?P<r1>[\w.-]+)/(?:blob|tree|raw|edit)/(?P<ref1>[\w.-]+)/"
    r"|raw\.githubusercontent\.com/(?P<o2>[\w.-]+)/(?P<r2>[\w.-]+)/(?P<ref2>[\w.-]+)/)"
    r"(?P<path>[^\s\"'<>)#\]`]*)(?:#(?P<frag>[^\s\"'<>)\]`]*))?"
)
# A cited heading starts with a letter, digit or quote mark and holds no path, table or escape.
CITED_HEADING_RE = re.compile(r"^[\w\"'“‘(][^/|\\\n]*$")
FILENAME_RE = re.compile(r"^[\w.-]+\.[A-Za-z]{1,5}$")
# URLs assembled at run time: "${REPOSITORY}/blob/main/docs" and then "${DOCS}/page.md".
RELATIVE_BLOB_RE = re.compile(r"(?<![\w.])/(?:blob|tree|raw)/(?:main|master|trunk|HEAD|v?\d[\w.-]*)/(?P<path>[\w@+.-]+(?:/[\w@+.-]+)*)")
INTERPOLATED_DOC_RE = re.compile(r"[}\)]/((?:[\w@+-][\w.@+-]*/)*[\w@+-][\w.@+-]*\.md)(?:#([\w%~.:-]+))?")
FREEZING_KINDS = frozenset({"code", "test", "ci", "build", "generator", "config", "shipped"})
AGENT_PREFIXES = (".agents/", ".claude/", ".serena/", ".cursor/", ".github/copilot-instructions.md", "AGENTS.md", "CLAUDE.md", "GEMINI.md")
CODE_EXTENSIONS = frozenset(
    [
        ".rs",
        ".go",
        ".py",
        ".js",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".jsx",
        ".vue",
        ".svelte",
        ".c",
        ".h",
        ".cc",
        ".cpp",
        ".hpp",
        ".java",
        ".kt",
        ".kts",
        ".swift",
        ".rb",
        ".php",
        ".cs",
        ".lua",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".ps1",
        ".blp",
        ".ui",
        ".css",
        ".scss",
    ]
)
CONFIG_EXTENSIONS = frozenset([".yml", ".yaml", ".toml", ".json", ".jsonc", ".ini", ".cfg", ".conf", ".xml", ".in", ".hcl", ".tf", ".lock"])


def _strip_dot_slash(token: str) -> str:
    """Drop leading "./" and "/" prefixes (not characters: .agents/ keeps its dot)."""
    while token.startswith(("./", "/")):
        token = token.removeprefix("./").removeprefix("/")
    return token


def source_kind(rel: str, line: str, site: Site) -> str:
    """Classify where a reference lives; code, tests, CI and generators make a path frozen."""
    path = PurePosixPath(rel)
    name = path.name
    if "go:generate" in line:
        return "generator"
    if rel.startswith(AGENT_PREFIXES):
        return "agent"
    if rel.startswith((".github/workflows/", ".gitlab-ci", ".circleci/")) or name in (
        ".pre-commit-config.yaml",
        ".goreleaser.yaml",
        ".goreleaser.yml",
    ):
        return "ci"
    if name in ("Makefile", "meson.build", "justfile", "Justfile", "Dockerfile") or path.suffix == ".mk" or name.startswith("Dockerfile"):
        return "build"
    if path.suffix.lower() in MARKDOWN_EXTENSIONS:
        return "doc" if site.in_docs(rel) else "root-doc"
    parts = set(path.parts[:-1])
    if parts & {"test", "tests", "testdata", "__tests__", "spec"} or re.search(r"(^test_|_test\.|\.test\.|\.spec\.)", name):
        return "test"
    if path.suffix.lower() in CODE_EXTENSIONS:
        return "code"
    if path.suffix.lower() in CONFIG_EXTENSIONS or name.startswith("."):
        return "config"
    return "other"


def _heading_match(doc: MarkdownDoc, text: str) -> str:
    """Whether a cited heading exists: ok, bold-label (only a bold list label) or missing."""
    wanted = heading_plain_text(text).casefold().rstrip(":. ")
    stripped = NUMBER_RE.sub("", wanted).strip()
    slug = github_slug_base(heading_plain_text(text))
    for heading in doc.headings:
        name = heading.text.casefold()
        bare = NUMBER_RE.sub("", name).strip()
        if wanted in (name, bare) or stripped == bare or heading.gh_slug == slug or bare.startswith(stripped + " ("):
            return "ok"
    if any(wanted == label.casefold() for label in doc.bold_labels):
        return "bold-label"
    return "missing"


def _this_repo(repo: Repo, site: Site) -> set[str]:
    names = set()
    for url in (repo.remote_url(), site.repo_url):
        if url:
            match = re.match(r"https?://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url)
            if match:
                names.add(f"{match.group(1)}/{match.group(2)}".lower())
    return names


def scan_couplings(corpus: Corpus, report: Report) -> list[dict[str, Any]]:
    repo, site = corpus.repo, corpus.site
    ours = _this_repo(repo, site)
    found: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    skipped: list[str] = []
    excluded = 0

    def add(entry: dict[str, Any]) -> None:
        key = (entry["source"], entry["line"], entry["ref"], entry["target"], entry.get("detail", ""))
        if key not in seen:
            seen.add(key)
            found.append(entry)

    # a restructure's own artifacts (baselines, logs, receipts, the report) name every old path on
    # purpose: they are records of the move, not references that must keep resolving
    artifact_dirs = {
        str(PurePosixPath(rel).parent)
        for rel in repo.files
        if PurePosixPath(rel).name == "plan.toml" and f"{PurePosixPath(rel).parent}/blocks.json" in repo.file_set
    }
    for rel in repo.files:
        if str(PurePosixPath(rel).parent) in artifact_dirs:
            excluded += 1
            continue
        text, status = repo.text(rel)
        if text is None:
            if status == "binary":
                excluded += 1
            else:
                skipped.append(f"{rel} ({status})")
            continue
        base_dir = str(PurePosixPath(rel).parent)
        names_us = any(name in text.lower() for name in ours)
        for number, line in enumerate(text.split("\n"), 1):
            if ".md" not in line and "github" not in line and "/blob/" not in line:
                continue
            kind = source_kind(rel, line, site)
            if names_us and "github.com" not in line:
                for match in RELATIVE_BLOB_RE.finditer(line):
                    path = match.group("path").rstrip("/.")
                    add(
                        {
                            "source": rel,
                            "line": number,
                            "kind": kind,
                            "ref": "blob",
                            "target": path,
                            "detail": match.group(0),
                            "status": "ok" if repo.exists(path) else "missing",
                        }
                    )
            for match in INTERPOLATED_DOC_RE.finditer(line):
                target = corpus.resolve_doc(base_dir, PurePosixPath(match.group(1)).name)
                if target is not None:
                    add(
                        {
                            "source": rel,
                            "line": number,
                            "kind": kind,
                            "ref": "blob" if names_us else "path",
                            "target": target,
                            "detail": match.group(0),
                            "status": "ok",
                        }
                    )
                    if match.group(2):
                        anchors = {a.lower() for a in corpus.docs[target].anchors()}
                        state = "ok" if unquote(match.group(2)).lower() in anchors else "missing"
                        add(
                            {
                                "source": rel,
                                "line": number,
                                "kind": kind,
                                "ref": "anchor",
                                "target": target,
                                "detail": "#" + match.group(2),
                                "status": state,
                            }
                        )
            for match in DOC_PATH_RE.finditer(line):
                token, frag = match.group(1), match.group(2)
                target = corpus.resolve_doc(base_dir, token)
                if target is None:
                    candidate = normalize_path("", _strip_dot_slash(token)) or ""
                    if site.in_docs(candidate) and site.docs_dir != "." and candidate.startswith(site.docs_dir + "/"):
                        add({"source": rel, "line": number, "kind": kind, "ref": "path", "target": candidate, "detail": token, "status": "missing"})
                    continue
                if target == rel:
                    continue
                doc = corpus.docs[target]
                add({"source": rel, "line": number, "kind": kind, "ref": "path", "target": target, "detail": token, "status": "ok"})
                if frag:
                    status_frag = "ok" if unquote(frag).lower() in {a.lower() for a in doc.anchors()} else "missing"
                    add({"source": rel, "line": number, "kind": kind, "ref": "anchor", "target": target, "detail": "#" + frag, "status": status_frag})
                rest = line[match.end() :]
                opener = line[match.start() - 1] if match.start() else ""
                if (opener in "`\"'" and opener and rest.startswith(opener)) or rest.startswith((")", "]")):
                    rest = rest[1:]
                after = AFTER_PATH_RE.match(rest)
                if not after:
                    continue
                if after.group("num"):
                    numbers = {h.number for h in doc.headings if h.number}
                    state = "ok" if after.group("num") in numbers else "missing"
                    add(
                        {
                            "source": rel,
                            "line": number,
                            "kind": kind,
                            "ref": "section",
                            "target": target,
                            "detail": "section " + after.group("num"),
                            "status": state,
                        }
                    )
                    continue
                quoted = after.group("dq") or after.group("sq") or after.group("cq") or after.group("bq")
                unquoted = after.group("uq")
                cited = quoted or unquoted
                if not cited or not CITED_HEADING_RE.match(cited.strip()) or FILENAME_RE.match(cited.strip()):
                    continue
                state = _heading_match(doc, cited)
                if unquoted and state != "ok":
                    continue
                if quoted and state == "missing" and " " not in cited.strip():
                    continue
                add({"source": rel, "line": number, "kind": kind, "ref": "heading", "target": target, "detail": cited.strip(), "status": state})
            for match in BLOB_RE.finditer(line):
                owner = (match.group("o1") or match.group("o2") or "").lower()
                name = (match.group("r1") or match.group("r2") or "").lower()
                if f"{owner}/{name}" not in ours:
                    continue
                path = unquote(match.group("path").rstrip("/."))
                if not path:
                    add(
                        {"source": rel, "line": number, "kind": kind, "ref": "blob-base", "target": "", "detail": match.group(0), "status": "runtime"}
                    )
                    continue
                state = "ok" if repo.exists(path) else "missing"
                add({"source": rel, "line": number, "kind": kind, "ref": "blob", "target": path, "detail": match.group(0), "status": state})
                if state == "ok" and match.group("frag") and path in corpus.docs:
                    anchors = {a.lower() for a in corpus.docs[path].anchors()}
                    frag_state = "ok" if unquote(match.group("frag")).lower() in anchors else "missing"
                    add(
                        {
                            "source": rel,
                            "line": number,
                            "kind": kind,
                            "ref": "anchor",
                            "target": path,
                            "detail": "#" + match.group("frag"),
                            "status": frag_state,
                        }
                    )
    if ".pre-commit-config.yaml" in repo.file_set:
        _precommit_couplings(repo, add, skipped)
    reason = f"{len(repo.files)} files; {excluded} binary files excluded"
    if skipped:
        report.coverage.append(CoverageRow("couplings", "partial", reason + "; not scanned: " + ", ".join(skipped[:10])))
    else:
        report.coverage.append(CoverageRow("couplings", "complete", reason))
    history = repo.ever_tracked()
    for entry in found:
        # Links in Markdown are check's job; here only citations that check cannot see.
        if entry["kind"] in ("doc", "root-doc") and entry["ref"] in ("path", "anchor"):
            continue
        if entry["status"] in ("missing", "bold-label"):
            bold = entry["status"] == "bold-label"
            pinning = entry["kind"] in FREEZING_KINDS or entry["ref"] == "blob"
            severity = "P1" if pinning and not bold else "P2"
            confidence = "likely" if entry["ref"] == "heading" or not pinning else "verified"
            reason = "a bold list label, not a heading, so it has no anchor" if bold else f"the {entry['ref']} does not exist"
            foreign = entry["ref"] == "path" and history is not None and entry["target"] not in history
            if entry["ref"] == "regex":
                severity, confidence = "P2", "likely"
                reason = "the pattern names a file that is not in the repository, so the hook never sees it"
            elif foreign:
                # A path no commit ever held is more often another repository's file than a stale link.
                severity, confidence = "P3", "unverified"
                reason += " and no commit ever held it; it may name a file in another repository"
            cited = entry["target"] if entry["detail"] in ("", entry["target"]) else f"{entry['target']} {entry['detail']}"
            report.add(
                Finding(
                    "coupling-bold-label" if bold else "coupling-missing",
                    severity,
                    confidence,
                    entry["source"],
                    entry["line"],
                    f"cites {cited}: " + reason,
                    [f"{entry['kind']} reference"],
                    "promote the label to a heading or cite the enclosing heading" if bold else "update the citation or restore the target",
                )
            )
    return found


MD_TOKEN_RE = re.compile(r"[\w][\w./-]*\.(?:md|markdown)\b")


def _precommit_couplings(repo: Repo, add: Callable[[dict[str, Any]], None], skipped: list[str]) -> None:
    """pre-commit files:/exclude: regexes (Python re.search on repo paths) that name Markdown files."""
    rel = ".pre-commit-config.yaml"
    text, _ = repo.text(rel)
    if text is None:
        return  # the file scan already reported it
    lines = text.split("\n")
    patterns: list[tuple[str, str, str]] = []
    try:
        data = yaml_load(text)
    except YamlError as error:
        # The YAML subset stops at constructs elsewhere in the file (a multi-line args list, say);
        # single-line files:/exclude: scalars are still read exactly, anything else stays unread.
        unread = _precommit_line_patterns(lines, patterns)
        if unread:
            skipped.append(f"{rel} (files:/exclude: on lines {', '.join(map(str, unread[:5]))} not read: {error})")
    else:
        if not isinstance(data, dict):
            return
        patterns += [("(top level)", key, data[key]) for key in ("files", "exclude") if isinstance(data.get(key), str)]
        for entry in data.get("repos") or []:
            for hook in (entry.get("hooks") or []) if isinstance(entry, dict) else []:
                if isinstance(hook, dict):
                    patterns += [(str(hook.get("id", "?")), key, hook[key]) for key in ("files", "exclude") if isinstance(hook.get(key), str)]
    markdown = repo.markdown_files()
    for hook_id, key, pattern in patterns:
        try:
            regex = re.compile(pattern)
        except re.error as error:
            skipped.append(f"{rel} (hook {hook_id} {key}: {error})")
            continue
        chunk = pattern.strip().split("\n", 1)[0].strip()[:24]
        number = next((i for i, line in enumerate(lines, 1) if chunk and chunk in line), 0)
        number = number or next((i for i, line in enumerate(lines, 1) if re.search(rf"\bid:\s*{re.escape(hook_id)}\s*$", line)), 1)
        literal = pattern.replace("\\", "")
        tokens = set(MD_TOKEN_RE.findall(literal))
        detail = f"{hook_id} {key}: {pattern.strip()}"
        for path in markdown:
            # Only a pattern that names the file pins it; a broad one (\.md$) still matches after a move.
            stem = re.escape(PurePosixPath(path).stem)
            if regex.search(path) and re.search(rf"(?<![\w-]){stem}(?![\w-])", literal):
                add({"source": rel, "line": number, "kind": "ci", "ref": "regex", "target": path, "detail": detail, "status": "ok"})
        for token in sorted(tokens):
            if not any(path == token or path.endswith("/" + token) for path in repo.files):
                add({"source": rel, "line": number, "kind": "ci", "ref": "regex", "target": token, "detail": detail, "status": "missing"})


PRECOMMIT_KEY_RE = re.compile(r"^[ \t]*(?:-[ \t]+)?(files|exclude):[ \t]*(.*)$")
PRECOMMIT_ID_RE = re.compile(r"^[ \t]*(?:-[ \t]+)?id:[ \t]*([^\s#]+)")


def _precommit_line_patterns(lines: list[str], patterns: list[tuple[str, str, str]]) -> list[int]:
    """Read single-line files:/exclude: scalars line by line; return the lines that could not be read."""
    unread: list[int] = []
    hook_id = "(top level)"
    for number, line in enumerate(lines, 1):
        found_id = PRECOMMIT_ID_RE.match(line)
        if found_id:
            hook_id = found_id.group(1).strip("'\"")
        match = PRECOMMIT_KEY_RE.match(line)
        if not match:
            continue
        value = match.group(2).strip()
        if value.startswith("'") and value.endswith("'") and len(value) > 1:
            patterns.append((hook_id, match.group(1), value[1:-1].replace("''", "'")))
        elif value.startswith('"') and value.endswith('"') and len(value) > 1 and "\\" not in value:
            patterns.append((hook_id, match.group(1), value[1:-1]))
        elif value and value[0] not in "|>'\"[{&*!" and " #" not in value:
            patterns.append((hook_id, match.group(1), value))
        else:
            unread.append(number)
    return unread


def frozen_paths(couplings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Doc paths and headings a restructure must keep, with the references that pin them."""
    frozen: dict[str, dict[str, Any]] = {}
    for entry in couplings:
        if entry["status"] != "ok" or not entry["target"]:
            continue
        pins = entry["kind"] in FREEZING_KINDS or entry["ref"] == "blob"
        if not pins:
            continue
        item = frozen.setdefault(entry["target"], {"path": [], "headings": defaultdict(list)})
        where = f"{entry['source']}:{entry['line']}"
        if entry["ref"] in ("path", "blob"):
            item["path"].append(where)
        else:
            item["headings"][entry["detail"]].append(where)
    return {k: {"path": v["path"], "headings": dict(v["headings"])} for k, v in sorted(frozen.items())}


# ---------------------------------------------------------------------------------------------
# Inventory analyses: enum headings, duplicates, lifecycle, page type, house style, census
# ---------------------------------------------------------------------------------------------

LITERAL_RE = re.compile(r"""(?<![\w\\])(?:"([^"\\\n]{2,80})"|'([^'\\\n]{2,80})'|`([^`\\\n]{2,80})`)""")


def code_literals(repo: Repo, site: Site) -> dict[str, str]:
    """String literals in code files, mapped to the first file that has each."""
    literals: dict[str, str] = {}
    for rel in repo.files:
        if source_kind(rel, "", site) not in ("code", "test", "generator"):
            continue
        text, _ = repo.text(rel)
        if text is None:
            continue
        for match in LITERAL_RE.finditer(text):
            value = match.group(1) or match.group(2) or match.group(3)
            literals.setdefault(value, rel)
    return literals


def enum_headings(corpus: Corpus, literals: dict[str, str]) -> list[dict[str, Any]]:
    """Sibling headings that spell code string literals: headings used as a machine interface."""
    groups: list[dict[str, Any]] = []
    for rel, doc in corpus.docs.items():
        siblings: dict[tuple[int, int], list[Heading]] = defaultdict(list)
        for heading in doc.headings:
            siblings[(heading.parent, heading.level)].append(heading)
        for (parent, _level), items in siblings.items():
            if len(items) < 3:
                continue
            hits = [h for h in items if h.text in literals or h.gh_slug in literals]
            if len(hits) >= 3 and len(hits) >= 0.75 * len(items):
                groups.append(
                    {
                        "file": rel,
                        "parent": doc.headings[parent].text if parent >= 0 else "",
                        "line": items[0].line,
                        "headings": [h.text for h in hits],
                        "count": len(hits),
                        "code": sorted({literals.get(h.text) or literals.get(h.gh_slug) or "" for h in hits}),
                    }
                )
    return groups


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def duplicates(corpus: Corpus) -> dict[str, list[dict[str, Any]]]:
    """Exact and near-duplicate prose and code across the Markdown files."""
    exact: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    shingle_index: dict[int, set[int]] = defaultdict(set)
    paragraphs: list[tuple[str, int, set[int], str]] = []
    for rel, doc in corpus.docs.items():
        for block in doc.blocks:
            if block.type in ("heading", "refdef", "table-row"):
                continue
            text = _norm(block.text)
            if (block.type == "code" and len(text) >= 30) or len(text) >= 80:
                exact[hashlib.sha256(text.encode()).hexdigest()].append((rel, block.line, block.type))
            words = text.split()
            if block.type in ("paragraph", "list-item") and len(words) >= 25:
                shingles = {hash(" ".join(words[i : i + 5])) for i in range(len(words) - 4)}
                index = len(paragraphs)
                paragraphs.append((rel, block.line, shingles, text))
                for s in shingles:
                    shingle_index[s].add(index)
    exact_groups = [
        {"kind": occurrences[0][2], "occurrences": [f"{r}:{n}" for r, n, _ in occurrences]} for occurrences in exact.values() if len(occurrences) > 1
    ]
    near: list[dict[str, Any]] = []
    candidates: Counter[tuple[int, int]] = Counter()
    for members in shingle_index.values():
        if 1 < len(members) <= 50:
            ordered = sorted(members)
            for i, a in enumerate(ordered):
                for b in ordered[i + 1 :]:
                    candidates[(a, b)] += 1
    for (a, b), shared in candidates.items():
        sa, sb = paragraphs[a][2], paragraphs[b][2]
        score = shared / len(sa | sb)
        if score >= NEAR_DUPLICATE and paragraphs[a][3] != paragraphs[b][3]:
            near.append(
                {"similarity": round(score, 2), "occurrences": [f"{paragraphs[a][0]}:{paragraphs[a][1]}", f"{paragraphs[b][0]}:{paragraphs[b][1]}"]}
            )
    near.sort(key=lambda n: -n["similarity"])
    repo_files: dict[str, str] = {}
    for rel in corpus.repo.files:
        if rel.lower().endswith(MARKDOWN_EXTENSIONS):
            continue
        body, _ = corpus.repo.text(rel)
        if body is not None and 40 <= len(body) <= 20000 and body.count("\n") >= 2:
            repo_files[hashlib.sha256(_norm(body).encode()).hexdigest()] = rel
    copies = []
    for rel, doc in corpus.docs.items():
        for _info, content, line in doc.code_blocks:
            digest = hashlib.sha256(_norm(content).encode()).hexdigest()
            if digest in repo_files and content.count("\n") >= 2:
                copies.append({"block": f"{rel}:{line}", "file": repo_files[digest]})
    return {"exact": exact_groups, "near": near[:100], "code_copies_of_files": copies}


LIFECYCLE_NAME_RE = re.compile(
    r"(plan|spike|round|draft|analysis|todo|roadmap|research|notes?|qa|preparation|hands-on|call-for|retro|postmortem|rfc|proposal)", re.IGNORECASE
)
RECORD_DIRS = frozenset(
    {"spikes", "spike", "research", "qa", "archive", "history", "rounds", "notes", "plans", "harness-runs", "retros", "postmortems"}
)
DATED_RE = re.compile(r"\b(?:done|completed?|as of|checked|verified|implemented|fixed)\b[^.\n]{0,40}\b20\d\d-\d\d(?:-\d\d)?\b", re.IGNORECASE)
MILESTONE_RE = re.compile(r"\b[MSR]\d{1,2}\b")
FIRST_PERSON_RE = re.compile(r"(?:^|[\s(])(?:I|I'm|I've|I'll|my)\s", re.MULTILINE)


def lifecycle(doc: MarkdownDoc, inbound: int) -> dict[str, Any]:
    reasons = []
    ticked, open_ = doc.tasks["x"], doc.tasks[" "]
    if ticked + open_ >= 5 and ticked / (ticked + open_) >= TICKED_RATIO:
        reasons.append(f"{ticked} of {ticked + open_} task items ticked")
    text = "\n".join(doc.lines)
    dated = len(DATED_RE.findall(text))
    if dated >= 5:
        reasons.append(f"{dated} dated done/as-of statements")
    milestones = len(set(MILESTONE_RE.findall(text)))
    if milestones >= 10:
        reasons.append(f"{milestones} milestone or spike ids")
    name = LIFECYCLE_NAME_RE.search(PurePosixPath(doc.path).stem)
    if name:
        reasons.append(f"file name says {name.group(1).lower()!r}")
    if re.match(r"\d{4}-\d{2}-\d{2}", PurePosixPath(doc.path).name):
        reasons.append("dated file name")
    record_dirs = sorted(set(PurePosixPath(doc.path).parts[:-1]) & RECORD_DIRS)
    if record_dirs:
        reasons.append(f"lives in {record_dirs[0]}/")
    first_person = len(FIRST_PERSON_RE.findall(text))
    if first_person >= 3:
        reasons.append(f"{first_person} first-person sentences")
    if doc.banners:
        reasons.append(f"status banner at line {doc.banners[0][0]}")
    if inbound == 0 and PurePosixPath(doc.path).name.lower() not in ("readme.md", "index.md"):
        reasons.append("no current page links to it")
    prose = [b for b in doc.blocks if b.type in ("paragraph", "list-item")]
    linky = [b for b in prose if re.search(r"\]\(", b.text)]
    strong = [r for r in reasons if "no current page" not in r]
    if prose and len(linky) / len(prose) >= INDEX_LINK_RATIO and len(doc.lines) < 150:
        hint = "index"
    elif any("'draft'" in r or "'call-for'" in r for r in reasons) or first_person >= 5:
        hint = "draft"
    elif len(strong) >= 2 or any(r.startswith(("lives in", "status banner")) for r in reasons):
        hint = "record"
    else:
        hint = "living"
    return {"hint": hint, "reasons": reasons}


DIATAXIS = (
    ("tutorial", re.compile(r"tutorial|getting[- ]started|quick[- ]?start|first steps|walkthrough", re.IGNORECASE)),
    (
        "how-to",
        re.compile(r"how[- ]to|install|deploy|troubleshoot|upgrad|migrat|releas|setup|set up|configur(?:e|ing)|adding|contributing", re.IGNORECASE),
    ),
    (
        "reference",
        re.compile(
            r"reference|\bapi\b|\bcli\b|commands?|options|configuration|schema|format|protocol|spec|compatib|glossary|faq|changelog", re.IGNORECASE
        ),
    ),
    (
        "explanation",
        re.compile(r"architecture|design|concepts?|overview|why|explanation|security|principles|decisions?|internals|how it works", re.IGNORECASE),
    ),
)


def diataxis(doc: MarkdownDoc) -> str:
    title = doc.headings[0].text if doc.headings else ""
    for kind, pattern in DIATAXIS:
        if pattern.search(PurePosixPath(doc.path).stem) or pattern.search(title):
            return kind
    tables = sum(1 for b in doc.blocks if b.type == "table-row")
    return "reference" if tables > 20 else "unknown"


def house_style(corpus: Corpus) -> dict[str, Any]:
    widths: list[int] = []
    markers: Counter[str] = Counter()
    fences: Counter[str] = Counter()
    sentence = title_case = numbered = 0
    for doc in corpus.docs.values():
        for block in doc.blocks:
            if block.type == "paragraph":
                widths += [len(doc.lines[block.line - 1])]
        for line in doc.lines:
            item = LIST_RE.match(line)
            if item and not item.group("marker")[0].isdigit():
                markers[item.group("marker")] += 1
        fences["```"] += doc.features["code-fence"]
        fences["~~~"] += doc.features["tilde-fence"]
        for heading in doc.headings[1:]:
            words = [w for w in re.findall(r"[A-Za-z][\w'-]*", heading.text) if len(w) > 3]
            if heading.number:
                numbered += 1
            if len(words) >= 2:
                if all(w[0].isupper() for w in words):
                    title_case += 1
                else:
                    sentence += 1
    widths.sort()
    wrap = widths[int(len(widths) * 0.95)] if widths else 0
    return {
        "wrap_p95": wrap,
        "list_marker": markers.most_common(1)[0][0] if markers else None,
        "fence": fences.most_common(1)[0][0] if fences.total() else None,
        "heading_case": "title" if title_case > sentence else "sentence",
        "numbered_headings": numbered,
    }


ROOT_FILES = (
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "RELEASING.md",
    "CHANGELOG.md",
    "LICENSE",
    "AGENTS.md",
    "CLAUDE.md",
    "SUPPORT.md",
    "GOVERNANCE.md",
)


def root_census(repo: Repo) -> dict[str, Any]:
    present = {}
    for name in ROOT_FILES:
        hits = [f for f in (name, f".github/{name}", f"docs/{name}") if f in repo.file_set]
        if name == "LICENSE":
            hits = [f for f in repo.files if "/" not in f and f.upper().startswith(("LICENSE", "COPYING"))]
        present[name] = hits
    templates = [f for f in repo.files if f.startswith(".github/") and ("ISSUE_TEMPLATE" in f or "PULL_REQUEST_TEMPLATE" in f.upper())]
    return {"files": present, "github_templates": templates}


def changelog_generators(repo: Repo) -> list[str]:
    found = []
    checks: dict[str, Callable[[str], bool]] = {
        "goreleaser": lambda f: PurePosixPath(f).name in (".goreleaser.yaml", ".goreleaser.yml"),
        "release-please": lambda f: "release-please" in f,
        "git-cliff": lambda f: PurePosixPath(f).name == "cliff.toml",
        "changesets": lambda f: f.startswith(".changeset/"),
        "semantic-release": lambda f: PurePosixPath(f).name.startswith(".releaserc"),
        "towncrier": lambda f: PurePosixPath(f).name in ("towncrier.toml",) or f.startswith("changelog.d/"),
    }
    for name, test in checks.items():
        hits = [f for f in repo.files if test(f)]
        if hits:
            found.append(f"{name} ({hits[0]})")
    for rel in repo.files:
        if rel.startswith((".github/workflows/", "scripts/", ".mk/")) or PurePosixPath(rel).name == "Makefile":
            text, _ = repo.text(rel)
            if text and "--generate-notes" in text:
                found.append(f"gh release --generate-notes ({rel})")
                break
    return found


# a test of Markdown links: "link" or "links" on its own or as an identifier part (test_no_broken_links),
# not inside a word (symlink, linker); or slugs
LINK_TEST_RE = re.compile(r"(?<![a-z])links?(?![a-z])|slug", re.IGNORECASE)


def tooling_census(repo: Repo) -> dict[str, Any]:
    names = {PurePosixPath(f).name for f in repo.files}
    result: dict[str, Any] = {
        "lychee": any(n in names for n in ("lychee.toml", ".lycheeignore")),
        "markdownlint": sorted(f for f in repo.files if PurePosixPath(f).name.startswith(".markdownlint")),
        "vale": ".vale.ini" in names,
        "link_tests": [],
    }
    precommit, _ = repo.text(".pre-commit-config.yaml") if ".pre-commit-config.yaml" in repo.file_set else (None, "")
    if precommit and "lychee" in precommit:
        result["lychee"] = True
    for rel in result["markdownlint"]:
        text, _ = repo.text(rel)
        match = re.search(r"line_length\D{0,4}(\d+)", text or "")
        if match:
            result["markdown_wrap"] = int(match.group(1))
    for rel in repo.files:
        if source_kind(rel, "", Site()) == "test":
            text, _ = repo.text(rel)
            if text and ".md" in text and LINK_TEST_RE.search(text):
                result["link_tests"].append(rel)
    return result


def inbound_links(corpus: Corpus) -> Counter[str]:
    counts: Counter[str] = Counter()
    for rel, doc in corpus.docs.items():
        base = str(PurePosixPath(rel).parent)
        for link in doc.links:
            target = link.target.split("#", 1)[0]
            if target and not re.match(r"^[a-z][a-z0-9+.-]*:", target):
                resolved = normalize_path(base, unquote(target))
                if resolved and resolved != rel:
                    counts[resolved] += 1
    return counts


# ---------------------------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------------------------

SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:|^//")


def _blob_suggestion(site: Site, repo: Repo, target: str) -> str:
    base = site.repo_url or repo.remote_url() or "https://github.com/OWNER/REPO"
    return f"link to {base.rstrip('/')}/blob/main/{target} (outside docs_dir the site cannot serve it)"


def check_links(corpus: Corpus, report: Report, scope: set[str]) -> dict[str, int]:
    repo, site = corpus.repo, corpus.site
    stats: Counter[str] = Counter()
    for rel in sorted(scope):
        doc = corpus.docs[rel]
        base = str(PurePosixPath(rel).parent)
        published = site.published(rel)
        for link in doc.links:
            stats[link.kind] += 1
            target = link.target.strip()
            if not target or SCHEME_RE.match(target):
                stats["external"] += 1
                continue
            path_part, _, fragment = target.partition("#")
            path_part = unquote(path_part.split("?", 1)[0])
            fragment = unquote(fragment)
            resolved = rel if not path_part else normalize_path(base, path_part)
            noun = "image" if link.kind in ("image", "html-src") else "link"
            if resolved is None:
                report.add(
                    Finding(
                        f"broken-{noun}",
                        "P1",
                        "verified",
                        rel,
                        link.line,
                        f"{target} leaves the repository",
                        suggestion="link inside the repository or use an absolute URL",
                    )
                )
                continue
            if not repo.exists(resolved) and resolved != ".":
                cased = repo.lower_map.get(resolved.lower())
                if cased:
                    report.add(
                        Finding(
                            f"broken-{noun}",
                            "P1",
                            "verified",
                            rel,
                            link.line,
                            f"{target}: the file is {cased[0]} (case differs; GitHub and Linux are case-sensitive)",
                            suggestion=f"use {cased[0]}",
                        )
                    )
                else:
                    report.add(Finding(f"broken-{noun}", "P1", "verified", rel, link.line, f"{target}: {resolved} does not exist"))
                continue
            target_doc = corpus.docs.get(resolved) or corpus.docs.get(repo.canonical(resolved))
            if fragment and target_doc is not None:
                anchors = {a.lower() for a in target_doc.anchors()}
                if fragment.lower() not in anchors:
                    near = [h.gh_slug for h in target_doc.headings if fragment.lower().strip("-") in h.gh_slug][:3]
                    evidence = [f"close matches: {', '.join(near)}"] if near else []
                    if fragment in target_doc.anchors(site=True):
                        evidence.insert(0, f"#{fragment} is an explicit {{#id}} the site knows; GitHub shows the attribute list as text")
                    report.add(
                        Finding(
                            "broken-anchor",
                            "P1",
                            "verified",
                            rel,
                            link.line,
                            f"{target}: {resolved} has no heading or id #{fragment}",
                            evidence,
                            "point at an existing heading's GitHub anchor",
                        )
                    )
                    continue
            if not published:
                continue
            if not site.in_docs(resolved):
                report.add(
                    Finding(
                        "leaves-docs-dir",
                        "P1",
                        "verified",
                        rel,
                        link.line,
                        f"{target} points outside {site.docs_dir}/, which the site does not contain",
                        suggestion=_blob_suggestion(site, repo, resolved),
                    )
                )
                continue
            if resolved in corpus.docs and not site.published(resolved):
                report.add(
                    Finding(
                        "links-unpublished",
                        "P1",
                        "verified",
                        rel,
                        link.line,
                        f"published page links to {resolved}, which the site excludes (exclude_docs or draft_docs); zensical build --strict fails",
                        suggestion="move the fact to a published page or drop the link; internal pages may link to published ones, not the reverse",
                    )
                )
                continue
            if fragment and target_doc is not None and site.slug_style != "unknown":
                # With a custom slugify docstool cannot know the site's ids; the slug_style row says so.
                site_anchors = target_doc.anchors(site=True)
                if fragment not in site_anchors:
                    gh = next((h for h in target_doc.headings if h.gh_slug == fragment.lower()), None)
                    report.add(
                        Finding(
                            "slug-divergence",
                            "P1",
                            "verified",
                            rel,
                            link.line,
                            f"#{fragment} works on GitHub but the site names that heading #{gh.site_slug if gh else '?'} ({site.slug_style} slugs)",
                            [f"{resolved}:{gh.line} {gh.text}"] if gh else [],
                            'set toc.slugify = { object = "pymdownx.slugs.slugify", kwds = { case = "lower" } } or give the heading an explicit {#id}',
                        )
                    )
        for label, line in doc.ref_uses:
            if not label.startswith("?") and label not in doc.ref_defs:
                report.add(Finding("undefined-reference", "P2", "verified", rel, line, f"reference [{label}] has no definition"))
        used = {label.lstrip("?") for label, _ in doc.ref_uses}
        for label, (_target, line) in doc.ref_defs.items():
            if label not in used:
                report.add(Finding("unused-reference", "P3", "verified", rel, line, f"reference definition [{label}] is never used"))
    return dict(stats)


def check_structure(corpus: Corpus, report: Report, scope: set[str]) -> None:
    site = corpus.site
    for rel in sorted(scope):
        doc = corpus.docs[rel]
        h1 = [h for h in doc.headings if h.level == 1]
        if len(h1) > 1:
            report.add(Finding("heading-structure", "P3", "verified", rel, h1[1].line, f"{len(h1)} level-1 headings; a page has one title"))
        previous = 0
        for heading in doc.headings:
            if previous and heading.level > previous + 1:
                report.add(
                    Finding("heading-structure", "P3", "verified", rel, heading.line, f"heading level jumps from {previous} to {heading.level}")
                )
            previous = heading.level
        if site.published(rel):
            seen: dict[str, Heading] = {}
            for heading in doc.headings:
                base = github_slug_base(heading_plain_text(heading.raw))
                if base in seen and not heading.explicit_id:
                    report.add(
                        Finding(
                            "duplicate-heading",
                            "P2",
                            "verified",
                            rel,
                            heading.line,
                            f"repeats {heading.text!r} (line {seen[base].line}): "
                            + (
                                f"the site anchors it #{heading.site_slug}, GitHub #{heading.gh_slug}"
                                if site.slug_style != "unknown"
                                else f"GitHub anchors it #{heading.gh_slug}; the site's custom slugify decides its id there"
                            ),
                            suggestion="rename one heading or give it an explicit {#id}",
                        )
                    )
                seen.setdefault(base, heading)
        for line in doc.odd_tasks:
            report.add(
                Finding(
                    "task-marker",
                    "P3",
                    "verified",
                    rel,
                    line,
                    "[-] is not a task-list marker on GitHub or the site; it renders as literal text",
                    suggestion="use [ ] or [x], or say in words that the item was dropped",
                )
            )
        for start, _end, label in doc.regions:
            if "no END marker" in label:
                report.add(Finding("generated-region", "P2", "verified", rel, start, f"generated region opened here is never closed ({label})"))


def check_site(corpus: Corpus, report: Report) -> None:
    repo, site = corpus.repo, corpus.site
    if site.config is None:
        return
    published = sorted(r for r in corpus.docs if site.published(r))
    docs_prefix = "" if site.docs_dir == "." else site.docs_dir + "/"
    if site.nav is not None:
        listed = set()
        for entry in site.nav:
            if SCHEME_RE.match(entry.target):
                continue
            target = docs_prefix + entry.target.split("#", 1)[0].lstrip("/")
            listed.add(target)
            if not repo.exists(target):
                report.add(
                    Finding(
                        "nav-missing",
                        "P1",
                        "verified",
                        site.config,
                        0,
                        f"nav entry {' > '.join([*entry.path, entry.title]).strip(' >')!r} points at {entry.target}, which does not exist",
                    )
                )
            elif target in corpus.docs and not site.published(target):
                report.add(Finding("nav-missing", "P1", "verified", site.config, 0, f"nav entry {entry.target} is excluded from the site"))
        for rel in published:
            inner = site.docs_rel(rel)
            if rel not in listed and not site.not_in_nav.match(inner) and inner not in ("index.md", "README.md"):
                report.add(
                    Finding(
                        "orphan-page",
                        "P3",
                        "verified",
                        rel,
                        0,
                        "published but not in nav: reachable only by search or a direct link",
                        suggestion="add it to nav or list it in not_in_nav",
                    )
                )
    for key in ("extra_css", "extra_javascript"):
        for entry in getattr(site, key):
            if SCHEME_RE.match(entry):
                continue
            candidates = [docs_prefix + entry.lstrip("/")]
            if site.custom_dir:
                candidates.append(f"{site.custom_dir}/{entry.lstrip('/')}")
            if not any(repo.exists(c) for c in candidates):
                report.add(
                    Finding(
                        "missing-asset",
                        "P1",
                        "verified",
                        site.config,
                        0,
                        f"{key} entry {entry} exists in neither {site.docs_dir}/ nor custom_dir; a strict build does not catch this",
                    )
                )
    if site.custom_dir and not repo.exists(site.custom_dir):
        report.add(Finding("missing-asset", "P1", "verified", site.config, 0, f"custom_dir {site.custom_dir} does not exist"))
    for source, target in site.redirects.items():
        page = docs_prefix + target.split("#", 1)[0]
        if not SCHEME_RE.match(target) and not repo.exists(page):
            report.add(Finding("redirect-target", "P1", "verified", site.config, 0, f"redirect {source} -> {target}: the target page does not exist"))
        old = docs_prefix + source.split("#", 1)[0]
        if "#" not in source and old in corpus.docs and site.published(old):
            report.add(
                Finding("redirect-target", "P1", "verified", site.config, 0, f"redirect source {source} is still a page; the redirect is never used")
            )
    internal = docs_prefix + "internal/"
    if any(r.startswith(internal) for r in corpus.docs) and not site.exclude.match("internal/x.md"):
        report.add(
            Finding(
                "internal-published",
                "P1",
                "verified",
                site.config,
                0,
                f"{internal} exists but exclude_docs does not exclude it, so it is published",
                suggestion='set exclude_docs = "internal/"',
            )
        )
    bases = snippet_bases(site)
    for rel in published:
        doc = corpus.docs[rel]
        for path, line in doc.snippets:
            if bases is None:
                report.add(
                    Finding(
                        "snippet",
                        "P2",
                        "verified",
                        rel,
                        line,
                        f"--8<-- {path!r} needs the pymdownx.snippets extension, which the site does not enable",
                    )
                )
                continue
            name = re.sub(r":(\d+(?::\d+)?|[\w-]+)$", "", path) if not any(repo.exists(normalize_path(b, path) or "") for b in bases) else path
            if not any(repo.exists(normalize_path(b, name) or "") for b in bases):
                report.add(Finding("snippet", "P1", "verified", rel, line, f"snippet {path!r} is not found under base_path {bases}"))
    home = corpus.docs.get(docs_prefix + "index.md") or corpus.docs.get(docs_prefix + "README.md")
    if home is not None and isinstance(home.front_matter, dict) and isinstance(home.front_matter.get("home"), dict):
        for action in home.front_matter["home"].get("actions") or []:
            link = str(action.get("link", "")) if isinstance(action, dict) else ""
            if link and not SCHEME_RE.match(link) and not _site_page_exists(repo, docs_prefix, link):
                report.add(
                    Finding(
                        "home-link", "P1", "verified", home.path, 1, f"home action {action.get('text', '')!r} links to {link}, which is not a page"
                    )
                )
    for rel in published:
        doc = corpus.docs[rel]
        if doc.front_matter_error:
            report.add(Finding("front-matter", "P1", "unverified", rel, 1, f"front matter could not be read: {doc.front_matter_error}"))


def _site_page_exists(repo: Repo, docs_prefix: str, link: str) -> bool:
    path = link.split("#", 1)[0].strip("/")
    if path.endswith(".md"):
        return repo.exists(docs_prefix + path)
    candidates = (
        [f"{docs_prefix}{path}.md", f"{docs_prefix}{path}/index.md", f"{docs_prefix}{path}/README.md"] if path else [f"{docs_prefix}index.md"]
    )
    return any(repo.exists(c) for c in candidates)


def select_scope(corpus: Corpus, scope: str) -> set[str]:
    site = corpus.site
    if scope == "docs":
        return {r for r in corpus.docs if site.in_docs(r)}
    if scope == "repo":
        return {r for r in corpus.docs if "/" not in r or r.startswith(".github/")}
    return set(corpus.docs)


def cmd_check(args: argparse.Namespace, report: Report) -> list[str]:
    repo = Repo(Path(args.root))
    site = load_site(repo, report)
    corpus = Corpus(repo, site)
    report.coverage.append(
        CoverageRow("markdown", "partial" if corpus.unreadable else "complete", ", ".join(corpus.unreadable) or f"{len(corpus.docs)} files")
    )
    scope = select_scope(corpus, args.scope)
    report.data["files_checked"] = len(scope)
    report.data["links"] = check_links(corpus, report, scope)
    check_structure(corpus, report, scope)
    if args.scope != "repo":
        check_site(corpus, report)
    required = ["config", "nav", "exclude_docs", "markdown"]
    if args.baseline and not args.built:
        raise UsageError("--baseline needs --built NEW_SITE (a docstool site-build output)")
    built = load_built(args.built, repo, site) if args.built else None
    if args.save_baseline:
        if built is not None:
            baseline = {
                "kind": "built",
                "generator": built.get("generator"),
                "generator_version": built.get("generator_version"),
                "dependencies": built.get("dependencies"),
                "unknown_dependencies": built.get("unknown_dependencies", []),
                **built["site"],
            }
            if built.get("dependencies") == "complete":
                report.coverage.append(CoverageRow("url_baseline", "complete", f"built by {built.get('generator')} {built.get('generator_version')}"))
            else:
                report.coverage.append(_url_baseline_row(baseline, {"dependencies": "complete"}))
        else:
            baseline = {"kind": "source", **source_url_baseline(corpus)}
            report.coverage.append(CoverageRow("url_baseline", "partial", "source-derived (no --built): preservation partially verified"))
        _write_output(_root_path(args, args.save_baseline), json.dumps(baseline, indent=1, ensure_ascii=False) + "\n")
        report.data["baseline_written"] = args.save_baseline
    elif args.baseline and built is not None:
        old = _read_json(_root_path(args, args.baseline))
        if not isinstance(old, dict) or "routes" not in old:
            raise UsageError(f"{args.baseline}: not a URL baseline written by check --save-baseline")
        compare_url_baseline(old, built["site"], report, args.baseline)
        report.coverage.append(_url_baseline_row(old, built))
        required.append("url_baseline")
    elif built is not None:
        report.coverage.append(CoverageRow("built_site", "complete", f"{len(built['site']['routes'])} routes"))
    return required


def _url_baseline_row(old: dict[str, Any], built: dict[str, Any]) -> CoverageRow:
    """URL preservation is verified only when both builds came from a generator run that saw every input."""
    reasons = []
    if old.get("kind") != "built":
        reasons.append("the baseline is source-derived")
    elif old.get("dependencies") != "complete":
        reasons.append("the baseline build had unknown dependencies (" + "; ".join(old.get("unknown_dependencies", [])[:3]) + ")")
    if built.get("dependencies") != "complete":
        reasons.append("the new build has unknown dependencies (" + "; ".join(built.get("unknown_dependencies", [])[:3]) + ")")
    if reasons:
        return CoverageRow("url_baseline", "partial", ", ".join(reasons) + ": preservation partially verified")
    return CoverageRow("url_baseline", "complete", f"{len(old['routes'])} routes")


# ---------------------------------------------------------------------------------------------
# inventory
# ---------------------------------------------------------------------------------------------


def block_baseline(corpus: Corpus) -> list[dict[str, Any]]:
    """Typed blocks with provenance and a hash of their normalised content (content conservation)."""
    out = []
    for rel in sorted(corpus.docs):
        for block in corpus.docs[rel].blocks:
            text = block.text if block.type == "code" else " ".join(block.text.split())
            digest = _block_hash(block)
            out.append(
                {
                    "file": rel,
                    "line": block.line,
                    "type": block.type,
                    "depth": block.depth,
                    "position": block.position,
                    "heading_path": block.heading_path,
                    "info": block.info,
                    "hash": digest,
                    "text": text,
                }
            )
    return out


def cmd_inventory(args: argparse.Namespace, report: Report) -> list[str]:
    repo = Repo(Path(args.root))
    site = load_site(repo, report)
    corpus = Corpus(repo, site)
    report.coverage.append(
        CoverageRow("markdown", "partial" if corpus.unreadable else "complete", ", ".join(corpus.unreadable) or f"{len(corpus.docs)} files")
    )
    inbound = inbound_links(corpus)
    files = {}
    for rel, doc in sorted(corpus.docs.items()):
        if args.section == "root" and "/" in rel and not rel.startswith(".github/"):
            continue
        if args.section == "docs" and not site.in_docs(rel):
            continue
        link_kinds: Counter[str] = Counter()
        base = str(PurePosixPath(rel).parent)
        for link in doc.links:
            target = link.target
            if SCHEME_RE.match(target):
                link_kinds["external"] += 1
                continue
            resolved = normalize_path(base, unquote(target.split("#", 1)[0])) if target.split("#", 1)[0] else rel
            if resolved and site.in_docs(rel) and not site.in_docs(resolved):
                link_kinds["leaves_docs_dir"] += 1
            elif resolved and site.config and site.in_docs(resolved) and not site.published(resolved) and resolved != rel:
                link_kinds["into_unpublished"] += 1
            else:
                link_kinds["internal"] += 1
        files[rel] = {
            "lines": len(doc.lines),
            "published": site.published(rel),
            "headings": [
                {"level": h.level, "text": h.text, "line": h.line, "github": h.gh_slug, "site": h.site_slug, "number": h.number} for h in doc.headings
            ],
            "front_matter": sorted(doc.front_matter) if isinstance(doc.front_matter, dict) else None,
            "features": dict(doc.features),
            "links": dict(link_kinds),
            "generated_regions": [{"start": s, "end": e, "marker": m} for s, e, m in doc.regions],
            "banners": [{"line": n, "text": t} for n, t in doc.banners],
            "lifecycle": lifecycle(doc, inbound[rel]),
            "diataxis": diataxis(doc),
            "inbound_links": inbound[rel],
        }
    couplings = scan_couplings(corpus, report)
    literals = code_literals(repo, site)
    report.data["slug_divergence"] = slug_divergence(corpus, couplings)
    frozen = frozen_paths(couplings)
    enums = enum_headings(corpus, literals)
    for group in enums:
        # Headings that spell code values are an interface even when nothing links to them here.
        item = frozen.setdefault(group["file"], {"path": [], "headings": {}})
        for text in group["headings"]:
            item["headings"].setdefault(text, []).append("enum: " + ", ".join(group["code"]))
    report.data.update(
        {
            "docs_dir": site.docs_dir,
            "site_config": site.config,
            "files": files,
            "couplings_summary": _coupling_summary(couplings),
            "couplings": couplings,
            "frozen": frozen,
            "enum_headings": enums,
            "duplicates": duplicates(corpus),
            "house_style": house_style(corpus),
            "root": root_census(repo),
            "changelog_generators": changelog_generators(repo),
            "doc_tooling": tooling_census(repo),
        }
    )
    if args.blocks:
        _write_output(
            _root_path(args, args.blocks),
            json.dumps({"tool": "docstool", "version": __version__, "blocks": block_baseline(corpus)}, ensure_ascii=False, indent=0) + "\n",
        )
        report.data["blocks_written"] = str(args.blocks)
    return ["config", "nav", "exclude_docs", "markdown", "couplings"]


def slug_divergence(corpus: Corpus, couplings: list[dict[str, Any]]) -> dict[str, Any]:
    """Linked anchors whose GitHub slug differs from a site's: what a migration must fix or keep."""
    linked: set[tuple[str, str]] = set()
    for rel, doc in corpus.docs.items():
        base = str(PurePosixPath(rel).parent)
        for link in doc.links:
            path_part, _, fragment = link.target.partition("#")
            if fragment and not SCHEME_RE.match(link.target):
                resolved = normalize_path(base, unquote(path_part)) if path_part else rel
                if resolved in corpus.docs:
                    linked.add((resolved, unquote(fragment).lower()))
    for entry in couplings:
        if entry["ref"] == "anchor" and entry["status"] == "ok":
            linked.add((entry["target"], unquote(entry["detail"].lstrip("#")).lower()))
    result: dict[str, Any] = {}
    for style in ("python-markdown", "pymdownx-lower"):
        diverging = []
        for target, fragment in sorted(linked):
            doc = corpus.docs[target]
            used = {h.explicit_id for h in doc.headings if h.explicit_id} | set(doc.html_ids)
            site = {h.gh_slug: unique_site_id(h.explicit_id or site_slug_base(h.text, style), used) for h in doc.headings}
            if fragment in site and site[fragment] != fragment:
                diverging.append(f"{target}#{fragment} -> #{site[fragment]}")
        result[style] = {"count": len(diverging), "anchors": diverging[:50]}
    return result


def _coupling_summary(couplings: list[dict[str, Any]]) -> dict[str, Any]:
    by_ref = Counter(c["ref"] for c in couplings)
    by_status = Counter(c["status"] for c in couplings)
    missing = {(c["target"], c["detail"]) for c in couplings if c["status"] == "missing"}
    bold = {(c["target"], c["detail"]) for c in couplings if c["status"] == "bold-label"}
    return {
        "total": len(couplings),
        "by_ref": dict(by_ref),
        "by_status": dict(by_status),
        "distinct_missing": len(missing),
        "distinct_bold_label": len(bold),
    }


def render_inventory_text(report: Report) -> str:
    data = report.data
    out = []
    files = data.get("files", {})
    out.append(f"Markdown files: {len(files)} (docs_dir {data.get('docs_dir')}, site config {data.get('site_config') or 'none'})")
    for rel, info in files.items():
        life = info["lifecycle"]
        out.append(
            f"  {rel}: {info['lines']} lines, {info['diataxis']}, {life['hint']}"
            + (f" ({'; '.join(life['reasons'][:3])})" if life["reasons"] else "")
        )
    summary = data.get("couplings_summary", {})
    out.append(
        f"Couplings: {summary.get('total', 0)} {summary.get('by_ref', {})}; missing {summary.get('distinct_missing', 0)}, bold-label {summary.get('distinct_bold_label', 0)}"
    )
    for path, pins in data.get("frozen", {}).items():
        out.append(f"  frozen {path}: path pinned by {len(pins['path'])}, headings {sorted(pins['headings'])[:5]}")
    for group in data.get("enum_headings", []):
        out.append(
            f"Enum headings: {group['file']} under {group['parent']!r}: {group['count']} headings match code literals ({', '.join(group['code'][:2])})"
        )
    dup = data.get("duplicates", {})
    out.append(
        f"Duplicates: {len(dup.get('exact', []))} exact, {len(dup.get('near', []))} near, {len(dup.get('code_copies_of_files', []))} code blocks copying repo files"
    )
    out.append(f"House style: {data.get('house_style')}")
    out.append(f"Changelog generators: {', '.join(data.get('changelog_generators', [])) or 'none'}")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------------------------
# slug
# ---------------------------------------------------------------------------------------------


def cmd_slug(args: argparse.Namespace, report: Report) -> list[str]:
    unknown = False
    if args.style is None:
        # The site's own slugify (from --root), or the toolkit template's when there is no site.
        site = load_site(Repo(Path(args.root)), report)
        if site.config is None:
            args.style = "pymdownx-lower"
        elif site.slug_style in SLUG_STYLES:
            args.style = site.slug_style
        else:
            # a slugify docstool cannot emulate: no site anchor, and the run is incomplete
            unknown = True
    github = GithubSlugger()
    used: set[str] = set()
    rows = []
    for text in args.text:
        plain = heading_plain_text(text)
        site_id = None if unknown else unique_site_id(site_slug_base(plain, str(args.style)), used)
        rows.append({"text": text, "github": github.slug(plain), "site": site_id, "style": "unknown" if unknown else args.style})
    report.data["slugs"] = rows
    return ["slug_style"] if unknown else []


# ---------------------------------------------------------------------------------------------
# Shared helpers for the analysis commands
# ---------------------------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str | None:
    """The SHA-256 of a regular file's bytes, or None when there is no file."""
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return sha256_bytes(path.read_bytes())
    except OSError:
        return None


FENCED_RE = re.compile(r"(?ms)^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[ \t]*$")


def without_fences(text: str) -> str:
    """Text with fenced code blocks blanked (line numbers kept)."""
    return FENCED_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def walk_values(value: Any, path: str = "") -> Iterable[tuple[str, Any]]:
    """Every (key path, value) pair in nested dicts and lists."""
    yield path, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk_values(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk_values(item, f"{path}[{index}]")
    elif isinstance(value, Tagged):
        yield from walk_values(value.value, path)


# ---------------------------------------------------------------------------------------------
# contrast
# ---------------------------------------------------------------------------------------------

# The page backgrounds of Zensical's two schemes (P0 S5, zensical-ui 0.0.43).
SCHEME_BACKGROUNDS = {"default": "#ffffff", "slate": "#0b0c0f"}
HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def parse_hex(value: str) -> tuple[int, int, int]:
    match = HEX_RE.match(value.strip())
    if not match:
        raise UsageError(f"not a hex colour: {value!r} (use #rrggbb or #rgb)")
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def to_hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    """WCAG 2.x relative luminance."""

    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = sorted((relative_luminance(a), relative_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _mix(colour: tuple[int, int, int], other: tuple[int, int, int], share: float) -> tuple[int, int, int]:
    return (
        round(colour[0] + (other[0] - colour[0]) * share),
        round(colour[1] + (other[1] - colour[1]) * share),
        round(colour[2] + (other[2] - colour[2]) * share),
    )


def _nearest_passing(colour: tuple[int, int, int], toward: tuple[int, int, int], against: tuple[int, int, int], minimum: float) -> str | None:
    for step in range(1, 21):
        candidate = _mix(colour, toward, step / 20)
        if contrast_ratio(candidate, against) >= minimum:
            return to_hex(candidate)
    return None


def cmd_contrast(args: argparse.Namespace, report: Report) -> list[str]:
    brand = parse_hex(args.colour)
    slate_colour = parse_hex(args.slate) if args.slate else brand
    white, black = (255, 255, 255), (0, 0, 0)
    light_bg, slate_bg = parse_hex(SCHEME_BACKGROUNDS["default"]), parse_hex(SCHEME_BACKGROUNDS["slate"])
    pairs = [
        ("accent text on the light page", brand, light_bg, 4.5, black),
        ("accent text on the slate page", slate_colour, slate_bg, 4.5, white),
        ("white button text on the accent fill", white, brand, 4.5, None),
        ("accent fill against the slate page (WCAG 1.4.11)", slate_colour, slate_bg, 3.0, white),
    ]
    rows = []
    for label, fg, bg, minimum, toward in pairs:
        ratio = contrast_ratio(fg, bg)
        rows.append(
            {
                "pair": label,
                "foreground": to_hex(fg),
                "background": to_hex(bg),
                "ratio": round(ratio, 2),
                "minimum": minimum,
                "pass": ratio >= minimum,
            }
        )
        if ratio >= minimum:
            continue
        if toward is None:
            fix = _nearest_passing(brand, black, white, minimum)
            suggestion = f"darken the fill (for example {fix}) or use dark button text" if fix else "use dark button text"
        elif bg == slate_bg:
            fix = _nearest_passing(slate_colour, toward, bg, minimum)
            suggestion = (
                f'override it for dark mode: [data-md-color-scheme="slate"] {{ --md-primary-fg-color: {fix}; }}' if fix else "pick another colour"
            )
        else:
            fix = _nearest_passing(brand, toward, bg, minimum)
            suggestion = f"darken it (for example {fix})" if fix else "pick another colour"
        report.add(
            Finding("contrast", "P1", "verified", "", 0, f"{label}: {ratio:.2f}:1, needs {minimum}:1", [f"{to_hex(fg)} on {to_hex(bg)}"], suggestion)
        )
    report.data["pairs"] = rows
    report.coverage.append(CoverageRow("colours", "complete", "computed (WCAG 2.x relative luminance)"))
    return []


def render_contrast_text(report: Report) -> str:
    out = ["Contrast:"]
    for row in report.data.get("pairs", []):
        flag = "ok  " if row["pass"] else "FAIL"
        out.append(f"  {flag} {row['ratio']:>5}:1 (min {row['minimum']})  {row['foreground']} on {row['background']}  {row['pair']}")
    return "\n".join(out) + "\n\n"


# ---------------------------------------------------------------------------------------------
# readme
# ---------------------------------------------------------------------------------------------

BADGE_RE = re.compile(
    r"img\.shields\.io|badgen\.net|badge\.svg|/badges?/|flathub\.org/api/badge|badge\.fury\.io|codecov\.io/.+/graph/badge", re.IGNORECASE
)
HTML_IMG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
PICTURE_RE = re.compile(r"<picture\b.*?</picture>", re.IGNORECASE | re.DOTALL)
ALT_RE = re.compile(r"""\balt\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.IGNORECASE)
CARD_TITLE_RE = re.compile(r"^[ \t]*[-*+][ \t]+(?::[\w-]+:(?:\{[^}]*\})?[ \t]*)?(?:\*\*|__)(.+?)(?:\*\*|__)")
FEATURE_BULLET_RE = re.compile(r"^[ \t]*[-*+][ \t]+(?:\S+[ \t]+)?(?:\*\*|__)(.+?)(?:\*\*|__)")
README_LINE_BUDGET = (50, 150)
MAX_BADGES = 4


def is_emoji(ch: str) -> bool:
    return unicodedata.category(ch) == "So" and ord(ch) >= 0x2000


def _strip_inline(text: str) -> str:
    text = TAG_RE.sub("", text)
    text = re.sub(r"(\*\*|__|\*|_|`)", "", text)
    return " ".join(text.split()).strip().rstrip(".")


def readme_facts(doc: MarkdownDoc, text: str) -> dict[str, Any]:
    """Tagline, feature titles and first install block of a README."""
    body = without_fences(text).split("\n")
    first_h2 = next((h.line for h in doc.headings if h.level == 2), len(body) + 1)
    tagline = None
    header = "\n".join(body[: first_h2 - 1])
    # a <strong> tagline may wrap over several lines in a repository with a line-length rule
    strong = re.search(r"<strong>(.+?)</strong>", header, re.DOTALL) or re.search(r"(?m)^[ \t]*(?:\*\*|__)(.+?)(?:\*\*|__)[ \t]*$", header)
    if strong:
        tagline = _strip_inline(" ".join(strong.group(1).split()))
    features: list[str] = []
    install = None
    sections = [(h, i) for i, h in enumerate(doc.headings) if h.level == 2]
    for position, (heading, _index) in enumerate(sections):
        end = sections[position + 1][0].line if position + 1 < len(sections) else len(body) + 1
        name = heading.text.casefold()
        if "feature" in name:
            for line in body[heading.line : end - 1]:
                match = FEATURE_BULLET_RE.match(line)
                if match:
                    features.append(_strip_inline(match.group(1)).rstrip(":"))
        if install is None and re.search(r"install|get(ting)? started|quick ?start", name):
            install = next((b.text.strip() for b in doc.blocks if b.type == "code" and heading.line < b.line < end), None)
    return {"tagline": tagline, "features": features, "install": install}


def home_facts(doc: MarkdownDoc) -> dict[str, Any]:
    """Tagline, feature card titles and first install block of a homepage built on home.html.

    A card is a bullet at the grid's own indentation; nested bullets belong to a card's body. Its
    title is the bold text on the bullet line (`- **Title**`) or, after an icon on the bullet
    line, the item's first line when that line is all bold (`    **Title**`). untitled_cards counts
    the cards with neither, so a caller can refuse to compare a partial list."""
    home = doc.front_matter.get("home") if isinstance(doc.front_matter, dict) else None
    tagline = _strip_inline(str(home["tagline"])) if isinstance(home, dict) and home.get("tagline") else None
    features: list[str] = []
    install = None
    untitled = 0
    region: str | None = None
    depth = 0
    start = 0
    card_indent: int | None = None
    awaiting_title = False
    for number, line in enumerate(doc.lines, 1):
        opening = re.search(r'<div\b[^>]*class="([^"]*)"', line)
        if region is None and opening:
            classes = opening.group(1).split()
            if "cards" in classes:
                region, depth, start, card_indent = "cards", 0, number, None
            elif "rdt-install" in classes:
                region, depth, start = "install", 0, number
        if region is not None:
            depth += len(re.findall(r"<div\b", line)) - len(re.findall(r"</div>", line))
            if region == "cards":
                bullet = re.match(r"^([ \t]*)[-*+][ \t]+", line)
                indent = len(bullet.group(1).expandtabs(4)) if bullet else -1
                if bullet and (card_indent is None or indent == card_indent):
                    card_indent = indent
                    if awaiting_title:
                        untitled += 1
                    match = CARD_TITLE_RE.match(line)
                    if match:
                        features.append(_strip_inline(match.group(1)).rstrip(":"))
                    awaiting_title = match is None
                elif awaiting_title and line.strip():
                    bold = re.match(r"^[ \t]+(?:\*\*|__)(.+?)(?:\*\*|__)[ \t]*$", line)
                    if bold:
                        features.append(_strip_inline(bold.group(1)).rstrip(":"))
                    else:
                        untitled += 1
                    awaiting_title = False
            if depth <= 0 and number >= start:
                if region == "cards" and awaiting_title:
                    untitled += 1
                    awaiting_title = False
                if region == "install" and install is None:
                    install = next((b.text.strip() for b in doc.blocks if b.type == "code" and start < b.line < number), None)
                region = None
    return {"tagline": tagline, "features": features, "install": install, "untitled_cards": untitled}


def _published_package(repo: Repo) -> str | None:
    """The registry a README is also shown on, when the manifest says the package is published."""
    cargo, _ = repo.text("Cargo.toml") if "Cargo.toml" in repo.file_set else (None, "")
    if cargo:
        try:
            package = tomllib.loads(cargo).get("package", {})
        except tomllib.TOMLDecodeError:
            package = {}
        if package and package.get("publish", True) is not False:
            return "crates.io"
    npm, _ = repo.text("package.json") if "package.json" in repo.file_set else (None, "")
    if npm:
        try:
            manifest = json.loads(npm)
        except json.JSONDecodeError:
            manifest = {}
        if isinstance(manifest, dict) and manifest.get("name") and not manifest.get("private"):
            return "npm"
    py, _ = repo.text("pyproject.toml") if "pyproject.toml" in repo.file_set else (None, "")
    if py:
        try:
            project = tomllib.loads(py).get("project", {})
        except tomllib.TOMLDecodeError:
            project = {}
        if project.get("name") and not any("Private" in str(c) for c in project.get("classifiers", [])):
            return "PyPI"
    return None


MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)")
IMG_SRC_RE = re.compile(r"""<(?:img|source)\b[^>]*?\b(?:src|srcset)\s*=\s*["']([^"'\s]+)""", re.IGNORECASE)


def _readme_images(body: str) -> list[Link]:
    """Every image of a README, nested in links or not: Markdown images, <img> and <source>."""
    images = []
    for number, line in enumerate(body.split("\n"), 1):
        masked = mask_code_spans(line)
        images += [Link("image", m.group(2), number, m.group(1)) for m in MD_IMAGE_RE.finditer(masked)]
        images += [Link("html-src", m.group(1), number) for m in IMG_SRC_RE.finditer(masked)]
    return images


def cmd_readme(args: argparse.Namespace, report: Report) -> list[str]:
    repo = Repo(Path(args.root))
    site = load_site(repo, report)
    rel = normalize_path("", args.file) or args.file
    text, status = repo.text(rel)
    if text is None:
        report.coverage.append(CoverageRow("readme", "failed", f"{rel}: {status}"))
        return ["readme"]
    report.coverage.append(CoverageRow("readme", "complete", rel))
    doc = parse_markdown(rel, text, None, False)
    lines = text.rstrip("\n").split("\n")
    low, high = README_LINE_BUDGET
    if len(lines) > high:
        report.add(
            Finding(
                "readme-length",
                "P2",
                "verified",
                rel,
                high + 1,
                f"{len(lines)} lines; a README stays within {low}-{high}",
                suggestion="move reference material into the docs and link to it",
            )
        )
    elif len(lines) < low:
        report.add(Finding("readme-length", "P3", "verified", rel, 1, f"{len(lines)} lines; under {low} usually means install or usage is missing"))
    body = without_fences(text)
    h1 = [h.line for h in doc.headings if h.level == 1] + [body[: m.start()].count("\n") + 1 for m in re.finditer(r"<h1\b", body, re.IGNORECASE)]
    if len(h1) != 1:
        report.add(Finding("readme-h1", "P2", "verified", rel, (sorted(h1)[1:] or [1])[0], f"{len(h1)} level-1 headings; a README has exactly one"))
    images = _readme_images(body)
    badges = [link for link in images if BADGE_RE.search(link.target)]
    if len(badges) > MAX_BADGES:
        report.add(
            Finding(
                "readme-badges",
                "P2",
                "verified",
                rel,
                badges[MAX_BADGES].line,
                f"{len(badges)} badges; keep at most {MAX_BADGES} (CI, version, docs, license)",
            )
        )
    styles = {m.group(1) if (m := re.search(r"[?&]style=([\w-]+)", b.target)) else "flat" for b in badges if "shields.io" in b.target}
    if len(styles) > 1:
        report.add(Finding("readme-badges", "P3", "verified", rel, badges[0].line, f"badges mix styles: {', '.join(sorted(styles))}"))
    for heading in doc.headings:
        emoji = [i for i, ch in enumerate(heading.text) if is_emoji(ch)]
        if emoji and (heading.level != 2 or emoji != [0] or len(heading.text) < 2):
            report.add(
                Finding("readme-emoji", "P3", "verified", rel, heading.line, f"emoji in {heading.text!r}: only as the first character of an h2")
            )
    for link in images:
        if link.kind == "image" and not link.text.strip():
            report.add(Finding("readme-alt", "P2", "verified", rel, link.line, f"image {link.target} has no alt text"))
    for match in HTML_IMG_RE.finditer(body):
        alt = ALT_RE.search(match.group(0))
        if not alt or not (alt.group(1) or alt.group(2) or "").strip():
            report.add(Finding("readme-alt", "P2", "verified", rel, body[: match.start()].count("\n") + 1, "an <img> without alt text"))
    for match in PICTURE_RE.finditer(body):
        if not HTML_IMG_RE.search(match.group(0)):
            report.add(
                Finding(
                    "readme-picture",
                    "P1",
                    "verified",
                    rel,
                    body[: match.start()].count("\n") + 1,
                    "<picture> without an <img> fallback renders nothing where <source> is unsupported",
                )
            )
    registry = "the registry" if args.registry else _published_package(repo)
    if registry:
        for link in images:
            if not SCHEME_RE.match(link.target):
                report.add(
                    Finding(
                        "readme-registry-image",
                        "P2",
                        "verified" if args.registry else "likely",
                        rel,
                        link.line,
                        f"relative image {link.target} breaks where the README is shown on {registry}",
                        suggestion="use an absolute https://raw.githubusercontent.com/... URL",
                    )
                )
    docs_url = site.site_url
    if docs_url:
        count = text.count(docs_url.rstrip("/"))
        if count > 3:
            report.add(
                Finding(
                    "readme-docs-url",
                    "P3",
                    "verified",
                    rel,
                    1,
                    f"the docs URL appears {count} times; link it once in the header and once where it helps",
                )
            )
    for number, line in enumerate(body.split("\n"), 1):
        if "TODO(verify" in line:
            report.add(
                Finding(
                    "readme-todo",
                    "P2",
                    "verified",
                    rel,
                    number,
                    "an unverified TODO(verify) is still in the README",
                    suggestion="settle it with the owner, or leave the claim out",
                )
            )
    alerts = [n for n, line in enumerate(lines, 1) if ALERT_RE.match(line)]
    if len(alerts) > 2:
        report.add(Finding("readme-alerts", "P3", "verified", rel, alerts[2], f"{len(alerts)} alerts; keep at most two so they still stand out"))
    h2 = [h for h in doc.headings if h.level == 2]
    licence = [h for h in h2 if "licen" in h.text.casefold()]
    if h2 and not licence:
        report.add(Finding("readme-license", "P3", "verified", rel, h2[-1].line, "no License section"))
    elif licence and licence[-1] is not h2[-1]:
        report.add(Finding("readme-license", "P3", "verified", rel, licence[-1].line, "License is not the last section"))
    anchors = doc.anchors()
    for link in doc.links:
        if link.target.startswith("#") and len(link.target) > 1 and unquote(link.target[1:]).lower() not in {a.lower() for a in anchors}:
            report.add(
                Finding(
                    "broken-anchor",
                    "P1",
                    "verified",
                    rel,
                    link.line,
                    f"{link.target}: no heading has that GitHub anchor",
                    suggestion="headings that start with an emoji get anchors like #-install",
                )
            )
    facts = readme_facts(doc, text)
    report.data["readme"] = {"file": rel, "lines": len(lines), "badges": len(badges), **facts}
    required = ["readme"]
    if args.home:
        home_rel = normalize_path("", args.home) or args.home
        home_text, home_status = repo.text(home_rel)
        if home_text is None:
            report.coverage.append(CoverageRow("home", "failed", f"{home_rel}: {home_status}"))
            return [*required, "home"]
        home = home_facts(parse_markdown(home_rel, home_text, None, True))
        untitled = home.pop("untitled_cards")
        if untitled:
            # comparing the README with a shorter feature list than the homepage has would look clean
            report.coverage.append(CoverageRow("home", "partial", f"{home_rel}: {untitled} feature cards with no recognised title"))
            report.data["home"] = home
            return [*required, "home"]
        report.coverage.append(CoverageRow("home", "complete", home_rel))
        report.data["home"] = home
        required.append("home")
        _readme_drift(report, rel, home_rel, facts, home)
    return required


def _readme_drift(report: Report, rel: str, home_rel: str, readme: dict[str, Any], home: dict[str, Any]) -> None:
    if home["tagline"] and readme["tagline"] != home["tagline"]:
        report.add(
            Finding(
                "readme-drift",
                "P2",
                "verified",
                rel,
                1,
                f"tagline {readme['tagline']!r} differs from the homepage's {home['tagline']!r}",
                [f"{home_rel}: home.tagline"],
                "the homepage front matter is canonical; copy its tagline verbatim",
            )
        )
    ours, theirs = {f.casefold() for f in readme["features"]}, {f.casefold() for f in home["features"]}
    for title in home["features"]:
        if title.casefold() not in ours:
            report.add(Finding("readme-drift", "P2", "verified", rel, 1, f"homepage feature {title!r} is not in the README's features", [home_rel]))
    for title in readme["features"]:
        if title.casefold() not in theirs and home["features"]:
            report.add(Finding("readme-drift", "P2", "verified", home_rel, 1, f"README feature {title!r} is not a homepage card", [rel]))
    if home["install"] and readme["install"] and home["install"] != readme["install"]:
        report.add(
            Finding("readme-drift", "P2", "verified", rel, 1, "the README's install block differs from the homepage's", [f"{home_rel}: rdt-install"])
        )


# ---------------------------------------------------------------------------------------------
# site-audit
# ---------------------------------------------------------------------------------------------

# Plugins Zensical 0.1.3 implements (zensical/config.py, _PLUGIN_UNSUPPORTED_OPTIONS); any other
# plugin entry is silently ignored. section-index is native, so its entry is ignored harmlessly.
ZENSICAL_PLUGINS = frozenset(
    [
        "api-autonav",
        "autorefs",
        "awesome-nav",
        "blog",
        "callouts",
        "exclude",
        "gh-admonitions",
        "git-revision-date-localized",
        "glightbox",
        "include-markdown",
        "literate-nav",
        "llmstxt",
        "macros",
        "markdown-exec",
        "markdownextradata",
        "meta",
        "meta-descriptions",
        "mike",
        "minify",
        "mkdocs-audio",
        "mkdocs-autoapi",
        "mkdocs-nav-weight",
        "mkdocs-video",
        "mkdocstrings",
        "offline",
        "optimize",
        "privacy",
        "redirects",
        "rss",
        "search",
        "social",
        "table-reader",
        "tags",
    ]
)
NATIVE_PLUGINS = frozenset({"section-index"})
# Feature flags no template or script of zensical-ui 0.0.43 reads, and documented incompatible pairs.
NOOP_FEATURES = frozenset({"search.suggest", "search.share"})
INCOMPATIBLE_FEATURES = (("navigation.indexes", "toc.integrate"), ("navigation.prune", "navigation.expand"))
SEARCH_OPTIONS = frozenset({"enabled", "separator"})
# The [project.validation] checks Zensical 0.1.3 marks deprecated in their current form.
DEPRECATED_VALIDATION = frozenset(
    {"unresolved_references", "unresolved_footnotes", "unused_definitions", "unused_footnotes", "shadowed_definitions", "shadowed_footnotes"}
)
FEATURE_SYNTAX = (
    ("admonition", re.compile(r"^[ \t]*!!!\s", re.MULTILINE), "!!! admonitions"),
    ("pymdownx.details", re.compile(r"^[ \t]*\?\?\?\+?\s", re.MULTILINE), "??? collapsible blocks"),
    ("pymdownx.tabbed", re.compile(r'^[ \t]*===\+?[ \t]+"', re.MULTILINE), '=== "Tab" content tabs'),
    ("pymdownx.snippets", re.compile(r"^[ \t]*;?--8<--", re.MULTILINE), "--8<-- snippets"),
    ("pymdownx.tasklist", re.compile(r"^[ \t]*[-*+][ \t]+\[[ xX]\][ \t]", re.MULTILINE), "task lists"),
    ("footnotes", re.compile(r"\[\^[^\]\s]+\]"), "footnotes"),
    ("md_in_html", re.compile(r"<\w+\b[^>]*\bmarkdown(?:=\"1\"|=\"block\"|\b)[^>]*>"), "Markdown inside HTML"),
    ("attr_list", re.compile(r"\{\s*[#.:][\w-][^}\n]*\}"), "attribute lists"),
    ("pymdownx.emoji", re.compile(r":(?:material|octicons|fontawesome|lucide|simple)-[\w-]+:"), "icon shortcodes"),
)


def _lock_pins(repo: Repo) -> dict[str, str]:
    """Hash-pinned zensical locks: path -> pinned version."""
    pins = {}
    for rel in repo.files:
        name = PurePosixPath(rel).name
        if not (name.endswith(".txt") and "requirements" in name) and name != "uv.lock":
            continue
        text, _ = repo.text(rel)
        if not text:
            continue
        pin = re.search(r"^zensical==([\w.]+)", text, re.MULTILINE)
        if pin and "--hash=" in text:
            pins[rel] = pin.group(1)
        if name == "uv.lock":
            # A [[package]] block counts only when it comes from a registry with sha256 hashes: a git,
            # path or editable source pins nothing that uv can check.
            for block in re.split(r"^\[\[package\]\]$", text, flags=re.MULTILINE)[1:]:
                uv = re.match(r'\s*name = "zensical"\nversion = "([\w.]+)"', block)
                if uv and re.search(r"^source = \{ registry = ", block, re.MULTILINE) and 'hash = "sha256:' in block:
                    pins[rel] = uv.group(1)
    return pins


def _zensical_requirement(repo: Repo) -> tuple[str, int, str] | None:
    """The first committed requirement line that names zensical: (path, line, the requirement)."""
    for rel in repo.files:
        name = PurePosixPath(rel).name
        if not (name.endswith((".in", ".txt")) and "requirements" in name) and name != "pyproject.toml":
            continue
        text, _ = repo.text(rel)
        for number, line in enumerate((text or "").split("\n"), 1):
            match = re.match(r"""^\s*["']?(zensical(?![\w-])[^"'#,]*)""", line)
            if match:
                return rel, number, match.group(1).strip()
    return None


def installed_zensical() -> str | None:
    try:
        from importlib import metadata  # noqa: PLC0415 - only site-audit needs it

        return metadata.version("zensical")
    except Exception:  # noqa: BLE001 - any failure means "not visible to this interpreter"
        return None


def cmd_site_audit(args: argparse.Namespace, report: Report) -> list[str]:
    repo = Repo(Path(args.root))
    site = load_site(repo, report)
    rows = {r.input: r for r in report.coverage}
    if site.config is None or not rows["config"].complete:
        return ["config"]
    cfg, raw = site.config, site.raw
    config_text, _ = repo.text(cfg)
    lines = (config_text or "").split("\n")

    def line_of(needle: str) -> int:
        return next((i for i, line in enumerate(lines, 1) if needle in line), 1)

    def add(check: str, severity: str, message: str, needle: str = "", suggestion: str = "", confidence: str = "verified") -> None:
        report.add(Finding(check, severity, confidence, cfg, line_of(needle) if needle else 1, message, suggestion=suggestion))

    if site.kind == "mkdocs" and "hooks" in raw:
        add(
            "hooks",
            "P1",
            "hooks: are not run by Zensical (silently ignored, even with --strict)",
            "hooks",
            "move the hook's work into a script run before the build, or drop it",
        )
    for name in site.plugins:
        canonical = name.removeprefix("material/").split("/", 1)[0]
        if canonical in NATIVE_PLUGINS:
            add("plugin-native", "P3", f"plugin {name}: Zensical does this natively and ignores the entry", name)
        elif canonical not in ZENSICAL_PLUGINS:
            add(
                "plugin-unsupported",
                "P1",
                f"plugin {name} is not supported by Zensical {KNOWN_ZENSICAL}; its configuration is silently ignored",
                name,
                "replace what it did, or keep building with MkDocs",
            )
    search = site.plugins.get("search")
    if isinstance(search, dict):
        for option in sorted(set(search) - SEARCH_OPTIONS):
            add("search-option", "P3", f"search option {option} is ignored by Zensical (only enabled and separator are read)", option)
    theme: dict[str, Any] = raw["theme"] if isinstance(raw.get("theme"), dict) else {}
    features = [str(f) for f in theme.get("features", []) or []]
    for feature in features:
        if feature in NOOP_FEATURES:
            add("feature-noop", "P2", f"feature {feature} does nothing in Zensical {KNOWN_ZENSICAL}", feature, "remove it")
    for first, second in INCOMPATIBLE_FEATURES:
        if first in features and second in features:
            add(
                "feature-conflict",
                "P2",
                f"features {first} and {second} do not work together",
                second,
                "keep the one the site is built around and remove the other; ask the owner which",
            )
    if site.slug_style not in GITHUB_STYLES:
        add(
            "slugify",
            "P2",
            f"toc slugify is {site.slug_style}: site anchors differ from GitHub's",
            "slugify" if "slugify" in (config_text or "") else "",
            'set toc.slugify = { object = "pymdownx.slugs.slugify", kwds = { case = "lower" } }',
        )
    if not site.site_url:
        add(
            "site-url",
            "P2",
            "site_url is not set: instant navigation, previews, the 404 page and social cards need it",
            suggestion="set site_url to the published URL",
        )
    if site.docs_dir == ".":
        add("docs-dir", "P1", "docs_dir is the project root, which Zensical does not allow", "docs_dir")
    internal = [r for r in repo.files if site.in_docs(r) and site.docs_rel(r).startswith("internal/")]
    if internal and any(site.published(r) for r in internal):
        add(
            "internal-published",
            "P1",
            f"{site.docs_dir}/internal/ exists but exclude_docs does not exclude it, so it is published",
            "exclude_docs",
            'set exclude_docs = "internal/"',
        )
    for key_path, value in walk_values(raw):
        if isinstance(value, Tagged):
            if value.tag.startswith("!ENV"):
                add(
                    "yaml-env",
                    "P2",
                    f"{key_path}: !ENV is read by MkDocs only",
                    key_path.rsplit(".", 1)[-1],
                    "write the value as a literal (or have CI write it before the build), then check the built page uses it",
                )
            elif value.tag.startswith("!!python/name:material"):
                add(
                    "yaml-python-name",
                    "P3",
                    f"{key_path}: {value.tag} works with mkdocs.yml; zensical.toml uses a plain string",
                    key_path.rsplit(".", 1)[-1],
                    confidence="likely",
                )
    explicit = site.kind == "mkdocs" or "markdown_extensions" in raw
    if explicit:
        _audit_extensions(repo, site, add)
    if "codehilite" in site.extensions:
        hint = "drop it: pymdownx.highlight is configured" if "pymdownx.highlight" in site.extensions else "use pymdownx.highlight instead"
        add("codehilite", "P3", "codehilite is redundant with Zensical's highlighter", "codehilite", hint)
    alerts = any(ALERT_RE.search(t or "") for t in (repo.text(r)[0] for r in repo.markdown_files() if site.published(r)))
    if alerts and "gh-admonitions" not in site.plugins:
        add(
            "gh-admonitions",
            "P2",
            "pages use GitHub alerts (> [!NOTE]) but the gh-admonitions plugin is not enabled, so they render as quotes",
            suggestion="add [project.plugins.gh-admonitions]",
        )
    validation = raw.get("validation")
    if validation is False or (isinstance(validation, dict) and validation and not any(validation.values())):
        add("validation", "P2", "link validation is turned off", "validation")
    if isinstance(validation, dict):
        for option in sorted(k for k, v in validation.items() if k in DEPRECATED_VALIDATION and v):
            add(
                "validation-deprecated",
                "P3",
                f"validation.{option} is deprecated in its current form (Zensical {KNOWN_ZENSICAL})",
                option,
                "keep only invalid_links and invalid_link_anchors",
            )
    has_internal = any(site.in_docs(r) and site.docs_rel(r).startswith("internal/") for r in repo.files)
    if not has_internal and site.published(PurePosixPath(site.docs_dir, "internal", "README.md").as_posix()):
        add(
            "exclude-internal",
            "P3",
            "exclude_docs does not exclude internal/: a maintainer page added to docs/internal/ later would be published",
            "exclude_docs",
            'set exclude_docs = "internal/"',
        )
    pins = _lock_pins(repo)
    requirement = None if pins else _zensical_requirement(repo)
    if requirement:
        path, number, spec = requirement
        report.add(
            Finding(
                "lock",
                "P2",
                "verified",
                path,
                number,
                f"zensical is required as '{spec}' but no committed hash-pinned lock pins it",
                suggestion=f"pin zensical=={KNOWN_ZENSICAL} there and commit its lock: uv lock for a uv project, a --generate-hashes compile for a requirements file (an ignored lock pins nothing)",
            )
        )
    elif not pins:
        add(
            "lock",
            "P2",
            "no hash-pinned lock pins zensical",
            suggestion=f"add a uv project, tools/docs/pyproject.toml with zensical=={KNOWN_ZENSICAL}, and commit its uv.lock",
        )
    for path, version in pins.items():
        if version != KNOWN_ZENSICAL:
            report.add(
                Finding(
                    "zensical-version", "P3", "verified", path, 1, f"the lock pins zensical {version}; docstool was checked against {KNOWN_ZENSICAL}"
                )
            )
    workflows = [r for r in repo.files if r.startswith(".github/workflows/")]
    if not any(re.search(r"\b(?:zensical|mkdocs) build\b|\bmake docs-build\b", repo.text(w)[0] or "") for w in workflows):
        add("ci-build", "P2", "no workflow builds the site, so a broken build is found only locally", suggestion="build with --strict in CI")
    installed = installed_zensical()
    if installed and installed != KNOWN_ZENSICAL:
        report.add(
            Finding("zensical-version", "P3", "verified", cfg, 1, f"zensical {installed} is installed; docstool was checked against {KNOWN_ZENSICAL}")
        )
    report.data.update({"site_config": cfg, "kind": site.kind, "known_zensical": KNOWN_ZENSICAL, "installed_zensical": installed, "locks": pins})
    return ["config"]


def _audit_extensions(repo: Repo, site: Site, add: Callable[..., None]) -> None:
    """Syntax the published pages use that the explicit extension list does not enable."""
    used: dict[str, str] = {}
    mermaid = False
    for rel in repo.markdown_files():
        if not site.published(rel):
            continue
        text, _ = repo.text(rel)
        if not text:
            continue
        mermaid = mermaid or bool(re.search(r"^[ \t]*(`{3,}|~{3,})[ \t]*mermaid\b", text, re.MULTILINE))
        prose = without_fences(text)
        for extension, pattern, label in FEATURE_SYNTAX:
            match = pattern.search(prose)
            if match and extension not in used:
                used[extension] = f"{rel}:{prose[: match.start()].count(chr(10)) + 1} ({label})"
    for extension, where in sorted(used.items()):
        if extension not in site.extensions:
            add(
                "extension-missing",
                "P1",
                f"{where} needs {extension}, which the explicit markdown_extensions list does not enable",
                suggestion="add it: an explicit list replaces the defaults",
            )
    if mermaid:
        fences = (
            (site.extensions.get("pymdownx.superfences") or {}).get("custom_fences", [])
            if isinstance(site.extensions.get("pymdownx.superfences"), dict)
            else []
        )
        if not any(isinstance(f, dict) and f.get("name") == "mermaid" for f in fences):
            add("extension-missing", "P1", "pages have mermaid fences but pymdownx.superfences has no mermaid custom fence", "superfences")


# ---------------------------------------------------------------------------------------------
# drift: commands, flags, environment variables and paths the docs name, against the code
# ---------------------------------------------------------------------------------------------

MAKE_VAR_RE = re.compile(r"^(?:override[ \t]+|export[ \t]+)?([A-Za-z_][\w.-]*)[ \t]*(::?=|:::=|\?=|\+=|!=|=)[ \t]*(.*)$")
MAKE_RULE_RE = re.compile(r"^([^\t#=:][^#=:]*?)[ \t]*::?(?![=])(.*)$")
MAKE_INCLUDE_RE = re.compile(r"^[ \t]*(-include|sinclude|include)[ \t]+(.+)$")
MAKE_REF_RE = re.compile(r"\$[({]([^(){}$]+)[)}]")
MAKE_FUNC_RE = re.compile(
    r"\$\((addprefix|addsuffix|wildcard|notdir|basename|patsubst|subst|strip|sort|eval|shell|call|foreach|filter|if|or|and|word|firstword|lastword|dir|realpath|abspath)[ \t]+([^()]*(?:\([^()]*\)[^()]*)*)\)"
)
SHELL_INFOS = frozenset(
    {"", "sh", "bash", "shell", "console", "zsh", "fish", "terminal", "shell-session", "sh-session", "shellsession", "powershell", "ps1"}
)
CMD_SPLIT_RE = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")
DOC_ENV_SPAN_RE = re.compile(r"^\$?\{?([A-Z][A-Z0-9]*_[A-Z0-9_]+)\}?(?:=\S*)?$")
DOC_ENV_BLOCK_RE = re.compile(
    r"(?:\bexport[ \t]+|^[ \t]*|[ \t]-e[ \t]+|--env[ \t=]+)([A-Z][A-Z0-9]*_[A-Z0-9_]+)=|\$\{?([A-Z][A-Z0-9]*_[A-Z0-9_]+)\b", re.MULTILINE
)
FLAG_TOKEN_RE = re.compile(r"^(--[a-zA-Z][\w-]*)(?:=.*)?$")
ENV_CONTEXT_RE = re.compile(r"\b(?:env(?:ironment)?(?:[ -]var(?:iable)?s?)?|variables?|export(?:ed)?|set(?:s|ting)?)\b", re.IGNORECASE)
FLAG_LITERAL_RE = re.compile(r"[\"'](--[a-zA-Z][\w-]*)[\"'=]")
GLIB_CONST_FLAG_RE = re.compile(r"add_main_option\(\s*(?:[\w]+::)*([A-Z][A-Z0-9_]*)\s*,")
RUST_STR_CONST_RE = re.compile(r"\bconst\s+([A-Z][A-Z0-9_]*)\s*:\s*&(?:'static\s+)?str\s*=\s*\"([^\"]+)\"")
IMPLICIT_ENV = frozenset(
    [
        "RUST_LOG",
        "RUST_BACKTRACE",
        "RUST_LIB_BACKTRACE",
        "RUST_MIN_STACK",
        "HOME",
        "PATH",
        "USER",
        "LOGNAME",
        "SHELL",
        "TERM",
        "LANG",
        "LANGUAGE",
        "TZ",
        "TMPDIR",
        "PWD",
        "NO_COLOR",
        "FORCE_COLOR",
        "CLICOLOR",
        "CLICOLOR_FORCE",
        "CI",
        "EDITOR",
        "VISUAL",
        "PAGER",
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "DBUS_SESSION_BUS_ADDRESS",
        "GOPATH",
        "GOFLAGS",
        "GOOS",
        "GOARCH",
        "GOBIN",
        "CGO_ENABLED",
        "GOPROXY",
        "GOPRIVATE",
        "PYTHONPATH",
        "PYTHONUNBUFFERED",
        "PYTHONDONTWRITEBYTECODE",
        "VIRTUAL_ENV",
        "NODE_ENV",
        "NODE_OPTIONS",
        "NPM_TOKEN",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "SSH_AUTH_SOCK",
        "DOCKER_HOST",
        "DOCKER_BUILDKIT",
        "SOURCE_DATE_EPOCH",
        "MAKEFLAGS",
        "DESTDIR",
        "PREFIX",
        "G_MESSAGES_DEBUG",
        "GTK_DEBUG",
        "GTK_THEME",
        "GSK_RENDERER",
        "GDK_BACKEND",
        "GDK_SCALE",
        "FLATPAK_ID",
    ]
)
IMPLICIT_ENV_PREFIXES = ("CARGO_", "XDG_", "GITHUB_", "RUNNER_", "LC_", "GIT_", "GSETTINGS_", "DEBIAN_", "ACTIONS_")
ENV_READERS = {
    "rust": (
        re.compile(r"\benv::var(?:_os)?\(\s*\"([A-Z][A-Z0-9_]*)\""),
        re.compile(r"\b(?:option_)?env!\(\s*\"([A-Z][A-Z0-9_]*)\""),
        re.compile(r"\benv\s*=\s*\"([A-Z][A-Z0-9_]*)\""),
    ),
    "go": (re.compile(r"\bos\.(?:Getenv|LookupEnv)\(\s*\"([A-Z][A-Z0-9_]*)\""), re.compile(r"\benv(?:config)?:\"([A-Z][A-Z0-9_]*)")),
    "python": (
        re.compile(r"\benviron\[\s*[\"']([A-Z][A-Z0-9_]*)[\"']"),
        re.compile(r"\b(?:environ\.get|getenv)\(\s*[\"']([A-Z][A-Z0-9_]*)[\"']"),
    ),
    "js": (
        re.compile(r"\bprocess\.env\.([A-Z][A-Z0-9_]*)"),
        re.compile(r"\bprocess\.env\[\s*[\"']([A-Z][A-Z0-9_]*)[\"']"),
        re.compile(r"\bimport\.meta\.env\.([A-Z][A-Z0-9_]*)"),
    ),
}
SHELL_ENV_RE = re.compile(r"\$\{?([A-Z][A-Z0-9_]*)")
COMPOSE_ENV_RE = re.compile(r"^[ \t]*-?[ \t]*([A-Z][A-Z0-9_]*)[ \t]*[=:]", re.MULTILINE)
DOCKER_ENV_RE = re.compile(r"^[ \t]*(?:ENV|ARG)[ \t]+([A-Z][A-Z0-9_]*)", re.MULTILINE)
DOTENV_RE = re.compile(r"^[ \t]*(?:export[ \t]+)?([A-Z][A-Z0-9_]*)=", re.MULTILINE)
LANG_OF = {
    ".rs": "rust",
    ".go": "go",
    ".py": "python",
    ".js": "js",
    ".mjs": "js",
    ".cjs": "js",
    ".ts": "js",
    ".tsx": "js",
    ".jsx": "js",
    ".mts": "js",
}
CLAP_FIELD_RE = re.compile(
    r"#\[(?:arg|clap)\(((?:[^\[\]]|\[[^\[\]]*\])*)\)\]\s*(?:(?:///[^\n]*|#\[[^\]]*\])\s*)*(?:pub(?:\([^)]*\))?\s+)?(?:r#)?(\w+)\s*:"
)
CLAP_FLATTEN_RE = re.compile(r"#\[(?:command|clap)\(\s*flatten\s*\)\]\s*(?:(?:///[^\n]*|#\[[^\]]*\])\s*)*(?:pub(?:\([^)]*\))?\s+)?\w+\s*:\s*([\w:]+)")
FLAG_DEFS = {
    "rust": (re.compile(r"\.long\(\s*\"([\w-]+)\""), re.compile(r"\b(?:visible_)?alias(?:es)?\s*=\s*\[?\s*\"([\w-]+)\"")),
    "go": (
        re.compile(r"\.(?:Persistent)?Flags\(\)\.\w+\(\s*(?:&[\w.\[\]]+\s*,\s*)?\"([\w-]+)\""),
        re.compile(r"\bflag\.\w+\(\s*(?:&[\w.\[\]]+\s*,\s*)?\"([\w-]+)\""),
        re.compile(r"&cli\.\w+Flag\{[^}]*?Name:\s*\"([\w-]+)\"", re.DOTALL),
        re.compile(r"\.Flag\(\s*\"([\w-]+)\""),
    ),
    "python": (re.compile(r"\b(?:add_argument|option|Option)\(([^)]*)\)"),),
    "js": (re.compile(r"\.(?:option|requiredOption)\(\s*['\"`]([^'\"`]+)['\"`]"),),
}
GLIB_FLAG_RE = re.compile(r"add_main_option\(\s*\"([\w-]+)\"")
AUTO_FLAGS = frozenset({"--help", "--version"})
STATUS_RE = re.compile(
    r"\b(since|from|as of|added in|introduced in|available in|new in|released in|until|before|planned for|coming in|will (?:be|ship|land) in)[ \t]+(?:version[ \t]+)?v?(\d+\.\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)
COUNT_RE = re.compile(
    r"\b(\d{1,4})[ \t]+(commands?|subcommands?|checks?|rules?|crates?|skills?|plugins?|tests?|flags?|options?|endpoints?|languages?|monitors?|models?|refusals?|devices?)\b",
    re.IGNORECASE,
)
PATH_SPAN_RE = re.compile(
    r"^(?:\./)?(?:\.?[\w@+-][\w.@+-]*/)+[\w@+.-]*$|^(?:\./)?\.?[\w@+-][\w.@+-]*\.(?:sh|py|rs|go|toml|ya?ml|json|mk|ts|js|md|txt|cfg|ini|conf|service|desktop|xml|blp|ui|css)$"
)


class _Unexpandable(Exception):
    pass


def _join_continuations(text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    pending = ""
    start = 0
    for number, line in enumerate(text.split("\n"), 1):
        if not pending:
            start = number
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        out.append((start, pending + line))
        pending = ""
    if pending:
        out.append((start, pending))
    return out


class MakeModel:
    """Targets of a Makefile and the files it includes, read statically (nothing is run)."""

    def __init__(self, repo: Repo, makefile: str) -> None:
        self.repo = repo
        self.base = str(PurePosixPath(makefile).parent)
        self.variables: dict[str, str] = {}
        self.targets: dict[str, str] = {}
        self.problems: list[str] = []
        self.files: list[str] = []
        self._read(makefile, 0)

    def expand(self, text: str, depth: int = 0) -> str:
        if depth > 12:
            raise _Unexpandable(text)
        previous = None
        while previous != text:
            previous = text
            text = MAKE_FUNC_RE.sub(lambda m: self._function(m.group(1), m.group(2), depth), text)
            text = MAKE_REF_RE.sub(lambda m: self._variable(m.group(1), depth), text)
        if "$(" in text or "${" in text:
            raise _Unexpandable(text)
        return text.replace("$$", "$")

    def _variable(self, name: str, depth: int) -> str:
        if name in self.variables:
            return self.expand(self.variables[name], depth + 1)
        if name == "CURDIR":
            return self.base
        if name in ("MAKE", "MAKEFILE_LIST", "SHELL"):
            return name
        raise _Unexpandable(name)

    def _function(self, name: str, body: str, depth: int) -> str:
        if name == "shell" and re.match(r"^\s*(?:git rev-parse --show-toplevel|pwd)\b", body):
            # the repository-root idiom: REPO_ROOT := $(shell git rev-parse --show-toplevel 2>/dev/null || pwd)
            return self.base
        args = [self.expand(a, depth + 1) for a in body.split(",")]
        if name == "addprefix" and len(args) == 2:
            return " ".join(args[0].strip() + w for w in args[1].split())
        if name == "addsuffix" and len(args) == 2:
            return " ".join(w + args[0].strip() for w in args[1].split())
        if name in ("strip", "sort"):
            words = args[0].split()
            return " ".join(sorted(set(words)) if name == "sort" else words)
        if name == "wildcard":
            matched = [
                f for pattern in args[0].split() for f in self.repo.files if PurePosixPath(f).match(normalize_path(self.base, pattern) or pattern)
            ]
            return " ".join(sorted({str(PurePosixPath(f).relative_to(self.base)) if self.base != "." else f for f in matched}))
        raise _Unexpandable(name)

    def _read(self, rel: str, depth: int) -> None:
        text, status = self.repo.text(rel)
        if text is None:
            self.problems.append(f"{rel} ({status})")
            return
        self.files.append(rel)
        for number, line in _join_continuations(text):
            if line.startswith("\t") or not line.strip() or line.lstrip().startswith("#"):
                continue
            stripped = re.sub(r"[ \t]+#.*$", "", line).rstrip()
            include = MAKE_INCLUDE_RE.match(stripped)
            if include:
                optional = include.group(1) != "include"
                try:
                    names = self.expand(include.group(2)).split()
                except _Unexpandable as error:
                    self.problems.append(f"{rel}:{number} include of {include.group(2).strip()} ({error} is not known statically)")
                    continue
                for name in names:
                    target = normalize_path(self.base, name)
                    if target and target in self.repo.file_set and depth < 10:
                        self._read(target, depth + 1)
                    elif not optional:
                        self.problems.append(f"{rel}:{number} includes {name}, which is not in the repository")
                continue
            if "$(eval" in stripped or stripped.startswith("define "):
                self.problems.append(f"{rel}:{number} defines targets dynamically ({stripped.split()[0]})")
                continue
            variable = MAKE_VAR_RE.match(stripped)
            if variable:
                if variable.group(2) == "+=":
                    self.variables[variable.group(1)] = self.variables.get(variable.group(1), "") + " " + variable.group(3)
                elif variable.group(2) != "?=" or variable.group(1) not in self.variables:
                    self.variables[variable.group(1)] = variable.group(3)
                continue
            rule = MAKE_RULE_RE.match(stripped)
            if rule:
                try:
                    names = self.expand(rule.group(1)).split()
                except _Unexpandable:
                    self.problems.append(f"{rel}:{number} rule {rule.group(1).strip()} names targets through unknown variables")
                    continue
                for name in names:
                    if not name.startswith(".") and "%" not in name:
                        self.targets.setdefault(name, f"{rel}:{number}")


def project_binaries(repo: Repo) -> dict[str, str]:
    """The project's own executables: name -> language."""
    binaries: dict[str, str] = {}
    for rel in repo.files:
        if _is_test_path(rel):
            continue  # a test fixture's manifest is not the project's binary, and its flags are never scanned
        name = PurePosixPath(rel).name
        if name == "Cargo.toml":
            text, _ = repo.text(rel)
            try:
                data = tomllib.loads(text or "")
            except tomllib.TOMLDecodeError:
                continue
            package = data.get("package", {})
            directory = str(PurePosixPath(rel).parent)
            main = normalize_path(directory, "src/main.rs")
            if package.get("name") and main in repo.file_set:
                binaries[str(package["name"])] = "rust"
            for entry in data.get("bin", []) or []:
                if isinstance(entry, dict) and entry.get("name"):
                    binaries[str(entry["name"])] = "rust"
        elif name == "main.go":
            parts = PurePosixPath(rel).parts
            if len(parts) >= 3 and parts[-3] == "cmd":
                binaries[parts[-2]] = "go"
        elif name == "pyproject.toml":
            text, _ = repo.text(rel)
            try:
                scripts = tomllib.loads(text or "").get("project", {}).get("scripts", {})
            except tomllib.TOMLDecodeError:
                continue
            binaries.update(dict.fromkeys(map(str, scripts), "python"))
        elif name == "package.json" and "node_modules/" not in rel:
            text, _ = repo.text(rel)
            try:
                manifest = json.loads(text or "{}")
            except json.JSONDecodeError:
                continue
            bin_field = manifest.get("bin") if isinstance(manifest, dict) else None
            if isinstance(bin_field, str) and manifest.get("name"):
                binaries[str(manifest["name"]).rsplit("/", 1)[-1]] = "js"
            elif isinstance(bin_field, dict):
                binaries.update(dict.fromkeys(map(str, bin_field), "js"))
    if "go.mod" in repo.file_set and not any(lang == "go" for lang in binaries.values()):
        text, _ = repo.text("go.mod")
        module = re.search(r"^module\s+(\S+)", text or "", re.MULTILINE)
        main_text = repo.text("main.go")[0] if "main.go" in repo.file_set else None
        if module and main_text and re.search(r"^package main\b", main_text, re.MULTILINE):
            binaries[module.group(1).rsplit("/", 1)[-1]] = "go"
    return binaries


def _is_test_path(rel: str) -> bool:
    path = PurePosixPath(rel)
    return bool(
        set(path.parts[:-1]) & {"test", "tests", "testdata", "__tests__", "spec"} or re.search(r"(^test_|_test\.|\.test\.|\.spec\.)", path.name)
    )


def flag_definitions(text: str, language: str, constants: dict[str, str] | None = None) -> set[str]:
    """Long flags a source file defines: CLI-library patterns, plus "--flag" literals of hand parsers."""
    flags: set[str] = set(FLAG_LITERAL_RE.findall(text))
    for name in GLIB_CONST_FLAG_RE.findall(text):
        if constants and name in constants:
            flags.add("--" + constants[name].lstrip("-"))
    if language == "rust":
        for match in CLAP_FIELD_RE.finditer(text):
            attrs = match.group(1)
            if not re.search(r"\blong\b", attrs):
                continue
            explicit = re.search(r"\blong\s*=\s*\"([\w-]+)\"", attrs)
            flags.add("--" + (explicit.group(1) if explicit else match.group(2).replace("_", "-")))
            flags.update("--" + a for a in re.findall(r"\b(?:visible_)?(?:long_)?alias(?:es)?\s*=\s*\[?\s*\"([\w-]+)\"", attrs))
    for pattern in FLAG_DEFS.get(language, ()):
        for match in pattern.finditer(text):
            value = match.group(1)
            if language == "python":
                flags.update(re.findall(r"[\"'](--[\w-]+)[\"']", value))
            elif language == "js":
                if "--" in value:
                    flags.update(re.findall(r"(--[\w-]+)", value))
                else:
                    flags.add("--" + value.strip())
            else:
                flags.add("--" + value)
    flags.update("--" + f for f in GLIB_FLAG_RE.findall(text))
    return flags


ENV_CALLS = {
    "rust": re.compile(r"\benv::var(?:_os)?\("),
    "go": re.compile(r"\bos\.(?:Getenv|LookupEnv)\("),
    "python": re.compile(r"\b(?:environ\.get|environ\.pop|environ\.setdefault|getenv)\(|\benviron\["),
    "js": re.compile(r"\bprocess\.env\["),
}
LITERAL_ARG_RE = re.compile(r"""^\s*(?:"[^"\\]*"|'[^'\\]*')\s*$""")
NAME_ARG_RE = re.compile(r"^\s*&?([A-Za-z_]\w*(?:(?:::|\.)[A-Za-z_]\w*)*)\s*$")
# string constants a reader may name, declared where a parameter cannot shadow them unnoticed
CONST_DECLS = {
    "rust": (re.compile(r"\b(?:const|static)\s+([A-Za-z_]\w*)\s*:\s*&(?:'static\s+)?str\s*=\s*\"([^\"]+)\""),),
    "go": (
        re.compile(r"^(?:const|var)\s+([A-Za-z_]\w*)\s*(?:[A-Za-z_][\w.]*\s*)?=\s*\"([^\"]+)\"", re.MULTILINE),
        re.compile(r"^\s+([A-Za-z_]\w*)\s*(?:[A-Za-z_][\w.]*\s*)?=\s*\"([^\"]+)\"\s*(?://.*)?$", re.MULTILINE),
    ),
    "python": (re.compile(r"^([A-Za-z_]\w*)\s*(?::\s*\w+\s*)?=\s*[\"']([^\"']+)[\"']\s*(?:#.*)?$", re.MULTILINE),),
    "js": (re.compile(r"^(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*(?::\s*\w+\s*)?=\s*[\"'`]([^\"'`$]+)[\"'`]", re.MULTILINE),),
}


def _const_decls(language: str, text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    if language == "go":
        # the second Go pattern reads the indented lines of const ( ... ) blocks only
        top = CONST_DECLS["go"][0].findall(text)
        blocks = "\n".join(re.findall(r"^const\s*\(\n(.*?)^\)", text, re.MULTILINE | re.DOTALL))
        found.update(dict(top))
        found.update(dict(CONST_DECLS["go"][1].findall(blocks)))
        return found
    for pattern in CONST_DECLS.get(language, ()):
        found.update(dict(pattern.findall(text)))
    return found


def _first_argument(text: str, start: int) -> str:
    """The text of the first argument of a call whose ( or [ ends just before start."""
    depth, index = 0, start
    while index < len(text):
        char = text[index]
        if char in "\"'":
            index += 1
            while index < len(text) and text[index] != char:
                index += 2 if text[index] == "\\" else 1
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            if depth == 0:
                return text[start:index]
            depth -= 1
        elif char == "," and depth == 0:
            return text[start:index]
        index += 1
    return text[start:]


def env_dynamic(rel: str, text: str) -> list[str]:
    """Arguments of environment API calls that are not string literals: names to resolve, or expressions."""
    pattern = ENV_CALLS.get(LANG_OF.get(PurePosixPath(rel).suffix.lower()) or "")
    if pattern is None:
        return []
    out = []
    for match in pattern.finditer(text):
        argument = _first_argument(text, match.end())
        if not LITERAL_ARG_RE.match(argument):
            out.append(" ".join(argument.split()))
    return out


def resolve_env_argument(repo: Repo, rel: str, argument: str, cache: dict[str, dict[str, str]]) -> str | None:
    """The variable a non-literal env argument names, or None when docstool cannot know it."""
    name = NAME_ARG_RE.match(argument)
    if name is None:
        return None
    language = LANG_OF.get(PurePosixPath(rel).suffix.lower()) or ""

    def decls(path: str) -> dict[str, str]:
        if path not in cache:
            cache[path] = _const_decls(LANG_OF.get(PurePosixPath(path).suffix.lower()) or "", repo.text(path)[0] or "")
        return cache[path]

    parts = re.split(r"::|\.", name.group(1))
    ident = parts[-1]
    if len(parts) == 1:
        scope = [rel]
        if language == "go":
            # a Go package is its directory
            folder = str(PurePosixPath(rel).parent)
            scope = [f for f in repo.files if f.endswith(".go") and str(PurePosixPath(f).parent) == folder and not _is_test_path(f)]
    elif language == "rust":
        scope = [f for f in repo.files if f.endswith(".rs") and not _is_test_path(f)]
    else:
        # pkg.Name / module.NAME: the package directory or module file of that name
        qualifier = parts[-2]
        scope = [
            f
            for f in repo.files
            if LANG_OF.get(PurePosixPath(f).suffix.lower()) == language
            and not _is_test_path(f)
            and (PurePosixPath(f).parent.name == qualifier or PurePosixPath(f).stem == qualifier)
        ]
    values = {decls(f)[ident] for f in scope if ident in decls(f)}
    return values.pop() if len(values) == 1 else None


def env_readers(rel: str, text: str) -> set[str]:
    """Environment variables the file reads through a language API."""
    language = LANG_OF.get(PurePosixPath(rel).suffix.lower())
    found: set[str] = set()
    for pattern in ENV_READERS.get(language or "", ()):
        found.update(pattern.findall(text))
    return found


def env_mentions(rel: str, text: str) -> set[str]:
    """Variables a script, compose file, Dockerfile, workflow or .env sample uses or defines."""
    name = re.sub(r"\.(?:j2|jinja2?|tmpl|tpl|template|example|sample|dist)$", "", PurePosixPath(rel).name)
    found: set[str] = set()
    if name.endswith((".sh", ".bash", ".zsh", ".mk")) or name in ("Makefile", "GNUmakefile", "justfile", "Justfile") or rel.startswith(".github/"):
        found.update(SHELL_ENV_RE.findall(text))
    if re.match(r"(docker-)?compose.*\.ya?ml$", name) or name.startswith("Dockerfile") or name.endswith(".env") or ".env." in name or name == ".env":
        found.update(SHELL_ENV_RE.findall(text))
        found.update(COMPOSE_ENV_RE.findall(text))
        found.update(DOCKER_ENV_RE.findall(text))
        found.update(DOTENV_RE.findall(text))
    return found


def _implicit_env(name: str) -> bool:
    return name in IMPLICIT_ENV or name.startswith(IMPLICIT_ENV_PREFIXES)


def doc_commands(doc: MarkdownDoc) -> Iterable[tuple[int, str, str]]:
    """(line, command, origin) for every shell command in a doc: code blocks and inline code."""
    for info, content, line in doc.code_blocks:
        if info.split(" ", 1)[0].lower() not in SHELL_INFOS:
            continue
        prompted = any(re.match(r"^[ \t]*[$%#][ \t]", text) for text in content.split("\n"))
        for offset, text in _join_continuations(content):
            stripped = text.strip()
            if prompted:
                prompt = re.match(r"^[$%][ \t]+(.*)$", stripped)
                if not prompt:
                    continue
                stripped = prompt.group(1)
            if stripped and not stripped.startswith("#"):
                yield line + offset, stripped, "block"
    body = without_fences("\n".join(doc.lines))
    for number, text in enumerate(body.split("\n"), 1):
        for match in CODE_SPAN_RE.finditer(text):
            yield number, match.group(2).strip(), "span"


def _split_command(text: str) -> list[list[str]]:
    """Shell words of each command in a line: comments dropped, split at ;, &, |, && and ||."""
    lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|()<>")
    lexer.whitespace_split = True
    try:
        words = list(lexer)
    except ValueError:
        words = text.split("#", 1)[0].split()
    commands: list[list[str]] = [[]]
    for word in words:
        if word and set(word) <= set(";&|()<>"):
            commands.append([])
        else:
            commands[-1].append(word)
    out = []
    for words_of_command in commands:
        start = 0
        while start < len(words_of_command) and (
            re.match(r"^[A-Za-z_]\w*=", words_of_command[start]) or words_of_command[start] in ("sudo", "env", "time", "exec", "command")
        ):
            start += 1
        if start < len(words_of_command):
            out.append(words_of_command[start:])
    return out


def _placeholder(token: str) -> bool:
    return not re.match(r"^[\w.+/@:-]+$", token) or token.isupper()


def cmd_drift(args: argparse.Namespace, report: Report) -> list[str]:
    repo = Repo(Path(args.root))
    site = load_site(repo, report)
    corpus = Corpus(repo, site)
    report.coverage.append(
        CoverageRow("markdown", "partial" if corpus.unreadable else "complete", ", ".join(corpus.unreadable) or f"{len(corpus.docs)} files")
    )
    scope = select_scope(corpus, args.scope)
    binaries = project_binaries(repo)
    # Definitions in the code
    makefiles = {r: None for r in repo.files if PurePosixPath(r).name in ("Makefile", "GNUmakefile", "makefile") and not _is_test_path(r)}
    models = {r: MakeModel(repo, r) for r in makefiles}
    make_problems = [p for m in models.values() for p in m.problems]
    flags: dict[str, set[str]] = defaultdict(set)
    readers: dict[str, list[str]] = defaultdict(list)
    mentioned: set[str] = set()
    flatten_unknown: list[str] = []
    rust_structs: set[str] = set()
    constants: dict[str, str] = {}
    declared: dict[str, dict[str, str]] = {}
    for rel in repo.files:
        if rel.endswith(".rs") and not _is_test_path(rel):
            constants.update(RUST_STR_CONST_RE.findall(repo.text(rel)[0] or ""))
    unresolved: list[str] = []
    for rel in repo.files:
        suffix = PurePosixPath(rel).suffix.lower()
        language = LANG_OF.get(suffix)
        text, _ = repo.text(rel)
        if not text:
            continue
        if language and not _is_test_path(rel):
            flags[language].update(flag_definitions(text, language, constants))
            if language == "rust":
                rust_structs.update(re.findall(r"\bstruct\s+(\w+)", text))
                flatten_unknown += [f"{rel}: {t}" for t in CLAP_FLATTEN_RE.findall(text)]
            if not _is_test_path(rel):
                for name in env_readers(rel, text):
                    readers[name].append(rel)
                for argument in sorted(set(env_dynamic(rel, text))):
                    resolved = resolve_env_argument(repo, rel, argument, declared)
                    if resolved is not None:
                        readers[resolved].append(rel)
                        mentioned.add(resolved)
                    else:
                        unresolved.append(f"{rel}: {argument}")
        if suffix not in MARKDOWN_EXTENSIONS:
            mentioned.update(env_mentions(rel, text))
            mentioned.update(env_readers(rel, text))
    flatten_unknown = [f for f in flatten_unknown if f.rsplit("::", 1)[-1].rsplit(" ", 1)[-1] not in rust_structs]
    scripts = _package_scripts(repo)
    recipes = _just_recipes(repo)
    languages = set(binaries.values())
    known_flags = set(AUTO_FLAGS).union(*(flags[lang] for lang in languages)) if languages else set(AUTO_FLAGS)
    if not makefiles:
        report.coverage.append(CoverageRow("make", "not_applicable", "no Makefile"))
    else:
        reason = f"{sum(len(m.targets) for m in models.values())} targets from {sum(len(m.files) for m in models.values())} files"
        report.coverage.append(
            CoverageRow("make", "partial" if make_problems else "complete", reason + ("; " + "; ".join(make_problems[:5]) if make_problems else ""))
        )
    if not binaries:
        report.coverage.append(CoverageRow("flags", "not_applicable", "no project binaries found"))
    else:
        missing_lang = sorted(lang for lang in languages if not flags[lang])
        problems = [f"no flag definitions recognised in the {lang} sources" for lang in missing_lang] + [
            f"flattened type defined outside the repository: {f}" for f in flatten_unknown[:5]
        ]
        report.coverage.append(
            CoverageRow(
                "flags", "partial" if problems else "complete", "; ".join(problems) or f"{len(known_flags)} flags for {', '.join(sorted(binaries))}"
            )
        )
    report.coverage.append(
        CoverageRow(
            "env",
            "partial" if unresolved else "complete",
            f"{len(readers)} variables read through language APIs"
            + (f"; {len(unresolved)} reads through a name docstool cannot resolve ({', '.join(unresolved[:5])})" if unresolved else ""),
        )
    )
    rows = {r.input: r for r in report.coverage}
    flag_confidence = "verified" if rows["flags"].complete else "likely"
    make_confidence = "verified" if rows["make"].complete else "likely"
    documented_env: dict[str, tuple[str, int]] = {}
    seen: set[tuple[str, int, str]] = set()

    def add(finding: Finding) -> None:
        key = (finding.file, finding.line, finding.message)
        if key not in seen:
            seen.add(key)
            report.add(finding)

    for rel in sorted(scope):
        doc = corpus.docs[rel]
        base_dir = str(PurePosixPath(rel).parent)
        for number, command, origin in doc_commands(doc):
            if origin == "span":
                env = DOC_ENV_SPAN_RE.match(command)
                line_text = doc.lines[number - 1] if number <= len(doc.lines) else ""
                if env and (command[0] == "$" or "=" in command or ENV_CONTEXT_RE.search(line_text)):
                    documented_env.setdefault(env.group(1), (rel, number))
                flag = FLAG_TOKEN_RE.match(command)
                mentions_binary = any(re.search(rf"(?<![\w-]){re.escape(b)}(?![\w-])", line_text) for b in binaries)
                if flag and mentions_binary and flag.group(1) not in known_flags:
                    add(
                        Finding(
                            "flag-unknown",
                            "P3",
                            "unverified",
                            rel,
                            number,
                            f"{flag.group(1)} is not a flag of {', '.join(sorted(binaries))}",
                            suggestion="if it is another tool's flag, ignore this lead",
                        )
                    )
            else:
                for match in DOC_ENV_BLOCK_RE.finditer(command):
                    documented_env.setdefault(match.group(1) or match.group(2), (rel, number))
            for tokens in _split_command(command):
                _check_command(
                    tokens,
                    rel,
                    number,
                    origin,
                    base_dir,
                    repo,
                    models,
                    scripts,
                    recipes,
                    binaries,
                    known_flags,
                    flag_confidence,
                    make_confidence,
                    add,
                )
    for name, (rel, number) in sorted(documented_env.items()):
        if name not in readers and name not in mentioned and not _implicit_env(name):
            add(
                Finding(
                    "env-unknown",
                    "P2",
                    "likely",
                    rel,
                    number,
                    f"{name} is documented but nothing in the repository reads it",
                    suggestion="remove it from the docs, or point at the code that reads it",
                )
            )
    all_text = "\n".join("\n".join(d.lines) for d in corpus.docs.values())
    for name, files in sorted(readers.items()):
        if not _implicit_env(name) and not re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", all_text):
            add(
                Finding(
                    "env-undocumented",
                    "P3",
                    "unverified",
                    files[0],
                    _line_of(repo, files[0], name) or 1,
                    f"{name} is read here but no Markdown file mentions it",
                )
            )
    if args.paths:
        _check_paths(corpus, scope, repo, add)
    history = _commit_times(repo)
    report.data["stale"] = _staleness(corpus, scope, repo, history)
    if args.leads:
        _status_leads(corpus, scope, repo, add)
        for item in report.data["stale"]:
            add(
                Finding(
                    "stale-lead",
                    "P3",
                    "unverified",
                    item["doc"],
                    1,
                    f"last changed {item['days']} days before {item['reference']}, which it references",
                    suggestion="check the doc against the current file",
                )
            )
    if args.base:
        _base_drift(args.base, repo, corpus, models, flags, readers, add)
        # a removed flag still documented is one problem, not also an unknown flag on the same line
        removed = {(f.file, f.line, f.message.split(" ")[0]) for f in report.findings if f.check == "removed-still-documented"}
        report.findings = [f for f in report.findings if not (f.check == "flag-unknown" and (f.file, f.line, _first_flag(f.message)) in removed)]
    report.data.update(
        {
            "binaries": binaries,
            "make_targets": sorted({t for m in models.values() for t in m.targets}),
            "flags": sorted(known_flags),
            "env_read": sorted(readers),
            "package_scripts": sorted(scripts),
        }
    )
    return ["markdown", "make", "flags", "env"]


def _first_flag(message: str) -> str:
    match = re.search(r"--[\w-]+", message)
    return match.group(0) if match else ""


def _line_of(repo: Repo, rel: str, needle: str) -> int:
    text, _ = repo.text(rel)
    for number, line in enumerate((text or "").split("\n"), 1):
        if needle in line:
            return number
    return 0


def _package_scripts(repo: Repo) -> set[str]:
    """Scripts of every package.json in the repository (a doc may cd into a package first)."""
    scripts: set[str] = set()
    for rel in repo.files:
        if PurePosixPath(rel).name != "package.json" or "node_modules/" in rel:
            continue
        text, _ = repo.text(rel)
        try:
            manifest = json.loads(text) if text else {}
        except json.JSONDecodeError:
            continue
        if isinstance(manifest, dict) and isinstance(manifest.get("scripts"), dict):
            scripts.update(manifest["scripts"])
    return scripts


def _just_recipes(repo: Repo) -> set[str]:
    for name in ("justfile", "Justfile", ".justfile"):
        if name in repo.file_set:
            text, _ = repo.text(name)
            return set(re.findall(r"^@?([a-zA-Z_][\w-]*)(?:[ \t]+[^:\n=]*)?:(?!=)", text or "", re.MULTILINE))
    return set()


def _check_command(
    tokens: list[str],
    rel: str,
    number: int,
    origin: str,
    base_dir: str,
    repo: Repo,
    models: dict[str, MakeModel],
    scripts: set[str],
    recipes: set[str],
    binaries: dict[str, str],
    known_flags: set[str],
    flag_confidence: str,
    make_confidence: str,
    add: Callable[[Finding], None],
) -> None:
    program = tokens[0]
    rest = tokens[1:]
    if program in ("make", "gmake"):
        directory, makefile, targets = ".", None, []
        index = 0
        while index < len(rest):
            token = rest[index]
            if token in ("-C", "--directory", "-f", "--file", "--makefile", "-j", "--jobs", "-l", "-o", "-W") and index + 1 < len(rest):
                if token in ("-C", "--directory"):
                    directory = normalize_path(directory, rest[index + 1]) or directory
                elif token in ("-f", "--file", "--makefile"):
                    makefile = rest[index + 1]
                index += 2
                continue
            if token.startswith("--directory="):
                directory = normalize_path(directory, token.split("=", 1)[1]) or directory
            elif token.startswith(("--file=", "--makefile=")):
                makefile = token.split("=", 1)[1]
            elif not token.startswith("-") and "=" not in token and not _placeholder(token):
                targets.append(token)
            index += 1
        path = (
            normalize_path(directory, makefile)
            if makefile
            else next((normalize_path(directory, n) for n in ("GNUmakefile", "makefile", "Makefile") if normalize_path(directory, n) in models), None)
        )
        model = models.get(path or "")
        if model is None:
            if targets and origin == "block":
                add(Finding("make-missing", "P2", "likely", rel, number, f"make {' '.join(targets)}: no Makefile at {directory}"))
            elif targets and not models:
                # inline code can name another project's make; with no Makefile anywhere it is a lead
                add(
                    Finding(
                        "make-missing",
                        "P3",
                        "unverified",
                        rel,
                        number,
                        f"make {' '.join(targets)}: the repository has no Makefile",
                        suggestion="if it is another project's command, ignore this lead",
                    )
                )
            return
        for target in targets:
            if target not in model.targets:
                add(
                    Finding(
                        "make-target-missing",
                        "P1",
                        make_confidence,
                        rel,
                        number,
                        f"make {target}: no such target in {path} or the files it includes",
                        suggestion=f"targets: {', '.join(sorted(model.targets)[:12])}",
                    )
                )
        return
    if (
        program in ("npm", "pnpm", "yarn", "bun")
        and len(rest) >= 2
        and rest[0] == "run"
        and not rest[1].startswith("-")
        and not _placeholder(rest[1])
    ):
        if rest[1] not in scripts:
            add(Finding("script-missing", "P1", "verified", rel, number, f"{program} run {rest[1]}: package.json has no such script"))
        return
    if program == "just" and rest and not rest[0].startswith("-") and recipes and not _placeholder(rest[0]):
        if rest[0] not in recipes:
            add(Finding("recipe-missing", "P1", "verified", rel, number, f"just {rest[0]}: the justfile has no such recipe"))
        return
    if program in ("bash", "sh", "zsh", "python", "python3") and rest and not rest[0].startswith("-"):
        program, rest = rest[0], rest[1:]
    if program.startswith("./") or re.match(r"^(?:scripts|bin|tools|hack|ci)/[\w./-]+$", program):
        target = _strip_dot_slash(program)
        if not _placeholder(target) and not repo.exists(target) and not repo.exists(normalize_path(base_dir, target) or ""):
            parent = str(PurePosixPath(target).parent)
            if parent == "." or repo.exists(parent):
                add(
                    Finding(
                        "path-missing",
                        "P2",
                        "likely",
                        rel,
                        number,
                        f"{program}: no such file in the repository",
                        suggestion="if it runs on another machine, say so in the text",
                    )
                )
            else:
                add(Finding("path-missing", "P3", "unverified", rel, number, f"{program}: {parent}/ is not in the repository (a build output?)"))
        return
    binary = program
    if program == "cargo" and rest[:1] == ["run"]:
        binary = next(iter(sorted(b for b, lang in binaries.items() if lang == "rust")), "")
        rest = rest[rest.index("--") + 1 :] if "--" in rest else []
    elif program == "go" and rest[:1] == ["run"] and len(rest) > 1:
        binary = PurePosixPath(rest[1]).name if rest[1].startswith(("./", "cmd/")) else ""
        rest = rest[2:]
    if binary in binaries:
        for token in rest:
            if token == "--":
                break
            flag = FLAG_TOKEN_RE.match(token)
            if flag and flag.group(1) not in known_flags:
                add(
                    Finding(
                        "flag-unknown",
                        "P1",
                        flag_confidence,
                        rel,
                        number,
                        f"{binary} {flag.group(1)}: the code defines no such flag",
                        suggestion="update the doc to the current flag name",
                    )
                )


# Slash-separated tokens that are not repository paths: hosts and import paths, OS/arch pairs, hex ids
NOT_A_PATH_RE = re.compile(
    r"^(?:[\w-]+\.)+[a-z]{2,}/|^[a-z0-9]+/(?:amd64|arm64|386|arm|armv\d|ppc64le|riscv64|s390x|x86_64|aarch64)$|\b0x[0-9a-fA-F]+\b"
)


def _check_paths(corpus: Corpus, scope: set[str], repo: Repo, add: Callable[[Finding], None]) -> None:
    basenames = {PurePosixPath(f).name for f in repo.files}
    top_level = {f.split("/", 1)[0] for f in repo.files}
    for rel in sorted(scope):
        doc = corpus.docs[rel]
        base_dir = str(PurePosixPath(rel).parent)
        for number, span, origin in doc_commands(doc):
            if origin != "span" or not PATH_SPAN_RE.match(span) or "://" in span or span.startswith(("~", "/")):
                continue
            target = _strip_dot_slash(span).rstrip("/")
            if _placeholder(target) or not target or NOT_A_PATH_RE.search(target):
                continue
            if repo.exists(target) or repo.exists(normalize_path(base_dir, target) or ""):
                continue
            if "/" not in target:
                # a bare file name: a path only when no file of that name exists anywhere
                if target not in basenames:
                    add(Finding("path-missing", "P3", "unverified", rel, number, f"{span}: no file of that name in the repository"))
                continue
            first = target.split("/", 1)[0]
            # a renamed top-level directory is drift too: a span that ends in a file name or a / names a path
            looks_like_path = bool(re.search(r"\.[A-Za-z0-9]{1,8}$", target)) or span.endswith("/")
            if first in top_level or repo.exists(normalize_path(base_dir, first) or "") or looks_like_path:
                add(Finding("path-missing", "P2", "likely", rel, number, f"{span}: no such path in the repository"))
            else:
                add(
                    Finding(
                        "path-missing",
                        "P3",
                        "unverified",
                        rel,
                        number,
                        f"{span}: no such path, and no {first}/ in the repository: it may not be a path",
                    )
                )


def _commit_times(repo: Repo) -> dict[str, int]:
    """The time of the last commit that touched each path (one read-only git log)."""
    if not repo.is_git:
        return {}
    out = git(repo.root, "log", "--format=%x00%ct", "--name-only", "--no-renames")
    times: dict[str, int] = {}
    if not out:
        return times
    for chunk in out.split("\0")[1:]:
        lines = chunk.strip("\n").split("\n")
        stamp = int(lines[0]) if lines and lines[0].isdigit() else 0
        for name in lines[1:]:
            if name and name not in times:
                times[name] = stamp
    return times


def _staleness(corpus: Corpus, scope: set[str], repo: Repo, history: dict[str, int]) -> list[dict[str, Any]]:
    """Docs whose last commit is older than the last commit of a file they link to or name."""
    out = []
    for rel in sorted(scope):
        if rel not in history:
            continue
        doc = corpus.docs[rel]
        base_dir = str(PurePosixPath(rel).parent)
        references: set[str] = set()
        for link in doc.links:
            target = unquote(link.target.split("#", 1)[0])
            if target and not SCHEME_RE.match(target):
                resolved = normalize_path(base_dir, target)
                if resolved and resolved in repo.file_set and not resolved.endswith(MARKDOWN_EXTENSIONS):
                    references.add(resolved)
        for _number, span, origin in doc_commands(doc):
            if origin == "span" and PATH_SPAN_RE.match(span):
                candidate = _strip_dot_slash(span)
                if candidate in repo.file_set and not candidate.endswith(MARKDOWN_EXTENSIONS):
                    references.add(candidate)
        dated = [(history[r], r) for r in references if r in history]
        if dated:
            newest, reference = max(dated)
            if newest > history[rel]:
                out.append({"doc": rel, "reference": reference, "days": (newest - history[rel]) // 86400})
    return out


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", version)[:3])


def _status_leads(corpus: Corpus, scope: set[str], repo: Repo, add: Callable[[Finding], None]) -> None:
    tags_out = git(repo.root, "tag", "--list") if repo.is_git else None
    tags = {m.group(1) for t in (tags_out or "").split() if (m := re.search(r"v?(\d+\.\d+(?:\.\d+)?)$", t))}
    latest = max(tags, key=_version_key) if tags else None
    for rel in sorted(scope):
        for block in corpus.docs[rel].blocks:
            if block.type not in ("paragraph", "list-item", "quote") and not block.type.startswith(("admonition", "alert")):
                continue
            for match in STATUS_RE.finditer(block.text):
                word, version = match.group(1).lower(), match.group(2)
                future = word.startswith(("planned", "coming", "will"))
                released = any(_version_key(t) == _version_key(version) for t in tags)
                if future and released:
                    add(Finding("status-claim", "P2", "unverified", rel, block.line, f"says {version} is upcoming, but it is tagged"))
                elif not future and tags and not released and latest and _version_key(version) > _version_key(latest):
                    add(Finding("status-claim", "P2", "unverified", rel, block.line, f"names {version} as released; the latest tag is {latest}"))
            for match in COUNT_RE.finditer(block.text):
                add(
                    Finding(
                        "count-lead",
                        "P3",
                        "unverified",
                        rel,
                        block.line,
                        f"hand-maintained count: {match.group(0)!r}",
                        suggestion="recount, or drop the number",
                    )
                )


def _diff_sides(repo: Repo, base: str) -> dict[str, tuple[str, str]]:
    """Per changed non-Markdown file: (removed lines, added lines) of git diff base."""
    if not repo.is_git or git(repo.root, "rev-parse", "--verify", "--quiet", base + "^{commit}") is None:
        raise UsageError(f"--base {base} is not a commit in this repository")
    out = git(
        repo.root, "diff", "--no-color", "--no-ext-diff", "--unified=0", "--no-renames", base, "--", ".", ":(exclude)*.md", ":(exclude)*.markdown"
    )
    sides: dict[str, tuple[list[str], list[str]]] = {}
    current = None
    for line in (out or "").split("\n"):
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else current
        elif line.startswith("--- "):
            current = line[6:] if line.startswith("--- a/") else None
        elif current and line.startswith("-") and not line.startswith("---"):
            sides.setdefault(current, ([], []))[0].append(line[1:])
        elif current and line.startswith("+") and not line.startswith("+++"):
            sides.setdefault(current, ([], []))[1].append(line[1:])
    return {k: ("\n".join(v[0]), "\n".join(v[1])) for k, v in sides.items()}


def _tokens(rel: str, text: str) -> set[tuple[str, str]]:
    language = LANG_OF.get(PurePosixPath(rel).suffix.lower())
    tokens: set[tuple[str, str]] = set()
    if language:
        tokens |= {("flag", f) for f in flag_definitions(text, language)}
        tokens |= {("env", e) for e in env_readers(rel, text)}
    name = PurePosixPath(rel).name
    if name in ("Makefile", "GNUmakefile", "makefile") or name.endswith(".mk"):
        for line in text.split("\n"):
            rule = MAKE_RULE_RE.match(line)
            if rule and not line.startswith("\t") and "=" not in rule.group(1):
                tokens |= {("make", t) for t in rule.group(1).split() if not t.startswith(".") and "%" not in t and "$" not in t}
    return tokens


def _base_drift(
    base: str,
    repo: Repo,
    corpus: Corpus,
    models: dict[str, MakeModel],
    flags: dict[str, set[str]],
    readers: dict[str, list[str]],
    add: Callable[[Finding], None],
) -> None:
    removed: dict[tuple[str, str], str] = {}
    added: dict[tuple[str, str], str] = {}
    for rel, (old, new) in sorted(_diff_sides(repo, base).items()):
        before, after = _tokens(rel, old), _tokens(rel, new)
        for token in before - after:
            removed.setdefault(token, rel)
        for token in after - before:
            added.setdefault(token, rel)
    current = (
        {("flag", f) for fs in flags.values() for f in fs} | {("env", e) for e in readers} | {("make", t) for m in models.values() for t in m.targets}
    )
    for token in list(removed):
        if token in added or token in current:
            removed.pop(token)
            added.pop(token, None)
    for (kind, value), source in sorted(removed.items()):
        for rel, doc in sorted(corpus.docs.items()):
            for number, line in enumerate(doc.lines, 1):
                pattern = rf"\bmake\b[^\n`]*\s{re.escape(value)}\b" if kind == "make" else rf"(?<![\w-]){re.escape(value)}(?![\w-])"
                if re.search(pattern, line):
                    add(
                        Finding(
                            "removed-still-documented",
                            "P1",
                            "verified",
                            rel,
                            number,
                            f"{value} ({kind}) was removed from {source} since {base} but the doc still names it",
                            [f"{source}: removed"],
                        )
                    )
    all_text = "\n".join("\n".join(d.lines) for d in corpus.docs.values())
    for (kind, value), source in sorted(added.items()):
        if not re.search(rf"(?<![\w-]){re.escape(value)}(?![\w-])", all_text):
            add(
                Finding(
                    "added-undocumented",
                    "P3",
                    "likely",
                    source,
                    _line_of(repo, source, f'"{value.lstrip("-")}"') or _line_of(repo, source, value.lstrip("-")) or 1,
                    f"{value} ({kind}) is new since {base} and no doc mentions it",
                )
            )


# ---------------------------------------------------------------------------------------------
# site-build and built-site baselines
# ---------------------------------------------------------------------------------------------

STAMP_NAME = ".docstool-build.json"
GENERATOR_HINTS = {
    "zensical": (
        "run docstool through the repository's docs uv project (uv run --project tools/docs --locked python3 -I docstool.py ...), "
        f"install it from the repository's hashed lock, or pip install zensical=={KNOWN_ZENSICAL}"
    ),
    "mkdocs": "pip install mkdocs and the theme and plugins mkdocs.yml names",
}
# Plugins whose inputs docstool knows: none beyond the pages, or the ones it adds below.
KNOWN_INPUT_PLUGINS = frozenset(
    [
        "search",
        "tags",
        "offline",
        "privacy",
        "social",
        "meta",
        "minify",
        "glightbox",
        "section-index",
        "literate-nav",
        "awesome-nav",
        "redirects",
        "gh-admonitions",
        "callouts",
        "exclude",
        "llmstxt",
        "meta-descriptions",
        "rss",
        "optimize",
        "blog",
        "autorefs",
        "mkdocs-nav-weight",
        "nav-weight",
        "mkdocs-video",
        "mkdocs-audio",
        "table-reader",
        "include-markdown",
        "git-revision-date-localized",
        "mike",
    ]
)
META_REFRESH_RE = re.compile(r"""<meta[^>]+http-equiv=["']refresh["'][^>]*content=["']\s*\d+\s*;\s*url=([^"'>]+)["']""", re.IGNORECASE)
ID_ATTR_RE = re.compile(r"""\bid=(?:"([^"]+)"|'([^']+)')""")
INCLUDE_MARKDOWN_RE = re.compile(r"""\{%\s*include(?:-markdown)?\s+["']([^"']+)["']""")
SNIPPET_BLOCK_RE = re.compile(r"^[ \t]*;?--8<--[ \t]*$")


def _snippet_paths(text: str) -> list[str]:
    paths = []
    in_block = False
    for line in text.split("\n"):
        if SNIPPET_BLOCK_RE.match(line):
            in_block = not in_block
            continue
        if in_block:
            if line.strip() and not line.strip().startswith(";"):
                paths.append(line.strip())
            continue
        match = SNIPPET_RE.match(line)
        if match:
            paths.append(match.group("path"))
    return paths


def build_inputs(repo: Repo, site: Site) -> tuple[dict[str, str], list[str]]:
    """Every file the build reads, with its SHA-256, and what makes that list incomplete."""
    inputs: dict[str, str] = {}
    partial: list[str] = []

    def take(rel: str) -> bool:
        if rel in inputs:
            return False
        digest = file_sha256(repo.root / rel)
        if digest is None:
            return False
        inputs[rel] = digest
        return True

    if site.config:
        take(site.config)
    pages = []
    for rel in repo.files:
        if site.in_docs(rel):
            inner = site.docs_rel(rel)
            if not (DEFAULT_EXCLUDES.match(inner) or site.exclude.match(inner)):
                take(rel)
                if rel.endswith(MARKDOWN_EXTENSIONS):
                    pages.append(rel)
        if site.custom_dir and rel.startswith(site.custom_dir + "/"):
            take(rel)
    bases = snippet_bases(site)
    options = site.extensions.get("pymdownx.snippets")
    appended = options.get("auto_append", []) if isinstance(options, dict) else []
    queue = list(pages)
    if bases is not None:
        for name in appended if isinstance(appended, list) else [appended]:
            for base in bases:
                candidate = normalize_path(base, str(name))
                if candidate and take(candidate):
                    queue.append(candidate)
    while queue:
        rel = queue.pop()
        text, _ = repo.text(rel)
        if not text:
            continue
        if bases is not None:
            for raw in _snippet_paths(text):
                if re.match(r"^https?://", raw):
                    partial.append(f"{rel}: snippet from a URL ({raw})")
                    continue
                name = re.sub(r":(\d+(?::\d+)?|[\w-]+)$", "", raw)
                found = [c for b in bases if (c := normalize_path(b, name)) and c in repo.file_set]
                for candidate in found[:1]:
                    if take(candidate) and candidate.endswith((*MARKDOWN_EXTENSIONS, ".html", ".txt")):
                        queue.append(candidate)
        if "include-markdown" in site.plugins:
            for name in INCLUDE_MARKDOWN_RE.findall(text):
                candidate = normalize_path(str(PurePosixPath(rel).parent), name)
                if candidate and take(candidate):
                    queue.append(candidate)
    for name, options_value in site.plugins.items():
        canonical = name.removeprefix("material/").split("/", 1)[0]
        if canonical == "git-revision-date-localized" or canonical.startswith("git-"):
            head = git(repo.root, "rev-parse", "HEAD") if repo.is_git else None
            inputs["git:HEAD"] = (head or "unknown").strip()
        elif canonical == "macros":
            module = options_value.get("module_name", "main") if isinstance(options_value, dict) else "main"
            if f"{module}.py" in repo.file_set or any(f.startswith(f"{module}/") for f in repo.files):
                partial.append(f"macros module {module} runs Python whose reads docstool cannot follow")
            include_dir = options_value.get("include_dir") if isinstance(options_value, dict) else None
            for rel in repo.files:
                if include_dir and rel.startswith(str(include_dir).strip("/") + "/"):
                    take(rel)
        elif canonical not in KNOWN_INPUT_PLUGINS:
            partial.append(f"plugin {name}: its inputs are not known")
    if site.kind == "mkdocs" and "hooks" in site.raw:
        partial.append("hooks: run Python whose reads docstool cannot follow")
    return dict(sorted(inputs.items())), partial


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != STAMP_NAME):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0" + (file_sha256(path) or "").encode() + b"\n")
    return digest.hexdigest()


def _safe_extract(archive: bytes, dest: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or member.isdev():
                raise UsageError(f"refusing archive member {member.name}")
            if member.issym() or member.islnk():
                target = (dest / name.parent / member.linkname).resolve()
                if not target.is_relative_to(dest.resolve()):
                    raise UsageError(f"refusing archive link {member.name} -> {member.linkname}")
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
        else:  # pragma: no cover - Python 3.11 before 3.11.4
            tar.extractall(dest)


def _copy_worktree(repo: Repo, dest: Path) -> None:
    for rel in repo.files:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo.root / rel, target)
    for rel, real in repo.symlinks.items():
        if real is not None:
            link = dest / rel
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(os.readlink(repo.root / rel))


def _fresh_out(out: Path) -> None:
    if out.is_symlink():
        raise UsageError(f"--out {out} is a symlink")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise UsageError(f"--out {out} must not exist or must be empty")
    if ".git" in out.resolve().parts:
        raise UsageError(f"refusing to write inside .git: {out}")


def cmd_site_build(args: argparse.Namespace, report: Report) -> list[str]:
    repo = Repo(Path(args.root))
    out = Path(args.out_dir)
    _fresh_out(out)
    with tempfile.TemporaryDirectory(prefix="docstool-build-") as scratch:
        source = Path(scratch) / "src"
        source.mkdir()
        commit = None
        if args.ref:
            commit = git(repo.root, "rev-parse", "--verify", "--quiet", args.ref + "^{commit}") if repo.is_git else None
            if commit is None:
                raise UsageError(f"--ref {args.ref} is not a commit in this repository")
            commit = commit.strip()
            archive = subprocess.run(["git", "-C", str(repo.root), "archive", "--format=tar", commit], capture_output=True, check=False)
            if archive.returncode != 0:
                raise UsageError(f"git archive {args.ref} failed: {archive.stderr.decode('utf-8', 'replace').strip()}")
            _safe_extract(archive.stdout, source)
        else:
            _copy_worktree(repo, source)
        built_repo = Repo(source)
        site = load_site(built_repo, report, prefer_mkdocs=args.generator == "mkdocs")
        if site.config is None or not {r.input: r for r in report.coverage}["config"].complete:
            raise UsageError("no readable zensical.toml or mkdocs.yml to build")
        generator = args.generator or ("zensical" if site.kind == "zensical" else "mkdocs")
        if repo.is_git and any("git-" in name for name in site.plugins):
            # git-revision-date-localized and similar plugins read the history: lend it to the staged
            # tree (read-only; the clone's own .git lives in the staging directory)
            _lend_history(repo, source, commit or (git(repo.root, "rev-parse", "--verify", "--quiet", "HEAD") or "").strip())
        command = shlex.split(args.generator_cmd) if args.generator_cmd else [shutil.which(generator) or ""]
        if not command[0]:
            raise UsageError(f"{generator} is not installed: {GENERATOR_HINTS[generator]}")
        version_run = subprocess.run([*command, "--version"], capture_output=True, text=True, check=False, cwd=source)
        version = (version_run.stdout or version_run.stderr).strip().split("\n")[0] if version_run.returncode == 0 else "unknown"
        build = [*command, "build", "--strict", "--clean", "-f", site.config]
        environment = {**os.environ, "NO_COLOR": "1"}
        result = subprocess.run(build, capture_output=True, text=True, check=False, cwd=source, env=environment)
        if result.returncode != 0:
            lines = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", result.stdout + result.stderr).strip().split("\n")
            # the generator's own diagnostics first: a traceback's tail alone hides the cause
            diagnostics = [
                line
                for line in lines
                if re.search(r"\b(?:error|warning|does not exist|not found|failed)\b", line, re.IGNORECASE) or re.search(r"[\w./-]+\.md:\d+", line)
            ]
            shown = list(dict.fromkeys([*diagnostics[:15], *lines[-10:]]))
            raise UsageError(f"{generator} build --strict failed (exit {result.returncode}); no stamp written:\n" + "\n".join(shown))
        site_dir = str(site.raw.get("site_dir", "site"))
        built = source / site_dir
        if not built.is_dir():
            raise UsageError(f"{generator} build wrote no {site_dir}/ directory")
        # built_repo was listed before the history was lent, so --ref inputs are the archive's files
        inputs, partial = build_inputs(built_repo, site) if args.ref else build_inputs(repo, _reload_site(repo, args.generator == "mkdocs"))
        out.mkdir(parents=True, exist_ok=True)
        shutil.copytree(built, out, dirs_exist_ok=True, symlinks=True)
    stamp = {
        "tool": "docstool",
        "version": __version__,
        "ref": args.ref,
        "commit": commit,
        "generator": generator,
        "generator_version": version,
        "command": " ".join([generator, *build[len(command) :]]),
        "output_sha256": _tree_sha256(out),
        "dependencies": "partial" if partial else "complete",
        "unknown_dependencies": partial,
        "inputs": inputs,
    }
    (out / STAMP_NAME).write_text(json.dumps(stamp, indent=1) + "\n", encoding="utf-8")
    report.coverage.append(CoverageRow("dependencies", "partial" if partial else "complete", "; ".join(partial[:5]) or f"{len(inputs)} inputs"))
    report.data.update({k: v for k, v in stamp.items() if k != "inputs"} | {"inputs": len(inputs), "out": str(out)})
    return []


def _reload_site(repo: Repo, prefer_mkdocs: bool = False) -> Site:
    return load_site(repo, Report(command="site-build", root=str(repo.root)), prefer_mkdocs)


def _lend_history(repo: Repo, source: Path, commit: str) -> None:
    """Make the staged tree a git repository at commit, borrowing the objects of the real one.

    The staged .git lists the repository's object directory as an alternate, so nothing is copied
    and nothing in the repository is written; only git plumbing that writes inside source runs."""
    if not commit:
        return
    common = git(repo.root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not common:
        raise UsageError("cannot locate the repository's git directory for the build's history")
    git_dir = source / ".git"
    # No inherited GIT_DIR or GIT_WORK_TREE can point these at the real repository, no template
    # or hook from the user's configuration runs, and nothing outside source is written.
    environment = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    for command in (["init", "--quiet", "--template=", str(source)], ["--git-dir", str(git_dir), "update-ref", "--no-deref", "HEAD", commit]):
        if command[0] == "--git-dir":
            alternates = git_dir / "objects" / "info" / "alternates"
            alternates.write_text(str(Path(common.strip()) / "objects") + "\n", encoding="utf-8")
        run = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *command], capture_output=True, text=True, check=False, env=environment)
        if run.returncode != 0:
            raise UsageError(f"git {command[0]} for the build's history failed: {run.stderr.strip()}")


def load_built(path: str, repo: Repo, site: Site) -> dict[str, Any]:
    """Read a site-build output; refuse one docstool did not build or whose inputs changed since."""
    out = Path(path)
    stamp_path = out / STAMP_NAME
    if not stamp_path.is_file():
        raise UsageError(f"{path} has no {STAMP_NAME}: build it with docstool site-build")
    stamp: dict[str, Any] = json.loads(stamp_path.read_text(encoding="utf-8"))
    if _tree_sha256(out) != stamp.get("output_sha256"):
        raise UsageError(f"{path} changed after it was built (output hash differs from the stamp)")
    if stamp.get("ref"):
        current = git(repo.root, "rev-parse", "--verify", "--quiet", str(stamp["ref"]) + "^{commit}") if repo.is_git else None
        if (current or "").strip() != stamp.get("commit"):
            raise UsageError(f"{path} was built from {stamp['ref']} at {stamp.get('commit')}, which now names another commit")
    else:
        # a MkDocs build read mkdocs.yml even where Zensical would read zensical.toml
        inputs, _ = build_inputs(repo, _reload_site(repo, prefer_mkdocs=True) if stamp.get("generator") == "mkdocs" else site)
        if inputs != stamp.get("inputs"):
            changed = sorted(k for k in set(inputs) | set(stamp.get("inputs", {})) if inputs.get(k) != stamp.get("inputs", {}).get(k))
            raise UsageError(f"{path} is stale: {len(changed)} build inputs changed since it was built ({', '.join(changed[:5])})")
    stamp["site"] = read_built_site(out)
    return stamp


def _page_url(rel: str) -> str:
    if rel == "index.html":
        return ""
    if rel.endswith("/index.html"):
        return rel[: -len("index.html")]
    return rel


def _join_url(page: str, target: str) -> str:
    joined = urljoin("https://site.invalid/" + page, target.strip())
    if not joined.startswith("https://site.invalid/"):
        return target.strip()
    return joined.removeprefix("https://site.invalid/")


def read_built_site(out: Path) -> dict[str, Any]:
    """Routes of a built site: pages with their element ids, redirect stubs, anchor redirects."""
    routes: dict[str, dict[str, Any]] = {}
    for path in sorted(out.rglob("*.html")):
        rel = path.relative_to(out).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        url = _page_url(rel)
        refresh = META_REFRESH_RE.search(text)
        if refresh:
            routes[url] = {"type": "redirect", "to": _join_url(url, html.unescape(refresh.group(1)))}
        else:
            ids = sorted({html.unescape(a or b) for a, b in ID_ATTR_RE.findall(text)} - {""})
            routes[url] = {"type": "page", "ids": [i for i in ids if not i.startswith("__")]}
    anchors: dict[str, str] = {}
    redirect_json = out / "redirect.json"
    if redirect_json.is_file():
        try:
            anchors = {str(k): str(v) for k, v in json.loads(redirect_json.read_text(encoding="utf-8")).items()}
        except (json.JSONDecodeError, AttributeError):
            anchors = {}
    sitemap = out / "sitemap.xml"
    locations = re.findall(r"<loc>([^<]+)</loc>", sitemap.read_text(encoding="utf-8")) if sitemap.is_file() else []
    return {"routes": routes, "anchor_redirects": anchors, "sitemap": locations}


def _source_url(inner: str) -> str:
    """The directory URL a page under docs_dir gets (use_directory_urls, the default)."""
    path = PurePosixPath(inner)
    if path.name in ("index.md", "README.md"):
        return "" if str(path.parent) == "." else f"{path.parent}/"
    return str(path.with_suffix("")) + "/"


def source_url_baseline(corpus: Corpus) -> dict[str, Any]:
    """Routes the site would have, derived from the Markdown (used when no build is possible)."""
    site = corpus.site
    routes: dict[str, dict[str, Any]] = {}
    for rel, doc in sorted(corpus.docs.items()):
        if not site.published(rel):
            continue
        routes[_source_url(site.docs_rel(rel))] = {"type": "page", "ids": sorted(doc.anchors(site=True))}
    for source, target in site.redirects.items():
        page, _, fragment = target.partition("#")
        routes.setdefault(_source_url(source), {"type": "redirect", "to": _source_url(page) + ("#" + fragment if fragment else "")})
    github = {rel: sorted(doc.anchors()) for rel, doc in sorted(corpus.docs.items())}
    return {"routes": routes, "anchor_redirects": {}, "sitemap": [], "github": github}


def compare_url_baseline(baseline: dict[str, Any], new: dict[str, Any], report: Report, where: str) -> None:
    routes, anchors = new["routes"], new.get("anchor_redirects", {})

    def follow(url: str) -> tuple[str | None, int, str]:
        seen_urls: list[str] = []
        current = url.split("#", 1)[0]
        while True:
            entry = routes.get(current)
            if entry is None:
                return None, len(seen_urls), "missing" if not seen_urls else "dangling"
            if entry["type"] == "page":
                return current, len(seen_urls), "ok"
            if current in seen_urls:
                return None, len(seen_urls), "loop"
            seen_urls.append(current)
            current = entry["to"].split("#", 1)[0]

    for url, old in sorted(baseline["routes"].items()):
        final, hops, state = follow(url)
        shown = "/" + url
        if state == "missing":
            report.add(
                Finding(
                    "route-missing",
                    "P1",
                    "verified",
                    where,
                    0,
                    f"{shown} existed before and is neither a page nor a redirect now",
                    suggestion="add a redirect to the page that took its content",
                )
            )
            continue
        if state in ("loop", "dangling"):
            report.add(
                Finding(
                    f"redirect-{state}",
                    "P1",
                    "verified",
                    where,
                    0,
                    f"{shown}: the redirect chain {'loops' if state == 'loop' else 'ends at a missing page'}",
                )
            )
            continue
        if hops > 1:
            report.add(
                Finding(
                    "redirect-chain",
                    "P3",
                    "verified",
                    where,
                    0,
                    f"{shown} reaches /{final} through {hops} redirects",
                    suggestion="point the first redirect at the final page",
                )
            )
        if old["type"] != "page" or final is None:
            continue
        have = set(routes[final].get("ids", []))
        lost = []
        for fragment in old.get("ids", []):
            if fragment in have:
                continue
            mapped = anchors.get(f"{url}#{fragment}") or anchors.get(f"{final}#{fragment}")
            if mapped:
                target_page, _, target_id = mapped.partition("#")
                if target_id in set(routes.get(target_page, {}).get("ids", [])):
                    continue
            lost.append(fragment)
        if lost:
            report.add(
                Finding(
                    "fragment-lost",
                    "P1",
                    "verified",
                    where,
                    0,
                    f"/{final}: {len(lost)} anchors of /{url} are gone: {', '.join('#' + f for f in lost[:8])}",
                    suggestion="keep the heading text, add an explicit {#id}, or add an anchor redirect",
                )
            )


# ---------------------------------------------------------------------------------------------
# plan: validate, approve, apply, resume, rollback, verify a restructure
# ---------------------------------------------------------------------------------------------

PLAN_SCHEMA = 1
PLAN_TYPES = ("move", "archive", "split", "merge", "anchor", "reference", "freeze", "keep", "stub", "delete", "decision")
MAPPING_TYPES = ("rewritten", "dropped")
JOURNAL_NAME = ".apply-journal.json"
LOG_NAME = "apply-log.json"
STAGING_NAME = ".staging"
BACKUPS_NAME = ".backups"
RECEIPTS_NAME = "review-receipts.json"
MAPPINGS_NAME = "mappings.toml"
APPROVAL_RE = re.compile(r"(?m)^\[approval\][ \t]*$")
SENSITIVE_RE = re.compile(r"\b(?:warning|caution|never|must not|do not|don't|before you|requires?)\b", re.IGNORECASE)
LINK_DEST_RE = re.compile(
    r"(\]\(\s*<?)([^)\s>]+)|(^[ \t]{0,3}\[[^\]]+\]:[ \t]*<?)(\S+?)(?=>|\s|$)|(\b(?:href|src)\s*=\s*[\"'])([^\"']+)", re.MULTILINE
)

# Tests replace this to simulate a crash at a named point of apply (it must raise a BaseException
# that is not an Exception, which apply's own rollback does not catch).
_CRASH_HOOK: Callable[[str, int], None] | None = None


def _crash_point(name: str, index: int = -1) -> None:
    if _CRASH_HOOK is not None:
        _CRASH_HOOK(name, index)


def _digest(data: bytes | None) -> str | None:
    return None if data is None else sha256_bytes(data)


def plan_digest(text: str) -> str:
    """SHA-256 of the plan with its [approval] table removed."""
    match = APPROVAL_RE.search(text)
    if match:
        rest = text[match.end() :]
        following = re.search(r"(?m)^\[", rest)
        text = text[: match.start()] + (rest[following.start() :] if following else "")
    return sha256_bytes(text.rstrip().encode() + b"\n")


def _fsync_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_dir(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=1, sort_keys=True) + "\n").encode()


@dataclass
class Plan:
    rel: str
    text: str
    data: dict[str, Any]
    directory: str

    @property
    def meta(self) -> dict[str, Any]:
        meta = self.data.get("meta")
        return meta if isinstance(meta, dict) else {}

    def entries(self, kind: str) -> list[dict[str, Any]]:
        value = self.data.get(kind, [])
        return [e for e in value if isinstance(e, dict)] if isinstance(value, list) else []

    def artifact(self, name: str) -> str:
        return f"{self.directory}/{name}" if self.directory != "." else name


def _paths_of(entry: dict[str, Any], key: str) -> list[str]:
    value = entry.get(key)
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value] if isinstance(value, list) else []


def load_plan(repo: Repo, rel: str) -> Plan:
    text, status = repo.text(rel)
    if text is None:
        raise UsageError(f"{rel}: {status}")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise UsageError(f"{rel}: {error}") from error
    return Plan(rel, text, data, str(PurePosixPath(rel).parent))


class PlanContext:
    """Everything validate, approve and apply share: the repo, its site, docs and couplings."""

    def __init__(self, args: argparse.Namespace, report: Report) -> None:
        self.repo = Repo(Path(args.root))
        self.report = report
        self.site = load_site(self.repo, report)
        self.corpus = Corpus(self.repo, self.site)
        report.coverage.append(
            CoverageRow(
                "markdown", "partial" if self.corpus.unreadable else "complete", ", ".join(self.corpus.unreadable) or f"{len(self.corpus.docs)} files"
            )
        )
        self.plan = load_plan(self.repo, _plan_rel(self.repo, str(args.plan)))

    def couplings(self) -> list[dict[str, Any]]:
        if not hasattr(self, "_couplings"):
            # Coupling findings belong to inventory; a plan only needs the couplings and their coverage.
            scratch = Report(command="inventory", root=self.report.root)
            self._couplings = scan_couplings(self.corpus, scratch)
            self.report.coverage += [row for row in scratch.coverage if row.input == "couplings"]
        return self._couplings

    def error(self, check: str, message: str, file: str = "", line: int = 0, suggestion: str = "") -> None:
        self.report.add(Finding(check, "Blocking", "verified", file or self.plan.rel, line, message, suggestion=suggestion))


def _plan_rel(repo: Repo, given: str) -> str:
    """--plan as a safe path inside the root; everything the plan writes sits next to it."""
    path = Path(given)
    if path.is_absolute():
        try:
            given = path.resolve().relative_to(repo.root.resolve()).as_posix()
        except ValueError:
            raise UsageError(f"--plan {path} is outside --root") from None
    rel = normalize_path("", given)
    problem = _path_problem(repo, rel) if rel else "must stay inside --root"
    if rel is None or problem:
        raise UsageError(f"--plan {given}: {problem}")
    return rel


def _path_problem(repo: Repo, rel: str) -> str | None:
    """Why a plan path is unsafe, or None."""
    if not rel or rel.startswith("/") or re.match(r"^[A-Za-z]:", rel):
        return "must be a relative path"
    if normalize_path("", rel) != rel or ".." in PurePosixPath(rel).parts:
        return "must be normalised (no .., no ./, no //)"
    if ".git" in PurePosixPath(rel).parts:
        return "must not touch .git"
    parts = PurePosixPath(rel).parts
    for index in range(len(parts)):
        prefix = "/".join(parts[: index + 1])
        if prefix in repo.symlinks or (repo.root / prefix).is_symlink():
            return f"{prefix} is a symlink"
    try:
        (repo.root / rel).resolve().relative_to(repo.root)
    except ValueError:
        return "resolves outside the repository"
    return None


def plan_sources(context: PlanContext) -> set[str]:
    """Files the plan reads or rewrites in place; their hashes are bound into [meta.sources]."""
    plan = context.plan
    sources: set[str] = set()
    for kind in ("move", "archive", "split", "delete"):
        for entry in plan.entries(kind):
            sources.update(_paths_of(entry, "from") or _paths_of(entry, "path"))
    for entry in plan.entries("merge"):
        sources.update(_paths_of(entry, "from"))
        sources.update(p for p in _paths_of(entry, "into") if context.repo.exists(p))
    for entry in plan.entries("reference"):
        sources.update(_paths_of(entry, "file"))
    for key in ("site_config", "inventory", "blocks"):
        value = plan.meta.get(key)
        if isinstance(value, str) and value:
            sources.add(value)
    return sources


def validate_plan(context: PlanContext) -> None:
    repo, site, plan = context.repo, context.site, context.plan
    meta = plan.meta
    error = context.error
    unknown = sorted(set(plan.data) - {"meta", "approval", *PLAN_TYPES})
    for key in unknown:
        error("plan-schema", f"unknown table [{key}]" + (" (rewritten/dropped mappings go in mappings.toml)" if key in MAPPING_TYPES else ""))
    if meta.get("schema") != PLAN_SCHEMA:
        error("plan-schema", f"[meta] schema must be {PLAN_SCHEMA}")
    if str(meta.get("docs_dir", "")) != site.docs_dir:
        error("plan-schema", f"[meta] docs_dir is {meta.get('docs_dir')!r}; the site config says {site.docs_dir!r}")
    if (meta.get("site_config") or None) != site.config:
        error("plan-schema", f"[meta] site_config is {meta.get('site_config')!r}; the repository has {site.config!r}")
    if not isinstance(meta.get("blocks"), str):
        error(
            "plan-schema",
            "[meta] blocks must name the inventory --blocks baseline",
            suggestion="docstool inventory --blocks docs/internal/restructure/blocks.json",
        )
    base = meta.get("base_commit")
    if not isinstance(base, str) or not repo.is_git or git(repo.root, "rev-parse", "--verify", "--quiet", base + "^{commit}") is None:
        error("plan-base", f"[meta] base_commit {base!r} is not a commit in this repository")
    elif git(repo.root, "merge-base", "--is-ancestor", base, "HEAD") is None:
        error("plan-base", f"HEAD does not descend from base_commit {base}")
    hashes: dict[str, Any] = meta["sources"] if isinstance(meta.get("sources"), dict) else {}
    for rel in sorted(plan_sources(context)):
        current = file_sha256(repo.root / rel)
        if rel not in hashes:
            error(
                "plan-stale",
                f"{rel} is read or written by the plan but not hashed in [meta.sources]",
                suggestion=f"{rel!r} = {current!r}" if current else "",
            )
        elif hashes[rel] != current:
            error("plan-stale", f"{rel} changed since the plan was written (hash differs)", rel)
    for rel in sorted(set(hashes) - plan_sources(context)):
        # files declared only so apply may rewrite their links: bound to the approval like the rest
        problem = _path_problem(repo, rel)
        if problem:
            error("plan-path", f"[meta.sources] {rel}: {problem}")
        elif hashes[rel] != file_sha256(repo.root / rel):
            error("plan-stale", f"{rel} changed since the plan was written (hash differs)", rel)
    rows = {r.input: r for r in context.report.coverage}
    for name in ("config", "nav", "exclude_docs", "redirects", "markdown"):
        if name in rows and not rows[name].complete:
            error("plan-coverage", f"{name} coverage is {rows[name].state}: a plan never runs on incomplete analysis")
    couplings = context.couplings()
    rows = {r.input: r for r in context.report.coverage}
    if not rows["couplings"].complete:
        error("plan-coverage", f"couplings coverage is {rows['couplings'].state}: {rows['couplings'].reason}")
    _validate_entries(context, couplings)


def _link_rewritable(context: PlanContext, rel: str) -> bool:
    """Apply rewrites the links of Markdown files inside the docs, and of files [meta.sources] declares."""
    sources = context.plan.meta.get("sources")
    return _writable(context, rel) or (isinstance(sources, dict) and rel in sources)


def _writable(context: PlanContext, rel: str) -> bool:
    site, plan = context.site, context.plan
    if site.in_docs(rel) and site.docs_dir != ".":
        return True
    references = {p for e in plan.entries("reference") for p in _paths_of(e, "file")}
    return rel in references or rel == site.config


def _validate_entries(context: PlanContext, couplings: list[dict[str, Any]]) -> None:
    repo, site, plan, corpus = context.repo, context.site, context.plan, context.corpus
    error = context.error
    targets: dict[str, str] = {}
    moved: dict[str, str] = {}
    covered: set[str] = set()
    covered_dirs: list[str] = []
    references = {(e.get("file"), e.get("line")) for e in plan.entries("reference")}
    stub_paths = {p for e in plan.entries("stub") for p in _paths_of(e, "path")}
    merge_into = {p for e in plan.entries("merge") for p in _paths_of(e, "into")}

    def claim(rel: str, what: str) -> None:
        problem = _path_problem(repo, rel)
        if problem:
            error("plan-path", f"{what} {rel}: {problem}")
            return
        if not _writable(context, rel):
            error("plan-path", f"{what} {rel}: outside {site.docs_dir}/ and not a reference or the site config")
        lower = rel.lower()
        clash = next((t for t in targets if t.lower() == lower), None)
        if clash is not None:
            error("plan-collision", f"{what} {rel} collides with {targets[clash]} {clash}" + (" (names differ only by case)" if clash != rel else ""))
        targets[rel] = what
        exists = repo.exists(rel) or bool(repo.lower_map.get(lower))
        allowed = (what == "merge target") or (what == "stub" and rel in moved)
        if exists and not allowed:
            error("plan-collision", f"{what} {rel} already exists (an unexpected destination change)")

    def needs_source(rel: str, what: str) -> bool:
        problem = _path_problem(repo, rel)
        if problem:
            error("plan-path", f"{what} {rel}: {problem}")
            return False
        if rel not in repo.file_set:
            error("plan-source", f"{what} {rel} does not exist")
            return False
        return True

    for kind in ("move", "archive"):
        for entry in plan.entries(kind):
            source, target = str(entry.get("from", "")), str(entry.get("to", ""))
            if needs_source(source, kind):
                moved[source] = target
                covered.add(source)
            if kind == "archive" and not str(entry.get("status", "")).strip():
                error("plan-entry", f"archive {source}: a status line is required")
            if target:
                claim(target, kind + " target")
            else:
                error("plan-entry", f"{kind} {source}: no 'to'")
            if site.config and site.published(source):
                landing = str(entry.get("redirect_to") or target)
                if entry.get("redirect", True) is False:
                    error("plan-redirect", f"{source} is published: redirect = false would break its URL")
                elif not site.published(landing):
                    error(
                        "plan-redirect", f"{source} is published but {landing} is not: set redirect_to to the published page that takes its readers"
                    )
                elif site.kind == "mkdocs" and "redirects" not in site.plugins:
                    error(
                        "plan-redirect",
                        f"{source} is published: moving it needs a redirect, and mkdocs.yml has no redirects plugin",
                        suggestion="add the redirects plugin with an empty redirect_maps first",
                    )
    for entry in plan.entries("split"):
        source, heading, target = str(entry.get("from", "")), str(entry.get("heading", "")), str(entry.get("to", ""))
        if needs_source(source, "split"):
            covered.add(source)
            matches = [h for h in corpus.docs[source].headings if h.text == heading] if source in corpus.docs else []
            if len(matches) != 1:
                error("plan-entry", f"split {source}: heading {heading!r} occurs {len(matches)} times; it must occur once")
        claim(target, "split target")
    for entry in plan.entries("merge"):
        sources, into = _paths_of(entry, "from"), str(entry.get("into", ""))
        for source in sources:
            if needs_source(source, "merge"):
                covered.add(source)
        if into not in repo.file_set and into not in {t for t, w in targets.items() if w != "merge target"}:
            error("plan-entry", f"merge into {into}: the target must exist or be created by this plan")
        if into in repo.file_set:
            targets.setdefault(into, "merge target")
    for entry in plan.entries("stub"):
        path, target = str(entry.get("path", "")), str(entry.get("target", ""))
        claim(path, "stub")
        if target not in moved.values() and target not in repo.file_set:
            error("plan-entry", f"stub {path}: target {target} is neither moved by the plan nor an existing file")
    for entry in plan.entries("reference"):
        rel, number, old = str(entry.get("file", "")), entry.get("line"), entry.get("old")
        if needs_source(rel, "reference") and isinstance(number, int) and isinstance(old, str) and isinstance(entry.get("new"), str):
            text, _ = repo.text(rel)
            lines = (text or "").split("\n")
            if not 1 <= number <= len(lines) or lines[number - 1].count(old) != 1:
                error(
                    "plan-reference",
                    f"reference {rel}:{number}: the line must contain {old!r} exactly once",
                    rel,
                    number if isinstance(number, int) else 0,
                )
        else:
            error("plan-reference", f"reference {rel}: needs file, line (an integer), old and new")
    for entry in plan.entries("delete"):
        rel = str(entry.get("path", ""))
        if needs_source(rel, "delete"):
            covered.add(rel)
            if entry.get("approved") is not True or not str(entry.get("proof", "")).strip():
                error("plan-delete", f"delete {rel}: needs approved = true and a proof (gate G5)")
            elif not _deletion_proven(corpus, rel):
                error("plan-delete", f"delete {rel}: not empty and not an exact duplicate of other docs, so deleting it could lose content")
    for kind in ("freeze", "keep"):
        for entry in plan.entries(kind):
            for path in _paths_of(entry, "paths") + _paths_of(entry, "path"):
                if path.endswith("/"):
                    covered_dirs.append(path)
                else:
                    covered.add(path)
    for entry in plan.entries("decision"):
        if not str(entry.get("answer", "")).strip():
            error("plan-decision", f"decision {entry.get('id', '?')} is open: {entry.get('question', '')}")
    # every doc under docs_dir is covered (the plan's own directory excepted)
    for rel in sorted(corpus.docs):
        if site.in_docs(rel) and not rel.startswith(plan.directory + "/") and rel not in covered and not any(rel.startswith(d) for d in covered_dirs):
            error(
                "plan-uncovered",
                f"{rel} is not covered by any entry (move, archive, split, merge, keep, freeze or delete)",
                suggestion="add it to a [[keep]] entry if it stays as it is",
            )
    frozen = {p for e in plan.entries("freeze") for p in _paths_of(e, "paths") + _paths_of(e, "path")}
    for rel in frozen & (set(moved) | {str(e.get("path", "")) for e in plan.entries("delete")}):
        error("plan-frozen", f"{rel} is frozen by the plan itself but also moved or deleted")
    _check_inbound(context, couplings, moved, references, stub_paths, merge_into)


def _deletion_proven(corpus: Corpus, rel: str) -> bool:
    doc = corpus.docs.get(rel)
    text = "\n".join(doc.lines) if doc else ""
    if not text.strip():
        return True
    others = Counter(_block_hash(b) for other, d in corpus.docs.items() if other != rel for b in d.blocks)
    mine = Counter(_block_hash(b) for b in doc.blocks) if doc else Counter()
    return bool(mine) and all(others[h] >= n for h, n in mine.items())


def _check_inbound(
    context: PlanContext, couplings: list[dict[str, Any]], moved: dict[str, str], references: set[tuple[Any, Any]], stubs: set[str], merged: set[str]
) -> None:
    """Every reference to a moved or split path or heading that a link rewrite cannot fix is handled."""
    corpus = context.corpus
    sections: dict[str, tuple[set[str], set[str], set[str]]] = {}
    for split in context.plan.entries("split"):
        source, heading = str(split.get("from")), str(split.get("heading"))
        doc = corpus.docs.get(source)
        if doc is None or sum(h.text == heading for h in doc.headings) != 1:
            continue
        first, end, _level = _section_bounds(doc, heading)
        inside = [h for h in doc.headings if first < h.line <= end]
        sections[source] = ({h.text.casefold() for h in inside}, {h.number for h in inside if h.number}, {h.gh_slug for h in inside})
    deleted = {str(e.get("path", "")) for e in context.plan.entries("delete")}
    own = context.plan.directory + "/"

    def follows(entry: dict[str, Any]) -> bool:
        """A relative path citation that still names its target after both files moved."""
        source, detail = entry["source"], str(entry["detail"])
        if entry["ref"] != "path" or source not in moved or entry["target"] not in moved or detail.startswith("/"):
            return False
        return normalize_path(str(PurePosixPath(moved[source]).parent), unquote(detail.split("#", 1)[0])) == moved[entry["target"]]

    # a heading, section or anchor cited next to a path that follows its move is still right:
    # moves keep every heading
    followed = {(e["source"], e["line"], e["target"]) for e in couplings if follows(e)}
    # ...unless an [[anchor]] entry renames the cited heading in that target
    renamed = {
        (path, str(a.get("from", "")).lower())
        for a in context.plan.entries("anchor")
        for path in (str(a.get("file", "")), moved.get(str(a.get("file", "")), ""))
    }

    def renamed_heading(entry: dict[str, Any]) -> bool:
        detail = str(entry["detail"])
        slug = detail.lstrip("#").lower() if entry["ref"] == "anchor" else github_slug_base(heading_plain_text(detail).rstrip(":. "))
        return any((path, slug) in renamed for path in (entry["target"], moved.get(entry["target"], "")))

    for entry in couplings:
        target = entry["target"]
        if entry["source"].startswith(own):
            continue  # the plan's own artifacts (plan, baselines, receipts) name every path it touches
        moves = target in moved or target in deleted
        if not moves and target in sections:
            titles, numbers, slugs = sections[target]
            detail = str(entry["detail"])
            moves = (
                (entry["ref"] == "heading" and heading_plain_text(detail).casefold().rstrip(":. ") in titles)
                or (entry["ref"] == "section" and (number := re.search(r"\d+(?:\.\d+)*", detail)) is not None and number.group(0) in numbers)
                or (entry["ref"] == "anchor" and detail.lstrip("#").lower() in slugs)
            )
        if not moves:
            continue
        if entry["status"] != "ok":
            continue
        source, line = entry["source"], entry["line"]
        doc = corpus.docs.get(source)
        if doc is not None and entry["ref"] in ("path", "anchor"):
            base = str(PurePosixPath(source).parent)
            linked = any(
                # a link whose text wraps starts on an earlier line than its destination
                (link.line == line or (link.line < line and f"]({link.target}" in doc.lines[line - 1]))
                and normalize_path(base, unquote(link.target.split("#", 1)[0])) == target
                for link in doc.links
                if not SCHEME_RE.match(link.target)
            )
            if linked and _link_rewritable(context, source):
                continue
            if linked:
                context.error(
                    "plan-inbound",
                    f"{source}:{line} links to {target}, which the plan moves; {source} is outside {context.site.docs_dir}/, so apply rewrites its links only when [meta.sources] declares it",
                    source,
                    line,
                    f"add {source!r} = <its sha256> to [meta.sources] (gate G10), or a [[reference]] edit for that line",
                )
                continue
        if (source, line) in references or follows(entry):
            continue
        if (
            entry["ref"] != "path"
            and target not in sections
            and target not in deleted
            and (source, line, target) in followed
            and not renamed_heading(entry)
        ):
            continue
        if target in stubs and entry["ref"] in ("path", "blob") and target not in deleted:
            continue
        pins = entry["kind"] in FREEZING_KINDS or entry["ref"] == "blob"
        context.error(
            "plan-frozen" if pins else "plan-inbound",
            f"{source}:{line} cites {target} {entry['detail']} ({entry['kind']} {entry['ref']}); the plan moves it but has no reference entry for that line",
            source,
            line,
            "freeze the path (gate G3), or add a [[reference]] edit for that line (gate G10)",
        )


# --- apply: preflight -------------------------------------------------------------------------


class VirtualTree:
    """The working tree as bytes, with the plan's edits applied in memory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.changed: dict[str, bytes | None] = {}
        self.original: dict[str, bytes | None] = {}
        # a moved file keeps its source's permission bits (an executable script stays executable)
        self.mode_from: dict[str, str] = {}

    def read(self, rel: str) -> bytes | None:
        if rel in self.changed:
            return self.changed[rel]
        return self._disk(rel)

    def _disk(self, rel: str) -> bytes | None:
        if rel not in self.original:
            path = self.root / rel
            self.original[rel] = path.read_bytes() if path.is_file() and not path.is_symlink() else None
        return self.original[rel]

    def write(self, rel: str, data: bytes | None, mode_from: str | None = None) -> None:
        self._disk(rel)
        self.changed[rel] = data
        if mode_from is not None:
            self.mode_from[rel] = mode_from

    def mode(self, rel: str) -> int | None:
        path = self.root / rel
        return stat.S_IMODE(path.stat().st_mode) if path.is_file() and not path.is_symlink() else None

    def text(self, rel: str) -> str:
        data = self.read(rel)
        return "" if data is None else data.decode("utf-8")

    def operations(self) -> list[dict[str, Any]]:
        ops = []
        for rel in sorted(self.changed):
            pre, post = self.original.get(rel), self.changed[rel]
            if pre != post:
                pre_mode = self.mode(rel)
                post_mode = None if post is None else (self.mode(self.mode_from[rel]) if rel in self.mode_from else pre_mode)
                ops.append(
                    {"path": rel, "pre": _digest(pre), "post": _digest(post), "data": post, "old": pre, "pre_mode": pre_mode, "mode": post_mode}
                )
        return ops


def _relative(from_dir: str, target: str) -> str:
    return os.path.relpath(target, from_dir if from_dir else ".").replace(os.sep, "/") if target else ""


def _rewrite_links(
    text: str,
    old_dir: str,
    new_dir: str,
    self_old: str,
    self_new: str,
    path_map: dict[str, str],
    anchor_map: dict[tuple[str, str], tuple[str, str]],
    section: set[str] | None = None,
) -> str:
    """Re-point every relative link of a Markdown text after the plan's moves (only changed links)."""
    out_lines = []
    fence: tuple[str, int] | None = None
    for line in text.split("\n"):
        fence, in_code = _fence_step(fence, line)
        if in_code:
            out_lines.append(line)
            continue
        out_lines.append(LINK_DEST_RE.sub(lambda m: _rewrite_one(m, (old_dir, new_dir, self_old, self_new), path_map, anchor_map, section), line))
    return "\n".join(out_lines)


def _fence_step(fence: tuple[str, int] | None, line: str) -> tuple[tuple[str, int] | None, bool]:
    """(the open fence after this line, whether the line is code or a fence), by the scanner's rules."""
    if fence is not None:
        close = re.match(r"^[ \t]*(`+|~+)[ \t]*$", line)
        if close and close.group(1)[0] == fence[0] and len(close.group(1)) >= fence[1]:
            return None, True
        return fence, True
    opening = FENCE_RE.match(line)
    if opening and not (opening.group("fence")[0] == "`" and "`" in opening.group("info")):
        return (opening.group("fence")[0], len(opening.group("fence"))), True
    return None, False


def _rewrite_one(
    match: re.Match[str],
    where: tuple[str, str, str, str],
    path_map: dict[str, str],
    anchor_map: dict[tuple[str, str], tuple[str, str]],
    section: set[str] | None,
) -> str:
    """One link destination re-pointed; the original text when nothing changes."""
    old_dir, new_dir, self_old, self_new = where
    prefix = match.group(1) or match.group(3) or match.group(5) or ""
    dest = match.group(2) or match.group(4) or match.group(6) or ""
    if not dest or SCHEME_RE.match(dest):
        return match.group(0)
    path_part, hash_mark, fragment = dest.partition("#")
    resolved = normalize_path(old_dir, unquote(path_part)) if path_part else self_old
    if resolved is None:
        return match.group(0)
    if not path_part and section is not None:
        # a same-page anchor inside a split section: it stays when its heading moved along
        if fragment.lower() in section:
            return match.group(0)
        return prefix + _relative(new_dir, path_map.get(self_old, self_old)) + "#" + fragment
    else:
        new_target, new_fragment = path_map.get(resolved, resolved), fragment
        if fragment and (resolved, fragment.lower()) in anchor_map:
            new_target, new_fragment = anchor_map[(resolved, fragment.lower())]
    if new_target == resolved and new_dir == old_dir and new_fragment == fragment:
        return match.group(0)
    same_page = new_target == self_new
    rebuilt = ("" if new_fragment else PurePosixPath(self_new).name) if same_page else _relative(new_dir, new_target)
    return prefix + rebuilt + ("#" + new_fragment if new_fragment else hash_mark)


def _status_line(text: str, status: str, width: int = 100) -> str:
    """The text with a status quote under its title, wrapped to the repository's line width."""
    lines = text.split("\n")
    # a wrapped line must not start like a list item, a heading or a quote: that would be structure
    starts_block = re.compile(r"^(?:[-+*]\s|\d+[.)]\s|#|>|=+$|-+$)")
    wrapped: list[str] = []
    for target in range(max(width, 40) - 2, 20, -1):
        wrapped = textwrap.wrap(f"**Status:** {status}", width=target, break_long_words=False, break_on_hyphens=False)
        if not any(starts_block.match(part) for part in wrapped[1:]):
            break
    else:
        wrapped = [f"**Status:** {status}"]
    note = "\n".join(f"> {part}" for part in wrapped)
    for index, line in enumerate(lines):
        heading = ATX_RE.match(line)
        if heading and len(heading.group(1)) == 1:
            return "\n".join([*lines[: index + 1], "", note, *lines[index + 1 :]])
    return "\n".join([note, "", *lines])


def _section_bounds(doc: MarkdownDoc, heading: str) -> tuple[int, int, int]:
    """(first line index, end line index, level) of the section a heading opens."""
    match = next(h for h in doc.headings if h.text == heading)
    end = next((h.line - 1 for h in doc.headings if h.line > match.line and h.level <= match.level), len(doc.lines))
    while end > match.line and not doc.lines[end - 1].strip():
        end -= 1
    return match.line - 1, end, match.level


def _promote(lines: list[str], by: int) -> list[str]:
    if by <= 0:
        return lines
    out = []
    fence: tuple[str, int] | None = None
    for line in lines:
        fence, in_code = _fence_step(fence, line)
        heading = None if in_code else re.match(r"^(#{1,6})([ \t].*|)$", line)
        out.append("#" * max(1, len(heading.group(1)) - by) + heading.group(2) if heading else line)
    return out


def preflight(context: PlanContext) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """Compute every write as exact before/after bytes. Returns (operations, redirects added)."""
    repo, site, plan, corpus = context.repo, context.site, context.plan, context.corpus
    tree = VirtualTree(repo.root)
    path_map: dict[str, str] = {}
    anchor_map: dict[tuple[str, str], tuple[str, str]] = {}
    redirects: list[tuple[str, str]] = []
    status_of: dict[str, str] = {}
    # a status line wraps where the repository's Markdown lint does, else at its usual width
    wrap_width = tooling_census(repo).get("markdown_wrap") or house_style(corpus)["wrap_p95"] or 100
    for kind in ("move", "archive"):
        for entry in plan.entries(kind):
            source, target = str(entry["from"]), str(entry["to"])
            path_map[source] = target
            if kind == "archive":
                status_of[source] = str(entry["status"])
            landing = str(entry.get("redirect_to") or target)
            if site.config and site.published(source) and site.published(landing):
                redirects.append((site.docs_rel(source), site.docs_rel(landing)))
    splits = []
    for entry in plan.entries("split"):
        source, heading, target = str(entry["from"]), str(entry["heading"]), str(entry["to"])
        doc = corpus.docs[source]
        first, end, level = _section_bounds(doc, heading)
        section_headings = [h for h in doc.headings if first < h.line <= end]
        for h in section_headings:
            anchor_map[(source, h.gh_slug.lower())] = (target, h.gh_slug)
        splits.append((source, heading, target, first, end, level, {h.gh_slug.lower() for h in section_headings}))
        if site.config and site.published(source) and site.kind == "zensical":
            for h in section_headings:
                redirects.append((f"{site.docs_rel(source)}#{h.site_slug}", f"{site.docs_rel(target)}#{h.site_slug}"))
    for entry in plan.entries("anchor"):
        anchor_map[(str(entry["file"]), str(entry["from"]).lower())] = (path_map.get(str(entry["file"]), str(entry["file"])), str(entry["to"]))
    # line edits first: their line numbers are the original file's, which a move, an archive's
    # status line or a split would shift or take away
    for entry in plan.entries("reference"):
        rel = str(entry["file"])
        lines = tree.text(rel).split("\n")
        lines[int(entry["line"]) - 1] = lines[int(entry["line"]) - 1].replace(str(entry["old"]), str(entry["new"]), 1)
        tree.write(rel, "\n".join(lines).encode())
    # structural edits, with every Markdown file's links re-pointed
    markdown = sorted(r for r in repo.files if r.endswith(MARKDOWN_EXTENSIONS))
    split_sources = {s[0]: s for s in splits}
    for rel in markdown:
        if not _link_rewritable(context, rel):
            continue  # outside the docs and not declared in [meta.sources]: validate reported its links
        text = tree.text(rel)
        new_rel = path_map.get(rel, rel)
        if rel in split_sources:
            source, heading, target, first, end, level, inner = split_sources[rel]
            lines = text.split("\n")
            section = _promote(lines[first:end], level - 1)
            pointer = [lines[first], "", f"Moved to [{heading}]({_relative(str(PurePosixPath(rel).parent), target)})."]
            remaining = "\n".join([*lines[:first], *pointer, *lines[end:]])
            moved_text = "\n".join(section) + "\n"
            moved_text = _rewrite_links(
                moved_text, str(PurePosixPath(rel).parent), str(PurePosixPath(target).parent), rel, target, path_map, {}, inner
            )
            tree.write(target, moved_text.encode())
            text = remaining
        rewritten = _rewrite_links(text, str(PurePosixPath(rel).parent), str(PurePosixPath(new_rel).parent), rel, new_rel, path_map, anchor_map)
        if rel in status_of:
            rewritten = _status_line(rewritten, status_of[rel], wrap_width)
        if new_rel != rel:
            tree.write(new_rel, rewritten.encode(), mode_from=rel)
            tree.write(rel, None)
        elif rewritten != text or rel in split_sources:
            tree.write(rel, rewritten.encode())
    for entry in plan.entries("stub"):
        path, target = str(entry["path"]), str(entry["target"])
        title = str(entry.get("title") or PurePosixPath(target).stem.replace("-", " ").capitalize())
        tree.write(path, f"# {title}\n\nThis page moved to [{title}]({_relative(str(PurePosixPath(path).parent), target)}).\n".encode())
    for entry in plan.entries("delete"):
        tree.write(str(entry["path"]), None)
    if redirects and site.config:
        tree.write(site.config, _append_redirects(tree.text(site.config), site, redirects).encode())
    return tree.operations(), redirects


def _append_redirects(text: str, site: Site, redirects: list[tuple[str, str]]) -> str:
    """The site config with redirect_maps entries added; re-parsed to prove the result."""
    if site.kind == "zensical":
        lines = [f"{json.dumps(src)} = {json.dumps(dst)}" for src, dst in redirects]
        header = re.search(r"(?m)^\[project\.plugins\.redirects\.redirect_maps\][ \t]*$", text)
        if header:
            insert = text.index("\n", header.end()) + 1 if "\n" in text[header.end() :] else len(text)
            updated = text[:insert] + "\n".join(lines) + "\n" + text[insert:]
        else:
            updated = text.rstrip("\n") + "\n\n[project.plugins.redirects.redirect_maps]\n" + "\n".join(lines) + "\n"
        maps = tomllib.loads(updated).get("project", {}).get("plugins", {}).get("redirects", {}).get("redirect_maps", {})
    else:
        key = re.search(r"(?m)^([ \t]*)redirect_maps:[ \t]*$", text)
        if not key:
            raise UsageError("mkdocs.yml has no 'redirect_maps:' block to add redirects to")
        child = re.match(r"([ \t]*)\S", text[key.end() + 1 :])
        indent = child.group(1) if child and len(child.group(1)) > len(key.group(1)) else key.group(1) + "  "
        lines = [f"{indent}{json.dumps(src)}: {json.dumps(dst)}" for src, dst in redirects]
        insert = key.end() + 1
        updated = text[:insert] + "\n".join(lines) + "\n" + text[insert:]
        parsed = _plugins_from_mkdocs(yaml_load(updated).get("plugins"))
        maps = parsed.get("redirects", {}).get("redirect_maps", {}) if isinstance(parsed.get("redirects"), dict) else {}
    missing = [src for src, dst in redirects if maps.get(src) != dst]
    if missing:
        raise UsageError(f"the edited site config does not parse back with the new redirects: {', '.join(missing[:3])}")
    return updated


# --- apply: transaction and recovery --------------------------------------------------------------


def _state_of(root: Path, entry: dict[str, Any]) -> str:
    current = file_sha256(root / entry["path"])
    if current == entry["post"]:
        return "post"
    if current == entry["pre"]:
        return "pre"
    return "other"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _cleanup(art: Path, *, keep_log: bool = True) -> None:
    for name in (STAGING_NAME, BACKUPS_NAME):
        if (art / name).exists():
            shutil.rmtree(art / name)
    (art / (LOG_NAME + ".tmp")).unlink(missing_ok=True)
    if not keep_log:
        (art / LOG_NAME).unlink(missing_ok=True)


def _restore(root: Path, art: Path, index: int, entry: dict[str, Any]) -> None:
    target = root / entry["path"]
    if entry["pre"] is None:
        target.unlink(missing_ok=True)
        return
    backup = art / BACKUPS_NAME / str(index)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".docstool-restore")
    shutil.copyfile(backup, temporary)
    if entry.get("pre_mode") is not None:
        os.chmod(temporary, entry["pre_mode"])
    os.replace(temporary, target)


def _finalise(root: Path, art: Path, journal: dict[str, Any]) -> None:
    log = {
        "status": "completed",
        "plan_sha256": journal["plan_sha256"],
        "paths": {e["path"]: {"pre": e["pre"], "post": e["post"]} for e in journal["ops"]},
    }
    temporary = art / (LOG_NAME + ".tmp")
    _fsync_write(temporary, _json_bytes(log))
    _crash_point("log-tmp")
    os.replace(temporary, art / LOG_NAME)
    _fsync_dir(art)
    _crash_point("after-log")
    if (art / STAGING_NAME).exists():
        shutil.rmtree(art / STAGING_NAME)
    _crash_point("after-staging")
    if (art / BACKUPS_NAME).exists():
        shutil.rmtree(art / BACKUPS_NAME)
    _crash_point("after-backups")
    (art / JOURNAL_NAME).unlink(missing_ok=True)
    _fsync_dir(art)


def _write_journal(art: Path, journal: dict[str, Any]) -> None:
    temporary = art / (JOURNAL_NAME + ".tmp")
    _fsync_write(temporary, _json_bytes(journal))
    os.replace(temporary, art / JOURNAL_NAME)
    _fsync_dir(art)


def run_transaction(root: Path, art: Path, ops: list[dict[str, Any]], digest: str) -> None:
    """Apply the operations with a write-ahead journal; roll back on any failure."""
    staging, backups = art / STAGING_NAME, art / BACKUPS_NAME
    if staging.exists() or backups.exists():
        raise UsageError(f"{staging} or {backups} is left from an earlier run: run plan resume or plan rollback")
    try:
        for index, op in enumerate(ops):
            if op["data"] is not None:
                _fsync_write(staging / str(index), op["data"])
            if op["old"] is not None:
                _fsync_write(backups / str(index), op["old"])
        journal: dict[str, Any] = {
            "plan_sha256": digest,
            "new_dirs": _new_dirs(root, [op["path"] for op in ops if op["post"] is not None]),
            "ops": [
                {
                    "path": op["path"],
                    "pre": op["pre"],
                    "post": op["post"],
                    "pre_mode": op.get("pre_mode"),
                    "mode": op.get("mode"),
                    "status": "planned",
                }
                for op in ops
            ],
        }
        _write_journal(art, journal)
    except OSError as error:
        # nothing in the tree has changed yet: drop the half-written staging and refuse
        _cleanup(art)
        (art / JOURNAL_NAME).unlink(missing_ok=True)
        raise UsageError(f"apply failed while staging ({error}); nothing was changed") from error
    try:
        for index in range(len(ops)):
            _apply_one(root, art, index, journal["ops"][index])
            journal["ops"][index]["status"] = "done"
            _write_journal(art, journal)
            _crash_point("after-done", index)
    except Exception as error:
        for index in reversed(range(len(ops))):
            entry = journal["ops"][index]
            if _state_of(root, entry) == "post":
                _restore(root, art, index, entry)
        _remove_new_dirs(root, journal)
        _cleanup(art)
        (art / JOURNAL_NAME).unlink(missing_ok=True)
        raise UsageError(f"apply failed ({error}); every completed operation was rolled back") from error
    _finalise(root, art, journal)


def _new_dirs(root: Path, paths: list[str]) -> list[str]:
    """Directories an apply would create, deepest first, so a rollback can remove them again."""
    made: set[str] = set()
    for rel in paths:
        parent = PurePosixPath(rel).parent
        while str(parent) != "." and not (root / parent).exists():
            made.add(parent.as_posix())
            parent = parent.parent
    return sorted(made, key=lambda d: (-d.count("/"), d))


def _remove_new_dirs(root: Path, journal: dict[str, Any]) -> None:
    for rel in journal.get("new_dirs", []):
        directory = root / rel
        if directory.is_dir() and not directory.is_symlink() and not any(directory.iterdir()):
            directory.rmdir()


def _apply_one(root: Path, art: Path, index: int, entry: dict[str, Any]) -> None:
    _crash_point("before-change", index)
    target = root / entry["path"]
    if entry["post"] is None:
        target.unlink()
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(art / STAGING_NAME / str(index), target)
        if entry.get("mode") is not None:
            os.chmod(target, entry["mode"])
    _crash_point("after-change", index)


def _plan_art(context: PlanContext) -> Path:
    return context.repo.root / context.plan.directory


def _approval_state(plan: Plan) -> str:
    approval = plan.data.get("approval")
    if not isinstance(approval, dict):
        return "missing"
    return "valid" if approval.get("plan_sha256") == plan_digest(plan.text) else "stale"


def _recognise_applied(context: PlanContext) -> bool:
    """True when apply-log.json says this plan is applied and every path is at its post-image."""
    art = _plan_art(context)
    log = _read_json(art / LOG_NAME)
    if not isinstance(log, dict) or log.get("plan_sha256") != plan_digest(context.plan.text):
        return False
    states = {path: _state_of(context.repo.root, {"path": path, **hashes}) for path, hashes in log.get("paths", {}).items()}
    if all(s == "post" for s in states.values()):
        return True
    for path, state in sorted(states.items()):
        context.error(
            "plan-mixed",
            f"{path} is at its {'pre-image' if state == 'pre' else 'post-image' if state == 'post' else 'neither image (edited by hand)'}",
            path,
        )
    raise _Refused


class _Refused(Exception):
    """The command stops; the findings already say why."""


def cmd_plan(args: argparse.Namespace, report: Report) -> list[str]:
    action = args.action
    context = PlanContext(args, report)
    required = ["config", "nav", "exclude_docs", "redirects", "markdown"]
    art = _plan_art(context)
    try:
        if action in ("resume", "rollback"):
            _recover(context, action)
            return []
        if action == "verify":
            return _verify(context, args)
        if action == "approve" and args.mappings:
            _approve_mappings(context, args)
            return ["conservation_baseline"]
        if (art / JOURNAL_NAME).exists() and action == "apply":
            context.error(
                "plan-journal",
                f"{context.plan.artifact(JOURNAL_NAME)} exists: an earlier apply did not finish",
                suggestion="run plan resume or plan rollback",
            )
            return required
        if action == "apply" and _recognise_applied(context):
            report.data["state"] = "already applied, nothing to do"
            return []
        validate_plan(context)
        report.data["approval"] = _approval_state(context.plan)
        required.append("couplings")
        blocking = [f for f in report.findings if f.severity == "Blocking"]
        if action == "validate" or blocking:
            if action == "approve" and blocking:
                report.data["state"] = "not approved: validate fails"
            return required
        if action == "approve":
            if not args.by:
                raise UsageError("plan approve needs --by NAME (the person approving, gate G9)")
            _write_approval(context, args.by)
            return required
        ops, redirects = preflight(context)
        report.data["operations"] = [
            {"path": op["path"], "change": "create" if op["pre"] is None else "delete" if op["post"] is None else "edit"} for op in ops
        ]
        report.data["redirects"] = [f"{src} -> {dst}" for src, dst in redirects]
        if not args.write:
            report.data["state"] = "dry run: nothing written (pass --write to apply)"
            return required
        if report.data["approval"] != "valid":
            context.error("plan-approval", f"the plan's approval is {report.data['approval']}: run plan approve after the owner agrees (gate G9)")
            return required
        dirty = git(context.repo.root, "status", "--porcelain", "--", *[op["path"] for op in ops]) if ops else ""
        if dirty and dirty.strip():
            for line in dirty.strip().split("\n"):
                context.error("plan-dirty", f"{line[3:]} has uncommitted changes; apply touches it")
            return required
        run_transaction(context.repo.root, art, ops, plan_digest(context.plan.text))
        report.data["state"] = f"applied: {len(ops)} paths written"
        return required
    except _Refused:
        return required


def _write_approval(context: PlanContext, by: str) -> None:
    plan = context.plan
    text = plan.text
    match = APPROVAL_RE.search(text)
    if match:
        rest = text[match.end() :]
        following = re.search(r"(?m)^\[", rest)
        text = text[: match.start()] + (rest[following.start() :] if following else "")
    digest = plan_digest(text)
    stamp = datetime.now(UTC).date().isoformat()
    text = text.rstrip("\n") + f"\n\n[approval]\nplan_sha256 = {json.dumps(digest)}\napproved_by = {json.dumps(by)}\ndate = {json.dumps(stamp)}\n"
    path = context.repo.root / plan.rel
    temporary = path.with_name(path.name + ".tmp")
    _fsync_write(temporary, text.encode())
    os.replace(temporary, path)
    context.report.data["state"] = f"approved by {by}"
    context.report.data["approval"] = "approved"
    context.report.data["plan_sha256"] = digest


def _recover(context: PlanContext, action: str) -> None:
    root, art = context.repo.root, _plan_art(context)
    journal = _read_json(art / JOURNAL_NAME)
    log = _read_json(art / LOG_NAME)
    if not isinstance(journal, dict):
        if (art / STAGING_NAME).exists() or (art / BACKUPS_NAME).exists():
            # the journal is written before any change, so without one the tree is untouched
            _cleanup(art)
            context.report.data["state"] = "removed the staging of a run that stopped before changing anything"
            return
        if action == "rollback" and isinstance(log, dict):
            raise UsageError("the apply completed and its backups are gone; revert it with git")
        context.report.data["state"] = "nothing to recover: no journal"
        return
    entries = journal.get("ops", [])
    states = [_state_of(root, e) for e in entries]
    finished = isinstance(log, dict) and log.get("plan_sha256") == journal.get("plan_sha256")
    if finished and action == "resume":
        if any(s != "post" for s in states):
            for entry, state in zip(entries, states, strict=True):
                if state != "post":
                    context.error("plan-conflict", f"{entry['path']} is not at its post-image although the apply log says completed", entry["path"])
            return
        _cleanup(art)
        (art / JOURNAL_NAME).unlink(missing_ok=True)
        context.report.data["state"] = "finished the interrupted cleanup; the plan is applied"
        return
    conflicts = [(e, s) for e, s in zip(entries, states, strict=True) if s == "other"]
    if action == "resume":
        conflicts += [
            (e, "staged copy missing")
            for i, (e, s) in enumerate(zip(entries, states, strict=True))
            if s == "pre" and e["post"] is not None and not (art / STAGING_NAME / str(i)).is_file()
        ]
    else:
        conflicts += [
            (e, "backup missing")
            for i, (e, s) in enumerate(zip(entries, states, strict=True))
            if s == "post" and e["pre"] is not None and not (art / BACKUPS_NAME / str(i)).is_file()
        ]
    if conflicts:
        for entry, state in conflicts:
            context.error(
                "plan-conflict",
                f"{entry['path']}: {'changed after the crash (neither its pre- nor post-image)' if state == 'other' else state}; nothing was written",
                entry["path"],
            )
        return
    if action == "resume":
        for index, (entry, state) in enumerate(zip(entries, states, strict=True)):
            if state == "pre":
                _apply_one(root, art, index, entry)
                entry["status"] = "done"
                _write_journal(art, journal)
        _finalise(root, art, journal)
        context.report.data["state"] = f"resumed: {states.count('pre')} pending operations done"
    else:
        for index, (entry, state) in reversed(list(enumerate(zip(entries, states, strict=True)))):
            if state == "post":
                _restore(root, art, index, entry)
        _remove_new_dirs(root, journal)
        _cleanup(art, keep_log=not finished)
        (art / JOURNAL_NAME).unlink(missing_ok=True)
        context.report.data["state"] = f"rolled back: {states.count('post')} operations undone"


# --- verify: content conservation ------------------------------------------------------------------


def _conservation_text(block: Block) -> str:
    if block.type == "code":
        return block.text
    text = " ".join(block.text.split())
    # Link destinations change when a restructure moves files; link text, emphasis and code stay.
    text = re.sub(r"\]\(\s*<?[^)\s>]*>?(\s+\"[^\"]*\")?\s*\)", "]()", text)
    return re.sub(r"^(\[[^\]]+\]:)\s*\S+", r"\1", text)


def _block_hash(block: Block) -> str:
    return hashlib.sha256(f"{block.type}\0{block.info}\0{_conservation_text(block)}".encode()).hexdigest()[:16]


def _load_mappings(context: PlanContext) -> list[dict[str, Any]]:
    path = context.repo.root / context.plan.artifact(MAPPINGS_NAME)
    if not path.is_file():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    out = []
    for kind in MAPPING_TYPES:
        for entry in data.get(kind, []) or []:
            if isinstance(entry, dict):
                out.append({"kind": kind, **entry})
    return out


def _entry_digest(entry: dict[str, Any]) -> str:
    return sha256_bytes(json.dumps(entry, sort_keys=True, ensure_ascii=False).encode())


def _destination_hashes(corpus: Corpus, entry: dict[str, Any]) -> list[str]:
    if entry["kind"] != "rewritten":
        return []
    doc = corpus.docs.get(str(entry.get("to", "")))
    if doc is None:
        return []
    heading = entry.get("heading")
    return [_block_hash(b) for b in doc.blocks if not heading or heading in b.heading_path]


def _approve_mappings(context: PlanContext, args: argparse.Namespace) -> None:
    if not args.by:
        raise UsageError("plan approve --mappings needs --by NAME (the person who reviewed the diff)")
    baseline = _load_baseline(context)
    if baseline is None:
        return
    by_hash = {b["hash"]: b for b in baseline}
    receipts = []
    review = []
    for entry in _load_mappings(context):
        missing = [h for h in entry.get("blocks", []) if h not in by_hash]
        if missing or not entry.get("id"):
            context.error(
                "mapping-invalid",
                f"mapping {entry.get('id', '?')}: needs an id and baseline block hashes ({', '.join(missing[:3])} not in the baseline)",
            )
            continue
        destination = _destination_hashes(context.corpus, entry)
        if entry["kind"] == "dropped" and not str(entry.get("proof") or "").strip():
            context.error(
                "mapping-invalid", f"mapping {entry['id']}: a dropped mapping needs proof (where the content lives on, or why it is obsolete)"
            )
            continue
        if entry["kind"] == "rewritten" and not destination:
            context.error("mapping-invalid", f"mapping {entry['id']}: destination {entry.get('to')} {entry.get('heading', '')} has no blocks")
            continue
        receipts.append(
            {
                "id": entry["id"],
                "entry_sha256": _entry_digest(entry),
                "baseline": entry.get("blocks", []),
                "destination": destination,
                "reviewer": args.by,
                "date": datetime.now(UTC).date().isoformat(),
            }
        )
        review.append(
            {
                "id": entry["id"],
                "kind": entry["kind"],
                "before": [by_hash[h]["text"] for h in entry.get("blocks", [])],
                "to": entry.get("to"),
                "proof": entry.get("proof"),
            }
        )
    context.report.data["review"] = review
    if [f for f in context.report.findings if f.severity == "Blocking"]:
        return
    path = context.repo.root / context.plan.artifact(RECEIPTS_NAME)
    _fsync_write(path.with_name(path.name + ".tmp"), _json_bytes({"receipts": receipts}))
    os.replace(path.with_name(path.name + ".tmp"), path)
    context.report.data["state"] = f"{len(receipts)} review receipts written"


def _load_baseline(context: PlanContext) -> list[dict[str, Any]] | None:
    rel = context.plan.meta.get("blocks")
    data = _read_json(context.repo.root / str(rel)) if isinstance(rel, str) else None
    if not isinstance(data, dict) or not isinstance(data.get("blocks"), list):
        context.report.coverage.append(CoverageRow("conservation_baseline", "failed", f"{rel}: missing or unreadable"))
        return None
    context.report.coverage.append(CoverageRow("conservation_baseline", "complete", f"{rel}: {len(data['blocks'])} blocks"))
    return [b for b in data["blocks"] if isinstance(b, dict)]


def _verify(context: PlanContext, args: argparse.Namespace) -> list[str]:
    report, corpus = context.report, context.corpus
    required = ["conservation_baseline", "markdown"]
    baseline = _load_baseline(context)
    if baseline is None:
        return required
    current = [(rel, b, _block_hash(b)) for rel in sorted(corpus.docs) for b in corpus.docs[rel].blocks]
    occurrences: dict[str, list[int]] = defaultdict(list)
    for index, (_rel, _block, digest) in enumerate(current):
        occurrences[digest].append(index)
    receipts = {r["id"]: r for r in (_read_json(context.repo.root / context.plan.artifact(RECEIPTS_NAME)) or {}).get("receipts", [])}
    excused: Counter[str] = Counter()
    # a block a reviewed rewritten mapping sends to another page sits where the owner agreed
    relocated: dict[str, str] = {}
    for entry in _load_mappings(context):
        receipt = receipts.get(entry.get("id"))
        if receipt is None:
            report.add(
                Finding(
                    "mapping-unreviewed",
                    "P0",
                    "verified",
                    context.plan.artifact(MAPPINGS_NAME),
                    0,
                    f"mapping {entry.get('id')} has no review receipt",
                    suggestion="show the diff to the owner, then run plan approve --mappings",
                )
            )
            continue
        valid = (
            receipt.get("entry_sha256") == _entry_digest(entry)
            and receipt.get("baseline") == entry.get("blocks", [])
            and all(any(b["hash"] == h for b in baseline) for h in entry.get("blocks", []))
            and receipt.get("destination") == _destination_hashes(corpus, entry)
        )
        if not valid:
            report.add(
                Finding(
                    "receipt-invalid",
                    "P0",
                    "verified",
                    context.plan.artifact(RECEIPTS_NAME),
                    0,
                    f"mapping {entry.get('id')}: the entry, its baseline blocks or its destination changed after review",
                    suggestion="review it again",
                )
            )
            continue
        excused.update(entry.get("blocks", []))
        if entry["kind"] == "rewritten":
            for digest in entry.get("blocks", []):
                relocated[digest] = str(entry.get("to", ""))
    expected = _reference_digests(context.plan, baseline)
    used: set[int] = set()
    matched: list[int | None] = []
    for position, block in enumerate(baseline):
        digest = block["hash"]
        free = [i for i in occurrences.get(digest, []) if i not in used]
        if not free and position in expected:
            # the block as the plan's own [[reference]] edits left it
            digest = expected[position]
            free = [i for i in occurrences.get(digest, []) if i not in used]
        if len(free) > 1:
            # of identical copies (a table copied into a spike, a repeated warning), the one still
            # in its section is the one this block became
            free.sort(key=lambda i: not _place_kept(context.plan, block, current[i][0], current[i][1].heading_path))
        if free:
            used.add(free[0])
            matched.append(free[0])
        elif excused[digest] > 0:
            excused[digest] -= 1
            matched.append(None)
        else:
            matched.append(None)
            report.add(
                Finding(
                    "block-unaccounted",
                    "P0",
                    "verified",
                    block["file"],
                    block["line"],
                    f"{block['type']} not found after the restructure: {block['text'][:100]!r}",
                    suggestion="restore it, or record a rewritten/dropped mapping and have it reviewed",
                )
            )
    unaccounted = sum(1 for f in report.findings if f.check == "block-unaccounted")
    groups: dict[tuple[Any, ...], list[int]] = defaultdict(list)
    for block, found in zip(baseline, matched, strict=True):
        if found is not None and block["type"] in ("list-item", "table-row"):
            groups[(block["file"], tuple(block["heading_path"]), block["type"], block["depth"])].append(found)
        if (
            found is not None
            and _sensitive(block)
            and relocated.get(block["hash"]) != current[found][0]
            and not _place_kept(context.plan, block, current[found][0], current[found][1].heading_path)
        ):
            report.add(
                Finding(
                    "context-lost",
                    "P1",
                    "verified",
                    current[found][0],
                    current[found][1].line,
                    f"{block['type']} {block['text'][:80]!r} left its section {block['file']}: {' > '.join(block['heading_path']) or '(top)'}",
                    suggestion="keep warnings and requirements under the heading they qualify",
                )
            )
    for (file, path, kind, _depth), indexes in sorted(groups.items()):
        if indexes != sorted(indexes):
            report.add(Finding("order-changed", "P1", "verified", file, 0, f"the order of the {kind}s under {' > '.join(path) or '(top)'} changed"))
    report.data["conservation"] = {
        "baseline_blocks": len(baseline),
        "unaccounted": unaccounted,
        "excused_by_mappings": sum(1 for i in matched if i is None) - unaccounted,
    }
    if args.urls:
        if not args.built:
            raise UsageError("plan verify --urls needs --built NEW_SITE")
        urls = _read_json(_root_path(args, args.urls))
        if not isinstance(urls, dict):
            raise UsageError(f"{args.urls}: not a URL baseline")
        built = load_built(args.built, context.repo, context.site)
        if "routes" not in urls:
            raise UsageError(f"{args.urls}: not a URL baseline written by check --save-baseline")
        compare_url_baseline(urls, built["site"], report, args.urls)
        report.coverage.append(_url_baseline_row(urls, built))
        required.append("url_baseline")
    elif context.site.config:
        report.coverage.append(CoverageRow("url_baseline", "partial", "not checked: pass --urls and --built to verify URL preservation"))
    else:
        report.coverage.append(CoverageRow("url_baseline", "not_applicable", "no site config: no URLs to preserve"))
    return required


def _reference_digests(plan: Plan, baseline: list[dict[str, Any]]) -> dict[int, str]:
    """Baseline position -> the digest of that block after the [[reference]] edits on its lines."""
    edits: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for entry in plan.entries("reference"):
        if isinstance(entry.get("line"), int) and isinstance(entry.get("old"), str) and isinstance(entry.get("new"), str):
            edits[str(entry.get("file"))].append((entry["line"], entry["old"], entry["new"]))
    starts: dict[str, list[int]] = defaultdict(list)
    for block in baseline:
        starts[str(block["file"])].append(int(block["line"]))
    out: dict[int, str] = {}
    for position, block in enumerate(baseline):
        file, first = str(block["file"]), int(block["line"])
        if file not in edits:
            continue
        after = [s for s in starts[file] if s > first]
        end = min(after) if after else first + 10**9  # the file's last block runs to its end
        text = str(block["text"])
        touched = False
        for line, old, new in sorted(edits[file]):
            if first <= line < end and old in text:
                text, touched = text.replace(old, new, 1), True
        if touched:
            out[position] = _block_hash(Block(type=str(block["type"]), text=text, line=first, heading_path=[], info=str(block.get("info", ""))))
    return out


def _place_kept(plan: Plan, block: dict[str, Any], now_file: str, now_path: list[str]) -> bool:
    """Whether a block still sits under its full heading path, in the file the plan sent it to."""
    file, path = str(block["file"]), [str(h) for h in block["heading_path"]]
    now = [str(h) for h in now_path]
    for split in plan.entries("split"):
        heading = str(split.get("heading"))
        if str(split.get("from")) == file and heading in path:
            return now_file == str(split.get("to")) and now == path[path.index(heading) :]
    for merge in plan.entries("merge"):
        if file in _paths_of(merge, "from"):
            # merged under the target's own title: the path below the source's title must survive
            tail = path[1:]
            return now_file == str(merge.get("into")) and (not tail or now[-len(tail) :] == tail)
    moves = {str(e.get("from")): str(e.get("to")) for kind in ("move", "archive") for e in plan.entries(kind)}
    return now_file == moves.get(file, file) and now == path


def _sensitive(block: dict[str, Any]) -> bool:
    kind = str(block["type"])
    return kind.startswith(("admonition", "alert")) or (kind in ("paragraph", "list-item") and bool(SENSITIVE_RE.search(str(block["text"]))))


# ---------------------------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------------------------


def _root_path(args: argparse.Namespace, value: str) -> Path:
    """A path flag naming a repository artifact: relative paths are relative to --root, not the cwd."""
    path = Path(value)
    return path if path.is_absolute() else Path(args.root) / path


def _write_output(path: Path, content: str) -> None:
    if path.is_symlink():
        raise UsageError(f"refusing to write through a symlink: {path}")
    target = path.resolve()
    if ".git" in target.parts:
        raise UsageError(f"refusing to write inside .git: {path}")
    if target.parent.exists() and not target.parent.is_dir():
        raise UsageError(f"the parent of {path} is not a directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _common(parser: argparse.ArgumentParser, out: bool = True) -> None:
    parser.add_argument("--root", default=".", help="repository root (default: the current directory)")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="output format")
    if out:
        parser.add_argument("--out", help="write the report to this file instead of stdout")
    parser.add_argument("--max", type=int, default=50, help="findings shown in text output (default 50)")
    parser.add_argument("--fail-on", choices=SEVERITIES, default="P3", help="lowest severity that makes the exit code 1 (default P3)")


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser; each command is a subparser of the `command` destination."""
    parser = argparse.ArgumentParser(
        prog="docstool",
        description="Check documentation against the repository it describes.",
    )
    parser.add_argument("--version", action="version", version=f"docstool {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    inventory = sub.add_parser("inventory", help="map the docs: headings, links, couplings, duplicates, lifecycle, style")
    _common(inventory)
    inventory.add_argument("--section", choices=("all", "docs", "root"), default="all", help="which Markdown files to list")
    inventory.add_argument("--blocks", help="also write the content-conservation block baseline to this file")
    check = sub.add_parser("check", help="find broken links, anchors, images, nav entries and publication problems")
    _common(check)
    check.add_argument("--scope", choices=("all", "docs", "repo"), default="all", help="which Markdown files to check")
    check.add_argument("--allow-partial", action="store_true", help="exit 0/1 even when coverage is incomplete (the summary says PARTIAL)")
    check.add_argument("--built", help="a docstool site-build output directory (refused when stale or not built by docstool)")
    check.add_argument("--save-baseline", help="write the URL and anchor baseline of --built (or, without it, a source-derived one) to this file")
    check.add_argument("--baseline", help="check --built against a saved URL baseline: routes, redirects, anchors")
    build = sub.add_parser("site-build", help="build the site with its generator into a fresh directory, with a stamp of its inputs")
    _common(build, out=False)
    build.add_argument("--out", dest="out_dir", required=True, help="fresh output directory (must not exist or be empty)")
    build.add_argument("--ref", help="build this commit from git archive instead of the working tree")
    build.add_argument("--generator", choices=("zensical", "mkdocs"), help="default: zensical for zensical.toml, mkdocs for mkdocs.yml")
    build.add_argument("--generator-cmd", help=argparse.SUPPRESS)
    plan = sub.add_parser("plan", help="validate, approve, apply, resume, roll back or verify a restructure plan")
    _common(plan)
    plan.add_argument("action", choices=("validate", "approve", "apply", "resume", "rollback", "verify"))
    plan.add_argument("--plan", default="docs/internal/restructure/plan.toml", help="the plan file (default docs/internal/restructure/plan.toml)")
    plan.add_argument("--write", action="store_true", help="apply: write the changes (the default is a dry run)")
    plan.add_argument("--by", help="approve: who approves (gate G9)")
    plan.add_argument("--mappings", action="store_true", help="approve: write review receipts for mappings.toml instead of the plan approval")
    plan.add_argument("--urls", help="verify: also check a saved URL baseline against --built")
    plan.add_argument("--built", help="verify --urls: the new site-build output")
    drift = sub.add_parser("drift", help="find commands, flags, env vars and paths the docs name that the code no longer has")
    _common(drift)
    drift.add_argument("--scope", choices=("all", "docs", "repo"), default="all", help="which Markdown files to read")
    drift.add_argument("--base", help="also report tokens removed or added since this commit (read-only git diff)")
    drift.add_argument("--paths", action="store_true", help="also check repository paths quoted in inline code")
    drift.add_argument("--leads", action="store_true", help="also report status claims, hand-maintained counts and stale docs as leads")
    drift.add_argument("--allow-partial", action="store_true", help="exit 0/1 even when coverage is incomplete (the summary says PARTIAL)")
    audit = sub.add_parser("site-audit", help="audit zensical.toml or mkdocs.yml for what Zensical ignores, misses or does differently")
    _common(audit)
    readme = sub.add_parser("readme", help="lint the README and compare it with the homepage")
    _common(readme)
    readme.add_argument("--file", default="README.md", help="the README to lint (default README.md)")
    readme.add_argument("--home", help="the homepage (docs/index.md) whose tagline, features and install block the README must match")
    readme.add_argument("--registry", action="store_true", help="the README is also shown on a package registry (relative images break there)")
    contrast = sub.add_parser("contrast", help="check a brand colour against both page schemes and as a button fill")
    _common(contrast)
    contrast.add_argument("colour", help="the brand colour, #rrggbb")
    contrast.add_argument("--slate", help="the dark-scheme override of the colour, when there is one")
    slug = sub.add_parser("slug", help="print GitHub's and the site's anchor for heading texts")
    _common(slug)
    slug.add_argument(
        "--style",
        default=None,
        choices=SLUG_STYLES,
        help="the site's slugify (default: read from the --root site config)",
    )
    slug.add_argument("text", nargs="+", help="heading texts, in document order")
    return parser


COMMANDS = {
    "inventory": cmd_inventory,
    "check": cmd_check,
    "drift": cmd_drift,
    "site-audit": cmd_site_audit,
    "readme": cmd_readme,
    "contrast": cmd_contrast,
    "site-build": cmd_site_build,
    "plan": cmd_plan,
    "slug": cmd_slug,
}


def render_plan_text(report: Report) -> str:
    """The operation list of an apply (dry run or written) and the redirects it adds."""
    operations = report.data.get("operations")
    if not isinstance(operations, list):
        return ""
    out = [f"Operations ({len(operations)}):"] + [f"  {op['change']:<6}  {op['path']}" for op in operations]
    redirects = report.data.get("redirects") or []
    if redirects:
        out += [f"Redirects added ({len(redirects)}):"] + [f"  {r}" for r in redirects]
    return "\n".join(out) + "\n\n"


TEXT_RENDERERS: dict[str, Callable[[Report], str]] = {"inventory": render_inventory_text, "contrast": render_contrast_text, "plan": render_plan_text}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_usage(sys.stderr)
        print("docstool: error: no command given", file=sys.stderr)
        return EXIT_USAGE
    report = Report(command=args.command, root=str(Path(args.root).resolve()))
    try:
        required = COMMANDS[args.command](args, report)
        code, incomplete = finalize(report, required, args.fail_on, getattr(args, "allow_partial", False))
        if args.format == "json":
            output = render_json(report, incomplete)
        elif args.command == "slug":
            output = "".join(
                f"{r['text']}\n  github: #{r['github']}\n  site ({r['style']}): "
                + (f"#{r['site']}" if r["site"] is not None else "not computed: pass --style")
                + "\n"
                for r in report.data["slugs"]
            )
        else:
            extra = TEXT_RENDERERS[args.command](report) if args.command in TEXT_RENDERERS else ""
            output = extra + render_text(report, incomplete, args.max)
        if getattr(args, "out", None):
            _write_output(Path(args.out), output)
        else:
            sys.stdout.write(output)
    except UsageError as error:
        print(f"docstool: error: {error}", file=sys.stderr)
        return EXIT_USAGE
    except OSError as error:
        # never exit 1 ("findings") on an I/O failure
        print(f"docstool: error: {error}", file=sys.stderr)
        return EXIT_USAGE
    return code


if __name__ == "__main__":
    sys.exit(main())
