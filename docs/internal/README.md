# Internal docs

This directory holds the project's internal documentation: material kept in the repository for
maintainers but not published on the documentation site (the site config excludes `internal/`).
"Internal" is not "private": in a public repository everything here is public too, so secrets
and personal data never belong here.

| Directory | What lives there |
| --- | --- |
| `release.md` and other runbooks | Maintainer procedures: releasing, repository setup |
| `history/` | Finished plans, ports, superseded designs, original requirements |
| `research/` | Spikes and research notes |
| `qa/` | QA rounds, audits, test-run records |
| `restructure/` | The artifacts of a docs restructure: plan, baselines, receipts |
| `notes/` | Anything else kept for maintainers |

Each archived file opens with a status line saying what it was, when, and what supersedes it.
Published pages never link here; pages here may link to published ones.
