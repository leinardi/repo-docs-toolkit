# Deploying to GitHub Pages

Read this when a Zensical site should be published on GitHub Pages, or when an existing docs
deployment (`mkdocs gh-deploy`, a `gh-pages` branch, an unpinned workflow) is replaced. The
shipped workflow builds every pull request with `--strict` and deploys the default branch.

## The workflow

`assets/workflows/docs.yaml` goes to `.github/workflows/docs.yaml`. It:

- runs on pull requests (build only), on pushes to `main` and on manual dispatch;
- installs uv and builds with `uv run --project tools/docs --locked zensical build --strict --clean`,
  so Zensical comes from the committed `uv.lock` ([config.md](config.md) covers the project);
- uploads `site/` and deploys it with GitHub's Pages actions, in a separate job that alone has
  `pages: write` and `id-token: write`;
- pins every action to a full commit SHA, with the tag in a comment.

Before you copy it, check against the repository:

- **The default branch.** Replace `main` (three places) when the branch is another
  (`git symbolic-ref refs/remotes/origin/HEAD`; without a remote, ask).
- **`site_dir`.** The upload path is `site`; change it when the config sets another.
- **Action versions.** The SHAs are the releases current when this skill was written. When the
  repository updates actions with Dependabot or Renovate, it updates these too; otherwise look up
  the current release SHAs (`gh api repos/actions/deploy-pages/releases/latest`) and say so in
  the report.
- **The docs project.** `DOCS_UV_PROJECT` at the top names `tools/docs`; change it when the uv
  project lives elsewhere. A repository that keeps a hashed requirements lock instead keeps its
  own two steps in place of setup-uv and the uv build: `pip install --require-hashes -r <lock>`
  after `actions/setup-python`, then `zensical build --strict --clean`.
- **make-common.** A repository that builds its docs with make-common's `zensical.mk` in uv mode
  can run `make docs-build` instead of the build step; it builds with `--strict` too.

## What the user does

Enabling Pages is a repository setting, gate Z2: tell the user, do not change it yourself.

1. Settings, Pages, Source: **GitHub Actions**. Until then the deploy job fails.
2. For a custom domain: add `docs/CNAME` with the domain (Zensical copies it to the site root),
   set `site_url` to it, and set the domain in the Pages settings with DNS at the registrar.
3. After the first deployment, open the live site and check the homepage, one deep page, search
   and a redirect, if any.

## Replacing an older deployment

- `mkdocs gh-deploy` pushes to a `gh-pages` branch. Switching the Pages source to GitHub
  Actions leaves that branch unused; deleting it is the user's decision.
- Switch only after the Zensical build has passed the URL baseline ([migrate.md](migrate.md),
  Step 4) and the user agrees (Z1). Remove the old job in the same change, so two workflows never
  deploy at once.
