# Plugin and skill mechanics

Read this when you change the plugin manifests, a skill's frontmatter or layout, the validation job,
or the install instructions, and need the Claude Code behaviour behind them.

> **Status:** Research record, November 2026. It collected how Claude Code plugins, skills and
> marketplaces behave, and how OpenCode and the `npx skills` installer read the same skills, so one
> repository could serve all of them. Checked on 2026-11-20 against the live Claude Code docs and a
> local Claude Code 2.1.329 (the spike on 2026-11-21 used 2.1.330) and OpenCode 2.3.2. Recheck
> against the current docs; versions move quickly.

## Contents

- Plugin layout and manifest
- Marketplace file
- Skills: discovery, frontmatter, limits
- Portability between tools
- Validation and evals
- OpenCode and shared installs
- Decisions that follow

## Plugin layout and manifest

- Standard locations at the plugin root: `.claude-plugin/plugin.json` (optional),
  `skills/<name>/SKILL.md`,
  `commands/`, `agents/`, `hooks/hooks.json`, `.mcp.json`, `bin/`. Only the manifest goes inside
  `.claude-plugin/`. A `CLAUDE.md` at the plugin root is not loaded (validate warns).
- `name` is the only required manifest key: kebab-case, no spaces, no `@` or `:`. Names that start
  with `claude-`, `anthropic-` or `cc-plugin-` are errors; `repo-docs-toolkit` is fine.
- `skills` in the manifest adds to the default scan; `commands`, `agents` and similar replace
  their default. Paths start with `./` and may not leave the plugin root. Unknown top-level keys are
  stripped (a warning, an error under `--strict`).
- `version`: setting it keeps users on that version until you change it, so bump it on each
  release or omit it. Do not set it in both the manifest and the marketplace entry. This is why
  the Release workflow writes the version into `plugin.json`.
- `claude plugin tag` creates `<name>--v<version>` tags after checking manifest and marketplace
  agree; the tag form in this repository follows it.
- The plugin root variable (CLAUDE_PLUGIN_ROOT) changes on update, so do not write state
  there; the plugin data variable (CLAUDE_PLUGIN_DATA) persists. Both are substituted in
  Markdown text, not exported to Bash.
- A top-level `bin/` is refused by claude.ai and Cowork; use `scripts/` and a root variable.
- Symlinks: inside a plugin copy they are kept only when they resolve within the plugin; links to
  elsewhere in the marketplace are dereferenced; links outside it are skipped. `claude plugin
  validate` does not follow symlinks. So `skills/` stays real directories and other tools point
  at them. This is consistent with docstool being a byte-identical copy per skill, not a link.

## Marketplace file

- `.claude-plugin/marketplace.json` needs `name`, `owner` and `plugins[]`; `description` is
  optional but `--strict` validation warns without it. A plugin entry needs `name` and `source`;
  `"./"` serves a single-plugin repository.
- Strict mode (default true) appends the entry's component fields to the manifest; setting
  `strict: false` with entry components is a conflicting-manifests load failure.
- Install: `/plugin marketplace add <owner>/<repo>`, then `/plugin install <plugin>@<marketplace>`.
  A marketplace added from a local directory loads in place each session.
- Background auto-update is off by default per marketplace; users update by command.

## Skills: discovery, frontmatter, limits

- Locations: personal, project `.claude/skills/`, `--add-dir`, plugin `skills/`. Claude Code does
  not
  read `.agents/skills`; repositories that want both link `.claude/skills` to `../.agents/skills`.
- Commands were merged into skills: a skill directory makes `/name`, namespaced as
  `/plugin:skill` for plugins. User-facing actions are therefore skills, not command files.
- All frontmatter is optional; unknown fields are silently ignored; frontmatter that fails to parse
  loads the skill with no fields.
- The listing shows `description` plus `when_to_use` truncated at 1,536 characters. The Agent Skills
  specification and the API cap `description` at 1,024 and `name` at 64 (lowercase, digits,
  hyphens, equal to the directory name). Angle brackets in descriptions display escaped.
- `disable-model-invocation: true` keeps a skill out of context entirely, so the model never
  suggests it. `allowed-tools` pre-approves tools for the invoking turn and does not restrict.
- The listing budget is about 1% of the context window; overflow drops the descriptions of
  least-used skills. After compaction each invoked skill keeps its first 5,000 tokens.
- Size guidance from the docs and the specification: keep `SKILL.md` under 500 lines, references one
  level deep, a contents list in references over 100 lines. These became the lint rules in
  `tests/test_skills_lint.py`.

## Portability between tools

- claude.ai uploads and the Skills API accept only `name`, `description`, `license`,
  `compatibility`, `metadata` and `allowed-tools`, and fail on other keys. Hence AGENTS.md rule 4:
  `SKILL.md` frontmatter has only `name` and `description`.
- Plugin agents are Claude-only (OpenCode agents use a different format) and ignore
  `permissionMode`, `hooks` and `mcpServers`; the toolkit ships none.
- Write paths relative to the skill directory. OpenCode has no `CLAUDE_SKILL_DIR` substitution, so
  commands are written as `python3 -I <skill-dir>/scripts/docstool.py`.

## Validation and evals

- `claude plugin validate <path> [--strict] [--profile directory]` exits 0 on pass, 1 on failure
  (or warnings under `--strict`), 2 on a validator error. It checks manifests, frontmatter and
  paths, warns on a root `CLAUDE.md`, and does not check a root-level `SKILL.md`. The directory
  profile adds submission checks (README, an `icon.png` of 512 to 2048px square).
- The spike showed it runs unauthenticated ([p0-spike.md](p0-spike.md), S11), so it is a CI job.
- `claude plugin eval` (Claude Code 2.1.269 or newer) runs each case with and without the plugin
  and grades with regex, tool-use, file and LLM graders; it costs model usage on every run and
  publishes a report unless told not to. It is not interchangeable with the skill-creator evals
  format. Neither is part of the toolkit's CI.

## OpenCode and shared installs

- OpenCode reads `.claude/skills`, `.agents/skills` and `.opencode/skills`, and extra paths from
  its config. The skill ID comes from the directory name; frontmatter `name` is a label. A skill
  without a description is not advertised. It does not read the Claude plugin cache.
- `npx skills add <owner>/<repo>` (vercel-labs/skills) discovers `skills/` and skills declared in
  the Claude manifests, symlinks by default, needs Node 22.20 or newer and sends telemetry unless
  disabled. It is the route considered for installing the skills into OpenCode and other agents.
- Do not also link the skills into `~/.claude/skills`: Claude Code would load them twice.

## Decisions that follow

1. Root marketplace and manifest, real `skills/<name>/` directories, each skill self-contained
   (own `references/`, `assets/`, `scripts/`).
2. Skills for every user action; no agents, commands or hooks.
3. Names equal directories; descriptions in third person, what and when, under 1,024 characters.
4. Gates: `claude plugin validate . --strict` in CI, the skill lint in the test suite.
5. An explicit version in `plugin.json`, written by the release bump.
