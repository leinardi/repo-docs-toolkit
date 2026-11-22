# Release procedure

The maintainer procedure for a repo-docs-toolkit release. `RELEASING.md` at the repository root is
the cheat sheet; this page is the reference behind it.

## How a release works

A release is two workflow runs of `.github/workflows/release.yaml`, both on
[leinardi/gh-reusable-workflows](https://github.com/leinardi/gh-reusable-workflows) (pinned to
v1.6.1 by commit):

1. **Bump**, on `workflow_dispatch`. `version-bump-pr` resolves the version, either the
   `version` input or svu's answer from the Conventional Commits since the last
   `repo-docs-toolkit--vX.Y.Z` tag. It runs `make release-bump VERSION=<version>`
   (`scripts/release_bump.py`), which writes the version into `.claude-plugin/plugin.json` and
   nothing else, checks that only that file changed, pushes one commit to
   `release/repo-docs-toolkit--v<version>` and opens a pull request into `main`. It dispatches CI
   on the branch, because a pull request opened with `GITHUB_TOKEN` triggers no `pull_request`
   run. With `dry_run` it only prints the version and the diff.
2. **Release**, on the push to `main` that changes `.claude-plugin/plugin.json`.
   `release-on-merge` checks that the push is the merge of exactly that bot pull request and
   waits for CI on the merge commit (30 minutes at most). Then `simple-tag-and-release` creates
   the GitHub release and with it the tag `repo-docs-toolkit--v<version>`.

The tag shape `<plugin-name>--vX.Y.Z` is the one `claude plugin tag` produces and Claude Code's
plugin dependency resolver looks for.

## One-time setup

- Settings, Actions, General: "Allow GitHub Actions to create and approve pull requests" is on.
  Without it the bump run fails.
- The branch ruleset on `main` requires the `ci-result` check and allows merge commits; squash
  and rebase merging are off, so the bump commit lands as it is.
- Settings, Pages, Source: "GitHub Actions", for the documentation site (`docs.yaml`).

## The steps

1. Check that `main` has everything the release should carry and that CI passed on it.
2. Dry run: `gh workflow run release.yaml -f dry_run=true`. Read the version in the run's log.
   Before 1.0.0, a `feat` gives a minor and a `fix` a patch; a breaking change (`!`) is still a
   major.
3. Dispatch: `gh workflow run release.yaml`, or `-f version=X.Y.Z` to choose the version.
4. Review the pull request: one commit, one changed line in `.claude-plugin/plugin.json`.
5. Merge it with a merge commit once its checks are green.
6. Watch the Release run on `main`. When it ends, the release page lists the tag and the notes
   generated from the merged pull requests.
7. Check the install from a clean Claude Code profile:
   `claude plugin marketplace add leinardi/repo-docs-toolkit`, then
   `claude plugin install repo-docs-toolkit@repo-docs-toolkit` and `claude plugin list`.

## Recovery

| What failed | What to do |
| --- | --- |
| The bump run, before a pull request exists | Fix the cause (often the Actions setting above) and dispatch again |
| The pull request is out of date or its CI failed for an unrelated reason | Dispatch again with the same version: the run reuses the open pull request and runs CI on it again |
| The Release run after the merge (cancelled, or CI was slow) | Re-run it with all jobs: every step reads the same facts again and is idempotent |
| A wrong version was merged | Do not delete or move the published tag; release the next version with the fix |
