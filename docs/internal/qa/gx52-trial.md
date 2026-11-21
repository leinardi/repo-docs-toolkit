# gx52 end-to-end trial (P7)

The toolkit's three skills run end to end on a throwaway clone of gx52 (`git clone` of the local
checkout at `24578dc`, remote removed). The real checkout was not touched. Run on
2026-11-21 with docstool 0.1.0 and Zensical 0.1.3; the owner answered every gate.

## What ran

| Stage | Command or step | Result |
| --- | --- | --- |
| Inventory | `inventory --blocks` | 43 Markdown files, 2,000 blocks; 11 frozen files; 13 broken or bold-label citations already in gx52 |
| URL baseline | `check --save-baseline` (no `--built`) | Source-derived: gx52 had no site, so URL preservation is partially verified by construction |
| Classify | repo-docs publication policy | 3 published pages stay; 2 runbook and design pages, 2 living plans, 3 records, 10 spikes and 1 draft go to `docs/internal/` |
| Plan | `plan validate` loop, then `plan approve` (owner, G9) | 31 moves and archives, 104 `[[reference]]` line edits in 61 files outside `docs/` |
| Apply | `plan apply --write` | 100 paths written; second dry run reported nothing to do |
| Site | `zensical.toml` from the template, landing page from the gtk-app example | Strict build passes; `site-audit` 0 findings; `contrast` passes with the metainfo branding colours |
| README | repo-readme, gates R1 and R4 | 141 lines down to 62; `readme --home` 0 findings; moved content in `getting-started.md` and `building.md` |
| Verify | `plan verify --urls --built` after `plan approve --mappings` (owner) | 0 findings: every block found or covered by one of 6 reviewed mappings |

Gates the owner answered: G3 and G10 (move the records and `release.md`/`ui.md` with an edit to every
citing line), G2 (the call for testers is internal), G8 (new getting-started and building pages),
R1 and R4 (rewrite the README), R6 (remove `CHANGELOG.md`: its entries are in the metainfo
`<releases>`), G11 and Z6 (build the site), G9 (the plan), and the mappings review. R3 (the
Contributor Covenant 1.4 code of conduct) was left open.

## Done criteria

| Criterion | Result |
| --- | --- |
| Content conservation reports zero unaccounted blocks | Met: `plan verify` 0 findings, 2,000 baseline blocks |
| Every heading and section citation valid or rewritten | Met with an owner waiver: the 6 citations of renamed headings ("Flathub by hand", "The release workflow", "TOML schema (version 1)") were fixed in the clone after review; the 7 citations of bold list labels in `architecture.md`, which have no anchor, were waived by the owner on 2026-11-21 and are listed under open items |
| Strict build passes, no published page links into `internal/` | Met: `site-build` exit 0, `check --built` no `links-unpublished` |
| gx52's own checks pass | Met after review (the first pass missed the lost executable bits, which only a `git diff --summary` showed): markdownlint, end-of-file, trailing whitespace, YAML, TOML, actionlint, yamllint, prettier, licence headers, `cargo fmt --check`, and the docs link test (`cargo test -p meta --test docs`, 3 passed). gx52 has no lychee |
| README at most 100 lines and lint-clean | Met: 62 lines, markdownlint clean |
| Landing page reviewed by the owner | Met after one change: the header logo and favicon now use the app's symbolic icon |

## Fixes folded back

docstool, each with a regression test (`tests/test_plan_trial.py`,
`tests/test_readme_examples.py`) that fails on the previous version:

- `plan validate` flagged a relative citation (`ui.md` in `roadmap.md`) whose file and target
  moved into the same directory, so it still resolved.
- `plan validate` treated a link whose text wraps onto the next line as a plain-text mention.
- `plan apply` crashed (IndexError) when a `[[reference]]` edit targeted a file the plan also
  moves; line edits now run first, on the original line numbers.
- `plan verify` called the blocks the plan's own `[[reference]]` edits changed lost.
- `plan verify` matched identical table rows to a copy in a moved file that sorts earlier,
  reporting `order-changed`; it now prefers the copy still in place.
- `plan verify` reported `context-lost` for a warning moved by hand under a reviewed mapping.
- Archive status lines were one line of any length; they now wrap at the repository's markdownlint
  `line_length` (or its usual width).
- `inventory` scanned the restructure artifacts (baselines, logs, report) as couplings: 1,388
  false `coupling-missing` findings after a restructure.
- `readme` could not read a `<strong>` tagline wrapped over two lines.
- `plan apply --write` dropped the executable bit of every file it rewrote: five gx52 release
  scripts went from 100755 to 100644. Found by the phase review, not by the trial's checks; apply
  and rollback now keep each file's mode, and a moved file takes its source's.
- The co-move exemption above ignored `[[anchor]]` entries that rename the cited heading.
- A wrapped status line could start with `-`, `1.` or `#` and become a list item or heading.

Skill text:

- repo-docs `restructure.md`: the three post-apply fixes (links into `internal/`, rewrapping,
  README content moved into the docs) and the optional mapping `heading`.
- zensical-site `config.md` and the config template: `theme.logo` and `theme.favicon`, the
  symbolic icon for GNOME apps.
- repo-readme `readme.md`: wrapping the header inside its tags under a line-length rule.

## Not tested

- The live GitHub Pages deployment: Pages is not enabled for gx52, and the docs URL in the new
  README and the badges point at a site that does not exist yet (gate Z2).
- The URL baseline against an old build: gx52 had no site.
- gx52's full `cargo test`, clippy and the Flatpak build: only comments changed in code, and
  `cargo fmt --check` and the docs link test ran.
- A screen reader pass over the landing page.

## Open items

- At 390 px the copy button of the install block overlaps the end of the long `flatpak`
  command, which scrolls horizontally (landing page `home.css`).
- The CHANGELOG decision removed history the metainfo still carries; a gx52 that drops 0.7.x
  from its metainfo would lose it.
- gx52's 7 citations of bold list labels in `architecture.md` (waived), and R3 for its code of
  conduct.
