# Audit

Read this when the user asks whether the docs are right, wants drift, broken links or stale pages
found, or asks for a documentation review. An audit reports; it changes nothing unless asked.

## Contents

- Scope
- Step 1: deterministic checks
- Step 2: confirm the leads
- Step 3: what only you can check
- Step 4: the report
- Step 5: the fix loop, when asked

## Scope

Agree the scope from the request: one page, `docs/`, the root files, or the whole repository. With
no scope given, audit everything breadth-first, then go deep where the findings cluster, and list
the files you only skimmed under "Surveyed only". Never present a skim as full coverage.

"The whole repository" means the product and contributor docs: `docs/`, the root files and
examples. Agent instruction files, agent memories and issue templates are surveyed only, unless
the user names them.

## Step 1: deterministic checks

Run these first; they settle in one call what would otherwise take dozens.

```sh
python3 -I <skill-dir>/scripts/docstool.py inventory --root <repo> --format json --out <scratch>/inventory.json
python3 -I <skill-dir>/scripts/docstool.py check --root <repo> --format json --out <scratch>/check.json
python3 -I <skill-dir>/scripts/docstool.py drift --root <repo> --scope docs --paths --leads --format json --out <scratch>/drift.json
```

- `check` covers links, anchors (GitHub slugs and the site's own), images, reference definitions,
  nav entries, orphan pages, published pages linking into `internal/`, links leaving the docs
  directory, duplicate headings, heading structure and slug divergence.
- `drift` covers make targets, package-manager scripts, script paths, the project's own binary
  flags, environment variables in both directions, quoted repository paths (`--paths`), status
  claims and hand-maintained counts (`--leads`), and per-doc staleness.
- Run `drift --scope repo` as well when the root files (README, CONTRIBUTING) are in scope.
  `--scope all` also reads agent skill files, which mostly name commands of other tools; use it
  only when those files are in scope.
- When the repository has its own doc checks (`doc_tooling` in the inventory: markdownlint, lychee,
  a link test), run them too and quote their summary. `link_tests` are candidates: open each before
  running it. A test runs project code, so it needs the user's agreement (SKILL.md rule 6); keep
  its build cache in `<scratch>`. A tool that is configured but not installed is not installed by
  you: list it under "Not tested".
- A site: building it is a site-build (gate G11). An audit that does not build says "site not built"
  under "Not tested".

Read each coverage table. A `partial` row (for example a Makefile with `$(eval)`, a config with YAML
anchors) is reported under "Not tested" with its reason, and the matching findings are incomplete.
Make up for it by hand where you can: for a partial `make` row, list every `make <target>` the docs
name and check each against the Makefiles; say in "Checks run" that you did. For a partial `env`
row, the reason names the reads docstool could not resolve; read them.

## Step 2: confirm the leads

docstool findings marked `likely` or `unverified` are leads. For each one you report:

1. Open the doc line and the source the finding names.
2. Search for the other side exhaustively (evidence.md: negative claims).
3. Record it as `verified`, keep it as `likely` with the reason, or drop it as a false positive and
   note why in "Checks run" (for example "12 env-unknown leads were Ansible variables, not env
   vars").

With many leads of one check, group them by shape, confirm one lead of each shape, and report the
counts per shape. `path-missing` leads marked `unverified` are often not paths at all: `owner/repo`
names, build outputs (`dist/`), files of another repository. `env-unknown` leads in configuration
management docs are often template or role variables, not process environment.

Findings in special places:

- Inside a generated region: trace the finding to the generator's input; duplicates there are by
  design.
- In a record (a "kept as written" banner, an archived plan): the record is history, not a claim
  about today. Report it as context, never as drift to fix (G7).
- An explicit `{#id}` heading id works on the site but not on GitHub: `check` reports links to it
  as `broken-anchor` because GitHub renders the file too. It matters when readers use the file on
  GitHub (a README, a page linked from code); otherwise report it as P3 with that note.
- docstool numbers its findings per run (`F1`, `F2`, ...). Do not cite those ids; the report has
  its own numbering.

## Step 3: what only you can check

| Dimension | What to look for |
| --- | --- |
| Claims | Each behaviour a page describes, against the code path that implements it |
| Procedures | Steps in order, prerequisites stated, a verification step, warnings before the steps they guard |
| Examples | Config and code examples against the current schema and API; outputs against the program |
| Completeness | Every flag, key, env var and exit code has a reference entry (page-types.md: Reference) |
| Page type | Each page does one job (page-types.md); mixed pages are a P3 finding with a split proposed |
| Duplication | `duplicates` in the inventory: copies that already disagree are P1; copies that agree are P3 with a single home proposed |
| Lifecycle | Pages the inventory hints are records (ticked checklists, dated status, plans) but read as current |
| Publication | Published pages that fail the test in publication-policy.md |

Style findings are reported only when they mislead (writing-rules.md W1 to W15).

## Step 4: the report

Use the shape of [audit-report.md](../assets/audit-report.md): a header with scope, coverage and
counts by severity; one entry per finding with both sides cited; then "Likely docs to update",
"Surveyed only", "Checks run", "Not tested" and "Assumptions". Number the findings `F1`, `F2`, ...
by severity, most severe first.

Return the report in the conversation. Write it to `docs/internal/qa/` only when the user asks; it
is a dated record, so its file name carries the date.

## Step 5: the fix loop, when asked

1. Fix only the findings the user selected, or every `verified` mechanical one if they said "fix
   them".
2. Keep each fix minimal and in the house style; regenerate generated docs instead of editing them.
3. Re-run the checks from step 1 and the repository's own doc checks.
4. Map each fixed finding to the file and line changed; list what is still open.
