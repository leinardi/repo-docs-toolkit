"""skills/zensical-site/scripts/screenshots.py: the manual review's screenshots, in a real browser."""

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
import shutil
import struct
import subprocess
import sys
import threading
import zlib
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest
from conftest import ZENSICAL_SITE, require_or_skip

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - the a11y job installs it
    sync_playwright = None

pytestmark = pytest.mark.a11y

SCRIPT = ZENSICAL_SITE / "scripts" / "screenshots.py"
NAMES = sorted(f"home-{scheme}-{width}.png" for scheme in ("light", "dark") for width in (1440, 768, 390))


@pytest.fixture(scope="module", autouse=True)
def _playwright() -> None:
    require_or_skip(sync_playwright is not None, "playwright", "DOCSTOOL_REQUIRE_A11Y")


def screenshots(built: Path, out: Path, *args: str) -> subprocess.CompletedProcess[str]:
    browser = ["--browser", os.environ["A11Y_CHROME"]] if os.environ.get("A11Y_CHROME") and "--browser" not in args else []
    command = [sys.executable, "-I", str(SCRIPT), str(built), str(out), *args, *browser]
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=300)


def png(path: Path) -> tuple[int, int, list[bytes]]:
    """Width, height and the unfiltered rows of an 8-bit RGB or RGBA PNG (standard library only)."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    pos, idat, header = 8, b"", b""
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind, body = data[pos + 4 : pos + 8], data[pos + 8 : pos + 8 + length]
        if kind == b"IHDR":
            header = body
        elif kind == b"IDAT":
            idat += body
        pos += 12 + length
    width, height, depth, colour = struct.unpack(">IIBB", header[:10])
    assert depth == 8 and colour in (2, 6), (depth, colour)
    bpp = 3 if colour == 2 else 4
    raw, stride = zlib.decompress(idat), width * bpp
    rows: list[bytes] = []
    prior = bytearray(stride)
    for y in range(height):
        kind, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1 : (y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = prior[i], prior[i - bpp] if i >= bpp else 0
            if kind == 1:
                line[i] = (line[i] + a) & 0xFF
            elif kind == 2:
                line[i] = (line[i] + b) & 0xFF
            elif kind == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif kind == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
        rows.append(bytes(line))
        prior = line
    return width, height, rows


def luma(rows: list[bytes], x: int, y: int, bpp: int = 3) -> float:
    r, g, b = rows[y][x * bpp : x * bpp + 3]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


@pytest.fixture(scope="module")
def shot(landing_sites: dict[str, Path], tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("shots") / "out"
    result = screenshots(landing_sites["cli"], out, "--prefix", "/repo/")
    assert result.returncode == 0, result.stdout + result.stderr
    return out


def test_six_full_page_screenshots_at_their_widths(shot: Path) -> None:
    assert sorted(p.name for p in shot.iterdir()) == NAMES
    for name in NAMES:
        width, height, _ = png(shot / name)
        assert width == int(name.rsplit("-", 1)[1].removesuffix(".png")), name
        assert height >= 900, name


def test_the_site_loads_with_its_stylesheets_under_the_prefix(shot: Path) -> None:
    # Without the theme's stylesheet both schemes would be a white page; the dark scheme's body
    # is dark only when the CSS served under /repo/ loaded.
    for width in (1440, 390):
        dark_width, height, dark = png(shot / f"home-dark-{width}.png")
        _, _, light = png(shot / f"home-light-{width}.png")
        bpp = len(dark[0]) // dark_width
        y = height - 5
        assert luma(dark, 2, y, bpp) < 80, width
        assert luma(light, 2, y, len(light[0]) // dark_width) > 200, width


def with_head(site: Path, dest: Path, extra: str) -> Path:
    shutil.copytree(site, dest)
    index = dest / "index.html"
    index.write_text(index.read_text(encoding="utf-8").replace("</head>", extra + "</head>", 1), encoding="utf-8")
    return dest


def test_horizontal_overflow_exits_1_and_names_the_width_and_scheme(landing_sites: dict[str, Path], tmp_path: Path) -> None:
    site = with_head(landing_sites["cli"], tmp_path / "site", "<style>.rdt-home{min-width:3000px}</style>")
    result = screenshots(site, tmp_path / "out")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "390 px, light scheme" in result.stderr, result.stderr
    assert "1440 px, dark scheme" in result.stderr, result.stderr


def test_an_output_inside_the_built_site_is_refused(landing_sites: dict[str, Path], tmp_path: Path) -> None:
    site = tmp_path / "site"
    shutil.copytree(landing_sites["cli"], site)
    before = sorted(p.relative_to(site) for p in site.rglob("*"))
    for out in (site, site / "shots"):
        result = screenshots(site, out)
        assert result.returncode == 2, result.stdout + result.stderr
        assert "inside" in result.stderr
    assert sorted(p.relative_to(site) for p in site.rglob("*")) == before


def test_a_browser_that_cannot_start_exits_3_not_1(landing_sites: dict[str, Path], tmp_path: Path) -> None:
    # Exit 1 means an overflow; a missing Chromium or a wrong --browser must not read as one.
    result = screenshots(landing_sites["cli"], tmp_path / "out", "--browser", str(tmp_path / "no-such-chrome"))
    assert result.returncode == 3, result.stdout + result.stderr
    assert "playwright install chromium" in result.stderr, result.stderr
    assert "--browser" in result.stderr, result.stderr


class _Counter(BaseHTTPRequestHandler):
    hits: ClassVar[list[str]] = []

    def do_GET(self) -> None:
        self.hits.append(self.path)
        self.send_response(204)
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        pass


class _QuietFiles(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture
def other_origin() -> Iterator[tuple[int, list[str]]]:
    """A second local server, on another port, that counts every request it gets."""
    hits: list[str] = []
    handler = type("Counter", (_Counter,), {"hits": hits})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], hits
    server.shutdown()
    server.server_close()


def test_the_browser_loads_nothing_from_another_origin(landing_sites: dict[str, Path], tmp_path: Path, other_origin: tuple[int, list[str]]) -> None:
    port, hits = other_origin
    other = f"127.0.0.1:{port}"
    probe = (
        f"<script>fetch('http://{other}/fetch').catch(() => 0);"
        f"new Image().src = 'http://{other}/img';"
        f"try {{ new WebSocket('ws://{other}/ws'); }} catch (e) {{}}</script>"
    )
    site = with_head(landing_sites["cli"], tmp_path / "site", probe)
    # The probe does reach the other server from an unrestricted browser, so a zero below means
    # the script blocked it.
    handler = functools.partial(_QuietFiles, directory=str(site))
    plain = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=plain.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.environ.get("A11Y_CHROME") or None)
            page = browser.new_page()
            page.route("**/*", lambda route: route.continue_() if "127.0.0.1" in route.request.url else route.abort())
            page.goto(f"http://127.0.0.1:{plain.server_address[1]}/")
            page.wait_for_timeout(1000)
            browser.close()
    finally:
        plain.shutdown()
        plain.server_close()
    assert {"/fetch", "/img", "/ws"} <= set(hits), hits
    hits.clear()

    result = screenshots(site, tmp_path / "out")
    assert result.returncode == 0, result.stdout + result.stderr
    assert hits == [], hits
