# README templates

Read this when you draft a README from scratch or rewrite one (gate R1). Pick the skeleton for the
project type, fill each placeholder from the file the table under it names, and delete what the
project does not have: a section is never kept with invented content. [readme.md](readme.md) has
the rules each part follows. Complete examples that pass `docstool readme` are in
`assets/examples/` (`cli`, `gtk-app`, `library`).

## Contents

- [Command-line tool](#command-line-tool)
- [GTK or Flatpak app](#gtk-or-flatpak-app)
- [Library](#library)
- [Service](#service)
- [Where each placeholder comes from](#where-each-placeholder-comes-from)

## Command-line tool

````markdown
<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="<logo-dark>">
    <img alt="<NAME> logo" src="<logo>" width="96">
  </picture>
  <br><NAME>
</h1>

<p align="center"><strong><tagline></strong></p>

<p align="center">
  <a href="<ci-url>"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/<owner>/<repo>/<workflow>?style=flat-square"></a>
  <a href="<release-url>"><img alt="Release" src="https://img.shields.io/github/v/release/<owner>/<repo>?style=flat-square"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/github/license/<owner>/<repo>?style=flat-square"></a>
</p>

<p align="center"><a href="<docs-url>">Documentation</a> · <a href="#-installation">Install</a> · <a href="CONTRIBUTING.md">Contributing</a></p>

<One or two sentences: what it does and for whom.>

## ✨ Features

- **<Title>:** <one sentence>.
- **<Title>:** <one sentence>.
- **<Title>:** <one sentence>.

## 📦 Installation

```sh
<the recommended install command>
```

<At most two alternatives in a sentence>, and every other method in the [installation guide][install].

## 🚀 Usage

```console
$ <a real command>
<its real output, shortened>
```

See the [documentation][docs] for every command and option.

## 🤝 Contributing

Bug reports and pull requests are welcome; read [CONTRIBUTING.md](CONTRIBUTING.md) first.

## 📝 License

Licensed under the [<licence name>](LICENSE).

[docs]: <docs-url>
[install]: <docs-url>/<install page>/
````

## GTK or Flatpak app

Changes from the command-line skeleton:

- **Badges:** CI, the shields.io Flathub version badge in place of the release badge, License.
  The official Flathub button goes in 📦 Installation.
- **Visual:** a screenshot pair after the intro, light and dark, from the app's metainfo
  screenshots when they exist:

  ```html
  <p align="center">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="<screenshot-dark>">
      <img alt="<what the screenshot shows>" src="<screenshot-light>" width="800">
    </picture>
  </p>
  ```

- **Installation:** `flatpak install flathub <app-id>`, with the Flathub button. Not on Flathub
  (no app id in the Flathub links or the manifest): the section is building from source.
- **Extra sections:** 🛠️ Building from source (the `meson` or `flatpak-builder` commands the
  repository uses, or a link to the docs page) and 🌍 Translations (where translations happen:
  the `po/` directory or the translation platform the project links).
- **Code of conduct:** a GNOME app that follows the GNOME Code of Conduct links it; do not add a
  second one.

## Library

Changes from the command-line skeleton:

- **Badges:** CI, the registry version (crates.io, PyPI, npm), the API docs (docs.rs or the docs
  site), License.
- **No screenshot.** The visual is a 10 to 20 line code example in 🚀 Quick start, using only
  the public API, compiled or run when that is safe and agreed.
- **Installation:** the one-line add command (`cargo add <name>`, `pip install <name>`), then
  one line on the supported versions (MSRV, Python versions) from the manifest.
- **Images are absolute URLs**: the README is also the registry page.

## Service

Changes from the command-line skeleton:

- **Badges:** CI, the container image or release, License.
- **Installation:** the compose file or the container command from the repository, linked rather
  than copied when it is longer than a few lines (`compose.yaml`), with the required environment
  variables named in one sentence and documented in the docs. No compose file meant for users and
  no published image: build from source, and link the deployment example in the docs.
- **Usage:** how to reach it once running (port, URL, health endpoint), as the code defines it.
- **🔒 Security:** one line linking SECURITY.md; a service gets one.

## Where each placeholder comes from

| Placeholder | Source |
| --- | --- |
| `<NAME>` | The package manifest name, the app's display name in its metainfo or desktop file, `site_name` in the site config, or the existing README's title |
| `<tagline>` | `home.tagline` in `docs/index.md` when there is a homepage; otherwise the manifest description, `site_description`, or the repository description (`gh repo view --json description`); none of these: ask |
| `<logo>`, `<logo-dark>` | Files in the repository (`docs/assets/`, `data/icons/`); none: no logo (R2) |
| `<owner>`, `<repo>` | `git remote get-url origin` |
| `<workflow>` | The workflow file that runs the tests, in `.github/workflows/` |
| `<release-url>` | Releases exist: `gh release list --limit 1` |
| `<docs-url>` | `site_url` in `zensical.toml` or `mkdocs.yml`, or the repository homepage field; no site: the docs index in the repository (`docs/README.md`, `docs/index.md`) as a relative link, and no docs badge |
| `<app-id>` | The metainfo or Flatpak manifest id |
| Install and usage commands | The Makefile, manifest, the code, `--help` when safe to run; the project's install docs only as a lead, each command confirmed in the code first |
| Features | The homepage's feature cards; otherwise capabilities the code has, each traceable to it |
| `<licence name>` | The LICENSE file's text, or the manifest's licence field |
