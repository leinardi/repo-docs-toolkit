# Getting started

repo-docs-toolkit is three agent skills and the checker they share. Install
it once, then ask your agent for what you need in plain words: "audit the docs", "move docs/ to a
Zensical site", "rewrite the README".

## Requirements

- Python 3.11 or newer, for docstool. It uses only the standard library.
- git: docstool reads the history with read-only commands.
- Zensical, only for building a site. The skills pin and test Zensical 0.1.3.

## Claude Code

Add the repository as a plugin marketplace, then install the plugin from it. In a Claude Code
session:

```text
/plugin marketplace add leinardi/repo-docs-toolkit
/plugin install repo-docs-toolkit@repo-docs-toolkit
```

`/plugin install` opens the plugin's details, where you choose the scope: you in every project,
everyone working on this repository, or you in this repository only. From a shell, the same two
steps install for you in every project:

```sh
claude plugin marketplace add leinardi/repo-docs-toolkit
claude plugin install repo-docs-toolkit@repo-docs-toolkit
```

Add `--scope project` to the install to enable the plugin in the repository's
`.claude/settings.json`; each collaborator still runs the install once in their clone. Claude
Code does not update plugins from third-party marketplaces on its own; run
`claude plugin update repo-docs-toolkit@repo-docs-toolkit` to get a new release.

## npx skills

The [`skills`](https://github.com/vercel-labs/skills) installer (it needs Node.js 22.20 or newer)
copies the skills into an agent's skills directory:

```sh
npx skills add leinardi/repo-docs-toolkit                    # asks which skills and agents
npx skills add leinardi/repo-docs-toolkit -s repo-readme     # one skill
npx skills add leinardi/repo-docs-toolkit -a claude-code -g  # for Claude Code, in your home directory
```

Without `-g` the skills go into the current project: `.claude/skills/` for Claude Code.

## OpenCode

OpenCode reads skills from `.opencode/skills/`, `.claude/skills/` and `.agents/skills/` in a
project, and from `~/.config/opencode/skills/`, `~/.claude/skills/` and `~/.agents/skills/` in
your home directory. `npx skills` installs there:

```sh
npx skills add leinardi/repo-docs-toolkit -a opencode       # .agents/skills/ in this project
npx skills add leinardi/repo-docs-toolkit -a opencode -g    # ~/.config/opencode/skills/
```

If you also use Claude Code, OpenCode can load the skills straight from the plugin's marketplace
clone instead, so one update serves both. Add the clone's `skills/` directory to the `skills`
array of your `opencode.json` or `opencode.jsonc`:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "skills": ["~/.claude/plugins/marketplaces/repo-docs-toolkit/skills"],
}
```

OpenCode allows directories outside the project by default. If your config asks before them
(`external_directory` rules), allow the clone:

```jsonc
{
  "permissions": [
    { "action": "external_directory", "resource": "~/.claude/plugins/marketplaces/repo-docs-toolkit/*", "effect": "allow" },
  ],
}
```

Use one route, not both. OpenCode names a skill by its file path, so the same skills installed
with `npx skills` and listed in `skills` load twice. The `skills` array and the permission rules
are from OpenCode's current documentation; an older OpenCode release may not have them, and
`npx skills` works with every release.

## Other agents

Each skill is a self-contained directory: a `SKILL.md`, its references and assets, and its own
copy of docstool. Copy `skills/repo-docs`, `skills/zensical-site` and `skills/repo-readme` from
the repository into the directory your agent loads skills from.

## First run

Open a repository and ask for an audit:

```text
Audit the docs in this repository against the code.
```

The repo-docs skill starts with `docstool inventory` and `docstool check`, then reports each
finding with the doc line and the source line behind it. It changes nothing until you ask it to.
The [guides](guides/write-and-audit.md) cover the other tasks.
