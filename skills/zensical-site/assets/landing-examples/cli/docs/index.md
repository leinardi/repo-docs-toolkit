---
title: Home
template: home.html
hide: [navigation, toc]
home:
  text: Batch renames you can review
  tagline: Rename thousands of files safely, with a preview of every change.
  actions:
    - { text: Get started, link: getting-started/, primary: true }
    - { text: GitHub, link: https://github.com/example/ferrule }
---

<div class="rdt-showcase" markdown>

```console
$ ferrule 's/IMG_(\d+)/holiday-$1/' photos/
photos/IMG_0001.jpg  ->  photos/holiday-0001.jpg
photos/IMG_0002.jpg  ->  photos/holiday-0002.jpg
2 files to rename. Apply? [y/N] y
Renamed 2 files.
```

</div>

<div class="rdt-install" markdown>

=== "cargo"

    ```sh
    cargo install ferrule
    ```

=== "brew"

    ```sh
    brew install ferrule
    ```

=== "binary"

    ```sh
    curl -fsSLO https://github.com/example/ferrule/releases/latest/download/ferrule-x86_64-linux.tar.gz
    ```

</div>

## Features

<div class="grid cards" markdown>

- :lucide-eye:{ .lg }

    **Preview first**

    Every run prints the full rename plan and waits for your answer, so nothing moves before you have read it.

- :lucide-undo-2:{ .lg }

    **Undo the last run**

    Each applied run writes a journal next to the files, and `ferrule undo` puts every name back.

- :lucide-shield-check:{ .lg }

    **No collisions**

    Two files that would end up with the same name stop the run before anything is renamed.

- :lucide-zap:{ .lg }

    **Fast on big trees**

    Directories are walked in parallel, so a hundred thousand files take seconds rather than minutes.

</div>
