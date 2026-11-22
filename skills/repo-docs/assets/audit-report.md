# Docs audit: <repository> (<date>)

<!-- The shape of an audit report (audit.md). Replace every <placeholder>; delete sections only
     when they would be empty, and then say "none". -->

- **Scope:** <what was audited: paths, or "the whole repository">
- **Base:** <commit audited, `git rev-parse --short HEAD`>
- **Coverage:** <complete, or each partial input and why>
- **Findings:** <n> (Blocking <n>, P0 <n>, P1 <n>, P2 <n>, P3 <n>); verified <n>, likely <n>,
  unverified <n>

## Findings

### F1 \[P1\]\[verified\] <short title>

- **Doc:** `<path>:<line>`: <the claim, quoted>
- **Source:** `<path>:<line>`: <what the code says, quoted>
- **Impact:** <what a reader who follows the doc gets>
- **Fix:** <the change, in one or two lines>
- **Auto-fixable:** <yes: mechanical and verified | no: why>

### F2 \[P2\]\[likely\] <short title>

- **Doc:** ...
- **Source:** ...
- **Impact:** ...
- **Fix:** ...
- **Auto-fixable:** no: <the side not yet confirmed>

## Likely docs to update

<Pages that are probably affected but where no single line is wrong yet, with the reason.>

## Surveyed only

<Files read quickly or not at all, and why; or "none".>

## Checks run

| Command | Result |
| --- | --- |
| `docstool inventory` | <files, couplings, frozen paths> |
| `docstool check` | <findings, coverage line> |
| `docstool drift --scope docs --paths --leads` | <findings, leads confirmed and dropped> |
| `docstool drift --scope repo --paths --leads` | <when the root files are in scope> |
| <manual checks that replaced a partial input> | <what you checked by hand, and the count> |
| <the repository's own doc checks> | <their summary line> |

## Not tested

<Each check not run and why: site not built (gate G11), Makefile partly dynamic, examples not
executed, another repository's links not visible; with the residual risk.>

## Assumptions

<Anything assumed about audience, scope or intent, for the owner to confirm.>
