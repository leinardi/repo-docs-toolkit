# Configuring a Zensical site

Read this when you create or change a `zensical.toml`: a new site, a site the audit found faults
in, or a migration's converted config. Every block below is in `assets/zensical.toml`, the
template this skill ships; copy it and replace each `<placeholder>`. Facts are for Zensical 0.1.3,
the version the template was built with.

## Contents

- [Rules that hold for every site](#rules-that-hold-for-every-site)
- [The project table](#the-project-table)
- [Theme, features and palette](#theme-features-and-palette)
- [Plugins](#plugins)
- [Markdown extensions](#markdown-extensions)
- [Validation and strict builds](#validation-and-strict-builds)
- [Pinning Zensical](#pinning-zensical)
- [Checking a config](#checking-a-config)

## Rules that hold for every site

- All settings live under `[project]`: the theme under `[project.theme]`, plugins under
  `[project.plugins.<name>]`, extensions under `[project.markdown_extensions]`.
- `docs_dir` defaults to `docs` and must be a subdirectory: `docs_dir = "."` is not allowed.
  `site_dir` defaults to `site`; neither may contain the other.
- `custom_dir` and the `extra_css` paths are separate: `custom_dir` is relative to the config
  file and holds templates (`overrides/home.html`), while `extra_css` paths are relative to
  `docs_dir` (`stylesheets/home.css` is `docs/stylesheets/home.css`).
- Unknown top-level keys print `Unrecognised configuration name`; under `--strict` the build
  fails. Settings of an unsupported plugin are ignored without a word, even under `--strict`.
- Templates run on MiniJinja: they cannot call Python functions.

## The project table

| Key | Why it is set |
| --- | --- |
| `site_name` | Required: the build fails without it. |
| `site_url` | Instant navigation and the sitemap need it. Set it to the published URL, with its path (`https://<owner>.github.io/<repo>/`), or to the custom domain. |
| `site_description` | The homepage tagline, and the page description for search engines. |
| `repo_url`, `edit_uri` | The repository link in the header. `edit_uri` names the default branch: check it (`git symbolic-ref refs/remotes/origin/HEAD`; without a remote, the branch the history is on, confirmed with the user) instead of assuming `main`. |
| `exclude_docs` | Always `internal/`: maintainer pages in `docs/internal/` are never published (repo-docs' publication policy). gitignore syntax, one pattern per line. |
| `extra_css` | `stylesheets/home.css` (the landing page, as shipped) and `stylesheets/brand.css` (the project's colour). |
| `nav` | Omit it to build the navigation from folders. Write it when the order matters. A page left out of an explicit `nav` is still built, with no warning; `docstool check` reports it as an orphan. |

Zensical also skips dotfiles, dot-directories and a top-level `templates/` directory.

## Theme, features and palette

- `variant` is `modern` by default (Inter and JetBrains Mono). `variant = "classic"` keeps the
  Material for MkDocs look and fonts; prefer it when migrating a site whose CSS targets Material.
- The template's features are the ones that change what a reader gets. Two flags do nothing in
  0.1.3 and are left out: `search.suggest` and `search.share`. Two pairs do not work together:
  `navigation.indexes` with `toc.integrate`, and `navigation.prune` with `navigation.expand`
  (the Zensical docs say so without saying what breaks). Keep the one the site is built around,
  usually `navigation.indexes` when sections have index pages, and ask before removing the
  other. `site-audit` reports all four cases.
- The palette has three entries, system first, so the site follows the reader's setting until
  they choose. Toggle icons must exist (`lucide/sun-moon`, `lucide/sun`, `lucide/moon` do), or
  the build fails.
- One accent. With `primary = "custom"` and `accent = "custom"`, the colour comes from
  `stylesheets/brand.css` (`assets/stylesheets/brand.css`). A named colour (`indigo`, `teal`)
  works too, but the dark scheme then keeps the light value for some text: check it with
  `contrast` before choosing.
- A custom colour needs a lighter value for the dark (slate) scheme. Text in the accent colour
  uses `--md-typeset-a-color`, which brand.css sets for both schemes. Check the pair:

  ```sh
  python3 -I <skill-dir>/scripts/docstool.py contrast '#1c71d8' --slate '#78aeed'
  ```

  Every row must say `ok`: accent text on both backgrounds, white text on the accent button,
  and the accent against the slate page. Choosing a colour when the project has none is gate Z3.
- `logo` and `favicon` under `[project.theme]` take paths relative to `docs/`. Without them the
  header shows the theme's book icon. A GNOME app's symbolic icon (`data/icons/*-symbolic.svg`,
  one grey fill) reads on both schemes; copy it into `docs/assets/`, since the site cannot serve
  files outside `docs/`. The full-colour icon belongs in the landing hero (`home.logo`).
  Checked on 0.1.3: the build writes `<link rel="icon">` and the header `<img>` from them.
- Fonts load from Google Fonts by default (the built page links `fonts.googleapis.com`).
  `font = false` under `[project.theme]` uses the reader's system fonts instead; offer it when
  the project cares about third-party requests.

## Plugins

- Search is on even when it is not listed. It reads only `enabled` and `separator`; other
  options are ignored.
- `[project.plugins.gh-admonitions]` renders GitHub alerts (`> [!NOTE]`) as admonitions, so a page
  reads the same on GitHub and on the site. Its only option is `enabled`.
- Redirects need no install. `[project.plugins.redirects.redirect_maps]` maps an old page to its
  new one, relative to `docs_dir`; a key or value may carry an anchor (`"old.md#a" =
  "new.md#b"`). A redirected source must no longer exist as a page. Page redirects become
  meta-refresh stubs; anchor redirects go into `redirect.json`, read by the theme. repo-docs'
  `docstool plan apply` appends the entries for a restructure.
- Zensical reimplements a fixed list of MkDocs plugins and ignores every other one silently.
  `site-audit` names the unsupported ones; [migrate.md](migrate.md) covers what replaces them.

## Markdown extensions

Setting `markdown_extensions` at all replaces Zensical's defaults; only `toc` and `tables` are
always added. The template therefore lists every extension, including the defaults it keeps:

- `toc` with `permalink = true` and GitHub-compatible anchors:
  `slugify = { object = "pymdownx.slugs.slugify", kwds = { case = "lower" } }`. The same `#slug`
  then works on GitHub and on the site. Without it, a heading with punctuation or a repeated
  heading gets a different anchor on each (`docstool slug "<heading>"` shows both).
- `pymdownx.snippets` with `base_path = ["."]` and `check_paths = true`, so
  `--8<-- "compose.yaml"` pulls a repository file into a page and a missing one fails the build.
- `pymdownx.superfences` with the `mermaid` custom fence; Zensical loads Mermaid itself and follows
  the palette.
- `pymdownx.tabbed` with `alternate_style = true`, the only style the theme supports.
- `attr_list` and `md_in_html`, which grid cards, buttons and the landing page wrappers need.

Left out on purpose: `pymdownx.arithmatex` (it needs MathJax added through `extra_javascript`) and
`codehilite` (redundant next to `pymdownx.highlight`). Add an extension when a page uses its
syntax; `site-audit` reports syntax used in the docs whose extension is missing.

## Validation and strict builds

`[project.validation]` turns on the link and anchor checks: `invalid_links` and
`invalid_link_anchors` (the defaults, written out). The six other checks are deprecated in their
current form; leave them out.

Without `--strict`, a build with broken links prints the issues and exits 0. Always build with
`zensical build --strict --clean`: `--strict` turns the warnings into exit 1, and `--clean`
clears the build cache so nothing stale survives.

A strict build still misses broken images, unsupported plugins, hooks and features that do
nothing. That is why `check` and `site-audit` run as well.

## Pinning Zensical

Zensical releases often, and its config and templates still change between 0.x versions. Pin it
in a small uv project, so nothing is installed into the system Python and Dependabot can propose
upgrades:

1. Copy `assets/tools/docs/pyproject.toml` (`zensical==0.1.3`, no build system) to
   `tools/docs/pyproject.toml`, and add `tools/docs/.venv/` to `.gitignore`.
2. Lock it and commit `pyproject.toml` and `uv.lock`:

   ```sh
   uv lock --project tools/docs
   ```

   The lock records a hash for every file, for every platform. Writing it resolves from PyPI and
   writes a file: tell the user first.
3. Run Zensical through uv, locally and in CI: `uv run --project tools/docs --locked zensical
   build --strict --clean`, or `zensical serve` to preview. `--locked` refuses a lock that no
   longer matches `pyproject.toml`. docstool's `site-build` needs that `zensical` on its path:
   `uv run --project tools/docs --locked python3 -I <skill-dir>/scripts/docstool.py site-build …`.
4. Let Dependabot propose upgrades: a `package-ecosystem: "uv"` entry for `/tools/docs`, with
   the repository's usual schedule and a `cooldown`. Treat each bump as an upgrade
   ([upgrade-and-audit.md](upgrade-and-audit.md)), not a routine merge.

A repository that uses make-common (`.mk/` and `MK_COMMON_FILES` in its `Makefile`) gets the
same through `zensical.mk` in uv mode, from make-common v1.16.0 (older copies ignore
`DOCS_UV_PROJECT`; run `make mk-common-update` first): add `zensical.mk` to `MK_COMMON_FILES` and set
`DOCS_UV_PROJECT := tools/docs` before the include. Then `make docs-build`, `make docs-serve`
(`DOCS_ADDR=IP:PORT` to change the address), `make docs-deps-lock`, `make docs-deps-upgrade`
and `make docs-deps-outdated` run through uv; `make help` lists them.

## Checking a config

```sh
python3 -I <skill-dir>/scripts/docstool.py site-audit --root <repo>
python3 -I <skill-dir>/scripts/docstool.py check --root <repo>
```

`site-audit` reads the config only and names faults with the line that causes them. `check`
reads the pages: links, anchors, images, nav entries, orphans, `extra_css` paths, and pages that
link into `internal/`. Both open with a coverage table; exit 3 means a part of the config could not
be read, and the result is not clean.
