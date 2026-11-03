# AS-IS scope and coverage

## ADDED Requirements

### Requirement: The AS-IS scope is a maintained list
The product SHALL keep `coverage-matrix.md` as the authoritative list of what an application's AS-IS consists of, with
a status (BUILT, PARTIAL, PLANNED, NOT_ASSESSED, OUT) and a method (F, S, G, T, X) for every item; the counts SHALL be
regenerated from the tables by a script, and a BUILT row SHALL name the fact or control and the test that covers it.
Status: BUILT, uncommitted (T-1.2, T-1.3): `openspec/scripts/matrix.py --write` regenerates the counts, `--check` fails on
drift or on a BUILT row with no test; every BUILT row names its test; test
`openspec/scripts/test_matrix.py::MatrixTest.test_check_fails_on_a_built_row_without_a_test`.

#### Scenario: an item is added
- WHEN a new AS-IS item is identified
- THEN it is added to its area as PLANNED with its method, and the counts are regenerated

### Requirement: Nothing is silently absent from the report
Every coverage-matrix item that is not BUILT for the analysed stack SHALL appear on the Scope page once for the
portfolio with its status and reason, and SHALL NOT appear per application as "not checked" (R-17).
Status: PLANNED.

#### Scenario: database indexes
- WHEN a client asks whether missing indexes were checked
- THEN the Scope page lists "Missing indexes: out of scope (needs query plans)"

### Requirement: The AS-IS view covers every area, with facts only
Each application's AS-IS view SHALL have a place for every coverage-matrix area (A0-A24), showing the facts read with
their evidence or search record, or "not read in this version" once for an area with none. It SHALL NOT show
assessment states, aspect statuses or findings (R-12).
Status: PARTIAL (AS-IS tab exists, commit c19fc9a, covering stack, components, dependencies, configuration, evidence;
it still shows aspect status, UI review A4).

#### Scenario: an application on an old framework
- WHEN the AS-IS view shows Spring Boot 1.5.10
- THEN it shows the version and the build line it was read from, and the support verdict appears only in the
  Assessment view, linked from the fact

### Requirement: What the client states is kept apart from what was read
Team, business criticality and other client-stated facts SHALL be shown as "stated by the client", from the input list
or a criticality file, and SHALL NOT be inferred from code.
Status: PARTIAL (team shown; the list file's criticality column is carried but not shown, and the criticality
dimension reads only `--criticality`).

#### Scenario: criticality in the input list
- WHEN the input list has `criticality = high` for an application
- THEN the application shows "Criticality: high (stated by the client)" and it can be filtered on

### Requirement: Modernisation targets are declared, not assumed
A run MAY declare a modernisation target (framework, Java version, platform); readiness gaps SHALL be raised only
against a declared target.
Status: PLANNED.

#### Scenario: no target
- WHEN no target is declared
- THEN readiness items appear as AS-IS facts only
