# Accuracy assurance

Decision D-4 (DECIDED 2026-11-02): results shown to a client are consultant-confirmed first; the corpus measures
accuracy internally; statistical validation that could be quoted to a client is deferred.

## ADDED Requirements

### Requirement: Verify runs before anything is published, and its result is visible
Every scan SHALL run the verify gate after `aspects.json` is built and before any report or the workspace `latest`
pointer is written. The result and the rules broken SHALL be in the run summary, `summary --json` and the report
header. `report` and `aspects` SHALL exit non-zero when verify fails. For the client file, a run-level failure SHALL
delete it and a per-application failure SHALL mark that application "Not available: verification failed" (design 8.8).
Status: PARTIAL. The gate is BUILT (commits 4f47cd7, 9479a59;
`tests/test_verify.py::VerifyTest.test_a_clean_run_passes`, `tests/test_verify.py::VerifyTest.test_a_cited_line_that_does_not_say_it_is_caught`); ordering, summary field, exit
codes and header are phase 1 (T-1.1; today `cli.py:145-152` writes the report and `latest` first).

#### Scenario: findings drift from the controls
- WHEN `aspects.json` lists a finding that is not a gap control
- THEN verify fails with CON-3, the summary says "verification: FAIL (CON-3)", and no client file is written

### Requirement: Verify does not rely on the code it checks
Verify SHALL check leaks with the literal secret values the secret detectors located (held in memory only, re-derived
by re-running the detectors on a rebuild or a standalone verify) and with a second pattern set not used for
redaction; and SHALL recompute coverage and aspect status with its own table-driven logic, not the writer's `rollup`.
Status: PLANNED (today ACC-9 uses the redaction function, `verify.py:161-172`; CON-1/2/4 call `A.rollup`,
`verify.py:135`).

#### Scenario: a token format redaction does not know
- WHEN a detector cites a line holding a token whose format the redaction patterns miss
- THEN the literal-value comparison finds it in the written file and the run fails, naming the file only

### Requirement: Verify reads evidence at the commit the run describes
Verify of a run SHALL re-read cited lines at the run's recorded commit for each repository, or refuse with the reason
when that commit is not available in the clone.
Status: PLANNED (today a rescan resets the shared clone, `sources.py:162-166`, so an older run is checked against newer
code).

#### Scenario: verifying last week's run
- WHEN the clone has moved to a newer commit
- THEN verify reads the files at the recorded commit, or says it cannot

### Requirement: A review covers a named set of applications, within a budget
`app-insight review <run>` SHALL take the applications in scope and who chose them, list every other analysed
application once as "Not in this review", record the time per individually reviewed item and per bulk screen, and
project the effort by item counts against a per-application budget set before T-2.1; a scope over budget SHALL be
reduced, never the must-review set.
Status: PLANNED (design 8.1).

#### Scenario: a scope over budget
- WHEN the projected effort for 40 named applications exceeds the budget
- THEN the review asks for a smaller scope; no must-review item is dropped

#### Scenario: a first meeting
- WHEN the client names 20 of 300 applications
- THEN the client file holds those 20, says "chosen by: client", and lists 280 once as not in this review

### Requirement: Must-review results are reviewed one by one
The results listed in design 8.2 (confirmed ISSUE; every ABSENT and PARTIAL; UNKNOWN, "Not seen here" and need-based
NOT_APPLICABLE on a high or critical control; high or critical PRESENT below enforced; every result with any outcome
other than Confirmed in an earlier review, shown with that outcome; every other UNKNOWN or "Not seen here"; and, after the stop rule fires, every
result of the implicated controls) SHALL be presented individually in the order severity, aspect, control, application
id, using the catalogue control severity (the evaluator's severity for a gap where it sets one), and SHALL NOT be confirmable in bulk. Possible issues SHALL NOT be in the client
file unless reviewed individually.
Status: PLANNED (design 8.2).

#### Scenario: a known false pass after expiry
- WHEN last month the consultant recorded "Gap stated by the consultant" on a medium "Timeouts set" result, and the new
  run shows it PRESENT again
- THEN it is presented individually with last month's outcome and note, and cannot be confirmed with its aspect

### Requirement: Bulk confirmation is limited, recorded and audited
Only PRESENT and NOT_APPLICABLE results outside the must-review set SHALL be confirmable by aspect, on a screen listing
each with its evidence; the mode SHALL be recorded and shown; an audit sample of 10% (at least 5) of bulk-confirmed and
carried-forward results SHALL be drawn from a recorded seed, extended only in that seeded order, and presented to a second person (required for a first
client meeting, otherwise recorded as absent); any outcome other than Confirmed in the sample SHALL count as a disagreement and SHALL revert every bulk confirmation of that aspect
and application to "Not reviewed" and double the sample.
Status: PLANNED (design 8.3).

#### Scenario: an audit-sample disagreement
- WHEN a bulk-confirmed "Health endpoint: in place" is disputed in the audit sample
- THEN every bulk confirmation of that application's Observability aspect reverts to "Not reviewed", and the sample doubles

#### Scenario: a small bulk population
- WHEN only 12 results were bulk-confirmed
- THEN the audit sample is 5

### Requirement: Every review situation has an outcome
The reviewer SHALL be able to record: confirmed; corrected by the consultant (one of the seven states plus a reason
category); gap stated by the consultant; disputed by the consultant (on a gap); cannot confirm; stated by the team (on
UNKNOWN or "Not seen here" only). Person outcomes SHALL carry strength "stated" and an optional evidence field. Every
outcome except confirmed SHALL expire at the next run or after 90 days and be re-presented. Reason categories SHALL be the
fixed list of design 8.4, each marked tool error or not.
Status: PLANNED (design 8.4).

#### Scenario: right state, wrong evidence
- WHEN the tool's "Integration tests: in place" cites a copied test file but real integration tests exist elsewhere
- THEN the consultant records "Corrected by the consultant: In place", reason "evidence is a test or a copy"

#### Scenario: truth unknown before the meeting
- WHEN the consultant cannot establish whether a high-severity "Retries in place" is true
- THEN "Cannot confirm" resolves the item, the client file shows "Not reviewed: could not be confirmed", and it counts as
  neither pass nor gap

#### Scenario: Dependabot at organisation level
- WHEN dependency updates is "Not seen here" and the team states it is enabled for the organisation
- THEN the client file shows "Stated by the team: enabled at organisation level" with who and when, and "In place (stated)"

### Requirement: The stop rule escalates instead of blocking
When more than 2 outcomes that count as a tool error (decided by the change, design 8.4: a tool pass or N/A changed to a
gap always counts; an undecided usually-outside result never counts) fall in any
30 consecutive individually reviewed results, every result of every control with a counted outcome in that window for every application in scope SHALL become must-review and the remaining audit sample
SHALL rise to 25%; the client file SHALL NOT be produced until that escalation is complete; the firing SHALL be listed in
the client file's review statement; a re-run SHALL NOT clear it.
Status: PLANNED (design 8.5).

#### Scenario: a systematic tool error
- WHEN three "tool missed it" corrections on the deploy control fall within 30 reviewed results
- THEN every deploy result in scope becomes must-review, and the client file is produced only after they are all resolved

#### Scenario: three false passes on one control
- WHEN the consultant records "Gap stated by the consultant" on three "Timeouts set" results within 30 reviewed results
- THEN the stop rule fires, every "Timeouts set" result in scope becomes must-review, and three backlog items are created

#### Scenario: a re-run does not clear the rule
- WHEN the run is scanned again before the escalation is complete
- THEN the firing, its must-review set and the 25% audit carry to the next review of the same scope

#### Scenario: branch protection the tool cannot see
- WHEN the consultant records "Gap stated by the consultant" on three "Not seen here" branch-protection results
- THEN the stop rule does not count them, because the tool could not see them by design

#### Scenario: a false pass recorded as a correction
- WHEN the consultant records "Corrected by the consultant: Not found" on a tool "In place", with reason "other"
- THEN it counts as a tool error, because a tool pass was changed to a gap

#### Scenario: a client fact repeated across applications
- WHEN ten deploy results are disputed with the reason "set outside the repository"
- THEN the stop rule does not fire, because that reason is not a tool error

### Requirement: A review mark is bound to what was reviewed
Each mark SHALL bind to the control's definition hash, the versions of the detectors feeding it, the state, the hash of
the redacted evidence text (for PRESENT, PARTIAL, ISSUE) or of the files in the control's search scope (for ABSENT,
UNKNOWN, NOT_APPLICABLE and the missing part of PARTIAL), and the remedies shown; and SHALL carry forward, shown as "carried forward from run <id>,
confirmed <date>", only when all are unchanged. A run with `review.json` SHALL be immutable and `review.json`
single-writer. Each run's commits SHALL be pinned with a local ref at scan time, and verify SHALL re-read evidence with
`git show` and re-run secret detectors over a temporary export, never by checking out the shared clone; for a local source
with uncommitted changes, verify of an older run SHALL refuse.
Status: PLANNED (design 8.7).

#### Scenario: a catalogue change to one control
- WHEN only the coverage-gate control's definition changes between runs
- THEN marks on every other control carry forward, and the coverage-gate results are presented again

#### Scenario: the searched files changed
- WHEN a confirmed "Not found" for owners is carried towards a new run and a CODEOWNERS file was added
- THEN the search-scope hash differs and the result is presented again

#### Scenario: a carried-forward mark
- WHEN a mark is carried forward to a new run
- THEN the result shows "carried forward from run <id>, confirmed <date>", not "checked individually"

#### Scenario: a second reviewer at the same time
- WHEN a second `review` starts on a run already under review
- THEN it is refused

### Requirement: The client file is verified after it is written
`app-insight review` SHALL write the client file under a temporary name and run verify on it, with the rules classified
as in design 8.8 (ACC-8, ACC-9, the leak check, CON-4, CON-6, the client-count rule and any unclassified rule are
run-level): a run-level failure SHALL delete the file; a per-application failure SHALL show that application as "Not
available: verification failed", and the file SHALL be regenerated without that application's content and verified
again.
Status: PLANNED (design 8.8).

#### Scenario: a note holding a token
- WHEN a consultant pastes a webhook URL into a dispute note
- THEN the note is redacted at write, and the leak check over `review.json` passes

#### Scenario: a leak in the client file
- WHEN the independent leak check finds a literal secret value in the temporary client file
- THEN the file is deleted and the review reports which file and rule failed, never the value

#### Scenario: one application's citation drifted
- WHEN ACC-1 fails for one application's cited line
- THEN that application shows "Not available: verification failed", and the others are published

### Requirement: Disputes become synthetic fixtures, never client code
A dispute or correction with a tool-error reason SHALL create a backlog item stored in the client workspace only; an
engineer SHALL write a synthetic fixture from a sanitised description, without model assistance on client-derived text,
and a test SHALL fail if the fixture contains any of the workspace's application names, package prefixes or hostnames
(R-08, R-09, R-18).
Status: PLANNED; practice BUILT (`engine/tests/test_accuracy.py`, one class per audit, commit 203d685; for example
`engine/tests/test_accuracy.py::SixthAuditTest.test_a_documented_manual_deploy_is_a_gap_not_unknown`); the sanitising test PLANNED.

#### Scenario: a fixture containing a client package name
- WHEN a fixture written from a dispute contains `com.acme.payments`, a package prefix of the client workspace
- THEN the sanitising test fails and the fixture cannot leave the workspace

### Requirement: Accuracy is measured internally, with honest statistics
A harness SHALL compute on the held-out half of an internal corpus (about 60 public repositories, weighted to the
dominant stack, split by a fixed hash of the URL before labelling), per control and stack value: false-pass rate,
false-gap rate, wrong-gap-kind rate, undecided rate where decidable, reason, level, evidence relevance and remedy fit;
each with its case count and exact one-sided upper bound; one case per (control, repository). Rates SHALL be worded as
what they bound ("on N held-out repositories using <value> whose truth was a gap, this check missed it in at most X% of them, 90%
one-sided") and SHALL
NOT be shown to clients while D-4's deferral stands.
Status: PLANNED (D-5).

#### Scenario: a hidden gap
- WHEN the label says ABSENT and the tool says UNKNOWN "pipeline is external" because the README mentions Jenkins
- THEN the case counts as a false pass for that control and CI-system value

### Requirement: A person's labels are the reference
A person SHALL label every case of high and critical controls and a stratified sample of the rest,
citing file and line without the tool's output. Model-drafted labels SHALL be used only for controls where the model
also labelled the person's cases and its agreement on the gap class has a 90% lower bound of at least 90%; a random
sample of cases where tool and label agree SHALL be re-checked by a person. No model SHALL review another model's
labels.
Status: PLANNED (D-5).

#### Scenario: model labels too weak for one control
- WHEN model agreement with the person on the gap class for the coverage gate has a lower bound of 82%
- THEN the coverage gate is labelled by a person

### Requirement: One regression gate, per corpus version
Each corpus version SHALL have a baseline table, and a change SHALL fail when any control's false-pass or false-gap
count on the held-out set rises above that baseline; held-out repositories inspected to make a fix SHALL move to
tuning.
Status: PLANNED.

#### Scenario: adding repositories
- WHEN new repositories are added to the held-out set
- THEN a new corpus version and baseline are created, and no change fails because of the addition

### Requirement: The seeded benchmark covers controls as well as facts
The existing benchmark (`engine/benchmark`) SHALL be extended to control states, including the enterprise patterns rare
in public code (company parent POM, Jenkins shared library, GitLab remote include, config server, GitOps).
Status: PARTIAL (facts BUILT, `engine/tests/test_benchmark.py::ShippedBenchmark.test_all_gates_pass`; 8 blind-spot fixture
tests, for example `engine/tests/test_accuracy.py::ScopeTest.test_an_organisation_parent_pom_outside_the_repository_is_a_blind_spot`;
control states PLANNED).

#### Scenario: a technology the corpus lacks
- WHEN no corpus repository uses IBM MQ
- THEN the benchmark still measures whether its consumers and error handling are detected

### Requirement: Every regression found becomes a test
Every error found by an audit, a review or a dispute SHALL get a regression test on a synthetic fixture that fails
before the fix and passes after it (R-18).
Status: BUILT as practice (`engine/tests/test_accuracy.py`, commits f4a7fd5, 203d685; for example
`engine/tests/test_accuracy.py::FourthAuditTest.test_timeouts_cover_only_the_clients_that_read_them`).

#### Scenario: an audit finds a wrong reason
- WHEN an audit finds "publishes only" where a consumer exists
- THEN a fixture with that shape is added before the fix
