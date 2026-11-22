# Maintain

Read this when the docs must follow a code change: a branch, a pull request, a commit range, or
"update the docs for what I just did". Maintenance is diff-driven: only the docs the change
touches are edited.

## Contents

- Step 1: resolve the base
- Step 2: map the change to the docs
- Step 3: update
- Step 4: generated docs and regions
- Step 5: changelogs
- Step 6: verify and report

## Step 1: resolve the base

Use the base the user names. Otherwise, in this order:

1. A pull request: its base branch (`gh pr view --json baseRefName`, read-only).
2. A feature branch: `git merge-base HEAD origin/<default-branch>` (the default branch from
   `git symbolic-ref refs/remotes/origin/HEAD`).
3. Uncommitted work only: `HEAD`, and include the working tree.
4. The last commits on the default branch ("I just committed X"): `HEAD~<n>`, where n is the
   number of commits the user means; confirm it when unclear.

State the base you used in the report. Read the diff yourself as well (`git diff <base>...HEAD`, and
`git diff` for uncommitted work); the checker sees tokens, you see meaning.

## Step 2: map the change to the docs

```sh
python3 -I <skill-dir>/scripts/docstool.py drift --root <repo> --base <base> --scope docs --format json --out <scratch>/drift.json
```

`--base` compares flags, environment variables and make targets defined before and after the base,
then reports:

- `removed-still-documented` (P1, verified): a token that no longer exists anywhere but a doc still
  names it. Search for its replacement in the diff before editing.
- `added-undocumented` (P3, likely): a new token no doc mentions. Decide with the user whether it
  is public (gate G8 when it needs a new page).

A new token that a doc already names produces no finding: re-read that doc's claim against the
new code. `drift --base` also reports drift that predates the base (an old `flag-unknown`, a
missing make target). Check each against `git show <base>:<doc>`; list the pre-existing ones under
"Outside this change" in the report and leave them alone unless the user asks.

Then find what tokens cannot show. From the diff, list the changed public surface: CLI behaviour
and output, config keys and defaults, file formats, API signatures, exit codes, supported
platforms and versions, renamed or moved files. For each item, search the docs for the old and
new names (`grep -rn` over the Markdown, plus the inventory's `couplings` for paths). Mark each doc
location confirmed (the doc states the old behaviour) or likely (the doc is about the area but
does not state the detail).

## Step 3: update

- Edit only the confirmed locations, plus likely ones the user agrees to.
- Keep the page's structure, terminology and customisations (local notes, examples the owner
  added, ordering). Replace the stale fact, not the paragraph.
- New facts pass the facts gate (evidence.md). A new flag documented from its definition cites the
  definition.
- When the change is user-visible and no page covers it, propose where it goes before writing a
  page (page-types.md).
- Paths and headings that code or tests cite (`frozen` in the inventory) keep their names unless
  the change itself renames them; then update the citing lines in the same change (gate G10 for
  code and CI text).

## Step 4: generated docs and regions

- A page or region produced by a generator (the inventory's `generated_regions`, a `go:generate`
  line, a pre-commit hook that rewrites a doc, a "do not edit" header) is changed by changing the
  generator's input and regenerating.
- Check that the generator exists (the program or package the `go:generate` line, hook or make
  target runs). When it does not, report the region as unregenerable; do not ask to run it.
- Regenerating writes into the repository. Name the command (from the Makefile, the hook or the
  `go:generate` line) and ask before running it, unless the user already asked you to run the
  project's generators.
- Never hand-edit between the markers, even to fix a typo; fix the source.
- Check that the regenerated output is the only change in that file.

## Step 5: changelogs

`changelog_generators` in the inventory lists release tooling that writes the notes (goreleaser,
release-please, git-cliff, changesets, semantic-release, towncrier, `gh release --generate-notes`).

- When one is listed, do not edit `CHANGELOG.md` or release notes by hand. The change's commit
  messages (or changeset or fragment files) are the input; check that they describe the change.
- When none is listed and a hand-written changelog exists, add an entry under its unreleased
  section in its existing format: what changed, what the reader must do, and a migration note for
  anything breaking.
- When neither exists, do not create a changelog; mention it in the report.

## Step 6: verify and report

1. Re-run `drift --base <base>`: every `removed-still-documented` finding is gone or explained.
   For a rename, a one-line migration note naming the old token is good practice; its finding is
   then explained in the report.
2. Run `docstool check --scope docs` and the repository's own doc checks.
3. Report: the base, the changed surface, each doc location with its status (updated, proposed,
   left as is and why), regenerated files with the command used, and "Checks run" and "Not
   tested".
