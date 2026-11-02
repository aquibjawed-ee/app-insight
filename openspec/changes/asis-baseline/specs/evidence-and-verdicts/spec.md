# Evidence and verdicts

## ADDED Requirements

### Requirement: Every positive claim cites a line that still says it
A PRESENT, PARTIAL or ISSUE result SHALL cite at least one file and line (negative-scan controls excepted: their
PRESENT means "scanned and nothing found" and SHALL name what was scanned), and the verify gate SHALL re-read every
cited line after every run.
Status: PARTIAL. BUILT for PRESENT and re-reading (ACC-1, ACC-2; commit 4f47cd7;
`tests/test_verify.py::test_a_cited_line_that_does_not_say_it_is_caught`, `test_in_place_without_a_citation_is_caught`).
PLANNED: ACC-2 for PARTIAL and ISSUE (today it checks PRESENT only, `verify.py:109`).

#### Scenario: a file changes after the scan
- WHEN a cited line no longer reads what was cited
- THEN verify fails with ACC-1 and names the control and line

### Requirement: Every verdict derived from not finding something says where it looked
An ABSENT result, a NOT_APPLICABLE result whose reason is that something was not found, an ISSUE that rests on a
default because a setting was not found, and a PARTIAL that rests on a missing part SHALL each carry a search record:
what was looked for, and in which areas, with the number and names of the files searched. The search record SHALL
name only places the detector actually reads.
Status: PARTIAL. BUILT for ABSENT (commit 9479a59; ACC-10; `tests/test_verify.py::test_every_not_found_says_where_it_looked`),
except the `repo` area, which records no count or files today (`aspects.py:384`). PLANNED: the other three verdicts; a
check that `search.for` names only places the detector reads (the owners record names README and build, which are not
read).

#### Scenario: no outbound HTTP client found
- WHEN runtime timeouts are NOT_APPLICABLE because no outbound HTTP client was found
- THEN the result says which source and configuration files were searched for which client types

### Requirement: Absence is decided only where it can be proven
ABSENT, NOT_APPLICABLE by need and ISSUE by default SHALL instead be UNKNOWN (PARTIAL by a missing part keeps its state
with a note), with the reason and the line that causes it,
when (a) the application's framework is outside the control's `understands` list, or the application is a service
with no recognised framework; (b) a blind spot exists in an area in the control's `search.blind_to`; (c) the pipeline
is named as external and no runbook shows a manual step, for pipeline controls; (d) the control is `usually_outside`
and nothing was found.
Status: PARTIAL. (a) BUILT for ABSENT on the 8 controls with `understands`, and for need-based N/A only where the need
is outbound HTTP or database (2 of the 8; `aspects.py:423`) (commit 4f47cd7); (b) BUILT for ABSENT, a note
on PARTIAL (commit 9479a59; CON-8; `tests/test_verify.py::test_a_blind_spot_turns_not_found_into_undecided`,
`test_a_blind_spot_only_hides_what_it_could_hold`); (c) BUILT (commit 203d685); (d) PLANNED; all four for N/A and
ISSUE-by-default PLANNED; verify rules for (a), (d) PLANNED.

#### Scenario: a company parent POM
- WHEN the root pom's parent is `com.acme.platform:acme-service-parent` and not in the repository
- AND no coverage minimum is found in the repository
- THEN the coverage gate is UNKNOWN, citing pom.xml:4
- AND integration tests are still decided, because a parent POM cannot add test classes

#### Scenario: secret scanning on a GitHub repository
- WHEN no secret scanner appears in CI or build files
- THEN secret scanning is UNKNOWN, "Not seen in the repository; confirm with the team (it is often a platform
  setting)", not ABSENT

### Requirement: A README mention does not hide the pipeline
A README naming a CI server SHALL make pipeline controls UNKNOWN only when it states that the pipeline for this
repository runs there (a job name, a URL, "built by"); a bare mention of a CI product SHALL NOT.
Status: PLANNED. Defect: `build_ci.py:37-38` treats any mention as an external pipeline.

#### Scenario: a README that lists Jenkins among supported tools
- WHEN the README says "integrates with Jenkins, TeamCity and GitHub Actions" and no CI file exists
- THEN the build control is ABSENT with its search record, not UNKNOWN

### Requirement: Blind spots are detected and shown
The engine SHALL record, with the line that names each, places the repository points to but does not contain: parent
POMs and Gradle plugins from outside it, remote Gradle scripts, GitLab remote includes, Jenkins shared libraries,
reusable GitHub workflows, Azure templates from another repository, CI systems and build tools it does not parse,
configuration servers and external configuration locations, deployment tools the availability checks do not read,
and (PLANNED) GitOps markers.
Status: BUILT except GitOps (commit 9479a59; `engine/tests/test_accuracy.py::ScopeTest`, 8 tests).

#### Scenario: a classpath configuration location
- WHEN a Dockerfile sets `-Dspring.config.location=classpath:/app.yml`
- THEN no configuration blind spot is recorded

### Requirement: Evidence comes only from files in a role the control accepts
Every file read SHALL have a role (application, build, CI, deployment, configuration, test, fixture or mock, example
or documentation, generated, build output), and a control SHALL accept evidence only from the roles it lists.
Status: PARTIAL (deployment files classified, `graph/resilience.py:47-49`; build output `target`, `build`, `out`
skipped, `evidence.py:17`). PLANNED: general classifier; IDE output such as `bin/` is read as configuration today.

#### Scenario: a stale copy in an IDE output folder
- WHEN `bin/main/logback-spring.xml` duplicates `src/main/resources/logback-spring.xml`
- THEN only the `src/main` file is read as configuration

### Requirement: A failed detector never produces a verdict
Every control fed by a detector that failed on a repository SHALL be NOT_ASSESSED, "the <name> detector failed",
and the failure SHALL appear in the run summary, `summary --json` and the report.
Status: PLANNED. Today the failure is recorded in `run_meta.failures` (`discover.py:56-60`) but its controls become
ABSENT or NOT_APPLICABLE (`aspects.py:266, 286`).

#### Scenario: the stack detector crashes
- WHEN the stack detector raises on one repository
- THEN that application's dependency-based and need-based controls are NOT_ASSESSED, not ABSENT or N/A

### Requirement: Strength is stated on three axes
Every result SHALL state its level (declared, configured, enforced, verified) and its certainty (text, parsed,
semantic); every ISSUE SHALL state `confirmed`. "Enforced" SHALL require a cited CI file that runs the control;
"verified" SHALL require a tool result; `confirmed: true` SHALL mean the issue is stated by a cited line, or by a
reference-data lookup on a cited value, after the absence guard; `confirmed: false` SHALL be used only for heuristic
patterns and for defaults inferred from a setting not being found (design 6.2, with the table of current sources).
Status: BUILT for level (ACC-3; `tests/test_verify.py::test_enforced_without_a_ci_file_is_caught`); PLANNED for
certainty and confirmed.

#### Scenario: a committed secret
- WHEN the secrets detector cites a line holding a password literal
- THEN the result is ISSUE, `confirmed: true`, counted in issue counts and shown in red

#### Scenario: open session in view
- WHEN a Spring Boot service using JPA does not set `spring.jpa.open-in-view` in any file read
- THEN the result is ISSUE, `confirmed: false`, "Possible issue: open session in view is on by default unless set
  elsewhere", because the setting can come from the environment

### Requirement: A declared dependency alone is not in place
A dependency declared with no configuration or use found, and a fact known only as INFERRED, SHALL be PARTIAL at level
declared. A negative scan ("no literal secret found in N files") and a platform default stated by the framework version
(graceful shutdown on Spring Boot 3.4+) SHALL stay PRESENT (review 3 F3-1).
Status: PLANNED (phase 1, T-1.12). Today `aspects.py:261` and `:294` return PRESENT.

#### Scenario: no secret found
- WHEN the secrets scan finds no literal secret
- THEN "No secrets committed" stays PRESENT, naming the files scanned

#### Scenario: a tracing library with no configuration
- WHEN an OpenTelemetry dependency is declared and nothing configures or uses it
- THEN tracing is PARTIAL, "declared only"

### Requirement: Possible issues are kept apart
ISSUE with `confirmed: false` SHALL be shown as "Possible issue", counted separately, and SHALL NOT count in issue
counts, aspect status "High gaps" or the home sort order.
Status: PLANNED (decision D-1).

#### Scenario: a repository call inside a loop
- WHEN a `findById` call is found inside a loop over a collection
- THEN the finding reads "Possible N+1 query" with both lines, and the application's issue count does not change

### Requirement: Results are verdicts, never descriptions
A result's summary SHALL describe what was found for this application and SHALL NOT be the control's description or
fix text.
Status: BUILT (ACC-5).

#### Scenario: a replica check
- WHEN replicas are set for 2 of 3 workloads
- THEN the summary names the workloads, not the control's rationale

### Requirement: Every finding carries its rule and source version
Every finding SHALL carry its control id, the catalogue version, and the source revision (commit; "uncommitted
changes: N files" when the tree is dirty).
Status: PARTIAL (control id and catalogue version BUILT; source revision per finding PLANNED; dirty state is recorded
in `run.json`).

#### Scenario: a dirty working tree
- WHEN a repository has 12 uncommitted files
- THEN every finding for it says the source revision is the commit plus 12 uncommitted files

### Requirement: Export maps to the upstream contract, without overclaiming
An export SHALL map results to the upstream `assessment-finding` states as follows, and SHALL carry rule id, rule
version and source revision. Export SHALL be blocked until the upstream schema can carry `level`, because a declared or
configured PRESENT must never arrive as VERIFIED_CONTROL (review 2 N8).

| app-insight | upstream |
|---|---|
| PRESENT at level verified | VERIFIED_CONTROL |
| PRESENT at a lower level | INSUFFICIENT_EVIDENCE until the upstream schema has a mandatory `level`; then VERIFIED_CONTROL with `level` |
| PARTIAL, ABSENT | POTENTIAL_ISSUE with `gap_kind` partial or not_found (extension field) |
| ISSUE confirmed | VERIFIED_ISSUE |
| ISSUE not confirmed | POTENTIAL_ISSUE |
| UNKNOWN | INSUFFICIENT_EVIDENCE |
| NOT_APPLICABLE | NOT_APPLICABLE |
| NOT_ASSESSED | NOT_ASSESSED |

Status: PLANNED (decision D-1); blocked on an upstream schema change (`additionalProperties: false` today).

#### Scenario: export of a not-found control
- WHEN an ABSENT control is exported
- THEN it is POTENTIAL_ISSUE with gap_kind not_found and its search record as evidence

### Requirement: Secrets never appear in any output
Every file the run writes SHALL be redacted at the writer; verify SHALL fail a run in which any written file holds a
value redaction would mask (ACC-9) or a literal value a secret detector located in the run (accuracy-assurance spec).
Status: PARTIAL (redaction and ACC-9 BUILT, commits 73f83ba, 4f47cd7; the independent literal-value check PLANNED).

#### Scenario: a webhook URL in a group_vars file
- WHEN the secrets detector cites a line holding a Slack webhook
- THEN every output shows `[REDACTED]` in its place and both checks pass
