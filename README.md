<h1 align="center">repo-docs-toolkit</h1>

<p align="center"><strong>Repository docs that stay true to the code.</strong></p>

<p align="center">
  <a href="https://github.com/leinardi/repo-docs-toolkit/actions/workflows/ci.yaml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/leinardi/repo-docs-toolkit/ci.yaml?branch=main&style=flat-square"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/github/license/leinardi/repo-docs-toolkit?style=flat-square"></a>
</p>

<p align="center">
  <a href="https://leinardi.github.io/repo-docs-toolkit/">Documentation</a> ·
  <a href="#-installation">Install</a> ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

repo-docs-toolkit is a Claude Code plugin, and a set of agent skills for other agents, for the
documentation that lives in a repository. Your agent writes, audits, maintains and restructures the
docs against the code, publishes them as a Zensical site, and keeps the README lean, with a
standard-library checker behind every claim.

## ✨ Features

- **Grounded in the code:** every claim comes from the source, a command's help, the tests or you.
- **Restructures that lose nothing:** an approved plan, a transactional apply and a verify step
  that accounts for every block and old URL.
- **Zensical sites with a landing page:** configuration, migration from MkDocs, GitHub Pages and a
  developer landing page.
- **Lean READMEs:** 50 to 100 lines that match the homepage, plus the community files.

## 📦 Installation

In a Claude Code session:

```text
/plugin marketplace add leinardi/repo-docs-toolkit
/plugin install repo-docs-toolkit@repo-docs-toolkit
```

For OpenCode and other agents, `npx skills add leinardi/repo-docs-toolkit` installs the skills;
the [getting started guide][start] covers each route. docstool needs Python 3.11 or newer.

## 🚀 Usage

Ask your agent in plain words:

```text
Audit the docs in this repository against the code.
Restructure docs/ into a user-facing site and keep the maintainer notes out of it.
Rewrite the README and match the docs homepage.
```

The [documentation][docs] has a guide for each task and the reference for docstool, the
restructure plan and the landing page.

## 🤝 Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md) first.

## 🔒 Security

Report a vulnerability privately, as [SECURITY.md](SECURITY.md) describes.

## 📝 License

Licensed under the [MIT License](LICENSE). Adapted third-party material is listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

[docs]: https://leinardi.github.io/repo-docs-toolkit/
[start]: https://leinardi.github.io/repo-docs-toolkit/getting-started/
