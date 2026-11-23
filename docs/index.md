---
title: Home
template: home.html
hide: [navigation, toc]
home:
  text: Agent skills for repository docs
  tagline: Repository docs that stay true to the code.
  actions:
    - { text: Get started, link: getting-started/, primary: true }
    - { text: GitHub, link: https://github.com/leinardi/repo-docs-toolkit }
---

<div class="rdt-showcase" markdown>

```console
$ python3 -I docstool.py drift --max 3
docstool drift: 5 findings (P1: 2, P2: 1, P3: 2); coverage complete
...
Findings:
  F1 [P1][verified] flag-unknown docs/usage.md:5: svc --port: the code defines no such flag
      fix: update the doc to the current flag name
  F2 [P1][verified] make-target-missing docs/usage.md:7: make release: no such target in Makefile or the files it includes
      fix: targets: build, lint
  F3 [P2][likely] env-unknown docs/usage.md:13: SVC_TIMEOUT is documented but nothing in the repository reads it
      evidence: dependencies were not scanned
      fix: remove it from the docs, point at the code that reads it, or confirm that a dependency reads it
  ... 2 more (raise --max or use --format json)
```

</div>

<div class="rdt-install" markdown>

<!-- Content tabs indent their fenced blocks, which markdownlint reads as indented code. -->
<!-- markdownlint-disable MD046 -->

=== "Claude Code"

    ```text
    /plugin marketplace add leinardi/repo-docs-toolkit
    /plugin install repo-docs-toolkit@repo-docs-toolkit
    ```

=== "npx skills"

    ```sh
    npx skills add leinardi/repo-docs-toolkit
    ```

=== "OpenCode"

    ```sh
    npx skills add leinardi/repo-docs-toolkit -a opencode
    ```

<!-- markdownlint-enable MD046 -->

</div>

## Features

<div class="grid cards" markdown>

- :lucide-file-check:{ .lg }

    **Grounded in the code**

    Every claim comes from the source, a command's help, the tests or you. Anything else is
    marked for verification, never guessed.

- :lucide-folder-tree:{ .lg }

    **Restructures that lose nothing**

    An approved plan, a transactional apply and a verify step that accounts for every block,
    link, anchor and old URL.

- :lucide-layout-template:{ .lg }

    **Zensical sites with a landing page**

    Configuration, migration from MkDocs, GitHub Pages and a developer landing page that keeps
    the native header, search and palette.

- :lucide-book-open-text:{ .lg }

    **Lean READMEs**

    A README of 50 to 150 lines that matches the homepage, plus the community files a
    repository actually needs.

</div>
