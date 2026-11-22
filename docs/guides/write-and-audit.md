# Write, audit and maintain docs

The repo-docs skill writes and checks documentation against the repository it describes. It has
three everyday modes, chosen from what you ask for.

## Audit

Ask for an audit of the docs, or of one page:

```text
Audit docs/ against the code and report what is wrong. Do not change anything yet.
```

The skill runs `docstool inventory`, `docstool check` and `docstool drift`, then reads the code
behind every claim it can trace. Each finding names the doc line and the source line, with a
severity (`Blocking`, then `P0` to `P3`) and a confidence:

- **verified**: the skill opened both sides, or reproduced the tool's result, and they disagree;
- **likely**: a strong inference, with one side not fully confirmed;
- **unverified**: a lead from a script or a heuristic, not yet confirmed.

The report ends with the checks that ran and what was not tested. Only verified findings are fixed
without asking, and only once you ask for fixes.

## Write

Ask for a page by what the reader needs, such as "a getting-started guide for the CLI" or "a
reference page for the config file". The skill picks the page type (tutorial, how-to, reference
or explanation), takes every command, flag and default from the code, its `--help` output when
that is safe to run, the tests or you, and marks anything it cannot confirm as
`TODO(verify: …)` instead of guessing. It keeps the project's own terminology and house style:
line wrapping, heading case, admonition syntax.

## Maintain

After a change to the code, ask the skill to update the docs for it:

```text
Update the docs for the changes since v1.4.0.
```

It runs `docstool drift --base v1.4.0`, which lists the commands, flags, environment variables and
paths that the diff removed or renamed but the docs still name, and the ones it added that no doc
mentions. Generated regions and changelogs that release tooling writes are left alone.

## Where the rules live

The skill's references hold the details an agent follows:
[evidence][repo-docs-evidence],
[page types][repo-docs-page-types],
[writing rules][repo-docs-writing-rules],
[audit][repo-docs-audit] and
[maintain][repo-docs-maintain].

[repo-docs-evidence]: https://github.com/leinardi/repo-docs-toolkit/blob/main/skills/repo-docs/references/evidence.md
[repo-docs-page-types]: https://github.com/leinardi/repo-docs-toolkit/blob/main/skills/repo-docs/references/page-types.md
[repo-docs-writing-rules]: https://github.com/leinardi/repo-docs-toolkit/blob/main/skills/repo-docs/references/writing-rules.md
[repo-docs-audit]: https://github.com/leinardi/repo-docs-toolkit/blob/main/skills/repo-docs/references/audit.md
[repo-docs-maintain]: https://github.com/leinardi/repo-docs-toolkit/blob/main/skills/repo-docs/references/maintain.md
