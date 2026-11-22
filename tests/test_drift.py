"""docstool drift: commands, flags, env vars and paths the docs name, against the code."""

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
from typing import Any

from conftest import docstool_code, docstool_json, git, make_repo


def found(report: dict[str, Any]) -> set[tuple[str, str, int]]:
    return {(f["check"], f["file"], f["line"]) for f in report["findings"]}


def test_rust_cli_planted_drift_and_negatives(tmp_path: Path) -> None:
    repo = make_repo("rust-cli", tmp_path)
    code, report = docstool_json(repo, "drift")
    assert code == 1
    assert found(report) == {
        ("make-target-missing", "docs/usage.md", 3),
        ("flag-unknown", "docs/usage.md", 5),
        ("env-undocumented", "src/main.rs", 13),
    }
    # negatives: the included .mk target, RCLI_CONFIG read through clap env=, RUST_LOG, ./.github and ~~~ fences
    assert "build" in report["data"]["make_targets"]
    assert "RCLI_CONFIG" in report["data"]["env_read"]
    states = {r["input"]: r["state"] for r in report["coverage"]}
    assert states["make"] == states["flags"] == "complete"


def test_go_service_flags_env_make_and_scripts(tmp_path: Path) -> None:
    repo = make_repo("go-service", tmp_path)
    _, report = docstool_json(repo, "drift")
    assert found(report) == {
        ("flag-unknown", "docs/usage.md", 5),
        ("make-target-missing", "docs/usage.md", 7),
        ("env-unknown", "docs/usage.md", 13),
        ("env-undocumented", "cmd/svc/main.go", 21),
        ("path-missing", "docs/usage.md", 10),
    }
    assert set(report["data"]["flags"]) >= {"--listen", "--verbose"}
    assert report["data"]["binaries"] == {"svc": "go"}


def test_base_reports_removed_and_added_tokens(tmp_path: Path) -> None:
    repo = make_repo("go-service", tmp_path)
    main = repo / "cmd" / "svc" / "main.go"
    main.write_text(main.read_text(encoding="utf-8").replace('"listen"', '"addr"'), encoding="utf-8")
    git(repo, "commit", "-q", "-am", "rename the flag")
    _, report = docstool_json(repo, "drift", "--base", "HEAD~1")
    removed = {(f["file"], f["line"]) for f in report["findings"] if f["check"] == "removed-still-documented"}
    assert ("docs/usage.md", 4) in removed
    assert ("docs/reference.md", 6) in removed
    added = {f["message"].split(" ")[0] for f in report["findings"] if f["check"] == "added-undocumented"}
    assert added == {"--addr"}
    assert docstool_code(repo, "drift", "--base", "no-such-ref") == 2


def test_leads_status_claims_counts_and_staleness(tmp_path: Path) -> None:
    repo = make_repo("go-service", tmp_path)
    git(repo, "tag", "v1.0.0")
    _, report = docstool_json(repo, "drift", "--leads")
    leads = {(f["check"], f["line"]) for f in report["findings"] if f["check"] in ("status-claim", "count-lead")}
    # the claim "available\nsince v2.0" wraps onto the next line; the block joins it
    assert leads == {("count-lead", 15), ("status-claim", 15)}


def test_staleness_is_per_doc_and_deterministic(tmp_path: Path) -> None:
    repo = make_repo("rust-cli", tmp_path)
    (repo / "docs" / "usage.md").write_text((repo / "docs" / "usage.md").read_text(encoding="utf-8") + "\nSee `src/main.rs`.\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "doc")
    env = {"GIT_COMMITTER_DATE": "2027-01-01T00:00:00Z", "GIT_AUTHOR_DATE": "2027-01-01T00:00:00Z"}
    (repo / "src" / "main.rs").write_text((repo / "src" / "main.rs").read_text(encoding="utf-8") + "// later\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "code", env=env)
    runs = [docstool_json(repo, "drift")[1]["data"]["stale"] for _ in range(2)]
    assert runs[0] == runs[1]
    assert [s["doc"] for s in runs[0]] == ["docs/usage.md"]
    assert runs[0][0]["reference"] == "src/main.rs"


def test_make_includes_dash_c_and_dot_slash_paths(tmp_path: Path) -> None:
    repo = make_repo("rust-cli", tmp_path)
    (repo / "sub").mkdir()
    (repo / "sub" / "GNUmakefile").write_text("RULES := sub/extra.mk\n-include missing.mk\ninclude extra.mk\n", encoding="utf-8")
    (repo / "sub" / "extra.mk").write_text("deploy-sub:\n\techo\n", encoding="utf-8")
    (repo / ".github" / "check.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo / "docs" / "more.md").write_text(
        "# More\n\n```sh\nmake -C sub deploy-sub\nmake -C sub nope\nmake -j4 VERBOSE=1 test\n./.github/check.sh\n./.github/missing.sh\n```\n",
        encoding="utf-8",
    )
    _, report = docstool_json(repo, "drift")
    more = {(f["check"], f["line"]) for f in report["findings"] if f["file"] == "docs/more.md"}
    assert more == {("make-target-missing", 5), ("path-missing", 8)}


def test_env_readers_in_each_language(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    sources = {
        "a.rs": 'std::env::var_os("RS_ONE"); option_env!("RS_TWO");',
        "b.go": 'os.LookupEnv("GO_ONE")',
        "c.py": 'os.environ["PY_ONE"]; os.getenv("PY_TWO")',
        "d.ts": "process.env.JS_ONE; process.env['JS_TWO']",
        "run.sh": 'echo "$SH_ONE"',
        "compose.yaml": "services:\n  a:\n    environment:\n      - COMPOSE_ONE=1\n",
    }
    for name, text in sources.items():
        (repo / name).write_text(text + "\n", encoding="utf-8")
    names = ["RS_ONE", "RS_TWO", "GO_ONE", "PY_ONE", "PY_TWO", "JS_ONE", "JS_TWO", "SH_ONE", "COMPOSE_ONE", "NOT_READ"]
    (repo / "docs" / "env.md").write_text("# Env\n\nEnvironment variables: " + ", ".join(f"`{n}`" for n in names) + ".\n", encoding="utf-8")
    _, report = docstool_json(repo, "drift")
    unknown = {f["message"].split(" ")[0] for f in report["findings"] if f["check"] == "env-unknown"}
    assert unknown == {"NOT_READ"}


def test_root_relative_links_resolve_from_the_repository_root(tmp_path: Path) -> None:
    # docs_drift.py joined /docs/x.md as an absolute filesystem path; check resolves it in the repo.
    repo = make_repo("clean", tmp_path)
    readme = repo / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\n[a](/docs/guide.md#install) [b](/docs/nope.md) [c](/docs/guide.md#nope)\n", encoding="utf-8"
    )
    _, report = docstool_json(repo, "check")
    got = {(f["check"], f["message"].split(":")[0]) for f in report["findings"]}
    assert got == {("broken-link", "/docs/nope.md"), ("broken-anchor", "/docs/guide.md#nope")}
