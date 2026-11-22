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
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote

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
    r"""^(?P<key>"(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^\s"'#\-?:,\[\]{}&*!|>%@`][^:#]*?|-[^\s:][^:#]*?)[ \t]*:(?:[ \t]+(?P<rest>.*)|$)"""
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


def load_site(repo: Repo, report: Report) -> Site:
    """Read the site config and add the config, nav, exclude_docs, redirects and slug-style rows."""
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
    chosen = toml_path if repo.exists(toml_path) else yaml_path
    note = f" (zensical.toml is used; {yaml_path} is ignored by Zensical)" if chosen == toml_path and repo.exists(yaml_path) else ""
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
        site.extensions = dict(data.get("markdown_extensions") or {}) if explicit else {name: {} for name in ZENSICAL_DEFAULT_EXTENSIONS}
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

    for rel in repo.files:
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
            if text and ".md" in text and re.search(r"slug|anchor|fragment|broken link", text, re.IGNORECASE):
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
    return ["config", "nav", "exclude_docs", "markdown"]


# ---------------------------------------------------------------------------------------------
# inventory
# ---------------------------------------------------------------------------------------------


def block_baseline(corpus: Corpus) -> list[dict[str, Any]]:
    """Typed blocks with provenance and a hash of their normalised content (content conservation)."""
    out = []
    for rel in sorted(corpus.docs):
        for block in corpus.docs[rel].blocks:
            text = block.text if block.type == "code" else " ".join(block.text.split())
            digest = hashlib.sha256(f"{block.type}\0{block.info}\0{text}".encode()).hexdigest()[:16]
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
            Path(args.blocks),
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
    github = GithubSlugger()
    used: set[str] = set()
    rows = []
    for text in args.text:
        plain = heading_plain_text(text)
        rows.append(
            {"text": text, "github": github.slug(plain), "site": unique_site_id(site_slug_base(plain, args.style), used), "style": args.style}
        )
    report.data["slugs"] = rows
    return []


# ---------------------------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------------------------


def _write_output(path: Path, content: str) -> None:
    if path.is_symlink():
        raise UsageError(f"refusing to write through a symlink: {path}")
    target = path.resolve()
    if ".git" in target.parts:
        raise UsageError(f"refusing to write inside .git: {path}")
    if not target.parent.is_dir():
        raise UsageError(f"the directory of {path} does not exist")
    target.write_text(content, encoding="utf-8")


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=".", help="repository root (default: the current directory)")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="output format")
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
    slug = sub.add_parser("slug", help="print GitHub's and the site's anchor for heading texts")
    _common(slug)
    slug.add_argument(
        "--style",
        default="pymdownx-lower",
        choices=("pymdownx-lower", "pymdownx-none", "python-markdown", "python-markdown-unicode"),
        help="the site's slugify",
    )
    slug.add_argument("text", nargs="+", help="heading texts, in document order")
    return parser


COMMANDS = {"inventory": cmd_inventory, "check": cmd_check, "slug": cmd_slug}


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
            output = "".join(f"{r['text']}\n  github: #{r['github']}\n  site ({r['style']}): #{r['site']}\n" for r in report.data["slugs"])
        else:
            extra = render_inventory_text(report) if args.command == "inventory" else ""
            output = extra + render_text(report, incomplete, args.max)
        if args.out:
            _write_output(Path(args.out), output)
        else:
            sys.stdout.write(output)
    except UsageError as error:
        print(f"docstool: error: {error}", file=sys.stderr)
        return EXIT_USAGE
    return code


if __name__ == "__main__":
    sys.exit(main())
