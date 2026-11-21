# Reference skills studied

Read this when you want to know which third-party skills informed the `repo-docs` guidance, what was
adapted and what was deliberately left out, or before adding material from another project.

> **Status:** Research record, November 2026. Three published documentation skills and Anthropic's
> skill-authoring guidance were read on 2026-11-20 to decide what to adapt and what to write fresh.
> The record of what actually landed, with licences, is
> [THIRD_PARTY_NOTICES.md](../../../THIRD_PARTY_NOTICES.md); this page is the reasoning. The bundled
> script of one skill was read, not run.

## Contents

- The three skills
- What each did well and badly
- What was adapted
- What was left out
- Other items evaluated
- Anthropic guidance used

## The three skills

| Skill | Size | Licence | Focus |
| --- | --- | --- | --- |
| technical-documentation, wondelai/skills | 231-line `SKILL.md`, 7 references, about 18,000 words | MIT, Wondel.ai sp. z o.o. | Style and page quality; adapts the Google developer documentation style guide (CC BY 4.0) |
| documentation, mcollina/skills | 109 lines, no references | MIT, Matteo Collina | Diátaxis page types and per-type checks |
| docs-sync-audit, github/awesome-copilot | 163-line `SKILL.md` plus a 474-line standard-library script | MIT, GitHub, Inc. | Docs against code drift audit |

## What each did well and badly

**technical-documentation.** Strong: facts before style as a blocking gate; four sources for a fact
(argument definitions, `--help` output, tests, the user) with an inline `TODO(verify)` marker
otherwise; stable rule IDs with severity; local conventions outranking the generic guide, with
grep probes to infer a house style. Weak: about 3,300 words load on each trigger and 18,000 more
sit behind them, mostly rules a model already knows; an over-broad trigger that would compete with
sibling skills; page-level only (no inventory, navigation, duplication or link checks); the
verification is an instruction with no mechanism; subjective scoring with no evals; affiliate
links in its further reading (not to be copied).

**documentation (mcollina).** Strong: the most compact statement of the four page types, a
decision table from reader signal to type, per-type titles and checks, and a reference entry
schema. Weak: no grounding in the code at all; "always ask clarifying questions" blocks agent runs;
its validations cannot be tested as written; it claims restructuring but has no procedure for it.

**docs-sync-audit.** Strong: the best audit discipline of the three (evidence on both sides of a
mismatch, confirmed against inferred, numbers backed by the command that produced them, negative
claims needing an exhaustive search, honest coverage, a "not tested" list, repository text treated
as evidence and never as instruction) and a sound split between a deterministic script and agent
judgement. Weak: drift only; no diff mode mapping a code change to the docs that mention it. The
script, read statically, was biased to JavaScript and Python (it missed Rust and Go environment
reads, ignored included `.mk` files, mishandled `./` prefixes, root-relative links and fragments,
and sampled staleness from an unordered set) and shipped no tests. Its stated upstream repository
returned 404, so its origin could not be checked.

## What was adapted

Listed in [THIRD_PARTY_NOTICES.md](../../../THIRD_PARTY_NOTICES.md); summarised here with why.

- From docs-sync-audit: the evidence standards, the P0 to P3 severity rubric defined by reader
  impact, repository text as evidence, and the report sections ("Surveyed only", "Checks run", "Not
  tested"). Added from the others: wondelai's blocking gate for wrong or unverifiable facts.
- From technical-documentation: the four sources of a fact and the `TODO(verify)` marker, the
  blocking gate and the local style probes, kept short.
- From documentation (mcollina): the page-type decision table and per-type checks, restated as
  things an agent can run, with the questions ("could a beginner finish this?") replaced by
  observable ones. Diátaxis is linked, not copied.
- From the Google style guide, through the wondelai skill: a short table of the writing rules that
  change meaning, condensed and changed.
- Shape, not text: a shared contract across the skills (evidence, confidence class, severity,
  report skeleton) and an inventory-first workflow in which a plan file is checked before a
  restructure is applied.

## What was left out

- The 60-rule style table, the word list and the voice rules (context cost, generic, specific to
  one style guide).
- The scoring scheme (counts and the blocking gate are easier to test).
- The ask-first rule: infer the audience from the repository and ask only when it matters.
- The drift script's code. The `drift` command of docstool was written fresh with those gaps in
  view; no code from the script is listed in the notices.
- Diátaxis prose: the framework text is CC BY-SA 4.0 (share-alike), which does not fit an MIT
  plugin, so the toolkit writes its own words and links to the site.

## Other items evaluated

- A third-party pair of Zensical plugins for an agent (development and debug skills), last pushed
  2026-02-20: not used. Its README says MIT but the repository has no licence file and the
  manifests have no licence field, so it was treated as unlicensed. Several claims did not hold
  against Zensical 0.1.3: that Zensical is Material for MkDocs, that CSS and config edits need a
  server restart (live reload worked, see [zensical.md](zensical.md)), and that a project must have
  a virtual environment. It does not cover configuration, overrides, plugins or deployment. The one
  useful idea, checking the rendered page in a browser, is kept as the screenshots step.
- A Node-specific documentation rules file in one of the repositories: not reusable content, but
  its pattern (a project-specific rules file recording that project's docs lint traps) is worth
  following.

## Anthropic guidance used

Concise context ("only add what Claude doesn't already have"), `SKILL.md` under 500 lines,
references one level deep with a contents list above 100 lines, third-person descriptions of at most
1,024 characters saying what and when, feedback loops (validate, fix, repeat), verifiable
intermediate outputs (the plan file) and evaluation scenarios before extensive text. None of the
three studied skills shipped evals; the toolkit's tests and the end-to-end trial play that role.
See [plugin-mechanisms.md](plugin-mechanisms.md).
