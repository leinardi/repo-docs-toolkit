# Documentation collections studied

Read this when you change restructure, audit or maintenance guidance or the docstool coupling
checks, and want the real-world hazards they were built to catch.

> **Status:** Research record, November 2026. Three real documentation collections were read,
> read-only, to learn what a restructure must detect: leinardi/gx52 at 24578dc (2026-11-20),
> leinardi/bitgauge at e349e25 (2026-11-20) and leinardi/monmux at 8cccc5f (2026-11-09). Counts were
> measured on those commits and will have moved. The later end-to-end run on gx52 is in [the gx52
> trial report](../qa/gx52-trial.md).

## Contents

- The three collections
- Hazards found
- Slug and link facts
- What was at risk of loss
- Decisions only a human can make
- How this shaped the toolkit

## The three collections

| Repository | Docs | Shape |
| --- | --- | --- |
| leinardi/gx52 (Rust, GTK app, rewritten from Python in 3 weeks) | 21 files, 5,180 lines in `docs/`, plus 7 root files | No site. Living specs (protocol, architecture, profiles, UI, release) mixed with planning records (analysis, roadmap, spikes, hands-on log, tooling checklist) |
| leinardi/bitgauge (Rust, self-hosted speed test) | 55 files, 13,503 lines in `docs/`, plus 4 root files | Three trees with stated authority: `features/` (normative spec), `engineering/` (working notes), `research/`. 1,503 links, none broken |
| leinardi/monmux (Go CLI that writes to monitors) | 11 flat files, 4,018 lines, plus 4 root files | Safety-heavy prose; a generated 1,025-line compatibility page; one historical requirements document |

None had front matter, admonitions or images in `docs/`; each had one mermaid diagram or none. All
three use compact tables and wrap at 100 columns, and all had a link checker that already used
GitHub slug rules.

## Hazards found

Each is a category the toolkit now checks or tells the agent to look for.

- **Docs as machine interfaces.** A test in bitgauge parses a section of `security.md` found by its
  `## 5.` heading prefix and a fenced `text` block; a front-end test checks that a CSP hash appears
  in the same file. monmux generates a region of `compatibility.md` between BEGIN and END
  GENERATED comments and its tests read the table back verbatim; a toolchain test parses the Go
  line in CONTRIBUTING.md.
- **Docs linked from shipped artifacts.** The released bitgauge binaries link to four `main`
  paths; an installed GNOME extension builds `troubleshooting.md#<reason>` URLs at run time, one
  heading per refusal reason (14 of 14 matched the code enum). GitHub blob URLs cannot redirect,
  so such paths stay put or leave a stub.
- **Prose citations that no link checker sees.** gx52 code cites docs by file and quoted heading
  about 130 times; three cited headings no longer exist and three cite a bold label, not a
  heading. bitgauge has about 880 "page section N" comments and 21 anchors that depend on
  double-hyphen slugs. CI error messages cite a section title (monmux: "Before the first
  release"). Renumbering or renaming breaks them silently.
- **Semantic IDs.** Spike, risk and milestone IDs (S1 to S9, R1 to R12, M0 to M9) and requirement
  numbers (monmux 9.5 to 9.12) are cited in prose and code; a split or renumber breaks them.
- **Links that leave `docs_dir`.** gx52 had 20, bitgauge 22 and monmux about 10 relative links to
  root files, workflows or source. They are legal on GitHub and illegal in a site; they must
  become repository URLs or snippet includes.
- **Inbound links from agent tooling.** AGENTS.md, project skills, issue and PR templates and
  agent memory files deep-link headings (`#validation-matrix`, `#commit-messages`).
- **Mixed-lifecycle files.** gx52's roadmap was 730 finished lines plus a 14-line live list;
  bitgauge's port record held live lint rules inside a historical record; monmux's release page
  mixed user, contributor, maintainer and one-time bootstrap content. Classify per section.
- **Duplicated facts that drift.** The commit-type to version table appeared 3 to 4 times per
  repository; monmux had the agent rule four times and `--unsafe-model` seven times, with the
  shorter copy already missing cases; install commands, make targets and tags tables repeated.
- **Hand-maintained numbers.** monmux hard-codes model counts in three places (correct at the
  time, unchecked).
- **Stale claims in current docs.** gx52: a claim of bundled SQLite against `Cargo.toml`, "crates
  are still stubs", a SECURITY check called open while a checklist ticked it. bitgauge: "not yet
  released" beside two tags (the phrase wraps across lines, so grep missed it), a QA status of
  "uncommitted" after the commit landed. monmux: a JSON example with the wrong count, a Go field
  name leaked into a YAML key, an IaC step described as open though the IaC already set it.
- **Records and queues.** QA rounds with session noise (PIDs, temporary paths), checklists
  with open items recorded nowhere else, a dormant runbook, a paste queue for an external tool, a
  never-posted call for testers.
- **Generated or frozen content.** monmux's generated region and "kept as written" requirements
  document must not be reformatted, rewrapped or renumbered.

## Slug and link facts

- GitHub slugs keep runs of hyphens and trailing hyphens (a heading with an em dash gives `--`);
  Python-Markdown's default `toc` slugify collapses them. Affected anchors: 21 (76 links) in
  bitgauge, several in gx52 and monmux, including those from headings with backticks and `--`.
- Emoji-prefixed headings give `#-slug` on GitHub (see [readme-homepage.md](readme-homepage.md)).
- The P0 spike confirmed `pymdownx.slugs.slugify(case=lower)` reproduces GitHub for all 1,111 ids
  of these collections; only duplicate headings diverge ([p0-spike.md](p0-spike.md)).
- A folder with both `README.md` and `index.md` has undefined behaviour in Zensical; bitgauge uses
  `README.md` as every section index.
- Verified spot checks (config keys, defaults, flags, make targets, enum headings) mostly matched
  the
  code in all three, so an audit must report precision, not only drift.

## What was at risk of loss

Rationale that lived only in planning or QA records: decision tables and "not chosen" alternatives,
risk lists, dated hardware evidence behind a normative spec, open items that existed only as
unchecked boxes, licence provenance for reused code (a script depended on it), and the exact
strings users search for. Nothing load-bearing may exist only in `docs/internal/`; see
[the publication policy](../../../skills/repo-docs/references/publication-policy.md).

## Decisions only a human can make

- Whether paths may move at all, given deployed links, and whether stub files are acceptable.
- Whether to publish history (decision records, QA logs, spikes), archive it or move it out.
- Whether maintainer material (release, bootstrap, audits) is published.
- Which copy of a duplicated fact is canonical, and whether AGENTS.md stays self-contained.
- Whether to fix stale claims in the same change as a restructure.
- The slug strategy and whether to change shipped links to a site URL (a security question for an
  application that makes no outbound calls).

## How this shaped the toolkit

- The restructure workflow works from a plan that records, per page, the target, archive or
  redirect and the constraints, and leaves the decisions above to the user; `docstool inventory`
  reports couplings, duplicates and lifecycle signals.
- Archiving keeps a status line and never deletes; a path referenced from outside stays put or
  leaves a stub.
- Audit separates confirmed from likely findings and states coverage, since these collections
  were mostly accurate and a noisy audit would bury the few real defects.
