---
name: adversarial-review
description: >
  Adversarial review of changes to repo-docs-toolkit: working tree, staged diff,
  branch, commit range, or PR. Hunts for guidance that would make an agent write
  false claims into someone's docs, docstool checks that miss real problems or
  flag correct docs, side effects docstool must not have, vendored copies that
  drift, claims about Zensical, MkDocs, GitHub or Claude Code that no source
  supports, weakened skill triggering, and CI/tooling gaps, then reports ranked
  findings. Use when the user asks to review changes, a diff, a PR, a branch or
  a commit, check work before committing, assess merge readiness, or poke holes
  in a change to this repository.
---

# Adversarial Review - repo-docs-toolkit

Assume the change teaches an agent something wrong, or makes docstool report a
clean result for broken docs, until proven otherwise. Do not praise or restyle.
A review with no findings is credible only after real attempts to break the
change.

Copy this checklist and tick items as you go:

```text
Review progress:
- [ ] 1. Diff and intent established (default scope if none given)
- [ ] 2. AGENTS.md read
- [ ] 3. Claims and checks verified
- [ ] 4. Consistency passes run
- [ ] 5. Gates run
- [ ] 6. Report written
```

## 1. Establish the diff

Never review from memory or from the user's description alone. With no scope
given, review the uncommitted work; if the tree is clean, review the branch
against `main`.

| User intent | Command |
| --- | --- |
| uncommitted changes | `git status --short`, then `git diff HEAD`; read every untracked file too |
| staged changes only | `git diff --staged` |
| branch, "this PR", "ready to merge" | `git diff main...HEAD` |
| commit range | `git diff <base>..<head>` |
| GitHub PR number | `gh pr view <n>`, then `gh pr diff <n>` |

## 2. Load project authority

Read `AGENTS.md`: its rules are review checks.

## 3. Verify claims and checks

- **Tool claims** (Zensical, MkDocs, GitHub rendering, Claude Code): confirm in
  the installed tool, its source or its official docs at the stated version.
  Build a scratch site when the claim is about Zensical output. Unverifiable
  claims must carry `(verify)`.
- **docstool checks**: for every new or changed check, construct an input it
  should flag and one it must not, and run docstool on both in a scratch copy.
  A check that cannot fail, or that fires on the `clean` fixture, is a finding.
- **Fail-closed coverage**: an input docstool cannot parse must give exit 3 or
  a `partial` row, never exit 0.
- **Side effects**: docstool writes only what its command documents; no
  network access, no project code outside `site-build`, no writing git
  commands, no path outside `--root` (try `..`, absolute paths and symlinks).

## 4. Consistency passes

- **Vendored copies**: the three `docstool.py` files are byte-identical.
- **Skills ↔ docstool**: every `docstool <command>` and flag named in shipped
  text exists, with the behaviour the text describes.
- **References ↔ each other**: no two files give conflicting advice; sibling
  links use exact file names; each SKILL.md routing table lists every reference.
- **Skill metadata**: frontmatter has only `name` and `description`;
  descriptions still say what and when, stay under 1024 characters, and were
  not narrowed in a way that stops triggering.
- **Attribution**: adapted third-party material is in `THIRD_PARTY_NOTICES.md`.
- **Commit types**: `feat`/`fix` only for what ships (skills, references,
  assets, docstool); tooling and CI never use `perf`/`refactor`.

## 5. Gates

Run `make check`, `make test` and `make validate-plugin`; say so explicitly
when the host cannot run one.

## 6. Report

Rank findings most severe first:

```text
<path>:<line> — <title> [blocker|major|minor]
Evidence: <the failing command, docstool output, doc quote or source line>
Fix: <the change>
```

Blocker: guidance that makes an agent write false docs or lose content, a
docstool false clean result, or a forbidden side effect. Major: wrong or
unsupported claim, a check with false positives on correct docs, untested
docstool path. Minor: unclear wording, missing cross-link. End with what was
verified and what could not be.
