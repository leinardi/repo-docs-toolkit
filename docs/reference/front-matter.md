# Landing page front matter

The landing page template, `home.html`, reads everything it shows from the front matter of
`docs/index.md`. Nothing in the template or its stylesheet changes per project.

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

| Key | Required | What it does |
| --- | --- | --- |
| `template` | yes | Must be `home.html` |
| `hide` | yes | `[navigation, toc]` hides both sidebars |
| `home.name` | no | The big name in the hero; defaults to `site_name` |
| `home.text` | no | A second line of the heading |
| `home.tagline` | no | One sentence under the heading; the README's tagline must match it |
| `home.logo`, `home.logo_dark` | no | The hero image for the light and dark schemes |
| `home.actions` | no | Buttons: `text`, `link`, and `primary: true` for the filled one |

## The page body

The body is plain Markdown, in this order:

1. `<div class="rdt-showcase" markdown>`: a code block, a terminal session or a pair of
   screenshots (`#only-light` and `#only-dark`).
2. `<div class="rdt-install" markdown>`: content tabs, at most four, or a single code block.
3. `## Features`: grid cards, at most four, each a bold title and one or two sentences. The
   titles must match the README's feature bullets.
4. Anything else the project wants to show.
