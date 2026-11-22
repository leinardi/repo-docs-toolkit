# Releasing

<!-- From the repo-readme skill (references/repo-files.md): the short version, at most 40 lines.
Every command comes from the Makefile or the release workflow; the full procedure, the one-time
setup and the recovery steps live in docs/internal/release.md. Delete this comment. -->

The short version. How it works, the setup and what to do when something fails are in
[docs/internal/release.md](docs/internal/release.md).

Needs <the tools and logins the release commands use, from the Makefile or workflow>. Run it from
an up-to-date <default branch>.

## A release

```sh
<the release command or commands, one per line, each with a short comment>
```

<How the version is chosen: given explicitly, or derived from the commits (and by which tool).>

## When something fails

<One paragraph: what to run again and what it does not repeat, as the release tooling
guarantees. Link to the recovery section of docs/internal/release.md for anything longer.>
