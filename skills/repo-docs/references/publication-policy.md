# Publication policy

Read this when you decide whether a file or section belongs on the published site or in
`docs/internal/`, or where an archived record goes. Published means part of the documentation
website; internal means kept in the repository for maintainers.

## Contents

- Ground truth
- The test
- By content type
- Gray zones
- Mixed files
- Constraints that override the test
- Defaults under uncertainty
- Lifecycle signals
- The internal/ layout

## Ground truth

- "Internal" means "not part of the documentation website", not "private". In a public repository
  everything is public on GitHub. Secrets, personal paths, private infrastructure details and anything the owner does not want
  public must not be in the repository at all; moving them to internal/ fixes nothing.
- Published = docs/ minus docs/internal/ (`exclude_docs = "internal/"`). Root files (README, CONTRIBUTING,
  SECURITY, RELEASING, AGENTS.md) are never published; a page that needs their content includes it via snippets.

## The test

Publish only when all four hold:

1. **Reader**: someone outside the maintainer team benefits — a user, operator, integrator, or contributor.
2. **Current**: it describes the project as it is (or a committed near future), not how it got here.
3. **Maintained**: it will be updated when the code changes. A record that is true "as of a date" fails this.
4. **Self-contained for that reader**: it does not depend on maintainer-only access (repo secrets, admin settings)
   to be useful.

Fails any test: internal. Redundant with another page: merge it into that page, then archive the
original; never delete it silently.

## By content type

| Publish | Internal |
| --- | --- |
| Tutorials, getting started, install | Release runbooks and repository-setup procedures |
| How-to guides, troubleshooting, FAQ | Spikes, research notes, prior-art surveys |
| Reference: CLI, config, API, file formats, protocols, exit codes | QA rounds, test/harness run records, audits |
| Explanation of the current design and its trade-offs | Plans, roadmaps of finished milestones, TODO trackers |
| Contributor guide: dev setup, architecture, testing (if contributions are accepted) | Rewrite/port records, superseded designs |
| Security model, verifying releases, versioning and release channels | Original requirements and source documents, kept verbatim |
| Changelog / release notes | Drafts never published (announcements, calls for testers) |
| Short forward-looking roadmap, if the owner wants one | Agent session outputs, design hand-off queues |

## Gray zones

- **Decisions/ADRs**: publish the ones that answer a "why does it work like this" a reader would ask, rewritten as
  explanation; the decision log with rejected options and dates goes to internal/history/.
- **Release process**: the maintainer procedure is internal (docs/internal/release.md, RELEASING.md cheat sheet at
  the root); the user-facing parts — version policy, channels, how to verify a release — are published.
- **Research**: raw notes internal; a finding that justifies current behaviour is rewritten into the published
  explanation page and the note is cited from internal only.
- **Roadmap**: finished milestones internal/history; open forward-looking items become a short public page or issues.
- **Design specs** (e.g. a UI spec): internal unless rewritten for users; often the raw material for a user guide.

## Mixed files: classify per section

Split living rules out of historical records before archiving (e.g. live lint rules inside a finished port
record). Nothing load-bearing may exist only in internal/: if published pages or AGENTS.md rely on a fact, the fact
lives in a published or root file.

## Constraints that override the test

- A path or heading referenced by code, tests, generators, CI messages, CLI output, shipped binaries or other
  repositories stays put (or leaves a stub) regardless of classification; record it in the move plan.
- Published pages never link into internal/ (`docstool check` reports it, and a Zensical 0.1.3 `--strict` build fails on it). Internal may link to published.

## Defaults under uncertainty

- Unsure whether to publish: put it in internal/, flag it in the report, ask.
- Unsure whether something is obsolete: keep it in internal/history/ with a status line; never delete.
- Deletion only for verified exact duplicates or empty files, listed in the report and confirmed by the owner.

## Lifecycle signals

Fully ticked checklists; dated "Done"/"as of" statements; milestone/phase IDs; "plan", "spike", "round", "draft",
"analysis" in names; first-person drafts; file not linked from anything current; claims contradicted by code or
tags; content describing a branch, tool or version that no longer exists.

## The internal/ layout

```text
docs/internal/
  README.md        what lives here and why it is not published
  release.md       maintainer procedures (plus other runbooks)
  history/         finished plans, ports, superseded designs, source requirements
  research/        spikes and research notes
  qa/              QA rounds, audits, test-run records
  notes/           anything else kept for maintainers
```

Each archived file gets a status line under its title: what it was, when, and what supersedes it.
`plan apply` writes it from the `status` of an `[[archive]]` entry, as
`> **Status:** Historical: plan for the 1.0 rewrite, completed in November 2026. Current design: architecture.md.`
