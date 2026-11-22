# Writing the README

Read this when you write, rewrite, shorten or review a README. The README is the repository's
front door: what the project is, how to install and start, where the docs are. It is not the
docs. Its shape here is the one the toolkit's checker tests (`docstool readme`).

## Contents

- [Budget](#budget)
- [The header](#the-header)
- [Sections and emoji](#sections-and-emoji)
- [Features, install and usage](#features-install-and-usage)
- [Badges](#badges)
- [Images](#images)
- [Links and anchors](#links-and-anchors)
- [Alerts and details](#alerts-and-details)
- [What the checker reports](#what-the-checker-reports)

## Budget

50 to 150 lines, and most READMEs land near 100. Under 50 usually means install or usage is
missing. Past 100, check that every section is something a first-time visitor needs: screenshots,
an install method per platform or a short configuration example can earn the space. Over 150
means reference material that belongs in the docs: full install matrices, every command or flag, configuration
reference, changelog, contributing rules. Link to them instead. Content you remove from a README
must exist in the docs first (gate R4): move it, check the link, then cut it.

## The header

GitHub strips `style` and `class`; layout comes from `align` and image sizes only. The header:

```html
<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.svg">
    <img alt="<project> logo" src="docs/assets/logo.svg" width="96">
  </picture>
  <br><project>
</h1>

<p align="center"><strong><tagline></strong></p>

<p align="center">
  <badges, one per line>
</p>

<p align="center"><a href="<docs URL>">Documentation</a> · <a href="#-installation">Install</a> · <a href="CONTRIBUTING.md">Contributing</a></p>
```

- **One `<h1>`**: the logo and the project name. No other level-1 heading.
- **The logo** comes from the repository (`docs/assets/`, `data/icons/`, the app icon). A
  screenshot or design preview that happens to show the logo is not a logo asset. No logo:
  the header is `<h1 align="center"><project></h1>`, and you ask before making one (gate R2).
  Never draw one.
- **`<picture>` always ends with an `<img>`**: it is what renders where `<source>` is not
  supported (registries, many viewers). Give it alt text.
- **The tagline** is one sentence, bold, no emoji. When the project has a Zensical homepage, its
  front matter (`home.tagline` in `docs/index.md`) is canonical: copy it verbatim.
- **The nav line** links the docs, the install section and CONTRIBUTING, separated by ` · `.
- Leave out a paragraph that would be empty: no badges, no badge row.
- **Line length.** In a repository whose markdownlint sets `line_length`, break the header's
  long lines inside the tags: the tagline over two lines inside `<strong>`, the nav links one per
  line inside `<p align="center">`, and a badge whose line is still too long between the
  attributes of its `<img>` (`alt` on the first line, `src` on the next). A badge URL itself is
  never broken. HTML collapses the line breaks; the checker reads the wrapped tagline.

## Sections and emoji

4 to 6 level-2 sections, each with exactly one emoji as its first character, from this fixed
list so every repository reads the same. When a template asks for more, first leave out a
section with nothing to say yet (🌍 Translations when the project has no translations, Usage for
a desktop app opened like any other). Then fold 🤝 Contributing into 📖 Documentation, keeping its
links (CONTRIBUTING.md, the issue tracker, SECURITY.md) as bullets there. Never drop a line that
exists nowhere else (gate R4).

| Emoji | Section |
| --- | --- |
| ✨ | Features |
| 📦 | Installation |
| 🚀 | Usage, Quick start |
| 📖 | Documentation |
| 🔧 | Configuration |
| 🛠️ | Building from source, Development |
| 🌍 | Translations |
| 🤝 | Contributing |
| 🔒 | Security |
| 📝 | License (always the last section) |

No emoji anywhere else: not in the tagline, body text, level-3 headings or badges. Keep the
repository's own section names when it has them; the emoji is a prefix, not a rename.

- **License** stays the last section even when there is no LICENSE file: say the project has no
  licence yet and ask the owner (`readme-todo` lists the open question). Never choose a licence.
- **Usage** for a desktop app is optional: the app is opened from the desktop like any other.
  Keep it when the app has a command line or a first step that is not obvious.

## Features, install and usage

- **Features**: 3 to 6 bullets, each `- **Title:** one sentence.`. With a homepage, the titles
  are the homepage's feature card titles, same order (`docstool readme --home` compares them).
- **Install**: the one recommended command in a code block, then at most two alternatives in a
  sentence, and a link to the full list in the docs. No published package: the section is
  building from source with the repository's own commands; no build commands either: ask, and
  leave the section as a question for the owner rather than guessing a command. With a homepage, the first code block of
  this section is the homepage's first install command, exactly.
- **Configuration**: only when a first run needs it (a required key, a mode with no default): the
  smallest working example, every key checked against the type the loader fills, and a link to
  the full reference in the docs.
- **Usage**: the shortest real example: two or three commands, or a 10 to 20 line code example
  for a library. Every command and flag comes from the code (repo-docs' facts gate); run it only
  when it is safe and the user agreed.
- **One visual**, when the project has one: a screenshot for an app (light and dark in a
  `<picture>`), a terminal recording or session for a CLI, the code example for a library.

## Badges

At most 4, all from one service in one style (shields.io, `style=flat-square` or the default),
in this order: CI, version (release, registry or Flathub), docs, license. A badge is a claim:
add one only for something you checked exists: the workflow file, the published package
(`gh release list`, the registry page), the docs site (a `site_url` and a workflow that deploys
it, or the user's word), the LICENSE file. Zero badges is fine. More than 4 is gate R5.

For a Flathub app, the version badge is the shields.io Flathub badge
(`https://img.shields.io/flathub/v/<app-id>?style=flat-square`), and the official button goes in
the Installation section:

```html
<a href="https://flathub.org/apps/<app-id>"><img width="200" alt="Get it on Flathub" src="https://flathub.org/api/badge?locale=en"></a>
```

## Images

- Every image has alt text that says what it shows.
- GitHub wraps a bare image in a link to the image file; wrap it in your own `<a>` to choose the
  target.
- **Registries.** When the README is also the package page (crates.io, PyPI, npm), relative image
  paths can break there. Use absolute
  `https://raw.githubusercontent.com/<owner>/<repo>/<branch>/...` URLs. `docstool readme` infers
  this from the manifest; pass `--registry` when you know.

## Links and anchors

- GitHub drops the emoji from a heading's anchor and keeps the hyphen: `## 📦 Installation` is
  `#-installation`. An emoji written with a variation selector (🛠️, ❤️) leaves that invisible
  character in the anchor, so never type an anchor by hand: copy the `github:` line of
  `docstool slug "<heading>"`, and prefer linking sections whose emoji has none (📦, 🚀, 📖).
  🛠️ Building from source is one that has it.
- The docs URL appears at most three times: the nav line, where usage points to the docs, and the
  Documentation section. A docs badge that links the site counts too, so with one, link the
  badge to the docs workflow run instead or keep deep links to the Documentation section. The checker counts every occurrence of it, including deeper URLs that
  start with it, badge links and reference definitions; one `[docs]:` definition used several
  times counts once.
- Reference-style links (`[docs]: https://...`) at the bottom keep long URLs out of the prose.
- Links to repository files are relative (`CONTRIBUTING.md`, `LICENSE`).

## Alerts and details

- At most two alerts (`> [!NOTE]`, `> [!WARNING]`), only for something a reader must not miss,
  never two in a row. Registries show them as plain quotes.
- `<details><summary>` folds a long but needed block (per-platform install). Leave a blank line
  after `<summary>` so the Markdown inside renders.

## What the checker reports

```sh
python3 -I <skill-dir>/scripts/docstool.py readme --root <repo>
python3 -I <skill-dir>/scripts/docstool.py readme --root <repo> --home docs/index.md
```

| Check | Meaning |
| --- | --- |
| `readme-length` | Outside 50 to 150 lines |
| `readme-h1` | Not exactly one level-1 heading (Markdown or `<h1>`) |
| `readme-badges` | More than 4 badges, or mixed shields.io styles |
| `readme-emoji` | An emoji anywhere but the first character of a level-2 heading |
| `readme-alt` | An image without alt text |
| `readme-picture` | A `<picture>` without an `<img>` fallback |
| `readme-registry-image` | A relative image in a README a registry also shows |
| `readme-docs-url` | The docs URL more than three times |
| `readme-alerts` | More than two alerts |
| `readme-license` | No License section, or not the last one |
| `broken-anchor` | An in-page link to an anchor no heading has |
| `readme-todo` | A `TODO(verify ...)` still in the README: an open question for the owner |
| `readme-drift` | Tagline, features or install command differ from the homepage (`--home`); reported on the README for what it lacks and on the homepage for what it lacks |
