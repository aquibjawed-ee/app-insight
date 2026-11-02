# Tasks (revision 3)

Phase 1 started before sign-off by user decision (2026-11-02); phase 2 onwards starts after sign-off. If D-9 is
rejected, T-1.13 is reverted. Each task names its acceptance evidence. IDs are stable; review-1 finding ids
(F1-F22, J1-J4) are cited where a task answers one.

## Phase 0: sign-off

- [x] T-0.1 Red-team review round 1. Evidence: `reviews/red-team-1.md` (REJECT), `reviews/red-team-1-response.md`.
- [x] T-0.2 Red-team review round 2. Evidence: `reviews/red-team-2.md` (REJECT; phase 1 cleared), `reviews/red-team-2-response.md`.
- [x] T-0.3a User decisions 2026-11-02: D-4 consultant-confirmed first (statistical validation deferred); phase 1 starts now.
- [x] T-0.3 Red-team review round 3: APPROVE WITH CONDITIONS (`reviews/red-team-3.md`, `red-team-3-response.md`).
- [x] T-0.4 User approved D-0 to D-3, D-5 to D-11 on 2026-11-02; R-12 amended (D-9).
- [x] T-0.5 Sign-off recorded in `proposal.md`, except D-7.
- [x] T-0.6 Section 8 revised; round 4 APPROVE WITH CONDITIONS; conditions met on re-check; user approved D-7, D-7a,
      D-7b on 2026-11-02.

## Phase 1: client safety and correctness

- [ ] T-1.1 Run verify before writing the report and `latest`; no report-client file on failure; verify result and
      rules in `summarise()`, `summary --json` and the report header; `report` and `aspects` exit non-zero on failure.
      (F5)
- [ ] T-1.2 Coverage-matrix recount script. (F6)
- [ ] T-1.3 Every BUILT row in the matrix and specs names its test id; false ones downgraded. (F6, R-20)
- [ ] T-1.4 Detector failure: controls fed by a failed detector NOT_ASSESSED; shown in summary and report. (F6)
- [ ] T-1.5 Per-repository isolation of extraction, safety net and resilience; unique clone folders and application
      ids; duplicate names disambiguated. (F14)
- [ ] T-1.6 Refuse credentialed source URLs; never store them. (R-08)
- [ ] T-1.7 Independent leak check: literal values located by the secret detectors (memory only) and a second
      pattern set, compared with every written file. (F7)
- [ ] T-1.8 Absence guard for NOT_APPLICABLE by need, ISSUE by default and PARTIAL by missing part; search records
      for them; verify rules for framework envelope and N/A by need. (F3)
- [ ] T-1.9 `usually_outside` attribute and GitOps blind spots; controls listed in design 6.6. (F9)
- [ ] T-1.10 Owners search record names only CODEOWNERS (or extend the detector). (F6)
- [ ] T-1.11 README mention of a CI product no longer makes the pipeline external without a statement that this
      repository is built there. (F2)
- [ ] T-1.12 Declared-only dependency and INFERRED-only facts → PARTIAL at level declared; negative scans and
      framework-version defaults stay PRESENT, with regression tests for secrets_in_code, secrets_externalised and
      graceful_shutdown on Boot 3.4+. (F18, N15, F3-1)
- [ ] T-1.13 Remove the maturity percentage from the report; dimension headlines checked against controls by verify.
      (F10)
- [ ] T-1.14 Remedy vocabulary declared per key; test on every remedy `requires`; fix `gitlab` → `gitlab-ci`.
- [ ] T-1.15 `critical` in the severity order. (F21)
- [ ] T-1.16 File roles: IDE output folders (`bin/`) excluded; general classifier for test fixtures and examples.
      (F11)
- [ ] T-1.17 Hazelcast and other grids typed as caches. (F21)
- [ ] T-1.18 Criticality from the list file shown and filterable. (F6)
- [ ] T-1.19 Report header "Internal: not validated" until the client-use gate passes. (D-0)
- [ ] T-1.20 Audit-6 minor items (design section 15), each with a regression test.
- [ ] T-1.21 Rescan the six repositories on the fixed code; verify passes; every state change explained.
- [ ] T-1.22 ACC-2 extended to PARTIAL and ISSUE; `repo` search area records what it checked; need-based N/A
      converted for every need on `understands` controls. (review 2 N7)
- [ ] T-1.23 Independent leak check also on rebuilds and standalone verify (detectors re-run in memory). (N10)
- [ ] T-1.24 `check`-sourced controls after a detector crash: NOT_ASSESSED with the true reason. (N17)
- [ ] T-1.25 Reference data review status on every result that rests on it (Assessment results). (R-11)

Started 2026-11-02 by user decision; T-1.1 to T-1.20 and T-1.22 to T-1.24 in progress (T-1.2, T-1.3 are spec
bookkeeping: the recount was done by script with each revision; per-row test ids are still to do). Later phase-1 items not yet started: T-1.25, T-1.26, T-1.27.

- [ ] T-1.26 Verify reads evidence at the run's recorded commit, or refuses. (N11)
- [ ] T-1.27 Verify recomputes coverage and status with its own table-driven logic. (N21)
- [ ] T-1.28 Gate state in `summary --json` and "internal" in the report file name. (F3-21)
- [ ] T-1.29 Make `report` rebuild the HTML only, as AGENTS.md says, or correct AGENTS.md; a run with `review.json`
      is never rebuilt in place. (F3-9)

Exit: both suites pass (browser test run, not skipped); verify passes on the six repositories.

## Phase 2: consultant review, client file, internal measurement

D-7 (consultant review, design section 8): round 4 APPROVE WITH CONDITIONS; conditions written in and checked
(`reviews/red-team-4-conditions.md`); User approved D-7 on 2026-11-02; phase 2 starts after phase 1. `review` runs verify and the independent leak check after writing
the client file and deletes it on failure (F3-8).

- [ ] T-2.0 Count must-review items per application on the six repositories, by 8.2 item (including item 7, every
      UNKNOWN and "Not seen here"); set the per-application review budget.
      (F4-11; before T-2.1)
- [ ] T-2.1 `app-insight review` per design 8.1-8.5: scope and chooser; must-review items 1-6 one by one in
      deterministic order; bulk for PRESENT/N/A outside them; outcomes incl. corrected and cannot confirm; expiry and
      re-presentation; audit sample (seed, second person, revert on disagreement); stop-rule escalation; time per item;
      single-writer lock.
- [ ] T-2.2 Mark binding and carry-forward per design 8.7; reviewed runs immutable; commits pinned with local refs at
      scan time; verify via `git show` and temporary exports; hashes over redacted text.
- [ ] T-2.3 Client file per design 8.6 (whitelist, precedence, recomputed derived views, summary row), written under a
      temporary name and verified with the rule classification of 8.8.
- [ ] T-2.3a Reference data reviewed by a person before first client use. (design 8.9)
- [ ] T-2.3b Sanitising test for fixtures written from disputes. (design 8.4)
- [ ] T-2.4 Strata and `depends_on` for every control fixed before any corpus run.
- [ ] T-2.5 Select about 60 repositories, weighted to the dominant stack; record URL and commit; split by hash. Needs
      D-5 approval for cloning.
- [ ] T-2.6 Labels per design 7.3 (person reference; model labels only where agreement bound ≥90%; re-check of
      agreeing cases). (N3)
- [ ] T-2.7 Harness: false-pass, false-gap, wrong-kind, undecided, reason, level, evidence, remedy; exact bounds;
      honest wording; internal only. (N2, N16)
- [ ] T-2.8 Seeded fixtures for enterprise patterns; benchmark extended to control states.
- [ ] T-2.9 Regression gate per corpus version baseline. (N13)
- [ ] T-2.10 Fix false passes and false gaps found on tuning cases, each with a synthetic regression fixture.

Exit: review and client file working on the six repositories, with time per reviewed item and per bulk screen recorded
and the effort projected by item counts; measurement table v1 for the team; client-use gate
passable once D-6 is signed off.

## Phase 3: report

- [ ] T-3.1 Mock v3 on the latest verified run, in both colour schemes, including the client file view; review;
      decide D-11. (May run during phase 2.)
- [ ] T-3.2 Home, filters (incl. criticality), sortable columns, summary row, expandable rows; dashboard removed.
- [ ] T-3.3 Vocabulary and colours from one table; browser test for raw values. (F16)
- [ ] T-3.4 Findings in four places; breadcrumb keeps the application; commands as code. (F21)
- [ ] T-3.5 Remove Timeline, empty Change impact, duplicated tabs, rings, empty widgets.
- [ ] T-3.6 Scope page, including tool runs not done listed once. (F22)
- [ ] T-3.7 AS-IS view with a place for every coverage-matrix area. (F17)
- [ ] T-3.8 300-application measurement: scan time, memory, report size, render. (F14, open question 2)

## Phase 4: coverage from files and git

- [ ] T-4.1 Scheduled and batch jobs; web tier; application boundary signals.
- [ ] T-4.2 Authentication mechanism, unprotected endpoints, CORS/CSRF, management exposure.
- [ ] T-4.3 Open session in view (possible issue); eager fetching.
- [ ] T-4.4 SOAP/WSDL, gRPC, GraphQL; API versioning.
- [ ] T-4.5 Size; git history (last change, frequency, contributors, concentration).
- [ ] T-4.6 Modernisation target input; javax/jakarta; removed APIs; build tool vs JDK compatibility.
- [ ] T-4.7 SBOM, signing; container security posture; producer settings; internal shared libraries.
- [ ] T-4.8 Application server and Jakarta EE recognition; JDK vendor; database version and dialect.
- [ ] T-4.9 Each new control measured on the corpus before it is shown.

## Phase 5: semantic prototype (D-3)

- [ ] T-5.1 Prototype PMD `CloseResource` and a JavaParser analyser on at least 2 repositories, source only, no
      classpath; fingerprint unchanged; at least 30 candidates checked by a person; adopt a rule only if its precision's
      90% lower bound is at least 70%, per rule (at least 30 candidates per rule). (F15, N20)
- [ ] T-5.2 Decide adoption from the measurement; if adopted, N+1 candidates, pagination, unbounded pools,
      transactions, outbox, idempotency, optimistic locking, calls through wrappers, all as possible issues unless
      confirmed.
- [ ] T-5.3 Kotlin applications listed once as not covered by the tier.
