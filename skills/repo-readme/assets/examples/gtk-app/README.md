<h1 align="center">
  <img alt="Driftwood icon" src="docs/assets/logo.svg" width="96">
  <br>Driftwood
</h1>

<p align="center"><strong>A calm notes app for GNOME that keeps every note as plain Markdown.</strong></p>

<p align="center">
  <a href="https://github.com/example/driftwood/actions/workflows/ci.yaml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/example/driftwood/ci.yaml?style=flat-square"></a>
  <a href="https://flathub.org/apps/io.example.Driftwood"><img alt="Flathub" src="https://img.shields.io/flathub/v/io.example.Driftwood?style=flat-square"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/github/license/example/driftwood?style=flat-square"></a>
</p>

<p align="center"><a href="https://example.github.io/driftwood/">Documentation</a> · <a href="#-installation">Install</a> · <a href="CONTRIBUTING.md">Contributing</a></p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/screenshot-dark.svg">
    <img alt="Driftwood's main window: the note list on the left, an open note on the right" src="docs/assets/screenshot-light.svg" width="800">
  </picture>
</p>

Driftwood is a notes app for the GNOME desktop. Your notes stay Markdown files in a folder you
choose, so nothing locks them in.

## ✨ Features

- **Plain files:** notes are Markdown files that any editor, sync tool or backup can read.
- **Instant search:** every matching note appears as you type, title matches first.
- **Light and dark:** follows the system style and adapts from a phone to a wide desktop.
- **Keyboard first:** every action has a shortcut, listed in the shortcuts window.

## 📦 Installation

```sh
flatpak install flathub io.example.Driftwood
```

<a href="https://flathub.org/apps/io.example.Driftwood"><img width="200" alt="Get it on Flathub" src="https://flathub.org/api/badge?locale=en"></a>

## 🛠️ Building from source

The [build guide][build] covers Meson and Flatpak builds and the dependencies each needs.

## 🌍 Translations

Translations live in the `po/` directory; the [guide][docs] explains how to add a language.

## 🤝 Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) first. Driftwood follows the
[GNOME Code of Conduct](https://conduct.gnome.org/).

## 📝 License

Licensed under the [GNU General Public License v3.0 or later](LICENSE).

[docs]: https://example.github.io/driftwood/
[build]: https://example.github.io/driftwood/guide/
