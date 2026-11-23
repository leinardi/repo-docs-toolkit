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

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import DOCSTOOL, docstool_code, docstool_json, git, make_repo


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


def test_env_read_through_named_constants_and_unknown_names(tmp_path: Path) -> None:
    # monmux reads its env vars as os.Getenv(envNoExec); a literal-only scan called them unread
    repo = make_repo("clean", tmp_path)
    (repo / "env.go").write_text('package main\n\nconst envNoExec = "APP_NO_EXEC"\n\nfunc a() { _ = os.Getenv(envNoExec) }\n', encoding="utf-8")
    (repo / "docs" / "env.md").write_text("# Env\n\nEnvironment variable `APP_NO_EXEC` disables writes.\n", encoding="utf-8")
    _, report = docstool_json(repo, "drift")
    assert "APP_NO_EXEC" in report["data"]["env_read"]
    assert "env-unknown" not in {f["check"] for f in report["findings"]}
    assert {r["input"]: r["state"] for r in report["coverage"]}["env"] == "complete"
    (repo / "dyn.go").write_text("package main\n\nfunc b(key string) { _ = os.Getenv(key) }\n", encoding="utf-8")
    code, report = docstool_json(repo, "drift")
    assert code == 3
    env = next(r for r in report["coverage"] if r["input"] == "env")
    assert env["state"] == "partial"
    assert "dyn.go: key" in env["reason"]


def test_path_leads_skip_what_is_not_a_repository_path(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "main.go").write_text("package main\n", encoding="utf-8")
    (repo / "docs" / "paths.md").write_text(
        "# Paths\n\n`main.go` `github.com/x/y` `linux/amd64` `GSM/0x7707` `src/gone.go` `owner/repo` `missing.toml` `olddir/tool.sh`\n",
        encoding="utf-8",
    )
    _, report = docstool_json(repo, "drift", "--paths")
    got = {(f["message"].split(":")[0], f["severity"], f["confidence"]) for f in report["findings"] if f["check"] == "path-missing"}
    assert got == {
        ("src/gone.go", "P2", "likely"),
        ("olddir/tool.sh", "P2", "likely"),
        ("owner/repo", "P3", "unverified"),
        ("missing.toml", "P3", "unverified"),
    }


def test_base_cites_the_flag_definition_and_does_not_double_count(tmp_path: Path) -> None:
    repo = make_repo("go-service", tmp_path)
    main = repo / "cmd" / "svc" / "main.go"
    main.write_text(main.read_text(encoding="utf-8").replace('"listen"', '"addr"'), encoding="utf-8")
    git(repo, "commit", "-q", "-am", "rename the flag")
    _, report = docstool_json(repo, "drift", "--base", "HEAD~1")
    added = next(f for f in report["findings"] if f["check"] == "added-undocumented")
    assert '"addr"' in main.read_text(encoding="utf-8").split("\n")[added["line"] - 1]
    on_line = [f["check"] for f in report["findings"] if (f["file"], f["line"]) == ("docs/usage.md", 4)]
    assert on_line.count("removed-still-documented") == 1
    assert "flag-unknown" not in on_line


@pytest.mark.parametrize(
    ("name", "source"),
    [
        ("concat.go", 'package main\n\nfunc a(p string) { _ = os.Getenv(p + "_TOKEN") }\n'),
        ("fmt.rs", 'fn a(p: &str) { let _ = std::env::var(format!("{}_TOKEN", p)); }\n'),
        ("fstr.py", 'import os\n\ndef a(p):\n    return os.environ.get(f"{p}_TOKEN")\n'),
        ("index.py", 'import os\n\ndef a(p):\n    return os.environ[p + "_X"]\n'),
        ("asstr.rs", "fn a(key: String) { let _ = std::env::var(key.as_str()); }\n"),
    ],
)
def test_env_reads_docstool_cannot_resolve_make_env_partial(tmp_path: Path, name: str, source: str) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / name).write_text(source, encoding="utf-8")
    code, report = docstool_json(repo, "drift")
    assert code == 3
    assert {r["input"]: r["state"] for r in report["coverage"]}["env"] == "partial"


def test_a_test_fixture_manifest_is_not_a_project_binary(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    fixture = repo / "tests" / "fixtures" / "demo"
    (fixture / "src").mkdir(parents=True)
    (fixture / "Cargo.toml").write_text('[package]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8")
    (fixture / "src" / "main.rs").write_text("fn main() {}\n", encoding="utf-8")
    code, report = docstool_json(repo, "drift")
    assert code == 0, report["coverage"]
    assert {r["input"]: r["state"] for r in report["coverage"]}["flags"] != "partial"
    # the same manifest at the root is the project's binary, and a binary with no flags found is partial
    for rel in ("Cargo.toml", "src/main.rs"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_bytes((fixture / rel).read_bytes())
    code, report = docstool_json(repo, "drift")
    assert code == 3
    assert {r["input"]: r["state"] for r in report["coverage"]}["flags"] == "partial"


def test_a_constant_in_another_file_does_not_resolve_a_parameter(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    (repo / "other.py").write_text('key = "HOME"\n', encoding="utf-8")
    (repo / "reader.py").write_text("import os\n\ndef a(key):\n    return os.getenv(key)\n", encoding="utf-8")
    code, report = docstool_json(repo, "drift")
    assert code == 3
    assert "HOME" not in report["data"]["env_read"]
    # a module-level constant in the same file, and a Go constant of another package, do resolve
    (repo / "reader.py").write_text('import os\n\nTOKEN = "APP_TOKEN"\n\ndef a():\n    return os.getenv(TOKEN)\n', encoding="utf-8")
    (repo / "other.py").unlink()
    (repo / "config").mkdir()
    (repo / "config" / "env.go").write_text('package config\n\nconst (\n\tEnvMode = "APP_MODE"\n)\n', encoding="utf-8")
    (repo / "main.go").write_text("package main\n\nfunc a() { _ = os.Getenv(config.EnvMode) }\n", encoding="utf-8")
    _, report = docstool_json(repo, "drift")
    assert {"APP_TOKEN", "APP_MODE"} <= set(report["data"]["env_read"])
    assert {r["input"]: r["state"] for r in report["coverage"]}["env"] == "complete"


def test_link_test_census(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path)
    tests = repo / "tests"
    tests.mkdir()
    (tests / "test_docs.py").write_text('def test_no_broken_links():\n    open("README.md")\n', encoding="utf-8")
    (tests / "test_headers.py").write_text('# the regex anchors at the start\ndef test_header():\n    open("x.md")\n', encoding="utf-8")
    (tests / "test_root.py").write_text('import os\ndef test_root():\n    os.readlink("a.md")\n', encoding="utf-8")
    _, report = docstool_json(repo, "inventory")
    assert report["data"]["doc_tooling"]["link_tests"] == ["tests/test_docs.py"]


def test_artifact_paths_are_relative_to_root(tmp_path: Path) -> None:
    repo = make_repo("clean", tmp_path / "repo")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    args = ["--root", str(repo), "--format", "json"]
    for command in (
        ["inventory", "--blocks", "docs/internal/restructure/blocks.json"],
        ["check", "--save-baseline", "docs/internal/restructure/urls.json"],
    ):
        result = subprocess.run([sys.executable, "-I", str(DOCSTOOL), *command, *args], cwd=elsewhere, capture_output=True, text=True, check=False)
        assert result.returncode in (0, 1), result.stderr
    assert (repo / "docs/internal/restructure/blocks.json").is_file()
    assert (repo / "docs/internal/restructure/urls.json").is_file()
    assert not any(elsewhere.iterdir())


def test_make_with_no_makefile_anywhere(tmp_path: Path) -> None:
    repo = tmp_path / "nomake"
    repo.mkdir()
    (repo / "README.md").write_text("# X\n\n```sh\nmake release\n```\n\nThen run `make docs`.\n", encoding="utf-8")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "x")
    _, report = docstool_json(repo, "drift")
    got = {(f["check"], f["severity"], f["line"]) for f in report["findings"]}
    # a block is a command to run here; inline code is only a lead (it may be another project's)
    assert {("make-missing", "P2", 4), ("make-missing", "P3", 7)} <= got


def test_env_set_in_a_recipe_or_read_through_a_prefix_mapping(tmp_path: Path) -> None:
    repo = make_repo("go-service", tmp_path)
    (repo / "internal" / "loader").mkdir(parents=True)
    (repo / "internal" / "loader" / "config.go").write_text(
        'package config\n\nimport "github.com/knadh/koanf/providers/env"\n\nconst envPrefix = "SVC_"\n\nvar provider = env.Provider(envPrefix, ".", nil)\n',
        encoding="utf-8",
    )
    (repo / "run.mk").write_text("run:\n\tSVC_LOG__LEVEL=debug ./svc\n", encoding="utf-8")
    usage = repo / "docs" / "usage.md"
    lines = usage.read_text(encoding="utf-8").splitlines()
    lines += ["", "Set the environment variable `SVC_LOG__LEVEL=info` or `SVC_AUTH__MODE=none`, never `OTHER_FLAG=1`."]
    usage.write_text("\n".join(lines) + "\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "config loader")
    _, report = docstool_json(repo, "drift")
    unknown = {f["message"].split(" ", 1)[0]: (f["severity"], f["confidence"]) for f in report["findings"] if f["check"] == "env-unknown"}
    # set by a recipe: a known variable; under the loader's prefix: unverified, not "likely" wrong
    assert "SVC_LOG__LEVEL" not in unknown
    assert unknown["SVC_AUTH__MODE"] == ("P3", "unverified")
    assert unknown["OTHER_FLAG"] == ("P2", "likely")
    env_row = next(r for r in report["coverage"] if r["input"] == "env")
    assert "SVC_* (internal/loader/config.go)" in env_row["reason"]


@pytest.mark.parametrize(
    ("source", "name", "line", "prefix"),
    [
        ("internal/a/conf.go", "conf.go", 'viper.SetEnvPrefix("svc")', "SVC_"),
        ("internal/a/conf.go", "conf.go", 'envconfig.Process("svc", &cfg)', "SVC_"),
        ("internal/a/conf.go", "conf.go", 'k.Load(env.Provider("SVC_", ".", nil), nil) // koanf/providers/env', "SVC_"),
        ("src/conf.rs", "conf.rs", 'Environment::with_prefix("SVC")', "SVC_"),
        ("src/conf.rs", "conf.rs", 'Env::prefixed("SVC_")', "SVC_"),
        ("app/conf.py", "conf.py", 'model_config = SettingsConfigDict(env_prefix="SVC_")', "SVC_"),
    ],
)
def test_each_prefix_loader(tmp_path: Path, source: str, name: str, line: str, prefix: str) -> None:
    repo = make_repo("go-service", tmp_path)
    path = repo / source
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(line + "\n", encoding="utf-8")
    usage = repo / "docs" / "usage.md"
    usage.write_text(usage.read_text(encoding="utf-8") + "\nSet the environment variable `SVC_AUTH__MODE=none`.\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "loader")
    _, report = docstool_json(repo, "drift")
    unknown = {f["message"].split(" ", 1)[0]: f["severity"] for f in report["findings"] if f["check"] == "env-unknown"}
    assert unknown["SVC_AUTH__MODE"] == "P3"
    env_row = next(r for r in report["coverage"] if r["input"] == "env")
    assert f"{prefix}* ({source})" in env_row["reason"]


def test_a_commented_assignment_does_not_make_a_variable_known(tmp_path: Path) -> None:
    repo = make_repo("go-service", tmp_path)
    (repo / "run.mk").write_text("# OLD_VAR=1 was removed\nrun:\n\t./svc\n", encoding="utf-8")
    usage = repo / "docs" / "usage.md"
    usage.write_text(usage.read_text(encoding="utf-8") + "\nSet the environment variable `OLD_VAR=1`.\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "comment")
    _, report = docstool_json(repo, "drift")
    assert any(f["check"] == "env-unknown" and f["message"].startswith("OLD_VAR ") and f["severity"] == "P2" for f in report["findings"])


def env_repo(tmp_path: Path, sources: dict[str, str], doc: str = "Set `FOO_MODE=1` and `FOO_PIN=2`.\n") -> Path:
    repo = make_repo("clean", tmp_path)
    for rel, text in {"docs/env.md": f"# Env\n\n{doc}", **sources}.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "env")
    return repo


def env_severity(report: dict[str, Any], name: str) -> str | None:
    return next((f["severity"] for f in report["findings"] if f["check"] == "env-unknown" and f["message"].startswith(name + " ")), None)


LOOKUP = "impl Fn(&str) -> Option<String>"
ENV_CLOSURE = "|key| std::env::var(key).ok()"


def test_env_read_through_a_traced_callback_is_a_lead(tmp_path: Path) -> None:
    repo = env_repo(
        tmp_path,
        {
            "src/main.rs": f"fn main() {{ run_with(vec![], {ENV_CLOSURE}, 1); }}\n",
            "src/run.rs": f"pub fn run_with(args: Vec<String>, getenv: {LOOKUP}, stop: u8) {{ docker::settings(&getenv); }}\n",
            "src/docker.rs": f'const PIN: &str = "FOO_PIN";\npub fn settings(getenv: {LOOKUP}) {{ getenv("FOO_MODE"); getenv(PIN); }}\n',
        },
    )
    _, report = docstool_json(repo, "drift")
    assert env_severity(report, "FOO_MODE") == "P3"
    assert env_severity(report, "FOO_PIN") == "P3"


def test_env_read_through_a_forwarding_function_is_a_lead(tmp_path: Path) -> None:
    repo = env_repo(
        tmp_path,
        {
            "src/main.rs": 'const PIN: &str = "FOO_PIN";\nfn read(key: &str) -> Option<String> { std::env::var(key).ok() }\nfn main() { read("FOO_MODE"); read(PIN); }\n'
        },
    )
    _, report = docstool_json(repo, "drift")
    assert env_severity(report, "FOO_MODE") == "P3"
    assert env_severity(report, "FOO_PIN") == "P3"


@pytest.mark.parametrize(
    "source",
    [
        # an unrelated callback of the same type, beside a real env closure
        f'fn main() {{ other({ENV_CLOSURE}); label(|k| names(k)); }}\nfn other(get: {LOOKUP}) {{}}\nfn label(get: {LOOKUP}) {{ get("FOO_MODE"); }}\n',
        # one call site passes something else
        f'fn main() {{ label({ENV_CLOSURE}); label(|k| names(k)); }}\nfn label(get: {LOOKUP}) {{ get("FOO_MODE"); }}\n',
        # the parameter is shadowed
        f'fn main() {{ label({ENV_CLOSURE}); }}\nfn label(get: {LOOKUP}) {{ let get = names; get("FOO_MODE"); }}\n',
        # the exact string as a metric label and a log field
        'fn main() { let v = labels.get("FOO_MODE"); counter("FOO_MODE"); log(field = "FOO_MODE"); let k = std::env::var(name); }\n',
        # a method of the same name as a forwarding function
        'fn read(key: &str) -> Option<String> { std::env::var(key).ok() }\nfn main() { labels.read("FOO_MODE"); }\n',
    ],
)
def test_env_lookalikes_stay_likely(tmp_path: Path, source: str) -> None:
    repo = env_repo(tmp_path, {"src/main.rs": source})
    _, report = docstool_json(repo, "drift")
    assert env_severity(report, "FOO_MODE") == "P2"


@pytest.mark.parametrize(
    "source",
    [
        f'fn main() {{ label({ENV_CLOSURE}); }}\nfn label(get: {LOOKUP}) {{ // get("FOO_MODE") was removed\n}}\n',
        f'fn main() {{ label({ENV_CLOSURE}); }}\nfn label(get: {LOOKUP}) {{ log("get(\\"FOO_MODE\\")"); }}\n',
        'fn read(key: &str) -> Option<String> { std::env::var(key).ok() }\n/// read("FOO_MODE")\nfn main() {}\n',
        'fn read(key: &str) -> Option<String> { std::env::var(key).ok() }\nfn main() {}\n#[cfg(test)]\nmod t { fn x() { read("FOO_MODE"); } }\n',
        'fn get(key: &str) -> Option<String> { std::env::var(key).ok() }\nfn main() { labels::get("FOO_MODE"); }\n',
        'use labels::get;\nfn main() { get("FOO_MODE"); }\nmod other { fn get(key: &str) -> Option<String> { std::env::var(key).ok() } }\n',
        f'fn main() {{ outer({ENV_CLOSURE}, |k| names(k)); }}\nfn outer(a: {LOOKUP}, b: {LOOKUP}) {{ inner(|k| b(k)); }}\nfn inner(get: {LOOKUP}) {{ get("FOO_MODE"); }}\n',
    ],
)
def test_comments_tests_and_foreign_calls_are_not_env_evidence(tmp_path: Path, source: str) -> None:
    repo = env_repo(tmp_path, {"src/main.rs": source})
    _, report = docstool_json(repo, "drift")
    assert env_severity(report, "FOO_MODE") == "P2"


@pytest.mark.parametrize(
    "source",
    [
        # a fake injected by an inline test does not break the production chain
        f'fn main() {{ label({ENV_CLOSURE}); }}\nfn label(get: {LOOKUP}) {{ get("FOO_MODE"); }}\n#[cfg(test)]\nmod tests {{ fn t() {{ label(|_| None); }} }}\n',
        # a closure forwarding to an env-backed parameter
        f'fn main() {{ outer({ENV_CLOSURE}); }}\nfn outer(a: {LOOKUP}) {{ inner(|k| a(k)); }}\nfn inner(get: {LOOKUP}) {{ get("FOO_MODE"); }}\n',
        # generic and where-bound callbacks
        f'fn main() {{ label({ENV_CLOSURE}); }}\nfn label<F: Fn(&str) -> Option<String>>(get: F) {{ get("FOO_MODE"); }}\n',
        f'fn main() {{ label({ENV_CLOSURE}); }}\nfn label<F>(get: F) where F: Fn(&str) -> Option<String> {{ get("FOO_MODE"); }}\n',
        # a path that names the function's module
        'mod cfgs;\nfn main() { main_helper::read("FOO_MODE"); }\n',
    ],
)
def test_real_env_chains_are_traced(tmp_path: Path, source: str) -> None:
    extra = {"src/main_helper.rs": "pub fn read(key: &str) -> Option<String> { std::env::var(key).ok() }\n"} if "main_helper" in source else {}
    repo = env_repo(tmp_path, {"src/main.rs": source, **extra})
    _, report = docstool_json(repo, "drift")
    assert env_severity(report, "FOO_MODE") == "P3"


def test_a_generic_function_counts_for_name_uniqueness(tmp_path: Path) -> None:
    source = (
        "fn read(key: &str) -> Option<String> { std::env::var(key).ok() }\n"
        "mod other { fn read<F: Fn(&str) -> Option<String>>(get: F) {} }\n"
        'fn main() { read("FOO_MODE"); }\n'
    )
    repo = env_repo(tmp_path, {"src/main.rs": source})
    _, report = docstool_json(repo, "drift")
    assert env_severity(report, "FOO_MODE") == "P2"


def test_an_unread_env_var_says_dependencies_were_not_scanned(tmp_path: Path) -> None:
    repo = env_repo(tmp_path, {})
    _, report = docstool_json(repo, "drift")
    finding = next(f for f in report["findings"] if f["message"].startswith("FOO_MODE "))
    assert finding["severity"] == "P2"
    assert "dependencies were not scanned" in finding["evidence"]


@pytest.mark.parametrize("line", ["FOO_MODE := app", "FOO_MODE ?= app", "FOO_MODE += app", "all:\n\t@echo $(FOO_MODE)"])
def test_make_variables_are_known(tmp_path: Path, line: str) -> None:
    repo = env_repo(tmp_path, {"Makefile": "include .mk/x.mk\n", ".mk/x.mk": f"{line}\n"})
    _, report = docstool_json(repo, "drift")
    assert env_severity(report, "FOO_MODE") is None


def test_a_lowercase_makefile_is_read(tmp_path: Path) -> None:
    repo = env_repo(tmp_path, {"makefile": "FOO_MODE := app\nall:\n\t@echo $(FOO_PIN)\n"})
    _, report = docstool_json(repo, "drift")
    assert env_severity(report, "FOO_MODE") is None
    assert env_severity(report, "FOO_PIN") is None


def test_a_commented_make_variable_is_not_known(tmp_path: Path) -> None:
    repo = env_repo(tmp_path, {"Makefile": "# FOO_MODE := app\n# $(FOO_MODE)\nall:\n\t@true\n"})
    _, report = docstool_json(repo, "drift")
    assert env_severity(report, "FOO_MODE") == "P2"


def test_partial_paths(tmp_path: Path) -> None:
    repo = env_repo(
        tmp_path,
        {"src/a/core/one.rs": "\n", "src/a/core/two.rs": "\n", "src/b/core/two.rs": "\n"},
        doc="See `core/one.rs` and `core/two.rs` and `core/three.rs`.\n",
    )
    _, report = docstool_json(repo, "drift", "--paths")
    by_span = {f["message"].split(":")[0]: f for f in report["findings"] if f["check"] == "path-missing"}
    assert by_span["core/one.rs"]["severity"] == "P3"
    assert by_span["core/one.rs"]["suggestion"] == "use src/a/core/one.rs"
    assert by_span["core/two.rs"]["severity"] == "P2"
    assert by_span["core/three.rs"]["severity"] == "P2"


def test_a_removed_root_path_is_not_redirected_to_a_deeper_twin(tmp_path: Path) -> None:
    repo = env_repo(tmp_path, {"src/keep.py": "\n", "tests/fixtures/src/config.py": "\n"}, doc="See `src/config.py`.\n")
    _, report = docstool_json(repo, "drift", "--paths")
    finding = next(f for f in report["findings"] if f["check"] == "path-missing")
    assert finding["severity"] == "P2"
    assert "tests/fixtures" not in finding["message"]


def test_records_are_skipped_and_can_be_included(tmp_path: Path) -> None:
    repo = env_repo(
        tmp_path,
        {
            "Makefile": "all:\n\t@true\n",
            "docs/internal/history/old.md": "# Old\n\nRun `make go-vet`.\n",
            "docs/internal/restructure/report.md": "# Report\n\nRun `make go-vet`.\n",
        },
        doc="Nothing.\n",
    )
    code, report = docstool_json(repo, "drift")
    assert "make-target-missing" not in {f["check"] for f in report["findings"]}
    assert next(r for r in report["coverage"] if r["input"] == "records")["state"] == "complete"
    assert code == 0
    _, included = docstool_json(repo, "drift", "--include-records")
    assert {f["file"] for f in included["findings"] if f["check"] == "make-target-missing"} == {
        "docs/internal/history/old.md",
        "docs/internal/restructure/report.md",
    }


def test_a_record_does_not_document_a_variable_or_hide_a_removal(tmp_path: Path) -> None:
    repo = env_repo(
        tmp_path,
        {
            "src/main.rs": 'fn main() { std::env::var("BAR_OLD"); std::env::var("BAR_NEW"); }\n',
            "docs/internal/history/old.md": "# Old\n\nBAR_OLD and BAR_NEW.\n",
        },
        doc="Nothing.\n",
    )
    _, report = docstool_json(repo, "drift")
    assert {"BAR_OLD", "BAR_NEW"} <= {f["message"].split(" ")[0] for f in report["findings"] if f["check"] == "env-undocumented"}
    (repo / "src/main.rs").write_text('fn main() { std::env::var("BAR_NEW"); }\n', encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "drop")
    _, report = docstool_json(repo, "drift", "--base", "HEAD~1")
    assert "removed-still-documented" not in {f["check"] for f in report["findings"]}
    _, included = docstool_json(repo, "drift", "--base", "HEAD~1", "--include-records")
    assert "removed-still-documented" in {f["check"] for f in included["findings"]}
