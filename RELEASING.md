# Releasing

The short version. How it works, the one-time setup and what to do when something fails are in
[docs/internal/release.md](docs/internal/release.md).

Needs the `gh` CLI, logged in with write access to the repository. Every change for the release
is already merged to `main` with CI green.

## A release

```sh
gh workflow run release.yaml -f dry_run=true   # show the version svu derives; change nothing
gh workflow run release.yaml                   # open the release/repo-docs-toolkit--vX.Y.Z pull request
gh workflow run release.yaml -f version=0.1.0  # or name the version yourself
```

Without `version`, svu derives it from the Conventional Commits since the last
`repo-docs-toolkit--vX.Y.Z` tag: `feat` is a minor, `fix` a patch, `!` a major. The workflow
writes it into `.claude-plugin/plugin.json` (`make release-bump`) and opens a pull request with
that one change. Merge it with a merge commit once its CI is green: the merge tags
`repo-docs-toolkit--vX.Y.Z` and publishes the GitHub release.

## When something fails

Before the merge, dispatch the workflow again with the same version: it reuses the open pull
request and runs CI on it again. After the merge, re-run the failed Release run (all jobs): every
step is idempotent and finishes what the first run started. Details are in the recovery section of
[docs/internal/release.md](docs/internal/release.md#recovery).
