"""docstool contrast: a brand colour on both schemes and as a button fill."""

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

from pathlib import Path

import pytest
from conftest import docstool_code, docstool_json


@pytest.mark.parametrize(("colour", "fails"), [("#4051b5", 2), ("#26c6da", 2), ("#000000", 2), ("#3f51b5", 2), ("#1565c0", 1)])
def test_contrast_pairs(colour: str, fails: int) -> None:
    code, report = docstool_json(Path("."), "contrast", colour)
    assert len(report["findings"]) == fails
    assert code == (1 if fails else 0)


def test_indigo_matches_the_p0_measurement() -> None:
    _, report = docstool_json(Path("."), "contrast", "#4051b5")
    ratios = [row["ratio"] for row in report["data"]["pairs"]]
    assert ratios == [6.86, 2.85, 6.86, 2.85]
    slate = next(f for f in report["findings"] if "slate page" in f["message"] and "text" in f["message"])
    assert "data-md-color-scheme" in slate["suggestion"]


def test_a_slate_override_is_checked_on_slate() -> None:
    code, _ = docstool_json(Path("."), "contrast", "#4051b5", "--slate", "#8c9eff")
    assert code == 0


def test_bad_colour_is_a_usage_error() -> None:
    assert docstool_code(Path("."), "contrast", "blue") == 2
