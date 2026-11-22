# README and homepage study

Read this when you change the README template or lint targets in `repo-readme`, or the landing page
assets in `zensical-site`, and want the observations behind the numbers.

> **Status:** Research record, November 2026. It studied three well-regarded READMEs (Starship,
> Neovim, Typst) and two documentation homepages (Hono, Biome) on 2026-11-20 to set targets for the
> README and for a minimal developer landing page. Layout numbers come from headless Chrome at
> 1440px wide; GitHub rendering behaviour was read from rendered HTML. Both change as the projects
> and GitHub change, so treat the measurements as a snapshot.

## Contents

- READMEs studied
- GitHub rendering facts
- README guidance derived
- Homepages studied
- Landing page guidance derived

## READMEs studied

|  | Starship | Neovim | Typst |
| --- | --- | --- | --- |
| Raw lines | 403 | 116 | 286 |
| Header | Centered logo image, 6 badges, text nav, 13 language flags | Logo and two links inside one centered h1 | Logo in a centered h1, 5 badges (first one links the docs) |
| Visual | Demo GIF floated right beside the pitch | None | One large example screenshot, plus a text version in `<details>` |
| Headings | h2 with an emoji each | Setext h2, no emoji | h2, no emoji |
| Install | Per-OS tables inside 15 collapsibles | Links to releases and distributions | Nested list per channel |

- Starship is visually strongest but heavy (about 200 lines of install matrices that duplicate its
  site). Neovim is the "README as an index" model: short, links into the docs, dated visually.
  Typst has one strong visual and keeps the text equivalent for accessibility and copying.
- Common denominators: a centered header with logo, a few badges and a docs link; a one-line
  tagline; four to seven feature bullets; one visual; a short install with the matrix pushed to the
  docs; reference-style links at the bottom; licence last.

## GitHub rendering facts

Observed in rendered HTML on 2026-11-20, plus GitHub's documentation for the picture element and
alerts.

- HTML is sanitised through an allowlist. `align`, `width`, `height`, `alt`, `details`, `picture`,
  tables and basic inline tags survive; `style`, `class`, scripts and iframes do not. Layout is
  limited to `align` plus image sizes.
- Every image gets an injected `max-width: 100%`; an image not already inside a link is wrapped in a
  link to its raw URL, so wrap logos in your own link. External images are proxied.
- Light and dark images use `<picture>` with `prefers-color-scheme` sources and a default `<img>`.
  The older URL-fragment trick is legacy; `<picture>` falls back to the default image on other
  renderers, which is inferred, not tested.
- Alerts (`> [!NOTE]` and so on) render as plain blockquotes on crates.io, PyPI and most mirrors.
  GitHub's own advice is one or two per article, never consecutive.
- A blank line after `<summary>` is needed for the Markdown inside `<details>` to render.
- A heading that starts with an emoji gets the anchor `#-slug` (the emoji is dropped, the hyphen
  stays), observed as `user-content--installation`. In-page links must use that form or an explicit
  anchor, and site slugs differ from README slugs.
- Relative image paths break where a README is republished (crates.io resolves them only when the
  repository field is set); use absolute raw URLs when it is.

## README guidance derived

The target was 50 to 100 lines:

1. A centered header: an h1 holding a `<picture>` logo with dark and light variants and alt text
   equal
   to the project name; one bold tagline; three or four badges in one style; a text nav
   (documentation, install, contributing).
2. One visual with alt text: a screenshot for an app, a recording for a CLI, a short code example
   for
   a library.
3. An intro of one or two sentences and three to six bold-label bullets that share text with the
   homepage feature cards.
4. Four to six h2 sections with a single emoji prefix from a fixed vocabulary (installation, usage,
   documentation, contributing, licence); no emoji in body text, badges or the tagline.
5. One recommended install path in a code block and at most two or three alternatives; the full
   matrix lives in the docs.
6. The docs URL in at most three places; reference-style links; no config reference, flag list or
   changelog; at most one alert; licence last.
7. Lint targets: 50 to 100 lines, at most four badges, exactly one h1, emoji only at the start of
   h2,
   alt text on every image.

The gx52 trial later found that the README header has to be wrapped to satisfy a line-length rule;
see [the gx52 trial report](../qa/gx52-trial.md). Variants: a Flathub app uses the official
Flathub badge button (CC0) and a light and dark screenshot pair; a library replaces the visual with
a
10 to 20 line example after the install line.

## Homepages studied

**Hono** (VitePress home layout, 1440px light): a 1,107px page with a 64px navigation, a 620px hero
and a 262px features row.

- Hero in two columns at 960px and up (container 1152px): a flat brand-colour name, a headline, a
  muted tagline, a pill call to action pair (primary and neutral, 40px high, 20px radius), a
  single-command install pill with a prompt that is not copied and a round copy button, and a
  code window card with a soft shadow. Below 960px everything centres and the window is hidden.
- Four feature cards in one row (two at tablet widths, one on mobile): 24px padding, 12px radius,
  soft background, a 48px icon tile, a short title and a one-line detail.
- Almost no animation; colour transitions of 0.25s and the copy button state.

**Biome** (Starlight splash template): 7,891px tall. Worth borrowing: compact segmented install
tabs (monospace labels, a hairline border, a 3px accent underline on the selected tab, selection
synced across the page), the split input and output panes that show the product working, and a very
subtle radial accent glow. Not worth borrowing: the announcement banner, promo video, benchmark
animation, hover glow on cards, and the logo, community and sponsor walls, which make the page long.

## Landing page guidance derived

Target: three sections plus the theme footer, about 1,100 to 1,500px tall at 1440px, usable without
JavaScript except copy and tabs. About 70% Hono, 30% Biome.

1. Hero: two columns from 960px with a 1152px container (the toolkit later used `72rem`; see
   [p0-spike.md](p0-spike.md) for why that is wider); name in the brand colour, headline, tagline;
   a primary and a neutral call to action; an install pill, or at most four tabs when there are
   several methods; a window card with five to eight lines of code or a screenshot pair.
2. Four feature cards with icon tiles (SVG icons, not emoji), titles of 16px and details of 15 to
   25 words, the same items as the README bullets.
3. Optionally one "see it work" block with real output.
4. Tokens: type scale 56, 24, 16 and 14px; weights 700 for the hero, 600 for titles and buttons;
   radii of 20, 12 and 6px; one brand colour; monospace for commands only; 0.25s colour
   transitions; no scroll animation; honour reduced motion.

Checks added later by the spike and the contrast work: accent text must use the scheme-aware link
colour, and the brand colour must pass on both scheme backgrounds ([p0-spike.md](p0-spike.md)).
