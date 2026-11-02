# OpenSpec for app-insight

Requirements and design are written here before code changes. The layout follows OpenSpec
(`proposal.md`, `design.md`, `tasks.md`, `specs/<capability>/spec.md` per change). The CLI is not installed.

- `config.yaml`: project context and the numbered project rules (R-01 ...) every design is checked against.
- `changes/asis-baseline/`: the product baseline, from the full AS-IS scope down to the report. Under review.
  Read `proposal.md` first, then `design.md` and `coverage-matrix.md`, then the capability specs.

Status words used throughout:

| Word | Meaning |
|---|---|
| DECIDED | settled by the user in session, or decided in the upstream design; the source is cited |
| PROPOSED | recommended here, needs sign-off |
| OPEN | needs a decision before the work it blocks |
| BUILT | in the code today; cites the commit and the test |
| PARTIAL | some of it is built; says which part |
| PLANNED | not built |
