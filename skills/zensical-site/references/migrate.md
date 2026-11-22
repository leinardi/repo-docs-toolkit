# Migrating to Zensical

Read this when a project moves to Zensical from MkDocs or Material for MkDocs, or when a plain
`docs/` folder that GitHub renders becomes a site. The goal is the same site at the same URLs:
every old page and anchor still resolves, and the old deployment stays until the new one is
proven. Facts are for Zensical 0.1.3.

## Contents

- [Before you start](#before-you-start)
- [Step 1: Baseline the old site](#step-1-baseline-the-old-site)
- [Step 2: Audit what Zensical will not do](#step-2-audit-what-zensical-will-not-do)
- [Step 3: Build with Zensical](#step-3-build-with-zensical)
- [Step 4: Verify the URLs](#step-4-verify-the-urls)
- [Step 5: Switch the deployment](#step-5-switch-the-deployment)
- [From mkdocs.yml to zensical.toml](#from-mkdocsyml-to-zensicaltoml)
- [What Zensical drops silently](#what-zensical-drops-silently)
- [From plain docs/ to a site](#from-plain-docs-to-a-site)
- [From other generators](#from-other-generators)

## Before you start

- Switching the generator or the deployment is gate Z1: the user decides, after seeing the
  side-by-side result.
- `site-build` runs the generator, and an MkDocs build runs the project's hooks and plugins. Ask
  before the first one in a repository (Z6). Build output goes to `<scratch>`, outside the
  repository.
- The baseline builds what is committed (`site-build --ref HEAD`, from `git archive`), so
  uncommitted edits and untracked files do not change it. Make it before you edit anything.
- Never run `zensical build` or `mkdocs build` by hand inside the repository: they write `site/`
  there. `site-build` builds in a staging copy; when you must run a generator yourself to read
  its full output, do it in a copy under `<scratch>`.

## Step 1: Baseline the old site

Build the current site with its own generator, then record every URL and anchor it produced:

```sh
python3 -I <skill-dir>/scripts/docstool.py site-build --root <repo> --ref HEAD --generator mkdocs --out <scratch>/old-site
python3 -I <skill-dir>/scripts/docstool.py check --root <repo> --built <scratch>/old-site --save-baseline <scratch>/urls.json
```

The MkDocs build needs MkDocs and every plugin the config names, at the versions the project
uses (its lock or requirements file). Install them in a scratch virtual environment after asking;
never into the user's environment.

When the old generator cannot be installed, or the project never had a site, save a
source-derived baseline instead (`check --save-baseline` without `--built`). It derives URLs
from file paths and GitHub anchors, so plugin pages and custom permalinks are missing: report the
result as "URL preservation partially verified", never as verified.

## Step 2: Audit what Zensical will not do

```sh
python3 -I <skill-dir>/scripts/docstool.py site-audit --root <repo>
```

A `hooks`, `plugin-unsupported` or `yaml-env` finding is work the old build did that the new
one will skip without an error. Record every finding in the report now: once a `zensical.toml`
exists, `site-audit` reads that file instead, and the `mkdocs.yml` findings stop appearing
although nothing replaced them. What replaces each one is the user's decision (gate Z4); build
while those questions are open, since the build shows what is lost, and settle them before
Step 5. [What Zensical drops silently](#what-zensical-drops-silently) lists the usual answers.

## Step 3: Build with Zensical

```sh
python3 -I <skill-dir>/scripts/docstool.py site-build --root <repo> --generator zensical --out <scratch>/new-site
```

This is a strict, clean build into a fresh directory. `--generator zensical` is needed while the
repository has only `mkdocs.yml`: without it, `site-build` picks MkDocs for that file.

Zensical can build `mkdocs.yml` as it is, but convert to `zensical.toml` as soon as the
migration needs a change the old build must not see: an anchor redirect (MkDocs' redirects
plugin rejects `page.md#anchor` keys, so the old build would break), a new slug style, a new
extension. Leave `mkdocs.yml` untouched so the old build stays reproducible; Zensical reads
`zensical.toml` when both exist, and `site-build --generator mkdocs` still reads `mkdocs.yml`.
Convert the old config key by key ([the table below](#from-mkdocsyml-to-zensicaltoml)); do not
start from `assets/zensical.toml`, whose landing page entries need files the project does not
have. Add only what this skill requires everywhere: `exclude_docs = "internal/"`, validation, and
GitHub-compatible `toc.slugify` (gate Z5, below).

Fix what the strict build reports in the docs or the config, never by turning `--strict` off:

- **A link that was already broken.** MkDocs does not fail on a missing anchor, so an old site
  can carry broken links that Zensical's strict build stops on. Point the link at the anchor the
  new site produces and list it in the report.
- **A new slug style changes anchors.** Adopting GitHub-compatible `toc.slugify` renames every
  anchor with punctuation, on the live site too. It is gate Z5. After the user agrees, every old
  anchor that changed needs an anchor redirect (`"page.md#old-id" = "page.md#new-id"`);
  Step 4 lists them as lost fragments.
- **Visible changes.** An extension the old site lacked (content tabs that never rendered, for
  example) changes what readers see. Make the change only if the user wants it, and list it.

## Step 4: Verify the URLs

```sh
python3 -I <skill-dir>/scripts/docstool.py check --root <repo> --built <scratch>/new-site --baseline <scratch>/urls.json
```

Every old route must be a page or a redirect that ends at one, and every old anchor must exist on
its destination or have an anchor redirect. A moved page gets a redirect
(`[project.plugins.redirects.redirect_maps]`, [config.md](config.md)). A page that a plugin
generated (gen-files, for example) has no new page to redirect to: commit its generated output as
a real page, or generate it in a step before the build (Z4), then redirect any anchor that came
out different. Changing the URL scheme (`use_directory_urls`, a new `docs_dir` layout) is gate
Z5. `check` refuses a build whose inputs changed after it was built: rebuild instead.

When the old build ran hooks or plugins whose inputs docstool cannot follow, the baseline is
partial for good, and `check --baseline` exits 3 even when every route and anchor resolves. Its
findings are still valid: fix them all. Then report "URL preservation partially verified" with
the reason the coverage table gives. `--allow-partial` only changes the exit code; it never makes
the result verified.

Then compare the two sites side by side for what no check sees: navigation order and labels,
search, code highlighting, admonitions, tabs, custom CSS. Without a browser, compare the built
HTML: the list of pages, the heading ids, the nav labels, and the classes of tabs, admonitions and
highlighted code. Report what you compared and what differs.

## Step 5: Switch the deployment

Only after Step 4 passes and the user agrees (Z1): replace the old build in CI with the Zensical
build from the hashed lock ([deploy.md](deploy.md)), and remove `mkdocs gh-deploy` or the old
workflow in the same change. Keep the old deployment running until then. When the repository
has neither a docs workflow nor `gh-deploy`, the site is published from somewhere you cannot
see: ask where before proposing anything.

## From mkdocs.yml to zensical.toml

| mkdocs.yml | zensical.toml |
| --- | --- |
| `site_name: X` and the other top-level keys | the same keys under `[project]` |
| `theme: {name: material, ...}` | `[project.theme]`; `variant = "classic"` keeps the Material look |
| `theme.palette` list | `[[project.theme.palette]]` tables |
| `plugins: [search, redirects: {...}]` | `[project.plugins.search]`, `[project.plugins.redirects.redirect_maps]` |
| `markdown_extensions:` list | one `[project.markdown_extensions.<name>]` table each; the list still replaces the defaults |
| `!!python/name:material.extensions.emoji.twemoji` | the string `"zensical.extensions.emoji.twemoji"` |
| `!ENV [VAR, default]` | no equivalent: a literal value, or a CI step that writes it before the build |
| `slugify: !!python/object/apply:pymdownx.slugs.slugify {kwds: {case: lower}}` under `toc` | `slugify = { object = "pymdownx.slugs.slugify", kwds = { case = "lower" } }` |
| `extra:`, `extra_css:`, `extra_javascript:` | `[project.extra]`, `extra_css`, `extra_javascript` |
| `nav:` list | `nav = [ { "Title" = "page.md" }, ... ]` |

## What Zensical drops silently

| In the old build | What happens | What to do |
| --- | --- | --- |
| `hooks:` | Not run, even with `--strict` | Move the work into a script run before the build, or drop it |
| An unsupported plugin (`gen-files` and others) | Ignored | `autoapi` or `api-autonav` for API pages; a pre-build script for generated pages |
| `!ENV` | Not supported in TOML | A literal value, or a CI step that writes it before the build. Then check the built HTML for what the value fed (an analytics ID, for example): if it is absent, that feature did not carry over, which is a Z4 question |
| Search options other than `separator` | Ignored | Nothing; the search UI is English only |
| i18n plugins | No replacement | One site per language, linked through `extra.alternate` |
| Templates that call Python functions | MiniJinja has no Python to call | Rewrite the logic in the template or drop it |
| `docs_dir: .` | Not allowed | Move the pages into `docs/` (a restructure: repo-docs) |
| `mkdocs gh-deploy` | No equivalent | The Pages workflow in [deploy.md](deploy.md) |

## From plain docs/ to a site

A `docs/` folder written for GitHub's renderer needs these before its first strict build:

- **A homepage.** `docs/index.md`; a `README.md` in a folder also counts as that folder's index.
  [landing-page.md](landing-page.md) builds the project homepage.
- **Links that leave `docs/`.** `../CONTRIBUTING.md` works on GitHub and breaks on the site.
  `docstool check` reports each one with a suggested blob URL; a file that belongs on the site
  moves into `docs/` instead (repo-docs, restructure mode).
- **Anchors.** Keep GitHub's anchors with the template's `toc.slugify`, so existing `#links`
  from issues, code and other repositories keep working.
- **Alerts.** `> [!NOTE]` needs `[project.plugins.gh-admonitions]`.
- **Maintainer pages.** Plans, research and release procedures go to `docs/internal/`, which
  `exclude_docs` keeps off the site; deciding what is published is repo-docs' job.
- **The URL baseline.** There was no site, so the baseline is source-derived: it still proves
  that GitHub links into `docs/` have somewhere to land.

## From other generators

Sphinx, Docusaurus, Jekyll, Hugo, VitePress and the like have no compatibility layer in Zensical:
the move is a content migration, not a config conversion. Treat it as one.

- **What carries over.** Plain Markdown pages, images, and the page tree as a starting point.
  Everything specific to the old generator does not: reStructuredText (Sphinx; MyST Markdown
  only partly), MDX components (Docusaurus), Liquid tags and includes (Jekyll), shortcodes (Hugo),
  Vue components (VitePress), and front matter keys that only the old generator reads
  (`sidebar_position`, `permalink`, `slug`, `weight`). List each kind the docs use, with a
  count, before proposing the move; converting them is the bulk of the work.
- **The baseline is source-derived.** `site-build` builds only Zensical and MkDocs, so
  `check --save-baseline` without `--built` is the only docstool baseline, and the result is
  "URL preservation partially verified". When the old generator writes a `sitemap.xml`, build the
  old site the project's documented way into `<scratch>` (after asking, Z6) and keep its URL
  list: it is the list of routes that need a page or a redirect.
- **URLs come from front matter, not paths.** A `permalink` or `slug` key, or a sidebar file,
  decides the old URL. Map every old URL to its new page and write a redirect for each one that
  changes (Z5 when the scheme changes).
- **Anchors.** Compare a few headings' ids in the old built HTML with `docstool slug`'s output;
  where they differ, the old anchors need anchor redirects or the links that use them change.
- **The page tree.** Moving, merging or renaming pages along the way is repo-docs' restructure
  mode, with its plan and approval; this skill takes over for the config, the landing page and
  the deployment.
