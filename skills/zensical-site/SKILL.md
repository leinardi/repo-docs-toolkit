---
name: zensical-site
description: >-
  Sets up, migrates, audits, upgrades and deploys Zensical documentation sites: a pinned, hash-locked
  zensical.toml with GitHub-compatible anchors and unpublished docs/internal/, migration from MkDocs,
  Material for MkDocs or plain GitHub-rendered docs/ with URL-preserving redirects, GitHub Pages
  deployment, and a reusable "Minimal Developer Showcase" landing page that keeps Zensical's native
  header, search, tabs and palette toggle. Use when the user mentions Zensical, MkDocs, mkdocs.yml,
  Material for MkDocs, a documentation site, GitHub Pages for docs, a docs homepage or landing page,
  site navigation or redirects, or wants to publish their docs as a website.
---

# Zensical site

Zensical documentation sites: setting one up, migrating to it, publishing it on GitHub Pages,
upgrading and auditing it, and giving it a landing page. Written for and tested with Zensical
0.1.3; the template, the examples and every fact in the references are for that version.

## The checker

Deterministic checks run through the bundled script (Python 3.11 or newer, standard library
only). It reads the repository and writes only the files a command documents:

```sh
python3 -I <skill-dir>/scripts/docstool.py <command> --root <repo>
```

`<skill-dir>` is the directory that holds this file; `<scratch>` is a directory outside the
repository, such as the session scratchpad. `contrast` reads no files and needs no `--root`.

| Exit | Meaning | What you do |
| --- | --- | --- |
| 0 | No findings, every required input analysed | Report it as clean |
| 1 | Findings | Fix them or report them |
| 2 | Usage error, refused operation, failed build | Read the message; fix the call or the precondition. A site that builds in a plain clone but not under `site-build` is a checker limitation: report it as one |
| 3 | Coverage incomplete: a required input could not be analysed | Never report it as clean; name the input. Findings are still valid |

The summary line also names rows the command does not require that are partial (a build whose
hooks docstool cannot follow, a URL baseline saved from it). Carry them into the report: the
result they qualify is "partially verified", whatever the exit code.

| Command | Used for |
| --- | --- |
| `docstool site-audit` | Config faults: unsupported plugins, hooks, no-op features, missing extensions, slugify, lock, CI |
| `docstool check` | Links, anchors, images, nav, orphans, `extra_css` paths; URL baselines with `--built` |
| `docstool site-build` | A strict, clean build into a fresh directory, stamped with its inputs |
| `docstool contrast` | A brand colour against both schemes |
| `docstool slug` | GitHub's and the site's anchor for a heading |
| `docstool inventory` | The docs map: couplings, frozen paths, house style |

## Rules

1. **Facts come from the repository and from Zensical itself.** Site name, URLs, branch, install
   commands and features come from the code, its config and its docs; a Zensical behaviour comes
   from the references here or the installed package. Anything else is `TODO(verify: ...)`.
2. **Pin Zensical.** `zensical==0.1.3` in a uv project (`tools/docs/pyproject.toml` and its
   committed `uv.lock`), run through `uv run --locked`, locally and in CI
   ([config.md](references/config.md)).
3. **`--strict` is not enough.** A strict build misses broken images, unsupported plugins, hooks
   and features that do nothing. Every change ends with `site-audit` and `check` as well.
4. **Keep the native UI.** Header, search, navigation tabs, palette toggle and footer stay the
   theme's. Customise through config, `extra_css` and the landing page, not by replacing
   partials.
5. **The landing page is configured, never edited.** `home.html` and `home.css` are copied as
   shipped; a project sets front matter and one brand colour
   ([landing-page.md](references/landing-page.md)).
6. **GitHub-compatible anchors and no published internals.** The template's `toc.slugify` and
   `exclude_docs = "internal/"` on every site. On a site that is already live, switching the
   slug style renames anchors: that is gate Z5, with anchor redirects for the old ids.
7. **No side effects without agreement.** `site-build` runs the generator and any project hooks;
   writing a lock resolves from PyPI. Ask before the first of each in a repository. Build output
   goes to `<scratch>`; never run `zensical build` by hand in the repository, which writes
   `site/` there.
8. **Switch only after a side-by-side check.** The old generator and deployment stay until the
   Zensical build passes the URL baseline and the user agrees.

## What the user wants

| Request | Read | Checklist |
| --- | --- | --- |
| A new site for a repository | [config.md](references/config.md), [landing-page.md](references/landing-page.md), [deploy.md](references/deploy.md) | New site |
| Move from MkDocs or Material, or turn `docs/` into a site | [migrate.md](references/migrate.md) | Migrate |
| A homepage for an existing site | [landing-page.md](references/landing-page.md) | Landing page |
| Publish on GitHub Pages, or replace `gh-deploy` | [deploy.md](references/deploy.md) | — |
| Is the site set up well? A new Zensical version? | [upgrade-and-audit.md](references/upgrade-and-audit.md) | — |

Restructuring the pages themselves (moving, merging, archiving, deciding what is published) is
the repo-docs skill's restructure mode; this skill takes over once the content is in place.

## Checklist: new site

1. `docstool inventory`: what docs exist, which paths are cited from code and must not move,
   the house style.
2. Copy `assets/zensical.toml` to the repository root; fill in the placeholders from the
   repository (name, description, URLs, default branch).
3. Navigation: folders, or an explicit `nav` when order matters. Fix the links that leave
   `docs/` (`check` lists them).
4. The landing page ([landing-page.md](references/landing-page.md)).
5. The `tools/docs` uv project and its `uv.lock`, plus a Dependabot `uv` entry; with make-common,
   `zensical.mk` in uv mode.
6. `site-audit`, `check` and `contrast` clean; `site-build` passes.
7. The Pages workflow ([deploy.md](references/deploy.md)); the user sets the Pages source (Z2).
8. `scripts/screenshots.py` at 1440, 768 and 390 pixels, light and dark, reviewed by the user
   ([landing-page.md](references/landing-page.md), Step 6).

## Checklist: migrate

1. Baseline the old site with its own generator: `site-build --ref HEAD --generator mkdocs`,
   then `check --built ... --save-baseline`. No old build possible: a source-derived baseline,
   reported as partial.
2. `site-audit` on `mkdocs.yml`; decide every `hooks` and `plugin-unsupported` finding with
   the user (Z4).
3. Build with Zensical (`site-build --generator zensical`); optionally convert to
   `zensical.toml`.
4. `check --built <new> --baseline <urls.json>`: every old URL and anchor resolves.
5. Side-by-side review; switch CI only when the user agrees (Z1).

## Checklist: landing page

1. Pick the example by project type: `cli`, `gtk-app` or `library`.
2. Copy `home.html`, `home.css` and `brand.css` as shipped.
3. Write `docs/index.md` from the example, every claim from the repository.
4. Brand colour in `brand.css`; `contrast` passes for both schemes.
5. Build, `check`, then `scripts/screenshots.py` and the manual review at three widths in both
   schemes.

## Stop and ask

| Gate | When |
| --- | --- |
| Z1 | Switching the generator or the deployment |
| Z2 | Pages source, the `github-pages` environment, custom domain or DNS: settings only the user changes |
| Z3 | Choosing a brand colour when the project has none, or changing one that fails `contrast` |
| Z4 | Replacing what an unsupported plugin or a hook did |
| Z5 | Changing URLs or anchors: `use_directory_urls`, the layout of `docs/`, the slug style (`toc.slugify`) |
| Z6 | The first `site-build` in a repository: it runs the generator and the project's hooks |

## Before you say done

- `site-audit` and `check` exit 0, or every remaining finding is reported with a reason.
- The strict build passed, and the report names the Zensical version it used.
- For a migration: the URL baseline check passed, or the report says "partially verified" and
  why.
- For a landing page: `contrast` passed, and the screenshots went to the user.
- For an audit: nothing in the repository changed, and every finding names its config line, its
  fix and the gate the fix needs.
- The report lists what was checked, with the command, and what was not.
