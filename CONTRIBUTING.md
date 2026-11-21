# Contributing

Read [`AGENTS.md`](AGENTS.md) before changing anything: it holds the rules a change must not break.
It applies equally to human and AI-assisted contributions.

## Setup

Install [`pre-commit`](https://pre-commit.com/), then install the hooks once with
`make pre-commit-install`. It installs both the `pre-commit` and the `commit-msg` hooks, so commit
messages are checked when you commit, not when the release runs.

```console
make dev-deps         # the pinned development dependencies, once per checkout
make test             # the unit tests
make check            # pre-commit on every file
make check-stage      # pre-commit on the staged files only
make sync-vendored    # after editing skills/repo-docs/scripts/docstool.py
make validate-plugin  # needs the claude CLI
```

`make help` lists every target. `make check` only sees files git already knows about, so run
`git add -N` on a new file before it. The tests need Python 3.11 or newer.

## Changing guidance or docstool

- Verify every claim about Zensical, MkDocs, GitHub or Claude Code against the tool itself, its
  source or its official docs, and say in the pull request how you verified it.
- A new docstool check comes with a fixture that triggers it and with the `clean` fixture still
  reporting nothing.
- Edit only the canonical `skills/repo-docs/scripts/docstool.py`; `make sync-vendored` writes the
  copies in the other skills.

## Pull requests

Every change lands through a pull request against `main` with the required CI checks green.

## Commit messages

All commits must follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/)
with a scope: `<type>(<scope>)[!]: <description>`. The `conventional-pre-commit` hook enforces this
on `commit-msg`, and the `conventional-commits` CI job checks it again on every pull request.
Release notes are not built from these messages: `gh release create --generate-notes` lists the
merged pull requests by title.

Use a lower-case, imperative description:

```text
fix(docstool): resolve anchors on headings that start with an emoji
feat(zensical-site): add a migration checklist for mkdocs hooks
ci(plugin): pin the Claude Code CLI used by plugin-validate
```

Mark breaking changes with `!` before the colon or a `BREAKING CHANGE: <description>` footer.

## Versioning

A release with no explicit version is derived from these types by svu: since the last release,
any `feat` makes the next release a minor, any `fix` a patch, and `!` or a `BREAKING CHANGE:`
footer a major; every other type (`build`, `chore`, `ci`, `docs`, `perf`, `refactor`, `revert`,
`style`, `test`) bumps nothing, so a change users receive is a `fix` even when it is a performance
improvement or a refactor.

Pull requests are merged with merge commits; squash and rebase merging are disabled. Every commit in
a pull request therefore lands on `main` as it is and counts toward the version, so each commit
needs a correct type, not just the pull request as a whole.

svu matches `feat` and `fix` anywhere in a subject, so a word ending in either directly before a
colon (`prefix:`) bumps as that type. It also reads the message body for a `BREAKING CHANGE:`
footer, and the merge commit's body is the pull request's title: give the pull request a title
whose type matches what it ships.
