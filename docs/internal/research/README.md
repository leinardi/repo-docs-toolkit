# Research records

Read this when you want the evidence behind a design decision in the toolkit, or you are about to
recheck a fact that shipped text relies on.

> **Status:** Research record, November 2026. These files distil the research and design notes made
> while the toolkit was built, keeping the facts that still justify its design, each with the
> version and date it was checked.

This directory holds maintainer-only research records: what was found out about Zensical, Claude
Code plugins, real documentation collections, READMEs and homepages, and third-party skills, and the
outcome of the verification spike. It is not published: `docs/internal/` is excluded from the site,
and nothing under it may be the only home of a fact that shipped text relies on. Facts here carry
the date they were checked and go stale; recheck against the current tool before relying on one, and
update the shipped text rather than this record.

| File | What it holds |
| --- | --- |
| [zensical.md](zensical.md) | Zensical 0.1.3 behaviour: configuration, defaults that surprise, strict mode, plugins, templates, deployment |
| [docs-collections.md](docs-collections.md) | What the gx52, bitgauge and monmux documentation showed: hazards, counts, slug facts |
| [plugin-mechanisms.md](plugin-mechanisms.md) | Claude Code plugin, marketplace and skill mechanics; OpenCode and shared installs |
| [readme-homepage.md](readme-homepage.md) | The README and homepage study behind the README lint targets and the landing page |
| [reference-skills.md](reference-skills.md) | The third-party skills studied, what was adapted and what was left out |
| [p0-spike.md](p0-spike.md) | The P0 verification spike: twelve assumptions checked and the design changes they caused |

The publication rules that put these files here are in
[the publication policy](../../../skills/repo-docs/references/publication-policy.md).
