"""docstool's command-line skeleton: the behaviour every command builds on."""

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

from conftest import DOCSTOOL, load_module, run_script

docstool = load_module("docstool", DOCSTOOL)


def test_version_runs_in_isolated_mode() -> None:
    result = run_script(DOCSTOOL, "--version")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"docstool {docstool.__version__}"


def test_no_command_is_a_usage_error() -> None:
    result = run_script(DOCSTOOL)
    assert result.returncode == docstool.EXIT_USAGE == 2
    assert "no command given" in result.stderr


def test_an_unknown_command_is_a_usage_error() -> None:
    assert run_script(DOCSTOOL, "no-such-command").returncode == 2


def test_exit_codes_are_the_documented_ones() -> None:
    assert (docstool.EXIT_OK, docstool.EXIT_FINDINGS, docstool.EXIT_USAGE, docstool.EXIT_INCOMPLETE) == (0, 1, 2, 3)
