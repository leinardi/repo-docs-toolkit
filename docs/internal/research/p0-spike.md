# P0 verification spike

Read this when you need the evidence behind a landing-page, slug, contrast or CI decision, or when
you want to rerun a spike item against a newer Zensical.

> **Status:** Research record, November 2026. The P0 spike checked, before any shipped text was
> written, twelve assumptions the plan depended on. Run on 2026-11-21 with Zensical 0.1.3,
> zensical-ui 0.0.43, pymdown-extensions 13.1.2, Python 3.14.4, Playwright 1.65.2 driving headless
> Google Chrome, and Claude Code 2.1.330. The spike sites were throwaway; the scripts, config,
> template and slug evidence were kept in a gitignored `.scratch/research/p0-spike/` directory that
> is not in the repository.

## Contents

- Results
- Findings that changed the design
- Design adjustments that followed

## Results

| Item | Result | Evidence |
| --- | --- | --- |
| S1 nested `page.meta.home` and the `url` filter | Pass | Nested maps, lists of inline maps and a `for` loop render; `'guide/' \| url` gives the relative URL ./guide/; absolute https links pass through |
| S2 cards, tabs, code copy in a custom template | Pass | `.grid.cards` and `.tabbed-set.tabbed-alternate` in the HTML; copy buttons added by JS |
| S3 `:has()` widening with instant navigation | Pass | `.md-main:has(.rdt-home) .md-grid` gave 1440px on `/` and 1220px on `/guide/`, and held after back, CTA click and tab click, in both schemes; no `<style>` needed |
| S4 light and dark images with the palette toggle | Pass | `#only-light` and `#only-dark` images swap on every toggle step |
| S5 accent legibility | Adjust | Indigo `#4051b5` is 6.86:1 on white but 2.85:1 on slate `#0b0c0f`; `--md-typeset-a-color` is scheme-aware (6.86 light, 5.65 dark) |
| S6 `custom_dir` and `extra_css` locations | Pass | Files under `custom_dir` are copied and work as `extra_css`, as do files under `docs/` |
| S7 snippets of root files under strict | Pass | `base_path = ["."]` and `check_paths = true` include `README.md` and a fenced `compose.yaml` |
| S8 GitHub slug parity | Pass; duplicates diverge | See below |
| S9 `exclude_docs` and an empty redirect map | Pass | `internal/` absent from output; `redirect.json` is `{}`; a published page linking into `internal/` fails strict |
| S10 `python3 -I` path semantics | Pass | `sys.path[0]` is the stdlib zip; importing a sibling module fails; a planted `json.py` in the cwd is not imported; `tomllib` is available |
| S11 `claude plugin validate --strict` | Pass | Same output with an empty environment, so a CI job works; strict needs a marketplace `description` |
| S12 GitHub alerts | Pass | `gh-admonitions` turns `> [!NOTE]` into `admonition note` |

## Findings that changed the design

- **Slug parity (S8).** Built with `pymdownx.slugs.slugify(case=lower)`, 1,111 of 1,111 heading ids
  matched GitHub's own rendering, per file as a multiset, across three real documentation
  collections at pinned commits (leinardi/gx52: 21 files, 222 ids; leinardi/bitgauge: 48 files,
  651; leinardi/monmux: 11 files, 238). None of the 80 files repeats a heading, so the duplicate
  case did not occur. A synthetic 14-heading set sent to GitHub's markdown endpoint (no repository
  content) covered it: Python-Markdown suffixes `_1`, GitHub `-1`, and GitHub skips an existing
`x-1` to `x-2`. A link to `#same-1` fails the strict build. See
[docs-collections.md](docs-collections.md)
  for why slug parity matters.
- **Contrast (S5).** The indigo primary fails on the slate background. The muted text variable is
  translucent; composited it measured 4.76:1 light and 5.30:1 dark.
- **Root font size.** Zensical sets `html { font-size: 125% }`, so 1rem is 20px and `72rem` is
  1440px against a default `.md-grid` of 1220px.
- **Strict gap.** `--strict` does not fail on a missing `extra_css` file (exit 0, "No issues
  found").
- **Built-in plugin.** `gh-admonitions` ships inside Zensical 0.1.3, so the lock needs no extra
  package.
- **Validate profile.** `claude plugin validate --profile directory` also wants a README of 40 or
  more words and a square `icon.png` of 512 to 2048px.

## Design adjustments that followed

1. `docstool check` reports a duplicate heading on a published page as slug-divergent and suggests
   an explicit `{#id}` or a rename; `docstool slug` prints both forms.
2. The landing page colours accent text with `--md-typeset-a-color`, not
   `--md-primary-fg-color`. `docstool contrast` checks text on both scheme backgrounds, white text
   on the colour as a button fill (4.5 or more) and the fill against slate (3 or more), and
   suggests a `[data-md-color-scheme="slate"]` override. The accessibility tests composite
   translucent colours before computing ratios.
3. The asset names `stylesheets/home.css` and `overrides/` stayed, since both locations work.
4. The container stays at `72rem`; the screenshots show it so the user can ask for less.
5. `docstool check` verifies `extra_css` and `extra_javascript` paths because strict does not.
6. Plugin validation is a CI job; the marketplace description is required for `--strict`; the icon
   is a logo decision left to the user.
7. Templates enable `gh-admonitions`.
8. docstool never sends repository content over the network; its slug tests use the synthetic
   headings and the ids GitHub returned for them.
