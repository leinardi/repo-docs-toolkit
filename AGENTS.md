# AGENTS.md

Project authority for `repo-docs-toolkit`. Read this before changing anything here.

For **how to review** a change to this repo, use the `adversarial-review` skill in
`.agents/skills/`. It owns the review procedure and the review checklist.

## What this is

A Claude Code plugin (and a set of open Agent Skills) for repository documentation:

- `skills/repo-docs/`: writing, auditing, maintaining and restructuring docs, grounded in the code.
- `skills/zensical-site/`: Zensical sites (config, migration, GitHub Pages, upgrades, the landing
  page).
- `skills/repo-readme/`: the README and the community files (CONTRIBUTING, SECURITY,
  CODE_OF_CONDUCT, RELEASING, the CHANGELOG policy).
- `skills/*/scripts/docstool.py`: the standard-library checker every skill runs as
  `python3 -I <skill-dir>/scripts/docstool.py <command>`. The canonical copy is in
  `skills/repo-docs/scripts/`; the other two are byte-identical copies.
- `.claude-plugin/`: plugin and marketplace manifests.

What ships is **text an agent acts on** and **a checker whose findings it trusts**. The failures
that matter are guidance that makes an agent write a false claim into someone's docs, a checker
that reports a clean result for docs that are broken, and a restructure that loses content or
breaks a reference.

## The rules

1. **Facts come from the repository.** A claim in shipped text about Zensical, MkDocs, GitHub or
   Claude Code is verified against the installed tool, its source or its official docs, with the
   version stated; anything that cannot be checked is left out or marked `(verify)`. The tested
   Zensical version is pinned in one place per artifact and named in the text that relies on it.
2. **docstool is fail-closed and side-effect free.** It uses only the standard library and Python
   3.11 or newer. It never executes project code (the one exception is `site-build`, which runs
   the site generator after the user agreed), never sends repository content over the network,
   runs only read-only git commands against the repository (`site-build` may create a git
   repository inside its own temporary staging directory, borrowing the objects, for plugins
   that read history), and writes only the paths its command documents. An input it cannot
   analyse is reported as incomplete coverage (exit 3), never as clean.
3. **The copies of docstool.py never drift.** Edit `skills/repo-docs/scripts/docstool.py`, then run
   `make sync-vendored`. The `check-vendored` hook and `tests/test_vendored.py` fail on any
   difference. The same holds for `docs/stylesheets/home.css`, the site's copy of the shipped
   `skills/zensical-site/assets/stylesheets/home.css`.
4. **Shipped text stays agent-shaped.** `SKILL.md` frontmatter has only `name` and `description`;
   the description says what the skill does *and* when to use it, under 1024 characters. `SKILL.md`
   bodies stay short and route to references; references open with "Read this when", carry a
   contents list when longer than 100 lines, and use exact sibling file names. Every
   `docstool <command>` the text names exists. `tests/test_skills_lint.py` checks all of this.
5. **Attribution is kept.** Material adapted from third parties is listed in
   `THIRD_PARTY_NOTICES.md` with its licence before it lands.

## Layout

| Path | What it is |
| --- | --- |
| `skills/*/SKILL.md` | Skill entry points (YAML frontmatter + Markdown). |
| `skills/*/references/*.md` | Topic references loaded on demand. |
| `skills/repo-docs/scripts/docstool.py` | The canonical checker; copied into the other skills. |
| `scripts/sync-vendored.py` | Writes (`make sync-vendored`) and checks (`--check`) the copies. |
| `tests/` | pytest suite: docstool, the vendored copies, the skill lint, the release bump. |
| `zensical.toml`, `docs/` | The plugin's own site, built from the zensical-site skill's template and landing page; `docs/internal/` is not published. |
| `.mk/test.mk` | Local make targets (`test`, `docs-build`, `sync-vendored`, `check-vendored`, `validate-plugin`). |
| `.mk/release.mk`, `scripts/release_bump.py` | `make release-bump VERSION=X.Y.Z`: writes the version into `.claude-plugin/plugin.json` for the Release workflow. |
| `.mk/help.mk`, `.mk/pre-commit.mk`, `scripts/bootstrap-mk-common.sh` | Fetched from `leinardi/make-common`; change them upstream. |

## Commands

```console
make help             # every target
make pre-commit-install
make check            # pre-commit on every file
make test             # the unit tests
make sync-vendored    # copy the canonical docstool.py into the other skills
make docs-build       # the plugin's own site, built strict and checked with docstool
make validate-plugin  # claude plugin validate . --strict
```

## Validation matrix

Run before considering an edit done. `make check` applies to every row.

| You edited | Run |
| --- | --- |
| `skills/repo-docs/scripts/docstool.py` | `make sync-vendored`, `make test` |
| `skills/**` guidance or references | `make test` (skill lint); verify every tool claim you touched (rule 1) |
| `skills/zensical-site/assets/**` (config template, landing page, examples) | `make test-landing` and `make test-a11y` (need `zensical-requirements.txt` and `requirements/a11y.txt`); screenshots at 1440, 768 and 390 px in both schemes for a layout change |
| `.claude-plugin/**`, `skills/*/SKILL.md` frontmatter | `make validate-plugin`, `make test` |
| `tests/**`, `scripts/**`, `.mk/**` | `make test`; for the bump, `make release-bump VERSION=<higher>` shows a one-line diff (then restore the file) |
| `.github/workflows/**`, `.github/dependabot.yml` | `pre-commit run actionlint --all-files`; reason through each trigger the workflow has |
| `docs/**`, `zensical.toml`, `README.md` | `make docs-build` (needs `zensical-requirements.txt`); `make test` for `docs/reference/docstool.md`, which must cover every docstool option |
| `**/*.md` | `make check` (markdownlint, lychee); prose wrapped at 100 columns outside `skills/` |

## Commits

[Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) with a scope, enforced
by `conventional-pre-commit` (`commit-msg`) and the `conventional-commits` CI job. Scopes in use:
`repo-docs`, `zensical-site`, `repo-readme`, `docstool`, `landing`, `plugin`, `docs`, `ci`,
`deps`, `make`, `tests`.

The type decides the release (svu, through the Release workflow): `feat` → minor, `fix` → patch,
`!` or `BREAKING CHANGE:` → major, even from a 0.x version; every other type (`build`, `chore`,
`ci`, `docs`, `perf`, `refactor`, `revert`, `style`, `test`) bumps nothing. What ships is the
skills, their references and assets, and docstool, so:

- new guidance, a new reference or skill, a new docstool command or check → `feat`;
- wrong guidance, a docstool false positive or false negative, broken landing assets → `fix`, even
  when it is a performance improvement, a refactor or a revert;
- CI, tests, repo tooling, README/CONTRIBUTING → `ci`, `test`, `build`, `chore` or `docs`.

svu matches `feat`/`fix` anywhere in the subject (`prefix:` counts as `fix:`), so avoid a word
ending in `feat` or `fix` directly before a colon in other subjects.

## Releases

Tags are `repo-docs-toolkit--v<version>`, created by the Release workflow
(`.github/workflows/release.yaml`) from the version in `.claude-plugin/plugin.json`.
