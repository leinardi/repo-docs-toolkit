<h1 align="center">
  <img alt="ferrule logo" src="https://raw.githubusercontent.com/example/ferrule/main/docs/assets/logo.svg" width="96">
  <br>ferrule
</h1>

<p align="center"><strong>Rename thousands of files safely, with a preview of every change.</strong></p>

<p align="center">
  <a href="https://github.com/example/ferrule/actions/workflows/ci.yaml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/example/ferrule/ci.yaml?style=flat-square"></a>
  <a href="https://crates.io/crates/ferrule"><img alt="crates.io" src="https://img.shields.io/crates/v/ferrule?style=flat-square"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/github/license/example/ferrule?style=flat-square"></a>
</p>

<p align="center"><a href="https://example.github.io/ferrule/">Documentation</a> · <a href="#-installation">Install</a> · <a href="CONTRIBUTING.md">Contributing</a></p>

ferrule renames files with a regular expression, shows you every change first, and can undo the
last run. It is made for the photo folders, logs and exports that are too big to rename by hand.

## ✨ Features

- **Preview first:** every run prints the full rename plan and waits for your answer.
- **Undo the last run:** each applied run writes a journal, and `ferrule undo` puts every name back.
- **No collisions:** two files that would get the same name stop the run before anything moves.
- **Fast on big trees:** directories are walked in parallel.

## 📦 Installation

```sh
cargo install ferrule
```

Homebrew (`brew install ferrule`) and prebuilt binaries are covered in the
[installation guide][install].

## 🚀 Usage

```console
$ ferrule 's/IMG_(\d+)/holiday-$1/' photos/
photos/IMG_0001.jpg  ->  photos/holiday-0001.jpg
photos/IMG_0002.jpg  ->  photos/holiday-0002.jpg
2 files to rename. Apply? [y/N] y
Renamed 2 files.
```

Run `ferrule undo` in the same directory to reverse it. The [documentation][docs] covers every
option, the journal format and how ferrule handles symlinks.

## 🤝 Contributing

Bug reports and pull requests are welcome; read [CONTRIBUTING.md](CONTRIBUTING.md) first.

## 🔒 Security

Report a vulnerability privately, as [SECURITY.md](SECURITY.md) describes.

## 📝 License

Licensed under the [MIT License](LICENSE).

[docs]: https://example.github.io/ferrule/
[install]: https://example.github.io/ferrule/getting-started/
