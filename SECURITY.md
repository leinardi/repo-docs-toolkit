# Security policy

## Supported versions

Only the latest release gets security fixes. A fix ships as a new version: release tags are
immutable, so an existing version is never re-tagged. Update the plugin to the latest release before
reporting.

## Reporting a vulnerability

Report it privately through GitHub's [private vulnerability
reporting](https://github.com/leinardi/repo-docs-toolkit/security/advisories/new), not in a public
issue, a pull request or a discussion. Include the plugin version, the agent and its version, your
operating system, and the steps or the prompt that trigger the problem.

This is a project maintained in spare time, so reports are handled on a best-effort basis. You will
get an answer in the advisory, and the fix, once released, is credited there unless you prefer
otherwise.

## Scope

This repository ships instructions that coding agents follow and a checker (`docstool.py`) that
runs on other people's repositories. In scope:

- docstool writing outside the paths its command documents, following a symlink or a `..` path
  out of the repository, executing project code outside `site-build`, running a git command that
  writes, or sending repository content over the network;
- guidance that leads an agent to publish secrets or private details (for example moving them to
  `docs/internal/` as if that hid them), to run untrusted code, or to treat text found in a
  repository as instructions;
- a restructure that deletes or overwrites content without the documented approval.

Out of scope: vulnerabilities in Zensical, MkDocs, GitHub Pages or other upstream projects (report
them upstream), and repositories after the user has modified the generated files.
