# docstool

docstool is the checker every skill runs. It is one Python file that uses only the standard
library, and needs Python 3.11 or newer. Each skill carries an identical copy in its `scripts/`
directory, so a skill installed on its own still has it:

```sh
python3 -I <skill-dir>/scripts/docstool.py <command> [options]
```

`-I` keeps Python from importing anything from the current directory or the script's
directory, so a file in the repository being checked can never shadow a standard-library module.
`python3 -I docstool.py --version` prints the version.

## Common options

Every command takes these options. `site-build` is the exception for `--out`, which there names
the build directory.

| Option | Values | Default | What it does |
| --- | --- | --- | --- |
| `--root` | `DIR` | `.` | repository root (default: the current directory) |
| `--format` | `text`, `json` | `text` | output format |
| `--out` | `PATH` |  | write the report to this file instead of stdout |
| `--max` | `N` | `50` | findings shown in text output |
| `--fail-on` | `Blocking`, `P0`, `P1`, `P2`, `P3` | `P3` | lowest severity that makes the exit code 1 |

Each finding has an id, a check name, a severity (`Blocking`, then `P0` to `P3`), a confidence
(`verified`, `likely` or `unverified`), a file and line, a message, its evidence and, when there
is one, a suggested fix. `--format json` prints the same report as one JSON object.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | No findings at or above `--fail-on`, and every input the command needs was analysed completely |
| `1` | Findings at or above `--fail-on` |
| `2` | Usage error, a refused operation (such as a stale build or a non-empty output directory), or a site generator that failed or is missing |
| `3` | Incomplete coverage: an input the command needs could not be analysed |

Coverage is reported apart from findings. Every run prints a coverage table with one row per input
(the site config, the nav, `exclude_docs`, redirects, the slug style, the files scanned), each
`complete`, `not_applicable`, `partial` or `failed` with a reason. A run whose required input is
partial exits 3 rather than reporting a clean result it cannot vouch for.

## What docstool writes

docstool never runs project code, never sends repository content over the network and runs only
read-only git commands. It writes only:

- the report file named by `--out`, and the block baseline named by `inventory --blocks`;
- the URL baseline named by `check --save-baseline`;
- the `[approval]` table of the plan (`plan approve`) and `review-receipts.json`
  (`plan approve --mappings`);
- the files a plan declares, with its journal, staging directory and log under
  `docs/internal/restructure/` (`plan apply --write`, `plan resume`, `plan rollback`);
- the output directory of `site-build` and the stamp inside it.

`site-build` is the one command that runs another program: the site generator, which can load
the project's hooks and plugins. The skills ask before the first `site-build` in a repository.

## inventory

Map the docs: headings, links, couplings, duplicates, lifecycle, style.

| Option | Values | Default | What it does |
| --- | --- | --- | --- |
| `--section` | `all`, `docs`, `root` | `all` | which Markdown files to list |
| `--blocks` | `PATH` |  | also write the content-conservation block baseline to this file |

Common options: `--root`, `--format`, `--out`, `--max`, `--fail-on`.

The JSON report lists, per file, the headings with their anchors, the links, front matter,
generated regions and a lifecycle hint, then the couplings: places anywhere in the repository that
cite a doc path, a heading or a section number, and which of them should freeze the path.

## check

Find broken links, anchors, images, nav entries and publication problems.

| Option | Values | Default | What it does |
| --- | --- | --- | --- |
| `--scope` | `all`, `docs`, `repo` | `all` | which Markdown files to check |
| `--allow-partial` | flag |  | exit 0/1 even when coverage is incomplete (the summary says PARTIAL) |
| `--built` | `DIR` |  | a docstool site-build output directory (refused when stale or not built by docstool) |
| `--save-baseline` | `PATH` |  | write the URL and anchor baseline of --built (or, without it, a source-derived one) to this file |
| `--baseline` | `PATH` |  | check --built against a saved URL baseline: routes, redirects, anchors |
| `--site-planned` | flag |  | with no site config: also report links that would break once docs/ is published (changes no baseline) |

Common options: `--root`, `--format`, `--out`, `--max`, `--fail-on`.

`--save-baseline` with `--built` records every route and element id of a site that
`site-build` produced. `--baseline` with `--built` then checks a new build against it: every old
route must still be a page, or a redirect whose chain ends at one, and every old anchor must still
exist on its destination.

## site-build

Build the site with its generator into a fresh directory, with a stamp of its inputs.

| Option | Values | Default | What it does |
| --- | --- | --- | --- |
| `--out` | `PATH` |  | fresh output directory (must not exist or be empty) |
| `--ref` | `REF` |  | build this commit from git archive instead of the working tree |
| `--generator` | `zensical`, `mkdocs` |  | default: zensical for zensical.toml, mkdocs for mkdocs.yml |

Common options: `--root`, `--format`, `--max`, `--fail-on`.

The build runs `<generator> build --strict --clean`. The stamp, `.docstool-build.json`, records
the ref, the generator and its version, and a hash of every input the build read; `check --built`
refuses output whose inputs have changed since.

## plan

Validate, approve, apply, resume, roll back or verify a restructure plan.

| Option | Values | Default | What it does |
| --- | --- | --- | --- |
| `action` | `validate`, `approve`, `apply`, `resume`, `rollback`, `verify`, `mappings` |  | what to do with the plan (see below) |
| `--plan` | `PATH` | `docs/internal/restructure/plan.toml` | the plan file |
| `--write` | flag |  | apply: write the changes (the default is a dry run) |
| `--by` | `NAME` |  | approve: who approves (gate G9) |
| `--mappings` | flag |  | approve: write review receipts for mappings.toml instead of the plan approval |
| `--urls` | `PATH` |  | verify, mappings: also check a saved URL baseline (a site's needs --built) |
| `--built` | `DIR` |  | verify --urls: the new site-build output |

Common options: `--root`, `--format`, `--out`, `--max`, `--fail-on`.

The actions, in the order a restructure uses them:

| Action | What it does |
| --- | --- |
| `validate` | Checks the plan against the repository: sources and their hashes, coverage of every doc, frozen paths, inbound references, redirects, open decisions |
| `approve` | Records the owner's approval (`--by`) in the plan, bound to the plan's and every source's hash; with `--mappings`, writes the review receipts instead |
| `apply` | Prints what would change; with `--write`, applies it as one journalled transaction that rolls back on failure |
| `resume` | Finishes an interrupted apply |
| `rollback` | Undoes an interrupted apply |
| `verify` | Checks that every block of the baseline is accounted for, that every mapping has a valid receipt and, with `--urls` and `--built`, that old URLs still resolve |

The file format is in [The plan format](plan-format.md).

## drift

Find commands, flags, env vars and paths the docs name that the code no longer has.

| Option | Values | Default | What it does |
| --- | --- | --- | --- |
| `--scope` | `all`, `docs`, `repo` | `all` | which Markdown files to read |
| `--base` | `REF` |  | also report tokens removed or added since this commit (read-only git diff) |
| `--paths` | flag |  | also check repository paths quoted in inline code |
| `--leads` | flag |  | also report status claims, hand-maintained counts and stale docs as leads |
| `--include-records` | flag |  | also read docs/internal/restructure/ and docs/internal/history/ |
| `--allow-partial` | flag |  | exit 0/1 even when coverage is incomplete (the summary says PARTIAL) |

Common options: `--root`, `--format`, `--out`, `--max`, `--fail-on`.

## site-audit

Audit zensical.toml or mkdocs.yml for what Zensical ignores, misses or does differently.

Common options: `--root`, `--format`, `--out`, `--max`, `--fail-on`.

It is checked against Zensical 0.1.3 and warns when another version is installed.

## readme

Lint the README and compare it with the homepage.

| Option | Values | Default | What it does |
| --- | --- | --- | --- |
| `--file` | `PATH` | `README.md` | the README to lint |
| `--home` | `PATH` |  | the homepage (docs/index.md) whose tagline, features and install block the README must match |
| `--registry` | flag |  | the README is also shown on a package registry (relative images break there) |

Common options: `--root`, `--format`, `--out`, `--max`, `--fail-on`.

## contrast

Check a brand colour against both page schemes and as a button fill.

| Option | Values | Default | What it does |
| --- | --- | --- | --- |
| `colour` | `#rrggbb` |  | the brand colour, #rrggbb |
| `--slate` | `#rrggbb` |  | the dark-scheme override of the colour, when there is one |

Common options: `--root`, `--format`, `--out`, `--max`, `--fail-on`.

## slug

Print GitHub's and the site's anchor for heading texts.

| Option | Values | Default | What it does |
| --- | --- | --- | --- |
| `--style` | `pymdownx-lower`, `pymdownx-none`, `python-markdown`, `python-markdown-unicode` |  | the site's slugify (default: read from the --root site config) |
| `text` | `TEXT …` |  | heading texts, in document order |

Common options: `--root`, `--format`, `--out`, `--max`, `--fail-on`.
