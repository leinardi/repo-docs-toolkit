# Write the README and community files

The repo-readme skill writes a README in the style of projects such as Starship, Neovim and Typst:
a short front page that says what the project is, how to install it and where the docs are, and
leaves the rest to the docs.

```text
Rewrite the README. Keep it short and match the docs homepage.
```

## The README

The skill detects the kind of project (a CLI, a GTK or Flatpak app, a library, a service) and
drafts from the matching template. It asks first whether to rewrite or edit in place, and moves
anything it would remove into the docs before removing it. The result follows a few fixed rules:

- 50 to 150 lines, with no reference material the docs already hold;
- a centred header with the logo (when one exists), a bold tagline, at most four badges in one
  style and a line of links;
- emoji only as the first character of a section heading, from a fixed set;
- a `<picture>` element always has an `<img>` fallback, and images are absolute URLs when the
  README is also shown on a package registry;
- no invented logo, claim, badge or support channel.

`docstool readme` checks these rules. With `--home docs/index.md` it also checks that the
README's tagline, feature titles and first install block match the site's home page, so the two
front pages never drift apart.

## Community files

| File | What the skill writes |
| --- | --- |
| `CONTRIBUTING.md` | Setup, checks and the pull-request flow; it links to `AGENTS.md` instead of repeating it |
| `SECURITY.md` | How to report a vulnerability privately, checked against the repository's settings; no invented response times |
| `CODE_OF_CONDUCT.md` | The Contributor Covenant 3.0, verbatim, and only once you agree to add one |
| `RELEASING.md` | A cheat sheet of at most 40 lines that links to the full procedure in `docs/internal/release.md` |
| `CHANGELOG.md` | Only when no release tooling writes the notes already |

The skill's references hold the details:
[readme][repo-readme-readme],
[templates][repo-readme-readme-templates] and
[repository files][repo-readme-repo-files].

[repo-readme-readme]: https://github.com/leinardi/repo-docs-toolkit/blob/main/skills/repo-readme/references/readme.md
[repo-readme-readme-templates]: https://github.com/leinardi/repo-docs-toolkit/blob/main/skills/repo-readme/references/readme-templates.md
[repo-readme-repo-files]: https://github.com/leinardi/repo-docs-toolkit/blob/main/skills/repo-readme/references/repo-files.md
