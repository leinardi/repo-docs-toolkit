<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://example.org/logo-dark.svg">
    <img src="https://example.org/logo.svg" alt="Tool logo" width="96">
  </picture>
  <br>Tool
</h1>

<p align="center"><strong>Checks your docs against your code.</strong></p>

<p align="center">
  <a href="https://github.com/example/tool/actions"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/example/tool/ci.yaml?style=flat"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/github/license/example/tool?style=flat"></a>
</p>

<p align="center"><a href="#-install">Install</a> · <a href="#-usage">Usage</a></p>

## ✨ Features

- **Fast:** reads only what changed.
- **Honest:** says what it could not check.

## 📦 Install

```sh
pip install tool
```

## 🚀 Usage

Run `tool check` in the repository root. It prints a report and exits non-zero when it finds
problems, so it fits a CI job. The report lists each finding with its file and line.

```console
$ tool check
no findings
```

## 📖 Documentation

The full guide covers configuration, the report format and the exit codes.

Configuration lives in one file. Every option has a default, so a new
repository needs no configuration at all. The guide shows each option with
an example and explains when you would change it.

The report format is stable: every finding has an id, a severity, a file
and a line. The exit codes are 0 for clean, 1 for findings and 2 for a
usage error, so scripts can tell them apart.

## 🛠️ Development

Clone the repository and run the tests:

```sh
make test
```

The tests use fixtures under `tests/fixtures`: small repositories with
planted problems, each with the list of findings the tool must report.

## 🤝 Contributing

Read CONTRIBUTING.md before you open a pull request.

## 🔒 Security

Report vulnerabilities privately, as SECURITY.md describes.

## 📝 License

MIT.
