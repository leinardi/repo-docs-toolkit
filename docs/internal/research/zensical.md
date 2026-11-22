# Zensical facts

Read this when you change guidance, templates or docstool checks that depend on how Zensical
behaves, or when you need to know how a Zensical claim in the shipped text was checked.

> **Status:** Research record, November 2026. It was the fact base for the `zensical-site` skill and
> the config template, checked against Zensical 0.1.3 and zensical-ui 0.0.43 on 2026-11-20 by
> official docs, the installed source and a throwaway test build. Zensical changes several times a
> week: recheck before relying on a fact here.

## Contents

- Version and cadence
- Commands and configuration
- Defaults that surprise
- Validation and strict mode
- Theme options and features
- Plugins and redirects
- Templates and the landing page
- Deployment
- Migration from MkDocs
- Roadmap and deprecations

Tags: **V** verified in the test build or installed source, **D** stated in the official docs.

## Version and cadence

- Zensical 0.1.3 (PyPI and GitHub release, 2026-11-20) pulls in zensical-ui 0.0.43 (templates and
  theme). Python 3.11 or newer. MIT licence.
- Releases: 0.0.71 (2026-10-16), 0.0.74 (2026-10-30), 0.1.0 (2026-11-05, out of alpha), 0.1.1
  (11-10), 0.1.2 (11-17), 0.1.3 (11-20). Several releases a week, so the toolkit pins one version.
- 0.1.3 added the git-revision-date-localized plugin and `zensical serve --external-origin`.
- The changelog page redirects to the GitHub releases page.

## Commands and configuration

- `zensical new [DIR]` (V) writes `zensical.toml`, `docs/index.md`, `docs/markdown.md` and
  `.github/workflows/docs.yml`. It errors if `zensical.toml` exists and has no options.
- `zensical build` takes `-f`, `-c/--clean` (clears the cache) and `-s/--strict`; `serve` takes
  `-f`, `-o`, `-a/--dev-addr` and `--external-origin` (0.1.3). Not supported from the MkDocs CLI:
  `--theme`, `--use-directory-urls`, `--site-dir`, `gh-deploy`, `get-deps` (D).
- `serve` answers `/` with a 302 to the `site_url` path, reloads on CSS edits under `docs/` and
  on `zensical.toml` edits without a restart (V).
- `zensical.toml` is native: everything under `[project]`, theme under `[project.theme]`, plugins
  under `[project.plugins.<name>]`, extensions under `[project.markdown_extensions]`. Python object
  references are plain strings in TOML (D, V).
- `mkdocs.yml` is read as is, including `theme: name: material` and `!!python/name:` tags (V).
- `site_name` is required; `site_url` is needed for instant navigation, previews, custom 404s and
  social cards. `docs_dir = "."` is not allowed; `docs_dir` and `site_dir` must be inside the
  project root and must not contain each other (D).
- `exclude_docs`, `draft_docs` and `not_in_nav` take gitignore syntax. Dotfiles, dot-directories and
  a top-level `templates/` are excluded by default (D).
- Navigation: with no `nav`, it is built from the folders (V). Any nav string that is not a Markdown
  page is a URL. A root `index.md` is the homepage even when unlisted; `README.md` counts as a
  section index. A page missing from an explicit nav is still built, with no warning (V).

## Defaults that surprise

- Setting `markdown_extensions` at all replaces the whole default list; only `toc` and `tables` are
  always added. The defaults carry tabbed, the mermaid fence, keys, mark, tilde, abbr and
  arithmatex, so a hand-written list silently loses them (V, `zensical/config.py`).
- Search is on by default. Only `enabled` and `separator` are honoured; `lang`, `pipeline`,
  `fields` and similar are ignored, and the UI is English only (D).
- `search.suggest` and `search.share` are referenced nowhere in the templates or bundle, so they
  are silent no-ops. `navigation.indexes` with `toc.integrate`, and `navigation.prune` with
  `navigation.expand`, are documented as incompatible (V, D).
- `hooks:` and unsupported plugins are silently ignored, even under `--strict` (V).
- Fonts: modern uses Inter and JetBrains Mono, classic uses Roboto; `variant = "classic"` keeps the
  Material look (V).
- The root font size is 20px, so `72rem` is 1440px (see [p0-spike.md](p0-spike.md)).

## Validation and strict mode

`[project.validation]` defaults: `invalid_links` and `invalid_link_anchors` true. Six other checks
(unresolved references, footnotes, unused and shadowed definitions) are false and marked deprecated
until Zensical's own parser ships (D). What the test build showed (V):

| Input | Result |
| --- | --- |
| Broken page link | Warning "page does not exist", with file, line and a code frame |
| Missing anchor, other page or same page | Warning "anchor does not exist" |
| Broken image path | Not reported |
| External URLs | Not checked |
| Unknown top-level key | Python `UserWarning`; fatal under `--strict` |
| Missing `extra_css` file | Not reported, even under `--strict` (P0 spike) |

- Without `--strict` the build exits 0 after "N issues found". With `--strict` it prints "Aborted
  because --strict flag is set" and exits 1, as a Python `RuntimeError` with a traceback.
- `NO_COLOR=1` gives plain output for parsing.
- These gaps are why docstool checks images, `extra_css` paths, nav coverage and unsupported
  plugins itself.

## Theme options and features

- Palette: `[[project.theme.palette]]` is one table per toggle state; automatic, light and dark need
  three entries. Toggle icons must exist or the build fails (`lucide/sun`, `lucide/moon`,
  `lucide/sun-moon`, `material/brightness-*`). `primary = "custom"` plus CSS variables set under
  `:root > *` gives a brand colour (D, V).
- Logo and favicon: `logo = "images/logo.png"` or `[project.theme.icon] logo`; `favicon` defaults to
  `assets/images/favicon.png`; `[project.extra] homepage` changes the logo link (D).
- The feature flags the 0.1.3 templates and bundle actually reference include `content.code.copy`,
  `content.code.annotate`, `content.action.edit`, `content.tabs.link`, `navigation.instant`,
  `navigation.tabs`, `navigation.sections`, `navigation.indexes`, `navigation.footer`,
  `navigation.top`, `navigation.tracking`, `search.highlight`, `toc.follow` and `toc.integrate` (V).
- `content.action.edit` needs `repo_url` and `edit_uri`; the build produced the expected GitHub edit
  link (V).
- Only one language per site; `extra.alternate` links to separately built sites (D).

## Plugins and redirects

- Plugins are native reimplementations, not the MkDocs plugin API. "Configuration for plugins not
  listed under Supported plugins is silently ignored"; unknown settings of a supported plugin are a
  config error (D). Supported as of 0.1.3 include redirects (0.0.58), gh-admonitions (0.0.67),
  glightbox, include-markdown, macros, mkdocstrings, social, tags, blog, offline and
  git-revision-date-localized (0.1.3). Not supported: gen-files, open-in-new-tab, `hooks`.
- Redirects need no install. Page maps (`"old.md" = "new/page.md"`) and anchor maps
  (`"a.md#old" = "b.md#new"`) go under `[project.plugins.redirects.redirect_maps]`. Anchor redirects
  are a Zensical extension over mkdocs-redirects. The build wrote a meta-refresh stub that keeps
  the hash and a `redirect.json` used client-side; the source path must no longer exist as a page
  (D, V).
- `gh-admonitions` is built in (`zensical/config.py`, option `enabled` only), so GitHub alerts
  render the same on GitHub and on the site (V).

## Templates and the landing page

- The engine is MiniJinja: no Python calls from templates. Overrides written for Material 9.6.18 or
  newer should work unchanged. `custom_dir = "overrides"` enables overrides; `main.html` extending
  `base.html` with blocks is the recommended form; front matter `template:` picks a page template
  (D).
- The `hero` block is empty and sits inside the container just above the tabs, so it is where a hero
  goes. The header, search and palette toggle stay native when only content blocks are overridden
  (V, zensical-ui 0.0.43).
- Instant navigation swaps the `[data-md-component=container]` subtree but not `<head>`. A page
  scoped `<style>` therefore must live inside the container, never in `extrahead`. The P0 spike
  later showed a `:has()` selector on the container avoids a `<style>` element altogether.
- Front matter `hide:` accepts navigation, toc, path, footer, feedback and tags (V). Files under
  `custom_dir` can serve as `extra_css` entries (P0 spike).

## Deployment

- `zensical new` writes the official Pages workflow (configure-pages, checkout, setup-python,
  `pip install zensical`, `zensical build --clean`, upload and deploy-pages). The repository's
  Pages source must be "GitHub Actions". The docs advise against CI caches for now (D, V).
- The official workflow pins actions by tag and Zensical not at all, and has no `--strict`; the
  toolkit's templates pin by SHA, lock Zensical and build strict.
- `docs/CNAME` is copied to `site/CNAME` (V).

## Migration from MkDocs

- The official sequence: keep the MkDocs deployment, run `zensical build` on the same
  `mkdocs.yml`, compare, confirm every plugin is supported, then switch CI (D).
- Material for MkDocs is in critical maintenance until 2027-05-05 (D).
- Caveats: unsupported plugins and `hooks` are ignored silently; templates must not call Python;
  uv symlink mode is unsupported (D, V).

## Roadmap and deprecations

- Semver on the 0.x line. Announced: the `plugins` scope is to be replaced by a module system,
  settings will move out of `[project]` with automatic refactorings, and `site_name` will become
  optional. In development: a Rust Markdown parser, a module API, a project model CLI for agents.
  Longer term: native versioning and i18n (D).
- Treat anything under "announced" as a reason to keep Zensical-specific text in one reference per
  skill and to name the tested version.
