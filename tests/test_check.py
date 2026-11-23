"""docstool check on the fixtures: every planted problem is found, the clean repo gives none."""

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
from conftest import DOCSTOOL, docstool_code, docstool_json, git, load_module, make_repo, run_script


def findings(report: dict[str, Any]) -> set[tuple[str, str, int]]:
    return {(f["check"], f["file"], f["line"]) for f in report["findings"]}


@pytest.mark.parametrize("command", ["check", "inventory"])
def test_clean_repo_has_no_findings(tmp_path: Path, command: str) -> None:
    repo = make_repo("clean", tmp_path)
    code, report = docstool_json(repo, command)
    assert report["findings"] == []
    assert code == 0
    assert all(row["state"] in ("complete", "not_applicable") for row in report["coverage"])


def test_rust_cli_planted_link_problems(tmp_path: Path) -> None:
    repo = make_repo("rust-cli", tmp_path)
    code, report = docstool_json(repo, "check")
    assert code == 1
    assert findings(report) == {
        ("broken-anchor", "docs/usage.md", 7),
        ("broken-link", "docs/usage.md", 8),
        ("leaves-docs-dir", "docs/usage.md", 8),
        ("broken-image", "docs/usage.md", 10),
    }
    leaving = next(f for f in report["findings"] if f["check"] == "leaves-docs-dir")
    assert "https://github.com/example/rcli/blob/main/README.md" in leaving["suggestion"]


def test_messy_docs_planted_problems(tmp_path: Path) -> None:
    repo = make_repo("messy-docs", tmp_path)
    _, report = docstool_json(repo, "check")
    assert findings(report) == {
        ("broken-anchor", "README.md", 9),
        ("broken-anchor", "docs/protocol.md", 18),
        ("links-unpublished", "docs/release.md", 7),
        ("task-marker", "docs/roadmap.md", 10),
    }
    explicit = next(f for f in report["findings"] if f["file"] == "docs/protocol.md")
    assert "explicit {#id}" in explicit["evidence"][0]


def test_mkdocs_site_nav_orphan_and_slug_divergence(tmp_path: Path) -> None:
    repo = make_repo("mkdocs-site", tmp_path)
    _, report = docstool_json(repo, "check")
    assert {(f["check"], f["file"]) for f in report["findings"]} == {
        ("slug-divergence", "docs/index.md"),
        ("nav-missing", "mkdocs.yml"),
        ("orphan-page", "docs/orphan.md"),
    }
    rows = {r["input"]: r for r in report["coverage"]}
    assert rows["slug_style"]["reason"].startswith("python-markdown")
    assert rows["redirects"]["reason"] == "1 redirects"


def test_scope_repo_checks_only_root_files(tmp_path: Path) -> None:
    repo = make_repo("messy-docs", tmp_path)
    _, report = docstool_json(repo, "check", "--scope", "repo")
    assert {f["file"] for f in report["findings"]} == {"README.md"}


def test_fail_on_raises_the_threshold(tmp_path: Path) -> None:
    repo = make_repo("messy-docs", tmp_path)
    code, report = docstool_json(repo, "check", "--fail-on", "P0")
    assert code == 0
    assert report["findings"]


def write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_site_assets_redirects_snippets_and_home_links(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    config = (repo / "zensical.toml").read_text(encoding="utf-8")
    config = config.replace('exclude_docs = """', 'extra_css = ["stylesheets/home.css", "stylesheets/missing.css"]\nexclude_docs = """')
    config += '\n[project.theme]\ncustom_dir = "overrides"\n\n[project.markdown_extensions."pymdownx.snippets"]\nbase_path = ["."]\n'
    config += '\n[project.plugins.redirects.redirect_maps]\n"old.md" = "gone.md"\n"guide.md" = "reference.md"\n'
    write(repo, "zensical.toml", config)
    write(repo, "overrides/stylesheets/home.css", "a {}\n")
    write(repo, "docs/guide.md", (repo / "docs/guide.md").read_text(encoding="utf-8") + '\n--8<-- "README.md"\n--8<-- "nope.txt"\n')
    write(
        repo,
        "docs/index.md",
        "---\nhome:\n  actions:\n    - { text: Start, link: guide/ }\n    - { text: Lost, link: lost/ }\n---\n"
        + (repo / "docs/index.md").read_text(encoding="utf-8"),
    )
    _, report = docstool_json(repo, "check")
    messages = sorted((f["check"], f["message"].split(":")[0]) for f in report["findings"])
    assert messages == [
        ("home-link", "home action 'Lost' links to lost/, which is not a page"),
        ("missing-asset", "extra_css entry stylesheets/missing.css exists in neither docs/ nor custom_dir; a strict build does not catch this"),
        ("redirect-target", "redirect old.md -> gone.md"),
        ("redirect-target", "redirect source guide.md is still a page; the redirect is never used"),
        ("snippet", "snippet 'nope.txt' is not found under base_path ['.']"),
    ]


def test_duplicate_headings_on_published_pages(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    write(repo, "docs/reference.md", (repo / "docs/reference.md").read_text(encoding="utf-8") + "\n## Options\n\nAgain.\n")
    _, report = docstool_json(repo, "check")
    dup = [f for f in report["findings"] if f["check"] == "duplicate-heading"]
    assert len(dup) == 1
    assert "#options_1" in dup[0]["message"]
    assert "#options-1" in dup[0]["message"]


def test_internal_without_exclude_docs_is_published(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    config = (repo / "zensical.toml").read_text(encoding="utf-8").replace('exclude_docs = """\ninternal/\n"""\n', "")
    write(repo, "zensical.toml", config)
    _, report = docstool_json(repo, "check")
    assert ("internal-published", "zensical.toml", 0) in findings(report)


def test_case_mismatch_is_reported(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    write(repo, "docs/extra.md", "# Extra\n\nSee [Guide](Guide.md).\n")
    _, report = docstool_json(repo, "check", "--scope", "docs")
    case = [f for f in report["findings"] if f["check"] == "broken-link"]
    assert case and "case differs" in case[0]["message"]


def test_unparseable_mkdocs_yml_is_incomplete_coverage(tmp_path: Path) -> None:
    repo = make_repo("mkdocs-site", tmp_path)
    write(repo, "mkdocs.yml", "site_name: x\nnav: &n\n  - a.md\n")
    code, report = docstool_json(repo, "check")
    assert code == 3
    assert {r["input"]: r["state"] for r in report["coverage"]}["config"] == "partial"
    assert report["summary"]["incomplete"]
    code, _ = docstool_json(repo, "check", "--allow-partial")
    assert code in (0, 1)


def test_text_output_is_capped_and_says_partial(tmp_path: Path) -> None:
    repo = make_repo("mkdocs-site", tmp_path)
    write(repo, "mkdocs.yml", "site_name: x\nnav: &n\n  - a.md\n")
    result = run_script(DOCSTOOL, "check", "--root", str(repo), "--allow-partial", "--max", "1")
    assert "PARTIAL" in result.stdout


def test_out_writes_the_report_and_refuses_git_dir(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    out = tmp_path / "report.json"
    result = run_script(DOCSTOOL, "check", "--root", str(repo), "--format", "json", "--out", str(out))
    assert result.returncode == 0
    assert out.read_text(encoding="utf-8").startswith("{")
    refused = run_script(DOCSTOOL, "check", "--root", str(repo), "--out", str(repo / ".git" / "x.txt"))
    assert refused.returncode == 2
    assert not (repo / ".git" / "x.txt").exists()


def test_slug_command() -> None:
    result = run_script(DOCSTOOL, "slug", "--format", "json", "Same", "Same", "The `--force` flag")
    rows = json.loads(result.stdout)["data"]["slugs"]
    assert [(r["github"], r["site"]) for r in rows] == [("same", "same"), ("same-1", "same_1"), ("the---force-flag", "the---force-flag")]


def test_reference_definition_targets_are_checked(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    write(
        repo,
        "docs/guide.md",
        (repo / "docs" / "guide.md").read_text(encoding="utf-8") + "\nSee [the page][p] and ![logo][l].\n\n[p]: missing.md\n[l]: assets/gone.png\n",
    )
    _, report = docstool_json(repo, "check")
    got = {(f["check"], f["message"].split(":")[0]) for f in report["findings"]}
    assert ("broken-link", "missing.md") in got
    assert ("broken-link", "assets/gone.png") in got


def test_links_through_symlinks_resolve(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    write(repo, "AGENTS.md", "# Agents\n\n## Rules\n")
    write(repo, ".agents/skills/x/SKILL.md", "# Skill\n")
    (repo / "CLAUDE.md").symlink_to("AGENTS.md")
    (repo / ".claude").mkdir()
    (repo / ".claude" / "skills").symlink_to("../.agents/skills")
    write(
        repo,
        "README.md",
        (repo / "README.md").read_text(encoding="utf-8") + "\n[c](CLAUDE.md#rules) [s](.claude/skills/x/SKILL.md) [d](.claude/skills/)\n",
    )
    _, report = docstool_json(repo, "check")
    assert [f for f in report["findings"] if f["check"].startswith("broken")] == []
    rows = {r["input"]: r for r in report["coverage"]}
    assert rows["symlinks"]["state"] == "complete"
    (repo / "gone").symlink_to("nowhere")
    _, report = docstool_json(repo, "check")
    rows = {r["input"]: r for r in report["coverage"]}
    assert rows["symlinks"]["state"] == "partial"
    assert "gone" in rows["symlinks"]["reason"]


def test_unknown_slugify_gives_no_slug_divergence(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    config = (repo / "zensical.toml").read_text(encoding="utf-8")
    write(repo, "zensical.toml", config.replace('{ object = "pymdownx.slugs.slugify", kwds = { case = "lower" } }', '{ object = "my.slugify" }'))
    write(repo, "docs/guide.md", (repo / "docs" / "guide.md").read_text(encoding="utf-8") + "\n## The `--dry-run` flag\n\nx\n")
    write(repo, "docs/index.md", (repo / "docs" / "index.md").read_text(encoding="utf-8") + "\n[dry](guide.md#the---dry-run-flag)\n")
    _, report = docstool_json(repo, "check")
    assert {r["input"]: r["state"] for r in report["coverage"]}["slug_style"] == "partial"
    assert [f for f in report["findings"] if f["check"] == "slug-divergence"] == []


def test_out_refuses_to_write_through_a_symlink(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    victim = tmp_path / "victim.txt"
    victim.write_text("keep\n", encoding="utf-8")
    (tmp_path / "link.json").symlink_to(victim)
    refused = run_script(DOCSTOOL, "check", "--root", str(repo), "--out", str(tmp_path / "link.json"))
    assert refused.returncode == 2
    assert victim.read_text(encoding="utf-8") == "keep\n"


def planned_repo(tmp_path: Path) -> Path:
    repo = make_repo("clean", tmp_path)
    (repo / "zensical.toml").unlink()
    (repo / "deployments").mkdir()
    (repo / "deployments" / "stack.yml").write_text("services: {}\n", encoding="utf-8")
    (repo / "docs" / "internal").mkdir(exist_ok=True)
    (repo / "docs" / "internal" / "notes.md").write_text("# Notes\n\n[Stack](../../deployments/stack.yml)\n", encoding="utf-8")
    (repo / "docs" / "page.md").write_text(
        "# Page\n\n[Stack](../deployments/stack.yml), [readme](../README.md), [notes](internal/notes.md), [self](#page)\n", encoding="utf-8"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "planned")
    return repo


def test_site_planned_reports_links_that_would_break(tmp_path: Path) -> None:
    repo = planned_repo(tmp_path)
    _, plain = docstool_json(repo, "check")
    assert not {f["check"] for f in plain["findings"]} & {"planned-leaves-docs", "planned-links-internal", "leaves-docs-dir", "links-unpublished"}
    _, report = docstool_json(repo, "check", "--site-planned")
    found = sorted((f["check"], f["file"]) for f in report["findings"] if f["check"].startswith("planned-"))
    assert found == [("planned-leaves-docs", "docs/page.md"), ("planned-leaves-docs", "docs/page.md"), ("planned-links-internal", "docs/page.md")]
    planned = [f for f in report["findings"] if f["check"].startswith("planned-")]
    assert all(f["severity"] == "P2" and f["confidence"] == "likely" for f in planned)
    assert not any("strict" in f["message"] for f in planned)
    assert not {f["check"] for f in report["findings"]} & {"leaves-docs-dir", "links-unpublished"}


@pytest.mark.parametrize("target", ["internal/", "templates/"])
def test_site_planned_reports_a_link_to_an_excluded_directory(tmp_path: Path, target: str) -> None:
    repo = planned_repo(tmp_path)
    (repo / "docs" / "templates").mkdir()
    (repo / "docs" / "templates" / "base.html").write_text("<html></html>\n", encoding="utf-8")
    (repo / "docs" / "page.md").write_text(f"# Page\n\n[x]({target})\n", encoding="utf-8")
    _, report = docstool_json(repo, "check", "--site-planned")
    assert [f["check"] for f in report["findings"] if f["check"].startswith("planned-")] == ["planned-links-internal"]


@pytest.mark.parametrize("name", ["internal", "templates"])
def test_site_planned_keeps_a_regular_file_named_like_an_excluded_directory(tmp_path: Path, name: str) -> None:
    module = load_module("docstool_planned", DOCSTOOL)
    site = module.Site()
    assert module._would_publish(site, f"docs/{name}") is True
    assert module._would_publish(site, f"docs/{name}", is_dir=True) is False


def test_site_planned_does_not_change_the_saved_baseline(tmp_path: Path) -> None:
    repo = planned_repo(tmp_path)
    docstool_json(repo, "check", "--save-baseline", "plain.json")
    docstool_json(repo, "check", "--site-planned", "--save-baseline", "planned.json")
    assert (repo / "planned.json").read_bytes() == (repo / "plain.json").read_bytes()
    assert json.loads((repo / "planned.json").read_text(encoding="utf-8"))["routes"] == {}


def test_site_planned_is_refused_when_a_site_exists(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    assert docstool_code(repo, "check", "--site-planned") == 2
