# Restructure a docs tree

A `docs/` directory that grew one file at a time mixes user guides with plans, research notes and
QA records, and other files cite its paths and headings. The repo-docs skill reorganises it into a
published site and an internal area without losing a paragraph or breaking a reference.

Ask for it in plain words:

```text
Restructure docs/ into a user-facing site. Keep the maintainer notes, but out of the site.
```

## What happens

1. **Baseline.** On a clean tree, the skill saves a block baseline of every doc
   (`docstool inventory --blocks`) and, when there is a site, builds it as it is today and records
   every URL and anchor (`docstool site-build`, then `docstool check --save-baseline`). It asks
   before the first `site-build`, because building runs the site generator.
2. **Classify.** Every file, and every section of a mixed file, is marked published or internal by
   the [publication policy](../reference/publication-policy.md).
3. **Design.** The new layout prefers changing the nav over moving files that code, tests or other
   repositories cite.
4. **Plan.** The skill writes `docs/internal/restructure/plan.toml` and a report, and runs
   `docstool plan validate` until it passes. **You approve the plan**; the skill records it only
   when you say so (`docstool plan approve --by <you>`).
5. **Apply.** `docstool plan apply --write` moves, splits and archives files, rewrites links,
   adds redirects and edits the references outside the docs, as one transaction. The agent then
   does the merges and rewrites the plan declared.
6. **Verify.** The skill builds the new site and checks every old URL and anchor against the
   baseline. You review each rewritten or dropped block (`docstool plan approve --mappings`), and
   `docstool plan verify` passes only when every block of the baseline is accounted for.

## When it stops to ask

The skill stops for your decision when the audience is unclear, when an item could be published or
internal, before moving or renaming anything that is cited, before any deletion, when copies of a
fact disagree and the code cannot settle it, before editing a historical record, before editing
anything outside the docs, and for the plan approval itself.

## If something goes wrong

An apply that fails part-way rolls back on its own. One that was interrupted leaves a journal:
`docstool plan resume` finishes it and `docstool plan rollback` undoes it. Both refuse when a file
has changed since, and overwrite nothing.

The plan's file format is in [The plan format](../reference/plan-format.md); the full procedure is
in the skill's [restructure reference][repo-docs-restructure].

[repo-docs-restructure]: https://github.com/leinardi/repo-docs-toolkit/blob/main/skills/repo-docs/references/restructure.md
