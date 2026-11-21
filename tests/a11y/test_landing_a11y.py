"""Accessibility checks on the built landing examples, in a real browser (Playwright + Chromium).

Every colour pair is read from the computed style of the rendered page, with translucent colours
composited over the background they sit on, in both schemes. These checks back the automated half of
the landing page's accessibility list; the visual review, the screen-reader pass and the feel of the
keyboard and the motion stay a manual checklist (skills/zensical-site/references/landing-page.md).
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

import functools
import os
import threading
from collections.abc import Iterator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from conftest import LANDING_EXAMPLES, require_or_skip

try:
    from playwright.sync_api import Browser, Page, sync_playwright
except ImportError:  # pragma: no cover - the a11y job installs it
    sync_playwright = None

pytestmark = pytest.mark.a11y

SCHEMES = ("light", "dark")

# Reads the colour pair an element shows: its text (or a given CSS property) and the opaque
# background under it, with every translucent layer composited in. Returns the WCAG ratio.
CONTRAST_JS = """
([el, prop]) => {
  const parse = (s) => {
    let m = s.match(/^rgba?\\(([^)]+)\\)/);
    if (m) {
      const p = m[1].split(/[\\s,\\/]+/).filter(Boolean).map(Number);
      return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
    }
    m = s.match(/^color\\(srgb ([^)]+)\\)/);
    if (m) {
      const p = m[1].split(/[\\s\\/]+/).filter(Boolean).map(Number);
      return [p[0] * 255, p[1] * 255, p[2] * 255, p.length > 3 ? p[3] : 1];
    }
    throw new Error("unparsed colour " + s);
  };
  const over = (top, under) => {
    const a = top[3] + under[3] * (1 - top[3]);
    if (a === 0) return [0, 0, 0, 0];
    const mix = (i) => (top[i] * top[3] + under[i] * under[3] * (1 - top[3])) / a;
    return [mix(0), mix(1), mix(2), a];
  };
  const layers = [];
  for (let node = el; node; node = node.parentElement) {
    const bg = parse(getComputedStyle(node).backgroundColor);
    if (bg[3] > 0) layers.push(bg);
    if (bg[3] >= 1) break;
  }
  let bg = [255, 255, 255, 1];
  for (const layer of layers.reverse()) bg = over(layer, bg);
  const style = getComputedStyle(el);
  let fgText = prop === "box-shadow" ? (style.boxShadow.match(/(rgba?\\([^)]+\\)|color\\([^)]+\\))/) || [""])[0] : style.getPropertyValue(prop);
  const fg = over(parse(fgText), bg);
  const lum = (c) => {
    const ch = c.slice(0, 3).map((v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
  };
  const [hi, lo] = [lum(fg), lum(bg)].sort((a, b) => b - a);
  const size = parseFloat(style.fontSize), weight = parseInt(style.fontWeight, 10);
  return { ratio: (hi + 0.05) / (lo + 0.05), large: size >= 24 || (size >= 18.66 && weight >= 700), fg: fgText };
}
"""

# Text pairs: selector, what it is, required on every example. Each needs 4.5:1, or 3:1 as large
# text. The optional ones exist only where the example uses them (a second line, install tabs).
TEXT_PAIRS = (
    (".rdt-hero__name", "project name", True),
    (".rdt-hero__text", "second line of the name", False),
    (".rdt-hero__tagline", "tagline", True),
    (".rdt-hero__actions .md-button--primary", "primary button text", True),
    (".rdt-hero__actions .md-button:not(.md-button--primary)", "secondary button text", True),
    (".rdt-install .tabbed-labels > label:nth-child(1)", "selected install tab", False),
    (".rdt-install .tabbed-labels > label:nth-child(2)", "unselected install tab", False),
    (".rdt-install code", "install command", True),
    (".rdt-home .grid.cards li strong", "feature card title", True),
    (".rdt-home .grid.cards li p:last-child", "feature card text", True),
)
# Non-text pairs (WCAG 1.4.11, 3:1): selector, CSS property, what it is, required on every example.
GRAPHIC_PAIRS = (
    (".rdt-install .tabbed-labels > label:nth-child(1)", "box-shadow", "selected tab marker", False),
    (".rdt-home .grid.cards .lg", "color", "feature icon on its tile", True),
    (".rdt-home .md-code__button", "color", "copy button", True),
)


@pytest.fixture(scope="module")
def served(landing_sites: dict[str, Path]) -> Iterator[dict[str, str]]:
    """Each built example over HTTP on localhost, as instant navigation needs."""
    servers = []
    urls = {}
    for name, site in landing_sites.items():
        handler = functools.partial(_QuietHandler, directory=str(site))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        urls[name] = f"http://127.0.0.1:{server.server_address[1]}/"
    yield urls
    for server in servers:
        server.shutdown()
        server.server_close()


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    require_or_skip(sync_playwright is not None, "playwright", "DOCSTOOL_REQUIRE_A11Y")
    assert sync_playwright is not None
    with sync_playwright() as playwright:
        # A11Y_CHROME points at a local Chrome when Playwright's own build is not downloaded.
        executable = os.environ.get("A11Y_CHROME") or None
        launched = playwright.chromium.launch(executable_path=executable)
        yield launched
        launched.close()


def open_page(browser: Browser, url: str, **context: Any) -> Page:
    options = {"viewport": {"width": 1440, "height": 900}, **context}
    page = browser.new_context(**options).new_page()
    # The theme loads its fonts from Google; the tests never leave localhost.
    page.route("**/*", lambda route: route.abort() if not route.request.url.startswith("http://127.0.0.1") else route.continue_())
    page.goto(url)
    page.wait_for_load_state("load")
    return page


def ratio(page: Page, selector: str, prop: str = "color") -> dict[str, Any]:
    element = page.locator(selector).first
    result: dict[str, Any] = element.evaluate(f"(el) => ({CONTRAST_JS})([el, {prop!r}])")
    return result


def present(page: Page, selector: str) -> bool:
    count: int = page.locator(selector).count()
    return count > 0


@pytest.mark.parametrize("scheme", SCHEMES)
@pytest.mark.parametrize("name", LANDING_EXAMPLES)
def test_text_contrast(browser: Browser, served: dict[str, str], name: str, scheme: str) -> None:
    page = open_page(browser, served[name], color_scheme=scheme)
    failures = []
    for selector, what, required in TEXT_PAIRS:
        if not present(page, selector):
            assert not required, f"{what} ({selector}) is missing"
            continue
        result = ratio(page, selector)
        minimum = 3.0 if result["large"] else 4.5
        if result["ratio"] < minimum:
            failures.append(f"{what}: {result['ratio']:.2f} < {minimum} ({result['fg']})")
    # The theme's link colour, on the page and on a feature card (probe links: the examples
    # have no prose links on the homepage).
    for host, what in ((".rdt-home", "link on the page"), (".rdt-home .grid.cards li", "link on a feature card")):
        result = page.locator(host).first.evaluate(
            f"(host) => {{ const a = document.createElement('a'); a.href = '#'; a.textContent = 'link'; host.append(a);"
            f" const r = ({CONTRAST_JS})([a, 'color']); a.remove(); return r; }}"
        )
        if result["ratio"] < 4.5:
            failures.append(f"{what}: {result['ratio']:.2f} < 4.5 ({result['fg']})")
    assert not failures, failures


def ring_ratio(page: Page, colour: str) -> dict[str, Any]:
    """A focus ring's colour against the homepage background behind the hero."""
    result: dict[str, Any] = page.evaluate(
        f"([c]) => {{ const probe = document.createElement('span'); probe.style.color = c; document.querySelector('.rdt-hero').append(probe);"
        f" const r = ({CONTRAST_JS})([probe, 'color']); probe.remove(); return r; }}",
        [colour],
    )
    return result


def keyboard_focus(page: Page, locator: Any) -> None:
    """Focus an element the way a keyboard does, so :focus-visible applies."""
    locator.focus()
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Tab")


@pytest.mark.parametrize("scheme", SCHEMES)
@pytest.mark.parametrize("name", LANDING_EXAMPLES)
def test_graphics_and_states_contrast(browser: Browser, served: dict[str, str], name: str, scheme: str) -> None:
    page = open_page(browser, served[name], color_scheme=scheme)
    failures = []
    for selector, prop, what, required in GRAPHIC_PAIRS:
        if not present(page, selector):
            assert not required, f"{what} ({selector}) is missing"
            continue
        result = ratio(page, selector, prop)
        if result["ratio"] < 3.0:
            failures.append(f"{what}: {result['ratio']:.2f} < 3 ({result['fg']})")
    # Hover: text stays readable, and the card border and copy button stay visible.
    hovers = [
        (".rdt-hero__actions .md-button--primary", "color", 4.5, "primary button on hover"),
        (".rdt-hero__actions .md-button:not(.md-button--primary)", "color", 4.5, "secondary button on hover"),
        (".rdt-home .grid.cards li", "border-top-color", 3.0, "feature card border on hover"),
        (".rdt-home .md-code__button", "color", 3.0, "copy button on hover"),
    ]
    if present(page, ".rdt-install .tabbed-labels"):
        hovers.append((".rdt-install .tabbed-labels > label:nth-child(2)", "color", 4.5, "unselected install tab on hover"))
    for selector, prop, minimum, what in hovers:
        page.locator(selector).first.hover()
        page.wait_for_timeout(400)
        result = ratio(page, selector, prop)
        if result["ratio"] < minimum:
            failures.append(f"{what}: {result['ratio']:.2f} < {minimum} ({result['fg']})")
    page.mouse.move(0, 0)
    # Focus: each call to action keeps readable text inside a ring that holds 3:1 against the page.
    buttons = page.locator(".rdt-hero__actions .md-button")
    for index in range(buttons.count()):
        button = buttons.nth(index)
        keyboard_focus(page, button)
        text: dict[str, Any] = button.evaluate(f"(el) => ({CONTRAST_JS})([el, 'color'])")
        minimum = 3.0 if text["large"] else 4.5
        if text["ratio"] < minimum:
            failures.append(f"button {index} text when focused: {text['ratio']:.2f} < {minimum} ({text['fg']})")
        outline = button.evaluate("(el) => getComputedStyle(el).outlineColor")
        ring = ring_ratio(page, outline)
        if ring["ratio"] < 3.0:
            failures.append(f"focus ring on button {index}: {ring['ratio']:.2f} < 3 ({outline})")
    # Focus on an install tab: the ring is drawn on its label.
    if present(page, ".rdt-install .tabbed-set"):
        keyboard_focus(page, page.locator(".rdt-install .tabbed-set > input").first)
        outline = page.locator(".rdt-install .tabbed-labels > label").first.evaluate("(el) => getComputedStyle(el).outlineColor")
        ring = ring_ratio(page, outline)
        if ring["ratio"] < 3.0:
            failures.append(f"focus ring on the install tab: {ring['ratio']:.2f} < 3 ({outline})")
    assert not failures, failures


@pytest.mark.parametrize("name", LANDING_EXAMPLES)
def test_keyboard_reaches_everything_in_order_with_a_visible_focus(browser: Browser, served: dict[str, str], name: str) -> None:
    page = open_page(browser, served[name])
    seen: list[dict[str, Any]] = []
    for _ in range(80):
        page.keyboard.press("Tab")
        seen.append(
            page.evaluate(
                """() => {
                  const el = document.activeElement;
                  let shown = el;
                  if (el.matches('.tabbed-set > input')) {
                    const index = [...el.parentElement.querySelectorAll(':scope > input')].indexOf(el);
                    shown = el.parentElement.querySelectorAll('.tabbed-labels > label')[index];
                  }
                  const s = getComputedStyle(shown);
                  const ring = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none';
                  return {
                    key: el.className + '|' + (el.getAttribute('href') || el.id || el.textContent.trim().slice(0, 20)),
                    home: !!el.closest('.rdt-home'),
                    skip: el.matches('.md-skip'),
                    palette: !!el.closest('[data-md-component="palette"]'),
                    search: !!el.closest('[data-md-component="search"]'),
                    cta: el.matches('.rdt-hero__actions a'),
                    copy: el.matches('.rdt-home .md-code__button'),
                    tab: el.matches('.rdt-install .tabbed-set > input'),
                    card: el.matches('.rdt-home .grid.cards a'),
                    ring,
                  };
                }"""
            )
        )
        if seen[-1]["key"] == seen[0]["key"] and len(seen) > 1:
            break
    keys = [entry["key"] for entry in seen]

    def indexes(flag: str) -> list[int]:
        return [i for i, entry in enumerate(seen) if entry[flag]]

    # Skip link first, then the theme's palette toggle and search, then the calls to action.
    order = [indexes(flag)[:1] for flag in ("skip", "palette", "search", "cta")]
    assert all(order), (order, keys)
    assert [i[0] for i in order] == sorted(i[0] for i in order), keys
    assert order[0] == [0], keys[:5]
    ctas = indexes("cta")
    assert len(ctas) == page.locator(".rdt-hero__actions a").count()
    # Every visible copy button and card link is reached, after the calls to action.
    copies = indexes("copy")
    assert len(copies) == page.locator(".rdt-home .md-code__button:visible").count() > 0, keys
    assert len(indexes("card")) == page.locator(".rdt-home .grid.cards a").count(), keys
    assert min(copies) > ctas[-1], keys
    if present(page, ".rdt-install .tabbed-set"):
        assert indexes("tab") and indexes("tab")[0] > ctas[-1], keys
    # Focus leaves the homepage content again: no trap.
    assert any(not entry["home"] for entry in seen[ctas[-1] + 1 :]), keys
    missing = [entry["key"] for entry in seen if entry["home"] and not entry["ring"]]
    assert not missing, missing


def test_arrow_keys_switch_install_tabs(browser: Browser, served: dict[str, str]) -> None:
    page = open_page(browser, served["cli"])
    page.locator(".rdt-install .tabbed-set > input").first.focus()
    page.keyboard.press("ArrowRight")
    assert page.locator(".rdt-install .tabbed-set > input").nth(1).is_checked()
    assert page.locator(".rdt-install .tabbed-block").nth(1).is_visible()


@pytest.mark.parametrize("name", LANDING_EXAMPLES)
def test_reduced_motion_stops_the_animation(browser: Browser, served: dict[str, str], name: str) -> None:
    page = open_page(browser, served[name], reduced_motion="reduce")
    hero = page.locator(".rdt-hero").evaluate("(el) => getComputedStyle(el).animationName")
    assert hero == "none"
    durations = page.locator(".rdt-home .grid.cards li").first.evaluate("(el) => getComputedStyle(el).transitionDuration")
    assert all(float(value.strip().rstrip("s")) <= 0.01 for value in durations.split(","))


@pytest.mark.parametrize("name", LANDING_EXAMPLES)
def test_works_without_javascript(browser: Browser, served: dict[str, str], name: str) -> None:
    page = open_page(browser, served[name], java_script_enabled=False)
    for selector in (".rdt-hero__name", ".rdt-hero__tagline", ".rdt-hero__actions a", ".rdt-home .grid.cards li"):
        assert page.locator(selector).first.is_visible(), selector
    labels = page.locator(".rdt-install .tabbed-labels > label")
    for index in range(labels.count()):
        labels.nth(index).click()
        assert page.locator(".rdt-install .tabbed-block").nth(index).is_visible()


@pytest.mark.parametrize("scheme", SCHEMES)
@pytest.mark.parametrize("name", LANDING_EXAMPLES)
def test_phone_width_has_no_overflow(browser: Browser, served: dict[str, str], name: str, scheme: str) -> None:
    page = open_page(browser, served[name], viewport={"width": 390, "height": 844}, color_scheme=scheme)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page.locator("h1").count() == 1
    assert page.locator("img:not([alt])").count() == 0
