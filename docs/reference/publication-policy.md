# Publication policy

When the repo-docs skill restructures a docs tree, it decides for each file, and for each section of
a mixed file, whether it belongs on the documentation site or in `docs/internal/`. This is the
rule it applies.

"Internal" means "not on the documentation site", not "private". In a public repository
`docs/internal/` is as public as the rest of it; secrets and personal data do not belong in the
repository at all. The site publishes `docs/` minus `docs/internal/`
(`exclude_docs = "internal/"`).

## The test

A page is published only when all four hold:

1. **Reader:** someone outside the maintainers benefits: a user, an operator, an integrator or a
   contributor.
2. **Current:** it describes the project as it is, not how it got here.
3. **Maintained:** it will be updated when the code changes. A record that is true "as of a date"
   fails this.
4. **Self-contained:** it is useful without maintainer-only access, such as repository secrets or
   admin settings.

A page that fails any of them goes to `docs/internal/`. A page that repeats another is merged into
it, and the original is archived, never silently deleted.

## By content type

| Published | Internal |
| --- | --- |
| Tutorials, getting started, install | Release runbooks and repository-setup procedures |
| How-to guides, troubleshooting, FAQ | Spikes, research notes, prior-art surveys |
| Reference: CLI, config, API, file formats, exit codes | QA rounds, test-run records, audits |
| Explanation of the current design | Plans, finished roadmaps, TODO trackers |
| Contributor guide, when contributions are accepted | Port records, superseded designs |
| Security model, verifying releases, versioning | Original requirements, kept verbatim |
| Changelog or release notes | Drafts never published |

## What overrides the test

- A path or heading that code, tests, CI, CLI output, a shipped binary or another repository
  cites stays where it is, or leaves a stub, whatever its classification.
- Published pages never link into `docs/internal/`. `docstool check` reports such a link, and a
  strict Zensical build fails on it.

## When in doubt

The skill puts the page in `docs/internal/`, flags it in its report and asks. It never deletes
anything except an empty file or an exact duplicate, and only after you confirm.

The full policy, with the gray zones and the lifecycle signals the skill looks for, is the skill's
[publication policy reference][repo-docs-publication-policy].

[repo-docs-publication-policy]: https://github.com/leinardi/repo-docs-toolkit/blob/main/skills/repo-docs/references/publication-policy.md
