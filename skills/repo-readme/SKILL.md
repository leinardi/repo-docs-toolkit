---
name: repo-readme
description: >-
  Writes and reviews a repository's README and community files (CONTRIBUTING, SECURITY,
  CODE_OF_CONDUCT, a short RELEASING cheat sheet and the CHANGELOG policy) in a lean, branded style:
  50 to 150 lines, logo and tagline, at most four badges, emoji only as section prefixes, a gateway to
  the docs rather than a copy of them, with every command and claim verified against the repository.
  Use when the user asks to create, rewrite, shorten or review a README, add badges or a logo header,
  add a contributing guide, security policy, code of conduct or release checklist, or make a
  repository look professional.
---

# README and repository files

The README and the community files around it: CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, a short
RELEASING cheat sheet and the CHANGELOG policy. A README here is lean and branded: 50 to 150
lines, a centered logo and tagline, at most four badges, emoji only as section prefixes, and a
gateway to the docs rather than a copy of them.

## The checker

Deterministic checks run through the bundled script (Python 3.11 or newer, standard library
only). It reads the repository and writes nothing but the files a command documents:

```sh
python3 -I <skill-dir>/scripts/docstool.py <command> --root <repo>
```

`<skill-dir>` is the directory that holds this file.

| Exit | Meaning | What you do |
| --- | --- | --- |
| 0 | No findings, every required input analysed | Report it as clean |
| 1 | Findings | Fix them or report them |
| 2 | Usage error | Read the message; fix the call |
| 3 | Coverage incomplete: the README or the homepage could not be read or parsed | Never report it as clean; name the input |

| Command | Used for |
| --- | --- |
| `docstool readme` | The README rules, and drift against the homepage with `--home docs/index.md` |
| `docstool inventory` | The root files, couplings to them, duplicates, the changelog generator |
| `docstool check` | Links and anchors in every Markdown file (`--scope repo` for the root files) |
| `docstool drift` | Commands, flags and environment variables the README names, against the code |
| `docstool slug` | The GitHub anchor of a heading, emoji included |

## Rules

1. **Facts come from the repository.** Every command, flag, version, badge, channel and claim
   comes from the code, the manifest, the workflows, `--help` output that is safe to run, or the
   user. Anything else is `TODO(verify: ...)`, never a guess. The project's own docs are leads,
   not evidence: they drift, so confirm every command, key and variable a doc gives in the code
   before copying it.
2. **Never invent** a logo, a feature, a support channel, a contact address, a response time or
   a badge for something that does not exist.
3. **50 to 150 lines, no reference material.** Most READMEs land near 100. Full install matrices, every command, configuration
   and changelogs go in the docs; the README links to them. When the repository has too few
   verifiable facts to reach 50 lines, a shorter README is right: report the `readme-length`
   finding with that reason, never pad.
4. **At most four badges**, one style, in the order CI, version, docs, license.
5. **Emoji only as the first character of a level-2 heading**, from the fixed list in
   [readme.md](references/readme.md); in-page links use GitHub's `#-slug` form.
6. **`<picture>` always has an `<img>` fallback**, and images are absolute URLs when the README is
   also a registry page.
7. **The homepage is canonical.** With a Zensical homepage, the README's tagline, feature titles
   and first install command are the homepage's, verbatim.
8. **Nothing is lost.** Content removed from a README lands in the docs first (R4).
9. **No side effects without agreement.** Read-only commands only; running the project to capture
   usage output, or any `gh` call that writes, needs the user's agreement.

## Steps

1. **Detect the project type**: command-line tool, GTK or Flatpak app, library or service, from
   the manifest, the workflows and the files (`*.metainfo.xml`, `Cargo.toml` `[[bin]]`,
   `compose.yaml`). Without a manifest, the build files (`meson.build`, `Makefile`), the
   sources and the install instructions decide; when they do not, ask.
2. **Map the root**:

   ```sh
   python3 -I <skill-dir>/scripts/docstool.py inventory --root <repo> --section root --format json --out <scratch>/inventory.json
   ```

   Note the couplings to README headings (a link to `README.md#install` from the docs or code
   freezes that heading), the duplicates between root files and docs, and `changelog_generators`.
   With `--out` nothing is printed: read the file. `--section root` narrows the file list, not
   the findings, which cover couplings in the whole repository.
3. **Edit or rewrite** (gate R1). An existing README with real content gets an incremental edit
   toward the rules; a rewrite starts from [readme-templates.md](references/readme-templates.md).
4. **Draft** following [readme.md](references/readme.md), every placeholder filled from the source
   the templates name.
5. **Check**, with `--home` only when `docs/index.md` exists (without it the run exits 3):

   ```sh
   python3 -I <skill-dir>/scripts/docstool.py readme --root <repo> --home docs/index.md
   python3 -I <skill-dir>/scripts/docstool.py check --root <repo> --scope repo
   python3 -I <skill-dir>/scripts/docstool.py drift --root <repo> --scope repo
   ```

   A `readme-drift` finding on the homepage means the README has something the homepage lacks:
   fix whichever is wrong, not always the README. `drift` checks commands in code blocks and
   inline code; a command written in plain prose is yours to check. A P3 `unverified` lead, such
   as `make-missing` in a repository with no Makefile, makes the run exit 1 although it may name
   another project's command: check it, then fix it or report it as a lead you ignored, with the
   reason.
6. **Community files** per [repo-files.md](references/repo-files.md), only those the decision table
   calls for.

## Stop and ask

| Gate | When |
| --- | --- |
| R1 | Rewriting a README instead of editing it |
| R2 | The project has no logo |
| R3 | Adding or replacing a code of conduct |
| R4 | Removing content from the README |
| R5 | More badges than the four defaults |
| R6 | What to do with an existing CHANGELOG |
| R7 | A security contact or reporting channel cannot be verified |

## Before you say done

- `docstool readme` exits 0 (with `--home` when there is a homepage), or every remaining
  finding is reported with a reason. A `readme-todo` finding means a question for the owner is
  still open: list it.
- Every command in the README was checked against the repository; say which you ran.
- Removed content has a home in the docs, linked from the README.
- The report lists what was checked, with the command, and what was not.
