# Upgrading and auditing a site

Read this when a project's Zensical version is bumped, when Dependabot or Renovate proposes a
new one, or when the user asks whether an existing site is set up well. Facts are for Zensical
0.1.3; `site-audit` reports a lock that pins another version (`zensical-version`).

## Contents

- [Auditing an existing site](#auditing-an-existing-site)
- [What site-audit reports](#what-site-audit-reports)
- [Upgrading Zensical](#upgrading-zensical)
- [Changes to watch](#changes-to-watch)

## Auditing an existing site

An audit changes nothing; it ends with a report and offered fixes.

**Step 1: the read-only checks.** None of them builds anything:

```sh
python3 -I <skill-dir>/scripts/docstool.py site-audit --root <repo>
python3 -I <skill-dir>/scripts/docstool.py check --root <repo>
python3 -I <skill-dir>/scripts/docstool.py contrast '<brand colour>' --slate '<dark value>'
```

The brand colour is the palette's `primary`: a named colour, or with `primary = "custom"` the
`--md-primary-fg-color` value in the project's `extra_css` (the palette's `accent` key is a
different, secondary colour). Pass `--slate` only when the CSS sets a dark-scheme value; without
it, `contrast` checks the one colour on both backgrounds. The "white text on the accent fill" row
matters even without a landing page when the site uses `variant = "classic"`, whose header bar
is that fill. For a named
colour you cannot resolve to a value, skip `contrast` and say so under "Not tested".

**Step 2: one strict build**, with the user's agreement (Z6), into `<scratch>`:

```sh
python3 -I <skill-dir>/scripts/docstool.py site-build --root <repo> --out <scratch>/site
```

If it fails, read the generator's message. A site that fails here but builds in a plain clone
of the repository points at docstool, not the site: report it as a checker limitation, with
both results, never as a broken site.

**Step 3: what only you can check.** The commands do not see these; read the files:

- **Deployment.** Which workflow builds and publishes the site, from which branch; whether its
  upload path matches `site_dir`; whether it installs from the lock. No workflow and no
  `gh-pages` branch means the site is published from somewhere else: ask. [deploy.md](deploy.md)
  is the target state.
- **The lock.** Zensical pinned with `==`, the lock committed (an entry in `.gitignore` voids it),
  installed from it: `uv run --locked` with a `uv.lock`, or `pip install --require-hashes` with a
  hashed requirements file. A requirements lock still works; moving it to a uv project is a
  suggestion, not a fault.
- **Settings that are on but do nothing or claim too much.** Deprecated validation checks, a
  cookie consent dialog with no analytics behind it, Google Fonts where the project avoids
  third-party requests (`font = false`).
- **Custom CSS.** Overrides of theme colours (header, code highlighting) checked with
  `contrast` like the brand colour.
- **The rules of this skill.** `exclude_docs = "internal/"`, GitHub-compatible anchors, the
  native header and tabs kept.
- **In a browser** when one is available: the homepage and one deep page at 1440, 768 and 390
  pixels in both schemes. Otherwise list it under "Not tested".

**Step 4: the report.** Write it to the user (or to `<scratch>`; into the repository only when
asked), in this shape:

```markdown
# Site audit: <repository>

Scope: files read, commit, Zensical version (lock and installed). Coverage: the coverage
tables' state. Counts: Blocking, P0, P1, P2, P3.

### F1 [P1] <check>: <one-line title>
- Config: <path:line> (and the source of the evidence, path:line)
- Impact: what a reader or maintainer gets wrong, and when
- Fix: the change; the gate it needs, if any

## Fixes, grouped
Config, extensions, CI and lock, colour, landing page: finding numbers each.

## Checks run
Each command with its exit code and one-line result.

## Not tested
What was not checked and why (no browser, no deployment access, a build the checker could not run).

## Assumptions
What you took as given (the default branch, where the site is published).
```

Some fixes need a gate before anyone applies them: a slug style change renames anchors (Z5),
deployment and Pages settings (Z1, Z2), a darker or lighter brand colour (Z3). Name the gate in
the finding.

## What site-audit reports

| Check | Severity | Meaning |
| --- | --- | --- |
| `hooks` | P1 | `hooks:` in mkdocs.yml: not run by Zensical |
| `plugin-unsupported` | P1 | A plugin Zensical does not implement: its config is ignored |
| `plugin-native` | P3 | A plugin Zensical does natively; the entry is ignored |
| `docs-dir` | P1 | `docs_dir` is `.` |
| `internal-published` | P1 | `docs/internal/` exists but `exclude_docs` does not exclude it |
| `extension-missing` | P1 | The docs use syntax whose extension the explicit list lacks |
| `feature-noop` | P2 | `search.suggest` or `search.share`, which do nothing |
| `feature-conflict` | P2 | Two features the Zensical docs say do not work together; the owner picks the one to keep |
| `slugify` | P2 | Anchors differ from GitHub's |
| `site-url` | P2 | No `site_url`: instant navigation and the sitemap need it |
| `gh-admonitions` | P2 | The docs use GitHub alerts but the plugin is off |
| `validation` | P2 | `validation = false`, or every validation check set to false |
| `yaml-env` | P2 | `!ENV` in mkdocs.yml |
| `lock` | P2 | No committed hash-pinned lock pins Zensical; named at the requirement line when one exists |
| `ci-build` | P2 | No workflow builds the site |
| `validation-deprecated` | P3 | One of the six deprecated validation checks is on |
| `exclude-internal` | P3 | No `docs/internal/` yet, but `exclude_docs` would publish one |
| `search-option`, `yaml-python-name`, `codehilite` | P3 | Ignored options, legacy tags, a redundant extension |
| `zensical-version` | P3 | The lock pins a version other than 0.1.3: this skill's facts may not hold for it; say so in the report |

## Upgrading Zensical

1. Read the release notes for every version between the pinned one and the target
   (`https://github.com/zensical/zensical/releases`). List what touches this site: config keys,
   plugins, templates, the theme's HTML.
2. Baseline the current site, as in [migrate.md](migrate.md) Step 1, with the current lock
   installed: `site-build --ref HEAD`, then `check --save-baseline`.
3. Change the pin in `tools/docs/pyproject.toml` (or take the Dependabot pull request that did),
   run `uv lock --project tools/docs`, and build again into a new directory.
4. `check --baseline` the new build, `site-audit` the config, and compare both sites in a
   browser, landing page included, in both schemes.
5. If the theme's HTML changed under `home.html` or `home.css` (a broken layout, a missing hero),
   stop: the landing page assets need a toolkit release first. Report it rather than patching
   them in the project.

## Changes to watch

Zensical's published plans that affect a site built with this skill:

- Settings will move out of `[project]` into new scopes, with automatic refactorings, and the
  `plugins` scope will be replaced by a module system. Expect the config template to change.
- The six optional validation checks are deprecated in their current form.
- A new Markdown parser (Zensical Markdown) is in development. When it lands, re-check anchors:
  `check --baseline` against a pre-upgrade build shows any anchor that changed.
- Native versioning and i18n are on the roadmap; today they need the mike fork and separate sites.
