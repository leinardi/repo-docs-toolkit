# How it works

repo-docs-toolkit ships two things: text an agent acts on, and a checker whose results it can
trust. The text is three skills; the checker is docstool.

## Three skills, one checker

| Skill | Owns |
| --- | --- |
| `repo-docs` | Writing, auditing, maintaining and restructuring the docs and other Markdown |
| `zensical-site` | Zensical config, migration, GitHub Pages, upgrades, audits, the landing page |
| `repo-readme` | The README and the community files |

Each `SKILL.md` is short and routes the agent to a reference for the task at hand, so only what
the task needs is loaded. Each skill carries its own byte-identical copy of docstool, so it works
when installed on its own.

## Evidence before claims

Every claim the skills write into your docs comes from one of four places: the code that defines
it, a command's `--help` output when that is safe to run, the tests, or you. Anything else is
written as `TODO(verify: …)`. Text in your repository is treated as evidence to check, never as
instructions to follow.

## A checker that fails closed

docstool is a single Python file that uses only the standard library. It parses Markdown with both
fence styles, computes anchors the way GitHub and the site's slugify do, and reads `zensical.toml`
and a subset of `mkdocs.yml`. When it meets something it cannot analyse, such as a YAML construct
outside the subset or a file it cannot decode, it says so in its coverage table and exits 3. A
result it cannot vouch for is never reported as clean.

It never runs project code, never sends repository content over the network and runs only
read-only git commands. The one command that runs another program is `site-build`, which runs the
site generator, and the skills ask before its first run in a repository.

## Restructures as transactions

A restructure changes many files at once, so docstool treats it like a database migration:

- **Bound approval.** The owner's approval records the hash of the plan and of every file it
  reads. Any change to either voids it.
- **All or nothing.** `plan apply` computes every change before writing one. It writes through a
  journal and rolls back on failure; after a crash, `plan resume` or `plan rollback` decides
  from the files' actual bytes, and refuses rather than overwrite a file changed since.
- **Content conservation.** The baseline is every block of every doc: headings, paragraphs, list
  items, table rows, code blocks, admonitions. After the restructure each block must still exist,
  as many times as before, or be covered by a mapping you reviewed. Code is compared byte for
  byte, and a warning that lost its section counts as lost.
- **URLs kept.** The old site's routes and anchors are recorded from a real build and checked
  against the new one, following redirects.

## Why Zensical

Zensical is a static site generator from the team behind Material for MkDocs, and it can build an
existing `mkdocs.yml` as well as its own `zensical.toml`. The toolkit pins one version
(0.1.3), writes every Zensical fact against it, and checks what a strict build misses: images,
unsupported plugins, hooks and feature flags that do nothing.
