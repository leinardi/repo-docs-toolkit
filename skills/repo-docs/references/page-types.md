# Page types

Read this when you write a new page, extend one, or judge whether a page does one job. The four
types follow [Diátaxis](https://diataxis.fr/); the checks below are written so you can test them.

## Contents

- Choosing the type
- Tutorial
- How-to guide
- Reference
- Explanation
- Pages that are not one type
- Before you begin and What's next

## Choosing the type

| The reader | Type | Title pattern | Must not contain |
| --- | --- | --- | --- |
| Is new and wants to learn by doing | Tutorial | "Get started with X", "Your first X" | Option lists, alternatives, design history |
| Has a goal and knows the basics | How-to | A task: "Install on Fedora", "Rotate the signing key" | Teaching, every option, rationale beyond one line |
| Needs a fact while working | Reference | The thing: "Configuration", "CLI", "Exit codes" | Procedures, opinions, narrative |
| Wants to understand why | Explanation | A topic: "How switching works", "Security model" | Steps to follow, complete option lists |

Match the repository's existing title style before these patterns (the inventory's
`house_style.heading_case` and the titles already in the nav).

## Tutorial

One path from nothing to a visible result, with no choices.

Checks:

- Every step states what the reader sees when it worked (output, a file, a window).
- Every command runs on a clean checkout or a stated starting point; prerequisites are listed
  first, with versions taken from the build files.
- No step depends on something only explained later.
- The tutorial ends by pointing to the how-to guides and the reference.

## How-to guide

The steps to reach one goal, for a reader who chose the goal.

Checks:

- The goal is in the title and the first sentence.
- Steps are numbered; each is one action. Alternatives appear as a short note or a separate guide.
- Every command, flag and path is checked by `docstool drift` or a cited source.
- Verification is a step: how the reader knows it worked.
- Destructive or irreversible steps carry their warning before the step, not after.

## Reference

Facts in a fixed, repeated shape, so a reader finds one in seconds.

Checks:

- One entry per item, in the same order for every entry: name, type or value form, default,
  description, example. Missing fields say "none", never skip silently.
- Completeness: every flag the parser defines, every config key the struct reads, every env var
  the code reads, every exit code returned. `drift` reports both directions (documented but
  absent, present but undocumented).
- Sorted in the order a reader looks things up (alphabetical, or the order of the file format).
- Generated reference is changed through its generator only.

## Explanation

Context, the idea, the trade-offs, and how it fits the whole.

Checks:

- It answers a "why" or "how does it work" question a reader would ask; the question can be
  stated in one sentence.
- Claims about behaviour cite code, tests or a design record, like any other fact.
- It links to the reference and how-to pages instead of repeating their content.

## Pages that are not one type

Many repositories have pages that teach, instruct and list options at once. When you edit one:

- Adding content: put it in the part of the page whose type matches, or propose a new page.
- Restructuring: plan a `split` by heading (restructure.md) so each part becomes one type; keep the
  original anchors working.
- Never split a page as a side effect of another task.

## Before you begin and What's next

How-to guides and tutorials open with "Before you begin" when they need anything beyond the
previous page: versions, permissions, accounts, hardware. They end with "What's next" linking one
to three follow-up pages. Use the repository's own wording for these headings if it has one.
