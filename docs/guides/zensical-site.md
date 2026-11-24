# Build a Zensical site

The zensical-site skill sets up, migrates, audits, upgrades and deploys
[Zensical](https://zensical.org/) documentation sites. Everything it says about Zensical is
written for and tested with Zensical 0.1.3, which it pins.

## A new site

```text
Publish docs/ as a Zensical site on GitHub Pages, with a landing page.
```

The skill starts from a template `zensical.toml` that sets:

- GitHub-compatible anchors, so `#a-heading` works the same on GitHub and on the site;
- `exclude_docs = "internal/"`, so maintainer pages in `docs/internal/` are never published;
- the full Markdown extension list (setting any extension replaces Zensical's defaults);
- GitHub alerts (`> [!NOTE]`) rendered as admonitions;
- a three-entry palette (system, light, dark) with one brand colour.

Zensical is pinned in a small uv project (`tools/docs/pyproject.toml` and its committed
`uv.lock`) and runs through `uv run --locked`, locally and in CI, so nothing is installed into the
system Python. A Dependabot `uv` entry proposes Zensical upgrades. The skill adds a Pages workflow
that builds every pull request and deploys from the default branch. Turning on Pages (Settings,
Pages, Source "GitHub Actions") is yours to do.

## Migrating from MkDocs

The skill first builds the current site with MkDocs and records every URL and anchor it produces,
then audits `mkdocs.yml` for what Zensical ignores or does differently: hooks, unsupported plugins,
`!ENV` tags, features that do nothing. After the change it builds with Zensical and checks the new
output against the recorded URLs, so a moved page gets a redirect instead of a 404. When MkDocs
cannot be installed, the report says the URL preservation was only partly verified.

## Checks after every change

A strict build is not enough: it does not catch a missing image, an unsupported plugin or a feature
flag that does nothing. Every change ends with:

```sh
python3 -I <skill-dir>/scripts/docstool.py site-audit
python3 -I <skill-dir>/scripts/docstool.py check
python3 -I <skill-dir>/scripts/docstool.py contrast '#0f766e' --slate '#5eead4'
```

## The landing page

The landing page is configured, never edited. The skill copies `home.html` and `home.css` as
shipped, writes `docs/index.md` from one of three examples (a CLI, a GTK app, a library) and sets
one brand colour in `brand.css`. The header, search, tabs and palette toggle stay Zensical's own.
The page needs no JavaScript: the install tabs fall back to stacked blocks. This site's own home
page is built that way; its front matter is described in
[Landing page front matter](../reference/front-matter.md).

The skill leaves the final look to you. Its screenshot script,
`skills/zensical-site/scripts/screenshots.py` (Playwright, run through `uv`), serves the built
site on 127.0.0.1 and takes full-page screenshots of the homepage at 1440, 768 and 390 pixels in
both schemes, and fails when the page is wider than the window.

The skill's references cover the details:
[config][zensical-site-config],
[migrate][zensical-site-migrate],
[deploy][zensical-site-deploy],
[upgrade and audit][zensical-site-upgrade-and-audit] and
[landing page][zensical-site-landing-page].

[zensical-site-config]: https://github.com/leinardi/repo-docs-toolkit/blob/main/skills/zensical-site/references/config.md
[zensical-site-migrate]: https://github.com/leinardi/repo-docs-toolkit/blob/main/skills/zensical-site/references/migrate.md
[zensical-site-deploy]: https://github.com/leinardi/repo-docs-toolkit/blob/main/skills/zensical-site/references/deploy.md
[zensical-site-upgrade-and-audit]: https://github.com/leinardi/repo-docs-toolkit/blob/main/skills/zensical-site/references/upgrade-and-audit.md
[zensical-site-landing-page]: https://github.com/leinardi/repo-docs-toolkit/blob/main/skills/zensical-site/references/landing-page.md
