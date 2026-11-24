"""Full-page screenshots of a built site's homepage, for the landing page's manual review.

Serves the built site on 127.0.0.1 under a path prefix (the path of `site_url`), opens the homepage
in Chromium at 1440, 768 and 390 pixels wide, in the light and the dark scheme, and writes six PNGs
named home-<scheme>-<width>.png into the output directory. It exits 1 when the page is wider than
the window at any width, naming the width and the scheme.

The browser is told to load nothing but the served site (service workers blocked, every request
and WebSocket to another origin refused); this is not a network sandbox.

Needs Playwright for Python and a Chromium (`playwright install chromium`, or --browser):

    uv run --no-project --with playwright==1.65.2 python3 -I screenshots.py <built> <out> [--prefix /repo/]

Exit codes: 0 the screenshots are written, 1 the page overflows horizontally, 2 a usage error,
3 the browser failed: it is not installed, --browser is wrong, or the page timed out.
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
import functools
import re
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import Route, WebSocketRoute, sync_playwright
except ImportError:  # reported by shoot(), with the command that provides it
    sync_playwright = None
    PlaywrightError = RuntimeError

WIDTHS = (1440, 768, 390)
SCHEMES = ("light", "dark")
HEIGHT = 900


class UsageError(Exception):
    pass


def normalise_prefix(prefix: str) -> str:
    """'/repo', 'repo/' and '/repo/' all become '/repo/'; '' and '/' become '/'."""
    parts = [part for part in prefix.split("/") if part]
    if any(part in (".", "..") for part in parts):
        raise UsageError(f"--prefix {prefix!r} must be a plain URL path")
    return "/" + "".join(part + "/" for part in parts)


class _Handler(SimpleHTTPRequestHandler):
    """Serves the built site under the prefix; every other path is a 404."""

    prefix = "/"

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _route(self) -> bool:
        path = urlsplit(self.path).path
        if self.prefix != "/" and path == self.prefix.rstrip("/"):
            self.send_response(301)
            self.send_header("Location", self.prefix)
            self.end_headers()
            return False
        if not path.startswith(self.prefix):
            self.send_error(404)
            return False
        return True

    def do_GET(self) -> None:
        if self._route():
            super().do_GET()

    def do_HEAD(self) -> None:
        if self._route():
            super().do_HEAD()

    def translate_path(self, path: str) -> str:
        return super().translate_path("/" + path[len(self.prefix) :])


def serve(built: Path, prefix: str) -> ThreadingHTTPServer:
    handler = type("Handler", (_Handler,), {"prefix": prefix})
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(handler, directory=str(built)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def same_origin(url: str, scheme: str, port: int) -> bool:
    """True only for the exact origin: this scheme, host 127.0.0.1, this port."""
    try:
        parts = urlsplit(url)
        return parts.scheme == scheme and parts.hostname == "127.0.0.1" and parts.port == port
    except ValueError:
        return False


def check_paths(built: Path, out: Path) -> None:
    if not (built / "index.html").is_file():
        raise UsageError(f"{built} has no index.html: pass the directory a site build wrote")
    built_real, out_real = built.resolve(), out.resolve()
    if out_real == built_real or out_real.is_relative_to(built_real):
        # site-build stamps its output with a hash of every file; a file written there breaks it.
        raise UsageError(f"{out} is inside {built}: write the screenshots outside the built site")
    if out.exists() and not out.is_dir():
        raise UsageError(f"{out} exists and is not a directory")


def shoot(built: Path, out: Path, prefix: str, browser_path: str | None) -> list[str]:
    """Write the six screenshots; return one line per width and scheme that overflows."""
    if sync_playwright is None:
        raise UsageError(
            "Playwright for Python is not installed: run this script through uv run --no-project --with playwright==1.65.2 python3 -I ..."
        )

    server = serve(built, prefix)
    port = server.server_address[1]
    home = f"http://127.0.0.1:{port}{prefix}"

    def on_request(route: Route) -> None:
        if same_origin(route.request.url, "http", port):
            route.continue_()
        else:
            route.abort()

    def on_websocket(ws: WebSocketRoute) -> None:
        if same_origin(ws.url, "ws", port):
            ws.connect_to_server()
        else:
            ws.close()

    overflows = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=browser_path)
            try:
                for scheme in SCHEMES:
                    for width in WIDTHS:
                        context = browser.new_context(
                            viewport={"width": width, "height": HEIGHT},
                            color_scheme=scheme,
                            service_workers="block",
                        )
                        try:
                            context.route("**/*", on_request)
                            context.route_web_socket(re.compile(".*"), on_websocket)
                            page = context.new_page()
                            response = page.goto(home, wait_until="load")
                            if response is None or not response.ok:
                                status = response.status if response else "no response"
                                raise UsageError(f"the homepage {prefix} did not load ({status}): check --prefix")
                            page.evaluate("document.fonts.ready.then(() => true)")
                            target = out / f"home-{scheme}-{width}.png"
                            page.screenshot(path=str(target), full_page=True, animations="disabled")
                            print(target)
                            scroll, inner = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
                            if scroll > inner:
                                overflows.append(f"{width} px, {scheme} scheme: the page is {scroll} px wide in a {inner} px window")
                        finally:
                            context.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
    return overflows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("built", type=Path, help="the built site (a site-build output or a zensical build directory)")
    parser.add_argument("out", type=Path, help="where the PNGs go; must be outside the built site")
    parser.add_argument("--prefix", default="/", help="the URL path the site is served under: the path of site_url (default /)")
    parser.add_argument("--browser", metavar="PATH", help="a Chromium or Chrome to use instead of Playwright's download")
    args = parser.parse_args(argv)
    try:
        prefix = normalise_prefix(args.prefix)
        check_paths(args.built, args.out)
        args.out.mkdir(parents=True, exist_ok=True)
        overflows = shoot(args.built, args.out, prefix, args.browser)
    except UsageError as error:
        print(f"screenshots: {error}", file=sys.stderr)
        return 2
    except PlaywrightError as error:
        # Not an overflow: the browser never produced the screenshots.
        first = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
        print(f"screenshots: the browser failed: {first}", file=sys.stderr)
        print(
            "screenshots: install Playwright's Chromium once (uv run --no-project --with playwright==1.65.2"
            " playwright install chromium), or pass --browser with the path of a Chrome or Chromium",
            file=sys.stderr,
        )
        return 3
    for line in overflows:
        print(f"screenshots: horizontal overflow at {line}", file=sys.stderr)
    return 1 if overflows else 0


if __name__ == "__main__":
    sys.exit(main())
