# Writing rules

Read this when you draft or edit prose in someone's docs. These are the rules whose breach changes
what a reader does; general style is the repository's own, found with the probes at the end.

## Contents

- Rules that change meaning
- Commands and code
- Local style probes
- What not to do

## Rules that change meaning

| # | Rule | Why |
| --- | --- | --- |
| W1 | Put a warning before the step it guards, in the same section | A reader stops reading once the step works |
| W2 | Keep "must", "never", "do not" and "only" exactly as strong as the source | Softening a requirement changes behaviour |
| W3 | One term per concept, the one the code and UI use | A synonym reads as a different thing |
| W4 | State conditions before the action: "On macOS, run ..." | Readers act on the first clause |
| W5 | Name versions, platforms and limits explicitly; no "recent", "modern", "fast" | Vague qualifiers cannot be verified |
| W6 | Write the default value, not "the default" | Readers need the value to decide |
| W7 | Say what happens on failure when the code defines it (exit code, message) | Readers need to recognise the failure |
| W8 | Use the present tense for current behaviour; date anything historical | Mixed tense reads as current |
| W9 | Make every link text say where it goes; no "here" or "this page" | Links are scanned, not read |
| W10 | Give every image alt text that says what it shows | Screen readers, and the image may not load |
| W11 | Use numbered lists for ordered steps, bullets only when order does not matter | Order is an instruction |
| W12 | Keep one action per numbered step | Combined steps get half-done |
| W13 | Quote UI labels and messages exactly, in the case the program uses | Readers search for the exact text |
| W14 | Do not promise what the code does not enforce ("safe", "always", "guaranteed") | It becomes a false claim |
| W15 | Mark unknowns as `TODO(verify: ...)`, never paper over them | See evidence.md |

## Commands and code

- Shell examples use the fence info string the repository already uses (`sh`, `bash`, `console`).
  When a block shows a prompt (`$`), output lines carry none.
- Placeholders follow the repository's existing form (`<name>`, `NAME`, `{name}`). When it has none,
  use `<name>` and say what to put there the first time it appears.
- Every command is copy-pasteable: no smart quotes, no trailing prompts, line continuations that
  work in the shell named in the fence.
- Commands that change the system (install, delete, flash, publish) are preceded by what they
  change.
- Code blocks are byte-exact copies of the repository file or the program's output when they claim
  to be one. When a block shows a file the repository has, prefer including it with the site's
  snippet syntax over pasting a copy that will drift.

## Local style probes

Run these before your first edit and match what wins. A habit that is inconsistent across the
docs is not a rule; follow the file you are editing, and mention the inconsistency in the report.

| Question | How to find out |
| --- | --- |
| Line wrap | `house_style.wrap_p95` in the inventory, the markdownlint `line-length` setting in `doc_tooling` |
| List marker, fence style, heading case | `house_style` in the inventory |
| Spelling (US or UK), product names, terms | Count variants across the docs, for example `grep -rio "colou\?r" docs \| sort \| uniq -c` |
| Admonition syntax | The site config's extensions; existing `!!! note` or `> [!NOTE]` blocks |
| Second person or "we" | The first paragraphs of the three most-linked pages |
| A style guide | `CONTRIBUTING.md`, `STYLE.md`, `docs/style*`, `.vale.ini` |

A written style guide in the repository outranks this file.

## What not to do

- Do not add marketing words (powerful, seamless, blazing), emoji or exclamation marks the
  repository does not already use.
- Do not reflow paragraphs you did not change, and do not "tidy" tables, headings or lists outside
  the task.
- Do not translate or change the language of a page.
- Do not turn a reference table into prose, or prose into bullets, unless that is the task.
