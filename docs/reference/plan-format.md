# The plan format

A restructure is driven by `docs/internal/restructure/plan.toml`. docstool reads it with Python's
`tomllib`, so it is plain TOML. The skill writes the plan; you read it, and approve it.

## `[meta]`

| Key | Value |
| --- | --- |
| `schema` | `1` |
| `base_commit` | The commit the plan was written against; `HEAD` must be it or descend from it |
| `docs_dir` | The site's docs directory, usually `"docs"` |
| `site_config` | `"zensical.toml"`, `"mkdocs.yml"`, or left out when there is no site |
| `blocks` | The block baseline written by `docstool inventory --blocks` |
| `inventory` | Optional: an inventory report (`inventory --format json --out`) kept with the plan |
| `[meta.sources]` | `"path" = "<sha256>"` for every file the plan moves, splits, merges, deletes or edits, the site config and the blocks baseline |

## Entries

Entries are arrays of tables. Paths are relative to the repository root.

| Entry | Keys | Effect |
| --- | --- | --- |
| `[[move]]` | `from`, `to`, optional `redirect_to` | Moves the file, rewrites links, adds a redirect when the source was published |
| `[[archive]]` | `from`, `to`, `status`, optional `redirect_to` | A move plus the status line `> **Status:** <status>` under the title |
| `[[split]]` | `from`, `heading`, `to`, optional `status` | Moves the section under a heading (which must occur once) to a new file; `status` writes the status line under its title |
| `[[merge]]` | `from` (list), `into` | Declares a merge the agent does by hand after apply |
| `[[anchor]]` | `file`, `from`, `to` | Re-points links to `file#from` at `#to` |
| `[[stub]]` | `path`, `target`, optional `title` | Writes a one-line "This page moved" page |
| `[[reference]]` | `file`, `line`, `old`, `new` | Replaces `old`, exactly once on that line, in a file outside the docs |
| `[[delete]]` | `path`, `approved = true`, `proof` | Deletes an empty file or an exact duplicate |
| `[[freeze]]` | `paths` | Must not change; a trailing `/` covers a directory |
| `[[keep]]` | `paths` | Stays as it is |
| `[[decision]]` | `id`, `question`, `answer` | An open question; `plan validate` refuses while `answer` is empty |

Every doc under the docs directory must be covered by some entry.

## `[approval]`

`docstool plan approve --by <name>` writes this table once `plan validate` passes: the plan's
SHA-256 (computed without the `[approval]` table), the SHA-256 of its decisions (every table but
`[meta]` and `[approval]`), who approved it and when. `plan apply --write` refuses when the
plan, or any file in `[meta.sources]`, has changed since.

## Rebasing on a newer upstream

When upstream changes the docs before an approved restructure is merged, the plan is moved, not
the applied commits. On a checkout of the fetched upstream ref, with the plan artifacts brought
over, `docstool plan rebase --onto origin/main` keeps every decision and rewrites only `[meta]`:
`base_commit` becomes the upstream commit, and the block baseline, the inventory and every
`[meta.sources]` hash are recomputed from it. It refuses, writing nothing, unless the ref is under
`refs/remotes/`, `HEAD` is that commit, the tree is clean apart from the plan artifacts, the plan
was not applied in this tree, the old `base_commit` is an ancestor of the ref, and no file a
`[[reference]]` entry edits changed upstream. It reports what upstream changed, block by block,
and whether the decisions still match the approved ones. Without `--write` it is a dry run.

## Mappings

Blocks that the agent rewrites or drops after apply are accounted for in
`docs/internal/restructure/mappings.toml`, separate from the plan, so editing a mapping never
invalidates the approval:

```toml
[[rewritten]]
id = "m1"
blocks = ["<hash from blocks.json>"]
to = "docs/guide/install.md"
heading = "Install"

[[dropped]]
id = "m2"
blocks = ["<hash>"]
proof = "exact duplicate of docs/guide/release.md:5"

[[github_loss]]
id = "m3"
path = "docs/old.md"
anchors = ["details"]
reason = "the owner renamed this section"
```

`docstool plan mappings` prints a skeleton of this file to stdout, one entry per block occurrence
still unaccounted for. It writes no file, and an entry left with an empty `to` or `reason` cannot be
approved.

`docstool plan approve --mappings` prints each mapping's text for you to review and writes a
receipt for it to `review-receipts.json`. Changing the mapping, its baseline blocks or its
destination afterwards invalidates the receipt.

A `[[github_loss]]` entry accepts a GitHub URL that a restructure of a repository with no site loses
on purpose. `page = true` accepts a path that no longer exists; for a page that still exists,
`anchors` names each lost fragment.

## An example

The plan the skill ships as its example:

```toml
--8<-- "skills/repo-docs/assets/restructure-plan.example.toml"
```
