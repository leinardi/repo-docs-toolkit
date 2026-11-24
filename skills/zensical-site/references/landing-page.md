# The landing page

Read this when a Zensical site needs a homepage: a new site, a migrated one, or a homepage that is
a plain list of links. The landing page ("Minimal Developer Showcase") is a hero, one showcase, the
install commands and four feature cards, on Zensical's own header, search, tabs and palette
toggle. It is configured through front matter and one colour; its template and stylesheet are
used as shipped.

## Contents

- [What ships](#what-ships)
- [Step 1: Pick the example](#step-1-pick-the-example)
- [Step 2: Copy the assets](#step-2-copy-the-assets)
- [Step 3: Write docs/index.md](#step-3-write-docsindexmd)
- [Step 4: Set the brand colour](#step-4-set-the-brand-colour)
- [Step 5: Build and check](#step-5-build-and-check)
- [Step 6: The manual review](#step-6-the-manual-review)
- [Front matter reference](#front-matter-reference)
- [Rules](#rules)

## What ships

| File | Goes to | Edited per project |
| --- | --- | --- |
| `assets/overrides/home.html` | `overrides/home.html` | Never |
| `assets/stylesheets/home.css` | `docs/stylesheets/home.css` | Never |
| `assets/stylesheets/brand.css` | `docs/stylesheets/brand.css` | The colour values only |
| `assets/landing-examples/<type>/docs/index.md` | `docs/index.md` | Yes: it is the content |

`home.html` overrides only the content block, so the header, search, navigation tabs and palette
toggle stay the theme's. Every rule in `home.css` is scoped to the homepage wrapper
(`.rdt-home`), so other pages are untouched, including after instant navigation. Both files need
`custom_dir = "overrides"` and the two `extra_css` entries from `assets/zensical.toml`
([config.md](config.md)).

## Step 1: Pick the example

| The project is | Example | Showcase | Install |
| --- | --- | --- | --- |
| A command-line tool | `landing-examples/cli` | A terminal session (`console` block) | Tabs: one per package manager |
| A desktop app (GTK, Flatpak) | `landing-examples/gtk-app` | A light and a dark screenshot | One `flatpak install` block; Flathub as the primary button |
| A library | `landing-examples/library` | A short code example | Tabs or one block |
| A service | `landing-examples/cli` | The compose file, included with `--8<--` | One block |

Each example is a complete site that builds with `--strict` (`tests/test_landing_build.py` in
the toolkit builds all three).

## Step 2: Copy the assets

Copy `home.html`, `home.css` and `brand.css` to the paths in the table, unchanged. If the
project already has `overrides/home.html` or a `docs/index.md` with content, stop and ask: the
existing content moves to a page of its own, or into the new homepage's body.

## Step 3: Write docs/index.md

Start from the example's `docs/index.md`. Every word on the page is a claim (repo-docs' facts
gate applies):

- **Tagline**: what the project does, for whom, in one sentence. Take it from the README or the
  repository description; the README carries the same sentence (`docstool readme --home` checks).
- **Actions**: one primary (getting started, or the store listing for an app) and at most one
  secondary (GitHub, the guide or the API reference). Each `link` is a page path relative to the
  site root (`getting-started/`) or a full URL.
- **Showcase**: real output. A terminal session is copied from a real run, a screenshot is of
  the real app, a code example runs against the current API. Never draw a mock-up. When there is
  nothing short enough to show (a service whose compose file is long), drop the showcase and its
  wrapper: on wide screens the hero and the install block are then centred above the cards.
- **Install**: the commands from the project's own install docs, at most four tabs. A service
  pulls its compose file in with `--8<-- "compose.yaml"` instead of copying it.
- **Features**: four cards, 15 to 25 words each, each one a capability the code has. Icons are
  `:lucide-<name>:{ .lg }`.

Keep the `<div class="rdt-showcase" markdown>` and `<div class="rdt-install" markdown>`
wrappers: the layout places the showcase beside the hero on wide screens by these classes. A blank
line after the opening tag and before the closing one is required.

## Step 4: Set the brand colour

Use the project's colour: its logo, its app icon (`data/icons/`), or an accent already in its
CSS. When there is none, propose one and let the user choose (gate Z3). Put the light value and a
lighter dark-scheme value into `brand.css` and check them:

```sh
python3 -I <skill-dir>/scripts/docstool.py contrast '<light>' --slate '<dark>'
```

Every row must be `ok`. The examples use `#c2410c`/`#fb923c`, `#1c71d8`/`#78aeed` and
`#0f766e`/`#2dd4bf`.

## Step 5: Build and check

```sh
python3 -I <skill-dir>/scripts/docstool.py site-build --root <repo> --out <scratch>/site
python3 -I <skill-dir>/scripts/docstool.py check --root <repo> --built <scratch>/site
```

Then open `<scratch>/site/index.html` and confirm: one `h1` (the project name), both sidebars
hidden, the tabs, search and palette toggle present, and no hero on any other page.

## Step 6: The manual review

The toolkit's automated tests cover contrast, keyboard order, reduced motion, rendering without
JavaScript and phone width for its own examples; a project's page still needs a person. Take
screenshots at 1440, 768 and 390 pixels wide, in the light and the dark scheme, and ask the user
to review them for:

- the layout at each width: nothing cut off, the showcase beside the hero only on wide screens;
- both schemes: the accent readable, the screenshots or logo matching the scheme;
- keyboard use in a real browser: Tab reaches the buttons, the install tabs and the cards, and
  the focus ring is always visible;
- a screen reader pass (Orca, VoiceOver or NVDA) over the hero and the cards;
- the motion: a short fade of the hero, nothing else.

Report these as reviewed by the user, never as automated.

## Front matter reference

```yaml
---
title: Home                 # the navigation label and the browser title
template: home.html
hide: [navigation, toc]
home:
  name: ferrule             # optional; default site_name
  text: Batch renames you can review   # optional second line of the h1
  tagline: Rename thousands of files safely, with a preview of every change.
  logo: assets/logo.svg     # optional, relative to docs/
  logo_dark: assets/logo-dark.svg      # optional; default logo
  actions:
    - { text: Get started, link: getting-started/, primary: true }
    - { text: GitHub, link: https://github.com/<owner>/<repo> }
---
```

Screenshots for both schemes use the theme's fragments, one image each:

```markdown
![Main window](assets/shot-light.png#only-light)
![Main window, dark style](assets/shot-dark.png#only-dark)
```

Every image needs alt text; the logo's is empty because the name follows it.

## Rules

- Never edit `home.html` or `home.css` for one project, and never add `<style>` to the page.
  A layout need they do not meet is a change to the toolkit.
- One accent colour, from `brand.css` or the palette. No gradients, no second accent.
- No JavaScript on the page. Install tabs are the theme's content tabs and work without it.
- Keep the sections in order: hero, showcase, install, features, then anything else.
- The tagline and feature titles stay in step with the README (`docstool readme --home
  docs/index.md`, repo-readme skill).
