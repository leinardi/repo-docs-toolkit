"""Strict builds of the landing examples, and what their homepage HTML must contain."""

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

import re
import shutil
import subprocess
import tomllib
from html.parser import HTMLParser
from pathlib import Path

import pytest
from conftest import LANDING_EXAMPLES, ZENSICAL_SITE, require_or_skip


class Page(HTMLParser):
    """The tags of one built page: (tag, attributes) in document order."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str]]] = []
        self.feed(path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, {key: value or "" for key, value in attrs}))

    def with_class(self, name: str, tag: str | None = None) -> list[dict[str, str]]:
        return [attrs for t, attrs in self.tags if name in attrs.get("class", "").split() and tag in (None, t)]

    def component(self, name: str) -> list[dict[str, str]]:
        return [attrs for _, attrs in self.tags if attrs.get("data-md-component") == name]


@pytest.mark.zensical
@pytest.mark.parametrize("name", LANDING_EXAMPLES)
def test_homepage_has_one_hero_and_the_native_chrome(landing_sites: dict[str, Path], name: str) -> None:
    page = Page(landing_sites[name] / "index.html")
    assert len(page.with_class("rdt-home")) == 1
    assert len(page.with_class("rdt-hero")) == 1
    h1s = [attrs for tag, attrs in page.tags if tag == "h1"]
    assert h1s == [{"class": "rdt-hero__name"}]
    # The theme's own header, tabs, search and palette toggle are still there.
    assert page.component("tabs"), "navigation tabs missing"
    assert page.component("search"), "search missing"
    assert page.component("palette"), "palette toggle missing"
    # hide: [navigation, toc] hides both sidebars.
    sidebars = page.component("sidebar")
    assert len(sidebars) == 2
    assert all("hidden" in attrs for attrs in sidebars)
    stylesheets = [attrs["href"] for tag, attrs in page.tags if tag == "link" and attrs.get("rel") == "stylesheet"]
    assert "./stylesheets/home.css" in stylesheets
    assert "./stylesheets/brand.css" in stylesheets
    # A primary call to action, and four feature cards.
    assert page.with_class("md-button--primary", "a")
    cards = page.with_class("cards")
    assert len(cards) == 1
    assert len(page.with_class("rdt-showcase")) == 1
    assert len(page.with_class("rdt-install")) == 1


@pytest.mark.zensical
@pytest.mark.parametrize("name", LANDING_EXAMPLES)
def test_feature_cards_have_four_items(landing_sites: dict[str, Path], name: str) -> None:
    html = (landing_sites[name] / "index.html").read_text(encoding="utf-8")
    cards = html.split('<div class="grid cards">', 1)[1].split("</ul>", 1)[0]
    assert cards.count("<li>") == 4


@pytest.mark.zensical
def test_install_tabs_render_as_native_content_tabs(landing_sites: dict[str, Path]) -> None:
    for name, count in (("cli", 3), ("library", 2)):
        page = Page(landing_sites[name] / "index.html")
        assert len(page.with_class("tabbed-set")) == 1
        assert len([attrs for tag, attrs in page.tags if tag == "input" and attrs.get("name", "").startswith("__tabbed_")]) == count
    # The GTK example has one install method: a code block, no tabs.
    assert not Page(landing_sites["gtk-app"] / "index.html").with_class("tabbed-set")


@pytest.mark.zensical
def test_gtk_logo_and_screenshots_have_a_light_and_a_dark_variant(landing_sites: dict[str, Path]) -> None:
    page = Page(landing_sites["gtk-app"] / "index.html")
    images = [attrs for tag, attrs in page.tags if tag == "img"]
    sources = [attrs["src"] for attrs in images]
    assert sum(src.endswith("#only-light") for src in sources) == 2
    assert sum(src.endswith("#only-dark") for src in sources) == 2
    assert all("alt" in attrs for attrs in images)


@pytest.mark.zensical
@pytest.mark.parametrize("name", LANDING_EXAMPLES)
def test_other_pages_have_no_hero(landing_sites: dict[str, Path], name: str) -> None:
    pages = [path for path in landing_sites[name].rglob("index.html") if path.parent != landing_sites[name]]
    assert pages
    for path in pages:
        page = Page(path)
        assert not page.with_class("rdt-home"), path
        # The stylesheet is site-wide, but every rule in it is scoped to the homepage wrapper.
        assert any(tag == "h1" for tag, _ in page.tags), path


TEMPLATE = ZENSICAL_SITE / "assets" / "zensical.toml"
# The tables an example may not change: everything but the project's own fields.
SHARED_KEYS = ("theme", "markdown_extensions", "plugins", "validation", "extra_css", "exclude_docs")


def filled_template() -> str:
    """The shipped template with its placeholders filled, as a project would."""
    text = TEMPLATE.read_text(encoding="utf-8").replace("<owner>", "example").replace("<repo>", "demo")
    return re.sub(r"<[^<>\n]+>", "Demo", text)


@pytest.mark.parametrize("name", LANDING_EXAMPLES)
def test_examples_use_the_template_config(name: str) -> None:
    template = tomllib.loads(filled_template())["project"]
    example = tomllib.loads((ZENSICAL_SITE / "assets" / "landing-examples" / name / "zensical.toml").read_text(encoding="utf-8"))["project"]
    for key in SHARED_KEYS:
        assert example.get(key) == template.get(key), key


@pytest.mark.zensical
def test_the_template_builds_with_a_redirect(tmp_path: Path) -> None:
    zensical = shutil.which("zensical")
    require_or_skip(zensical is not None, "zensical", "DOCSTOOL_REQUIRE_ZENSICAL")
    assert zensical is not None
    config = filled_template().replace(
        '# [project.plugins.redirects.redirect_maps]\n# "old-page.md" = "guide/new-page.md"',
        '[project.plugins.redirects.redirect_maps]\n"old-page.md" = "guide/new-page.md"\n"guide/new-page.md#old" = "guide/new-page.md#install"',
    )
    assert "[project.plugins.redirects.redirect_maps]" in config.replace("# [project.plugins.redirects", "")
    (tmp_path / "zensical.toml").write_text(config, encoding="utf-8")
    shutil.copytree(ZENSICAL_SITE / "assets" / "overrides", tmp_path / "overrides")
    (tmp_path / "docs" / "stylesheets").mkdir(parents=True)
    (tmp_path / "docs" / "guide").mkdir()
    for css in ("home.css", "brand.css"):
        shutil.copy2(ZENSICAL_SITE / "assets" / "stylesheets" / css, tmp_path / "docs" / "stylesheets" / css)
    (tmp_path / "docs" / "index.md").write_text(
        "---\ntemplate: home.html\nhide: [navigation, toc]\nhome:\n  tagline: Demo\n---\n\n> [!NOTE]\n> An alert.\n", encoding="utf-8"
    )
    (tmp_path / "docs" / "guide" / "new-page.md").write_text("# New page\n\n## Install\n\n[Home](../index.md)\n", encoding="utf-8")
    result = subprocess.run([zensical, "build", "--strict", "--clean"], cwd=tmp_path, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    site = tmp_path / "site"
    stub = (site / "old-page" / "index.html").read_text(encoding="utf-8")
    assert "guide/new-page/" in stub
    assert '"guide/new-page/#old":"guide/new-page/#install"' in (site / "redirect.json").read_text(encoding="utf-8").replace(" ", "")
    home = (site / "index.html").read_text(encoding="utf-8")
    assert 'class="admonition note"' in home


COMPOSE = """# --8<-- [start:service]
services:
  app:
    image: example/demo:1.0
# --8<-- [end:service]
volumes:
  data: {}
"""


def build_with_snippet(root: Path, compose: str, section: str) -> subprocess.CompletedProcess[str]:
    """A site from the filled template whose homepage includes a section of compose.yaml."""
    zensical = shutil.which("zensical")
    require_or_skip(zensical is not None, "zensical", "DOCSTOOL_REQUIRE_ZENSICAL")
    assert zensical is not None
    root.mkdir()
    (root / "zensical.toml").write_text(filled_template(), encoding="utf-8")
    shutil.copytree(ZENSICAL_SITE / "assets" / "overrides", root / "overrides")
    (root / "docs" / "stylesheets").mkdir(parents=True)
    for css in ("home.css", "brand.css"):
        shutil.copy2(ZENSICAL_SITE / "assets" / "stylesheets" / css, root / "docs" / "stylesheets" / css)
    (root / "compose.yaml").write_text(compose, encoding="utf-8")
    (root / "docs" / "index.md").write_text(f'# Demo\n\n```yaml\n--8<-- "compose.yaml:{section}"\n```\n', encoding="utf-8")
    return subprocess.run([zensical, "build", "--strict", "--clean"], cwd=root, capture_output=True, text=True, check=False)


@pytest.mark.zensical
def test_a_snippet_section_shows_only_its_part_of_the_file(tmp_path: Path) -> None:
    # landing-page.md, Step 3: a long compose file is shown through a snippet section.
    result = build_with_snippet(tmp_path / "ok", COMPOSE, "service")
    assert result.returncode == 0, result.stdout + result.stderr
    home = (tmp_path / "ok" / "site" / "index.html").read_text(encoding="utf-8")
    assert "example/demo:1.0" in home
    assert "volumes" not in home
    assert "[start:service]" not in home and "[end:service]" not in home


@pytest.mark.zensical
def test_a_missing_snippet_section_fails_the_strict_build(tmp_path: Path) -> None:
    result = build_with_snippet(tmp_path / "missing", COMPOSE, "web")
    assert result.returncode != 0
    assert "could not be located" in result.stdout + result.stderr


@pytest.mark.zensical
def test_a_lost_end_marker_is_not_caught_by_the_build(tmp_path: Path) -> None:
    # Why landing-page.md says to look at the excerpt after formatting: the build still passes
    # and the excerpt runs to the end of the file.
    result = build_with_snippet(tmp_path / "no-end", COMPOSE.replace("# --8<-- [end:service]\n", ""), "service")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "volumes" in (tmp_path / "no-end" / "site" / "index.html").read_text(encoding="utf-8")
