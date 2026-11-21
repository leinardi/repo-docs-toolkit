# Community and repository files

Read this when the user asks for a contributing guide, a security policy, a code of conduct, a
release checklist or a changelog, or when a README links to one of them that is missing or wrong.
Each file has one job; when two files say the same thing, one of them links to the other.

GitHub finds these files at the repository root, in `docs/` or in `.github/`. Keep them at the
root unless the repository already puts them elsewhere.

## Contents

- [Decision table](#decision-table)
- [CONTRIBUTING.md](#contributingmd)
- [SECURITY.md](#securitymd)
- [CODE_OF_CONDUCT.md](#code_of_conductmd)
- [RELEASING.md](#releasingmd)
- [CHANGELOG.md](#changelogmd)
- [Applying the table to an existing repository](#applying-the-table-to-an-existing-repository)

## Decision table

| File | Create when | Contents | Never |
| --- | --- | --- | --- |
| CONTRIBUTING.md | The project accepts contributions (ask for a personal repository) | How to build and test (the commands the Makefile or CI runs), the commit convention a hook or CI enforces, how pull requests are reviewed; a link to AGENTS.md for the rules it holds | Repeat AGENTS.md or the docs; state a rule nothing enforces as if something did |
| SECURITY.md | The project ships something others run: a binary, an app, a library, a service | Supported versions as the project really handles them; private reporting through GitHub when it is enabled, or a contact the owner confirmed | Invent a response time, a support window or an email (R7) |
| CODE_OF_CONDUCT.md | The project has a community beyond its owner, and the owner wants one (R3) | The Contributor Covenant 3.0, verbatim, with the reporting contact filled in; or a link to the code the project already follows (GNOME's) | Paraphrase or edit the covenant's text; add one next to an existing code |
| RELEASING.md | Releases are cut by hand with a command sequence | The short version, at most 40 lines: prerequisites, the release commands, how to resume; a link to `docs/internal/release.md` | Hold the full procedure (it goes in `docs/internal/release.md`); list commands that are not in the Makefile or workflows |
| CHANGELOG.md | Releases are not documented anywhere else | Keep a Changelog sections per release, newest first | Exist beside release tooling that generates notes (release-please, semantic-release, GitHub generated notes, metainfo `<releases>`): link to those instead |
| LICENSE | Never on your own initiative | Only the text of the licence the owner chose | Change or add one without the owner |

## CONTRIBUTING.md

- Build and test commands come from the Makefile, the manifest and the CI workflow; check that
  each target exists.
- When the repository has AGENTS.md (or another contributor handbook), link to its sections for
  the commit convention and the validation steps instead of copying them; a copy drifts.
- Name the checks a pull request must pass as CI names them.

## SECURITY.md

Start from `assets/SECURITY.template.md`. Check private vulnerability reporting before you
point to it:

```sh
gh api repos/<owner>/<repo>/private-vulnerability-reporting
```

`{"enabled":true}` means the "Report a vulnerability" link works. Anything else: ask the owner
how they want reports (gate R7). Supported versions follow what the project does: "the latest
release" when fixes only ship in new releases.

## CODE_OF_CONDUCT.md

`assets/CODE_OF_CONDUCT.contributor-covenant.md` is the Contributor Covenant 3.0 as published
at contributor-covenant.org (the current version when this skill was written), under CC BY-SA
4.0. Copy it unchanged and replace the one `[NOTE: describe your means of reporting here.]`
with a contact the owner confirmed; the second NOTE, about the enforcement ladder, stays unless
the owner has their own process. Adding or replacing a code of conduct is always the owner's call
(R3).

## RELEASING.md

Start from `assets/RELEASING.template.md`. It is a cheat sheet for the maintainer: the commands
in order, what to run again when one fails, and a link to the full procedure in
`docs/internal/release.md` (unpublished, as repo-docs' publication policy says). When the
repository has both and they repeat each other, the cheat sheet keeps the commands and the
internal doc keeps the explanation; merging them is repo-docs' restructure mode. When the full
procedure is still published (`docs/release.md`), link to it where it is, and raise its place
with the owner: under the publication policy it belongs in `docs/internal/`, and moving it is a
restructure.

## CHANGELOG.md

`docstool inventory` reports `changelog_generators`: when one is found, notes are generated and
a hand-written CHANGELOG.md is not added. An existing CHANGELOG.md that stopped being updated is
gate R6: the owner chooses between a pointer to where release notes live now, keeping it as a
record with a status line ("Not updated after <last version>; later releases are on <where>"),
or bringing it up to date from the tags. Where notes live now (the releases page, generated
notes, metainfo `<releases>`) is something you find in the repository or ask; never assume it.

## Applying the table to an existing repository

For each root file `docstool inventory --section root` lists:

1. Name its job from the table. A file with no job in the table (a TODO, notes) is repo-docs'
   business, not this skill's.
2. Check its contents against the "Contents" and "Never" columns, and its commands against the
   repository.
3. Find what it repeats from another file (`inventory`'s `duplicates` lists exact and near
   copies): the copy goes, replaced by a link, after the owner agrees when text is removed.
4. Report one line per file: keep, fix (what), shorten (what moves where), or ask (which gate).
