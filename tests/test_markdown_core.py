"""docstool's Markdown scanner, slug emulations, YAML subset and gitignore patterns."""

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

import pytest
from conftest import DOCSTOOL, REPO_ROOT, load_module

docstool = load_module("docstool", DOCSTOOL)

# Headings and the ids GitHub returned for them (gh api /markdown, 2026-11-21), plus the ids
# Zensical 0.1.3 built with pymdownx.slugs.slugify(case=lower). Recorded in the P0 spike.
SLUG_TABLE = json.loads((Path(__file__).parent / "golden" / "slug-synthetic-ids.json").read_text(encoding="utf-8"))


def test_github_slugs_match_github() -> None:
    slugger = docstool.GithubSlugger()
    got = [slugger.slug(docstool.heading_plain_text(h)) for h in SLUG_TABLE["headings"]]
    assert got == SLUG_TABLE["github"]


def test_site_slugs_match_zensical() -> None:
    used: set[str] = set()
    got = [docstool.unique_site_id(docstool.site_slug_base(docstool.heading_plain_text(h), "pymdownx-lower"), used) for h in SLUG_TABLE["headings"]]
    assert got == SLUG_TABLE["zensical"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The `--unsafe-model` override", "the-unsafe-model-override"),
        ("4. Engine — UI message contract", "4-engine-ui-message-contract"),
        ("Žluťoučký kůň", "zlutoucky-kun"),
    ],
)
def test_python_markdown_default_slugify(text: str, expected: str) -> None:
    assert docstool.site_slug_base(docstool.heading_plain_text(text), "python-markdown") == expected


def test_heading_text_drops_markup_but_keeps_code() -> None:
    assert docstool.heading_plain_text("**Bold** [link](x.md) `code` :rocket: ![img](a.png) <em>t</em>") == "Bold link code   t"


def parse(text: str) -> Any:
    return docstool.parse_markdown("doc.md", text)


def test_fences_of_both_kinds_and_any_length_hide_links() -> None:
    doc = parse("~~~\n[a](x.md)\n~~~\n\n````md\n```\n[b](y.md)\n```\n````\n\n[c](z.md)\n")
    assert [link.target for link in doc.links] == ["z.md"]
    assert [info for info, _, _ in doc.code_blocks] == ["", "md"]


def test_links_whose_text_wraps_are_found_on_their_first_line() -> None:
    doc = parse("intro\nsee [the long\nlink text](target.md#frag) here\n")
    assert [(link.target, link.line, link.text) for link in doc.links] == [("target.md#frag", 2, "the long link text")]


def test_code_spans_comments_and_escapes_hide_links() -> None:
    doc = parse("`[a](x.md)` \\[b](y.md)\n<!-- [c](z.md) -->\n<!--\n[d](w.md)\n-->\n[e](v.md)\n")
    assert [link.target for link in doc.links] == ["v.md"]


def test_reference_links_images_html_and_anchors() -> None:
    doc = parse('[x][ref] [y][] ![i](a.png)\n\n[ref]: target.md\n<img src="b.png"> <a href="c.md">c</a> <a name="here"></a>\n')
    kinds = sorted((link.kind, link.target) for link in doc.links)
    assert kinds == [("html-href", "c.md"), ("html-src", "b.png"), ("image", "a.png"), ("refdef", "target.md")]
    assert ("ref", 1) in doc.ref_uses
    assert doc.ref_defs["ref"][0] == "target.md"
    assert "here" in doc.html_ids


def test_front_matter_is_a_block_and_code_keeps_its_tabs() -> None:
    doc = parse("---\ntitle: x\n---\n# T\n\n```make\nall:\n\techo hi\n```\n\n  ```sh\n    indented\n  ```\n")
    assert (doc.blocks[0].type, doc.blocks[0].text) == ("front-matter", "---\ntitle: x\n---")
    code = [b.text for b in doc.blocks if b.type == "code"]
    assert code == ["all:\n\techo hi", "  indented"]


def test_indented_code_hides_links_but_container_bodies_do_not() -> None:
    doc = parse("Text\n\n    [x](missing.md)\n\n    more\n\nAfter\n")
    assert doc.links == []
    assert [b.text for b in doc.blocks if b.type == "code"] == ["[x](missing.md)\n\nmore"]
    for text in ("!!! note\n\n    [y](a.md)\n", '=== "Tab"\n\n    [y](a.md)\n', "- item\n\n    [y](a.md)\n", "Para\n    [y](a.md)\n"):
        assert [link.target for link in parse(text).links] == ["a.md"], text


def test_list_item_continuation_lines_stay_in_the_item() -> None:
    doc = parse("- first line\n  continued\nlazy\n- second\n\n  own paragraph\n")
    items = [(b.type, b.text) for b in doc.blocks]
    assert items == [("list-item", "first line continued lazy"), ("list-item", "second"), ("paragraph", "own paragraph")]


def test_atx_setext_numbered_and_explicit_id_headings() -> None:
    doc = parse("Title\n=====\n\n## 5.1 Implementation ##\n\nSub\n---\n\n### Exit codes {#codes}\n")
    assert [(h.level, h.text, h.number) for h in doc.headings] == [
        (1, "Title", None),
        (2, "5.1 Implementation", "5.1"),
        (2, "Sub", None),
        (3, "Exit codes", None),
    ]
    assert doc.headings[1].gh_slug == "51-implementation"
    assert doc.headings[3].gh_slug == "exit-codes-codes"
    assert doc.headings[3].site_slug == "codes"
    assert doc.headings[3].parent == 2


def test_front_matter_is_parsed_and_skipped() -> None:
    doc = parse("---\ntitle: Home\nhome:\n  actions:\n    - { text: Go, link: guide/ }\n---\n# Home\n")
    assert doc.front_matter == {"title": "Home", "home": {"actions": [{"text": "Go", "link": "guide/"}]}}
    assert [h.text for h in doc.headings] == ["Home"]


def test_blocks_carry_type_depth_and_heading_path() -> None:
    doc = parse(
        '# A\n\n## B\n\npara one\nline two\n\n1. step\n   - nested\n\n| h | i |\n| --- | --- |\n| 1 | 2 |\n\n!!! warning "Careful"\n    Never do it.\n\n> [!NOTE]\n> Read me.\n\n```sh\n  indented\n```\n'
    )
    blocks = [(b.type, b.text, b.depth, b.heading_path) for b in doc.blocks]
    assert ("paragraph", "para one line two", 0, ["A", "B"]) in blocks
    assert ("list-item", "step", 1, ["A", "B"]) in blocks
    assert ("list-item", "nested", 2, ["A", "B"]) in blocks
    assert ("table-row", "1 | 2", 0, ["A", "B"]) in blocks
    assert ("admonition:warning", "Careful Never do it.", 0, ["A", "B"]) in blocks
    assert ("alert:note", "[!NOTE] Read me.", 0, ["A", "B"]) in blocks
    assert ("code", "  indented", 0, ["A", "B"]) in blocks


def test_generated_regions_and_banners() -> None:
    doc = parse("> Historical: kept as written.\n\n<!-- BEGIN GENERATED -->\n| a |\n<!-- END GENERATED -->\n")
    assert doc.regions == [(3, 5, "<!-- BEGIN GENERATED -->")]
    assert doc.banners and doc.banners[0][0] == 1


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a: 1\nb: [x, 'y z']\nc: {d: true, e: null}\n", {"a": 1, "b": ["x", "y z"], "c": {"d": True, "e": None}}),
        (
            "nav:\n  - Home: index.md\n  - Guide:\n      - guide/a.md\n      - B: guide/b.md\n",
            {"nav": [{"Home": "index.md"}, {"Guide": ["guide/a.md", {"B": "guide/b.md"}]}]},
        ),
        ("x: >-\n  one\n  two\ny: |\n  keep\n", {"x": "one two", "y": "keep\n"}),
        ("k: v # comment\n'q:k': \"a#b\"\n", {"k": "v", "q:k": "a#b"}),
    ],
)
def test_yaml_subset(text: str, expected: object) -> None:
    assert docstool.yaml_load(text) == expected


def test_yaml_plain_key_may_contain_a_hash() -> None:
    # '#' starts a comment only after whitespace: an anchor redirect key needs no quotes.
    text = "redirect_maps:\n  guide.md#old: guide.md#new  # moved\n"
    assert docstool.yaml_load(text) == {"redirect_maps": {"guide.md#old": "guide.md#new"}}


def test_yaml_tags_are_kept_not_resolved() -> None:
    data = docstool.yaml_load(
        "i: !!python/name:material.extensions.emoji.twemoji\nk: !ENV [KEY, x]\ns: !!python/object/apply:pymdownx.slugs.slugify\n  kwds:\n    case: lower\n"
    )
    assert data["i"] == docstool.Tagged("!!python/name:material.extensions.emoji.twemoji", None)
    assert data["k"] == docstool.Tagged("!ENV", ["KEY", "x"])
    assert data["s"] == docstool.Tagged("!!python/object/apply:pymdownx.slugs.slugify", {"kwds": {"case": "lower"}})


@pytest.mark.parametrize(
    "text",
    [
        "a: &x 1\nb: *x\n",
        "a: 1\n---\nb: 2\n",
        "nav:\n  - Home: |\n      index.md\n",
        "a: [1,\n  2]\n",
        "base: &b {x: 1}\nc:\n  <<: *b\n",
    ],
)
def test_unsupported_yaml_raises_with_a_key_path(text: str) -> None:
    with pytest.raises(docstool.YamlError):
        docstool.yaml_load(text)


@pytest.mark.parametrize(
    ("patterns", "path", "matched"),
    [
        ("internal/\n", "internal/notes.md", True),
        ("internal/\n", "guide/internal/notes.md", True),
        ("/internal/\n", "guide/internal/notes.md", False),
        ("*.tmp.md\n!keep.tmp.md\n", "keep.tmp.md", False),
        ("drafts/**/wip.md\n", "drafts/a/b/wip.md", True),
        ("internal/\n", "internal.md", False),
    ],
)
def test_gitignore_patterns(patterns: str, path: str, matched: bool) -> None:
    assert docstool.GitignoreSpec(patterns).match(path) is matched


def test_the_slug_table_is_the_p0_evidence() -> None:
    assert len(SLUG_TABLE["headings"]) == len(SLUG_TABLE["github"]) == len(SLUG_TABLE["zensical"]) == 14
    assert (REPO_ROOT / "tests" / "golden" / "slug-synthetic-ids.json").is_file()
