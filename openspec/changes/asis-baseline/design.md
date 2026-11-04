# Design: app-insight AS-IS baseline (revision 3)

Status: PROPOSED. Revision 2 answered red-team review 1; revision 3 answers review 2 (`reviews/red-team-2.md`, verdict
REJECT, phase 1 cleared to proceed) and records two user decisions of 2026-11-02: **results shown to a client are
consultant-confirmed first; statistical validation comes later, for the dominant stack only**, and **phase 1 starts
now**. The answer to each finding is in `reviews/red-team-1-response.md` and `reviews/red-team-2-response.md`. Project rules are in `../../config.yaml` (R-01 ... R-20). "BUILT"
means implemented and tested at the cited commit and test; it never means "right often enough". Accuracy is measured
internally (section 7) and, for anything shown to a client, confirmed by the consultant (section 8).

## 1. What the product is for, and the cost of being wrong

A consultant runs app-insight over a client's application repositories and brings the result to a meeting. Both
sides look at the same picture: what each application is, how it is doing in every aspect that matters for running
it in production, what is wrong, and what can be done about it. The conversation that follows decides the work.

Being wrong costs trust in both directions:

| Error | Example | What it costs |
|---|---|---|
| False gap | "No automated deploy" when a Jenkins shared library deploys it | The client's engineers stop believing the rest of the page |
| False pass | "Timeouts set" when only one of three clients has them; or "not applicable: no HTTP client" when one is built in code | A real risk is signed off in front of the client |
| Hidden gap | "Pipeline is external" when the README shows a person deploying by hand | The gap disappears behind an unknown |
| Inconsistency | Coupling "0 unresolved" on one screen, "4 unresolved" on another | The report looks untrustworthy even where it is right |
| Leak | A webhook token shown in a report sent by email | A security incident caused by the assessment itself |
| Wrong application | Two repositories named `api` analysed under one name | Every claim on that row is about the wrong code |

So the design has one priority order: **say only what is proven, say where the proof is, and say plainly what was
not looked at**. Breadth comes second and grows only as fast as it can be proven.

## 2. Client-use gate (DECIDED 2026-11-02: consultant-confirmed first)

Until the gate is passed, the report is for internal preparation only: its header and file name say "internal", and
`summary --json` carries the gate state.

A run may be shown to a client only when all of these hold:

1. **The run passed verify**, and verify ran before any report was written (phase 1, T-1.1).
2. **A consultant reviewed it** (section 8): the client file shows verdicts only for applications whose must-review
   items are all resolved, was generated from that review and passed verify (phase 2, T-2.3).
3. **The severity table is signed off** (D-6), and the reference data (end-of-support dates, "unreviewed" today) has
   been reviewed by a person (8.9).

No result is shown to a client as "validated" until statistical validation exists for its stack (section 7.4, a
later decision). The client file therefore says, for each result, only what was found, the evidence, and that the
consultant confirmed it.

Before the gate exists, a consultant may show a client only results they have checked by hand.

## 3. Who uses it, and when

| Moment | Who | What they need |
|---|---|---|
| Preparation | Consultant | Run the scan; see what could not be decided; review the claims that will be shown; record corrections |
| The meeting | Consultant and client leads | One home screen across all applications; drill from an application to an aspect to a control to the evidence line; the remedies |
| Deep-dive | Client engineers | The trace for one application: every control, its evidence lines, where a "not found" looked |
| Planning | Both | Remedies ranked by how many gaps and applications they address, in dependency order |
| Re-assessment | Consultant | The same scan later, showing what changed (later change) |

## 4. Three perspectives, one trace (R-12; review F10, F17)

```
                       ┌── AS-IS inventory: what it is (facts with evidence; no verdicts)
repositories ─► engine ┼── Assessment: aspect ─► control ─► state + level + certainty + confirmed ─► evidence or search record
                       │                                         └─► gap ─► finding ─► remedy
                       └── Portfolio: relationships between applications, aggregates, change impact
```

- **AS-IS inventory** states facts and never a verdict. "Spring Boot 1.5.10" is a fact; "out of support" is a
  verdict and lives in the assessment. Every area of the coverage matrix has a home in the AS-IS view; an area with
  no facts yet shows "not read in this version", once.
- **Assessment** is the only assessment model (decision D-9). Code-level risk rules (N+1, leaks, outbox) are
  controls of the assessment with `confirmed: false` until proven; there is no separate risk-findings model.
- **Maturity score and dimensions are not separate models** (D-9). The engine's maturity criteria remain inputs to
  controls; the maturity score and band are removed from the report; each dimension shown is derived from aspect
  controls or AS-IS facts, and a verify rule checks every dimension headline against the controls it summarises.
- **Portfolio** aggregates across applications and holds the relationship graph.

Every report screen belongs to one perspective; a screen that needs another perspective links to it.

## 5. Architecture

```
inputs (paths, folders, URLs, .csv/.xlsx/.txt)
  └─ sources.py: resolve, clone with the user's git (no prompts), unique folder per source, reject URLs carrying credentials
       └─ per repository, read-only, each step isolated so one repository's failure does not stop the others:
            engine/discover.py     detectors → discovery.json (facts with evidence; scope: files read, blind spots, file roles)
            engine/relate.py       graph → relationships.json (portfolio graph)
            engine resilience      → resilience.json
            engine safetynet       → safetynet.json
            engine dimensions      → dimensions.json (derived views, D-9)
            [semantic tier]        → semantic.json (PLANNED, D-3)
            [tool runs]            → vulnerability scan, licence scan (opt-in; listed once in Scope when not run)
       └─ aspects.py: catalogue + facts → aspects.json (the trace)
       └─ verify.py: accuracy and consistency gate → verify.json; on failure stop here
       └─ report.py: report.html (internal) and, after review, report-client.html (section 2)
```

- **Facts and verdicts are separate layers.** Detectors produce facts; the catalogue turns facts into control
  states; the report never computes a verdict.
- **The catalogue is data**: each control names its source, when it applies, `search.in`, `search.for`,
  `search.blind_to`, `understands`, `usually_outside` (section 6.6), severity, fix, and the stack dimensions it
  depends on for validation (`depends_on`, section 7).
- **Application identity is unique**: host plus full path for remote sources; a duplicate name is disambiguated, not
  an abort (review F14).
- **Every finding carries** `rule` (control id), `rule_version` (catalogue version), `source_revision` (commit, and
  "dirty: N files" when the tree has uncommitted changes) (review F12).

## 6. Verdict model (R-02, R-03, R-04, R-13)

### 6.1 States

The seven states are BUILT (commit 4f47cd7; `tests/test_aspects.py`, `tests/test_verify.py`). Three meanings below
change, and are PLANNED (marked †).

| State | Meaning | Gap? |
|---|---|---|
| PRESENT | found, cited, and effective at the level stated | no |
| PARTIAL | found for part, or configured but not shown to run; † also: declared only (a dependency or inferred fact with nothing configuring it) | yes |
| ABSENT | searched and not found; the search record says where and what for. Shown as **"Not found"** | yes |
| ISSUE | a fact read shows a problem; † `confirmed` says whether it is a stated fact or a heuristic match | yes |
| UNKNOWN | cannot be decided from the files; the reason and the line that causes it are stated | no |
| NOT_APPLICABLE | does not apply, with the reason; † when the reason is that something was not found, it carries a search record | no |
| NOT_ASSESSED | applies, but the detector failed or its input was not produced | no |

Upstream DECIDED "assess effectiveness and CI enforcement, not dependency presence alone" is why declared-only becomes
PARTIAL (review 1 F18, review 2 N15).

### 6.2 Strength

- **Level** (BUILT, ACC-3): declared → configured → enforced (a cited CI file runs it) → verified (a tool result).
- **Certainty** (PLANNED): `text` (pattern over text) → `parsed` (syntax tree, types not fully resolved) →
  `semantic` (types resolved) → `runtime` (out of scope). The matrix uses the same words.
- **Confirmed** (PLANNED, ISSUE only; redefined after review 2 N4): `confirmed: true` when the issue is stated by a
  cited line or a reference-data lookup on a cited value, with the absence guard of 6.3 applied for anything outside
  the scan. `confirmed: false` ("Possible issue") only for **heuristic patterns** (a call inside a loop, a write next
  to a publish) and for **defaults inferred from a setting not being found** (no cited line states the value).

| ISSUE source today | Confirmed |
|---|---|
| Secret committed in code, build, CI or key files (`security.secrets_committed`) | yes |
| Secret literal in configuration (`security.secrets_in_config`) | yes |
| Timeout set to 0 or -1, or a resilience setting switched off (`runtime.*`) | yes |
| Tests or a scanner switched off in the build or pipeline | yes |
| Java or framework past end of support (reference data) | yes, labelled with the reference data's review status |
| Database shared with another analysed application | yes |
| OpenAPI generator present but disabled | yes |
| Vulnerability scan reports a concern (`security.exposure_known`) | yes, at the tool's certainty |
| Open session in view on because it is not set anywhere read (planned) | no: possible |
| N+1 candidate, missing outbox, unbounded pool (planned) | no: possible |

Possible issues are findings with a severity, shown as "Possible issue", counted separately, and not counted in issue
counts, "High gaps" or the home sort. Confirmed issues count everywhere.

### 6.3 Verdicts from not finding something (extended; review F3)

The guard applies to **every verdict derived from not finding something**, not only ABSENT. ABSENT, NOT_APPLICABLE by
need and ISSUE by default become UNKNOWN under the conditions below; PARTIAL by a missing part keeps its state (the
part found is a fact) and gets a note naming what outside the scan may complete it (review 2 N14).

| Derived from absence | Example |
|---|---|
| ABSENT | no coverage minimum found |
| NOT_APPLICABLE by need | "no outbound HTTP client found", "no database found" |
| ISSUE by default | open session in view not set, so on |
| PARTIAL by a missing part | coverage tool with no minimum |

Each carries a search record. The conditions:

1. the application's framework is outside the control's `understands` list, or it is a service with no recognised
   framework (BUILT for ABSENT on the 8 controls with `understands`, and for N/A by need only where the need is
   outbound HTTP or database, i.e. 2 of the 8, commit 4f47cd7; PLANNED for every need, T-1.8);
2. a blind spot exists in an area in the control's `search.blind_to` (BUILT for ABSENT, commit 9479a59; PARTIAL gets a
   note; PLANNED for N/A and ISSUE-by-default);
3. the pipeline is named as external, and no runbook shows a manual step (BUILT, commit 203d685);
4. the control is `usually_outside` the repository (6.6) and nothing was found (PLANNED).

Verify enforces 2 for ABSENT (CON-8) and the search record for ABSENT (ACC-10). PLANNED: rules for 1, for N/A by
need, and for ISSUE by default.

### 6.4 Detector failure (review F6)

A detector that raises leaves its section empty and names itself in `run_meta.failures` (BUILT). PLANNED: every
control fed by a failed detector is NOT_ASSESSED, "the <name> detector failed on this repository", never ABSENT or
N/A; the run summary, `summary --json` and the report show the failure; the application shows "Not available: analysis
incomplete (<detector> failed)" in the client file.

### 6.5 Applicability

A control applies by application kind and by need. PLANNED: application kinds beyond service and library
(monitoring stack, infrastructure, test harness) so such repositories are not assessed as services.

### 6.6 Controls that usually live outside the repository (review 1 F9; review 2 N6)

Some controls are usually set in the hosting platform or the organisation's settings: secret scanning and push
protection, Dependabot or Renovate at organisation level, branch protection, backups, alerting and SLOs. These carry
`usually_outside`: when nothing is found in the repository they are UNKNOWN, "Not seen in the repository; confirm with
the team", never ABSENT; when something is found they are decided normally.

**Deployment is different**, because a missing deploy automation is the gap clients most often have. The deploy and
rollback controls become UNKNOWN only when a positive marker shows deployment happens elsewhere: Argo CD or Flux
manifests, image-updater settings, or a CI step that pushes to a manifest repository (recorded as blind spots). An
image published with no deploy step is not a marker: it is also the shape of a manual deploy (review 3 F3-11). With no marker they stay ABSENT with their search record.

For labelling, "not decidable from the repository" is a label value. Usually-outside controls are measured on whether
they are found when present; their "not seen here" results are confirmed by the consultant, and the Scope page lists
them as consultant-confirmed controls.

### 6.7 File roles (review F11)

Every file read has a role: application, build, CI, deployment, configuration, test, test fixture or mock, example or
documentation, generated, build output. Evidence for a control is accepted only from roles that control allows.
Today roles exist for deployment files and build output folders `target`, `build`, `out` (BUILT); PLANNED: a general
classifier, including IDE output folders such as `bin/` (office reads a stale `bin/main/logback-spring.xml` today).

## 7. Accuracy assurance (rewritten for revision 3; review 2 N1, N2, N3, N13, N16)

### 7.1 Layers

| Layer | Catches | Cannot catch | Status |
|---|---|---|---|
| Unit and regression tests (engine 312, product 51 at 9479a59) | a known case breaking again | a case nobody wrote down | BUILT |
| Seeded benchmark (`engine/benchmark`) | detection patterns per technology, recall of facts | real-world variety | BUILT for facts; PLANNED for control states |
| Verify gate after every run (18 rules today) | wrong citation, inconsistent numbers, a writer that skipped redaction, "not found" with no search record or inside a blind spot | a false "not found" where the pattern was not recognised; a wrong pass with a real but irrelevant citation | BUILT |
| Independent checks in verify (PLANNED) | a leak redaction does not know (literal values); a roll-up logic error (independent table-driven recomputation, not the writer's own `rollup`, review 2 N21) | | PLANNED |
| Blind-spot and file-role detection | settings that may live in a named place; evidence from the wrong kind of file | places the repository does not name | PARTIAL |
| Internal measurement corpus | error rates per control, regressions | stacks absent from the corpus | PLANNED |
| **Consultant review** | errors on this client's code before they reach the client | errors in results the consultant confirms wrongly | PLANNED; **the client-facing safeguard** (DECIDED) |

### 7.2 Internal measurement (what the corpus is for now)

A corpus of about 60 public repositories, stratified with most repositories on the stack dominant in the first
client estates, measures accuracy **for the team, not for the client**:

- Per control and stack value: false-pass rate (truth a gap; tool PRESENT, UNKNOWN or N/A), false-gap rate (truth
  PRESENT or N/A; tool ABSENT, PARTIAL or ISSUE), wrong-gap-kind rate (truth PARTIAL, tool ABSENT, or the reverse),
  undecided rate where decidable; reason, level, evidence relevance and remedy fit.
- Each rate is reported with its case count and its exact one-sided upper bound, worded as what it is: "on N held-out
  repositories using Maven, this check missed a real gap in at most X% of cases (90% one-sided)". Never "fewer than 1
  in 10 wrong", which would need predictive values and joint confidence (review 2 N2).
- A unit of measurement is one (control, repository); controls evaluated per workload are aggregated to the
  repository's result before comparison.
- Held-out split by a fixed hash of the URL, before labelling; fixes made against tuning cases only.
- Used for: finding and fixing errors before clients see them, and the regression gate. The consultant's must-review
  list is set by state and severity (8.2), not by measured error rates, so it does not depend on measurements that do
  not exist yet (review 3 F3-7).

### 7.3 Labels

- A person labels the reference: every case of the high and critical controls, and a stratified sample of the rest, citing file and line, without the tool's output.
- Model-drafted labels are allowed for the rest only where a model also labelled the person's cases (the overlap is
  defined) and its agreement on the gap class, per control, has a 90% lower confidence bound of at least 90%;
  otherwise a person labels that control.
- A random sample of cases where tool and label agree is re-checked by a person too, so labels that share the tool's
  mistake are found (review 2 N3). No second model reviews a model's labels.

### 7.4 Statistical validation (DEFERRED by the user, 2026-11-02)

Validation that could be quoted to a client is deferred until a larger labelled set exists for the dominant stack. The
sizing is recorded so the later decision starts from the right numbers (review 2 N1): it needs, per control and stack
value, at least 22 error-free held-out cases **in each** truth class at 10% / 90% (38 with one error, 52 with two),
more at low gap prevalence, and a statement in terms of predictive values with a stated multiplicity policy. For one
stack this is in the order of 100-200 repositories with person labels on every deciding case. High-severity controls
would target 5% (45 error-free cases per class).

### 7.5 Regression gate (review 2 N13)

Each corpus version has a baseline table. A change fails when any control's false-pass or false-gap count on the
held-out set rises above that version's baseline. Adding repositories creates a new corpus version and a new baseline.
Held-out repositories that were inspected to make a fix move to tuning.

### 7.6 Accuracy figures

Every figure names the measure, the corpus, the run, the code version and the date (R-18), and is used inside the team
only until section 7.4 is decided. The audit-6 figure is restated as: "PRESENT precision 47 of 48, audit 6, run
20261102-061233, code before 203d685, six Gradle repositories, model-audited".

## 8. Consultant review (the client-facing safeguard; revised for round 4 conditions C1-C5 and F4-6 to F4-17)

Under D-4 the consultant's review is the only thing between the tool's output and the client. This section is
written so that a client file never says more than was checked, says how each result was checked, and never pushes the
reviewer towards confirming.

### 8.1 Review scope

A review covers a **named set of applications**. The client file records who chose it ("chosen by: consultant" or
"chosen by: client") and lists every other analysed application once as "Not in this review". The first meeting is
expected to cover tens of applications, not 300.

**Workload** (F4-11): the review records the time spent per individually reviewed item and per bulk screen, and
projects the effort by item counts. When a planned scope exceeds the budget, the scope is reduced. Must-review is never
capped.

**Budget (T-2.0, 2026-11-03)**: on the six repositories (run 20261102-195900) the must-review set is 26-32 items per
application (mean 29.3; mostly gaps, 15-23 each) and 5-20 bulk-confirmable results. At about one minute per item, the
budget is **40 minutes per application**; a first meeting of 15 applications is about 10 hours of review. Phase 2
replaces the one-minute assumption with the measured time per item.

**Interface (DECIDED 2026-11-03)**: `app-insight review <run>` serves a local review page (Python standard library,
bound to 127.0.0.1, a random port and a per-session token required on every request, nothing leaves the machine), one
item at a time with its evidence and the outcomes of 8.4, keyboard-driven, saving to `review.json` as it goes.

### 8.2 What is reviewed one by one (must-review)

For every application in scope, these results are presented individually and cannot be confirmed in bulk:

1. Every confirmed ISSUE ("Problem found"), including end of support.
2. Every ABSENT ("Not found") and PARTIAL ("Partly in place") of any severity: each is a claim about the client team's
   work. Possible issues (ISSUE not confirmed) are not must-review and are never in the client file unless reviewed
   individually.
3. Every UNKNOWN, "Not seen here" and need-based NOT_APPLICABLE on a high or critical control.
4. Every high or critical PRESENT below level enforced.
5. Every result that carried any outcome other than Confirmed in an earlier review of the same application and
   control, presented with the prior outcome, note, reviewer and date (C1, F4-1).
6. After the stop rule fires (8.5), every result of the implicated controls in scope.
7. Every other UNKNOWN or "Not seen here" result, so no undecided result is left without a review path (D9).

"High or critical" means the control's severity in the catalogue (the result's own severity only where the evaluator
sets one for a gap) (F4-12). Order: severity, aspect order, control order, application id.

### 8.3 What may be confirmed in bulk

Only PRESENT and NOT_APPLICABLE results outside 8.2, by aspect, on a screen that lists each result with its evidence or search record.
The mode is recorded and shown: "checked individually", "confirmed with its aspect", or "carried forward from run
<id>, confirmed <date>" (8.7).

**Audit sample** (F4-7): drawn from a recorded seed and only ever extended from that seed (doubling or raising to 25%
takes the next results in the same seeded order), never redrawn; a disagreement is any outcome other than Confirmed; 10% (at least 5) of bulk-confirmed
results including carried-forward ones; presented individually to a second person. For a first client meeting a
second person is required; otherwise the client file's review statement says "audited by a second person: no". Any
audit disagreement reverts every bulk confirmation of that aspect and application to "Not reviewed" and doubles the
sample.

### 8.4 Outcomes the reviewer can record

| Outcome | Allowed on | Shown in the client file as | Counts as |
|---|---|---|---|
| Confirmed | any result; for a gap, the reviewer also marks whether the remedy was confirmed | the tool's result and how it was confirmed | the tool's state |
| Corrected by the consultant | any result; a state from the seven and a reason category are required (C3) | "Corrected by the consultant: <state>" with the reason and note | the corrected state, strength "stated" |
| Gap stated by the consultant | a result the tool shows in place or undecided | "Gap stated by the consultant" with the note | a gap, at the control's severity, strength "stated" |
| Disputed by the consultant | a gap the consultant believes is not a gap | "Disputed by the consultant" with the reason category | resolved, neither pass nor gap |
| Cannot confirm | any result whose truth the reviewer cannot establish (C3) | "Not reviewed: could not be confirmed" (the tool's verdict is not shown) | resolved, neither pass nor gap |
| Stated by the team | undecided results only (UNKNOWN, "Not seen here") | "Stated by the team: <answer>", who and when | the stated state, strength "stated"; a stated pass shows "In place (stated)" |

Person outcomes have strength "stated" and an optional evidence field (a path and line, or "outside the repository").
None is a tool verdict; a person decides (R-01).

**Reason categories**, fixed:

| Tool error | Not a tool error |
|---|---|
| tool missed it; tool reported it in place wrongly; evidence is a test or a copy; wrong application; wrong kind or severity | set outside the repository; client fact; other, with a note |

**What counts as a tool error is decided by the change, not by the outcome or reason picked** (N1):

- a tool PRESENT or NOT_APPLICABLE that a person changes to a gap state (by "Gap stated by the consultant" or
  "Corrected by the consultant") always counts;
- a tool gap that a person changes to a pass, or disputes, counts when its reason is in the tool-error column;
- a tool UNKNOWN or "Not seen here" on a `usually_outside` control that a person changes to anything never counts: the
  tool could not see it by design;
- any other change counts when its reason is in the tool-error column.

Disputes, corrections, "Cannot confirm" and team statements expire at the next run or after 90 days, whichever is
first, and are re-presented under 8.2 item 5. Confirmations do not expire but are carried forward only under 8.7.

Every outcome that counts as a tool error creates a backlog item stored in the client workspace only. An engineer
writes a synthetic fixture from a sanitised description, without model assistance on the client-derived text; before
the fixture leaves the workspace, a test fails if it contains any of the workspace's application names, package
prefixes or hostnames (R-08, R-09; F4-16, open question 5).

### 8.5 Stop rule (C4)

The rule counts only outcomes that count as a tool error (8.4). When more than 2 such outcomes fall in any 30 consecutive
individually reviewed results (audit sample included), the rule fires and escalates deterministically:

1. every result of the implicated controls (every control with at least one counted outcome in the window), for every
   application in scope, becomes must-review (8.2 item 6),
   including any that were bulk-confirmed or carried forward;
2. the audit sample for the rest of the review rises to 25%.

The client file cannot be produced while that escalation is incomplete; once it is complete, the rule is cleared and
the firing, the controls and the outcomes are listed in the client file's review statement. A re-run does not clear
it: the firing, its item-6 must-review set and the 25% audit carry to the next review of the same scope (N3).

### 8.6 What the client file contains (C2, C5)

The client file contains exactly the following; anything else from the internal report is not in it.

- **Review statement**: scope and who chose it, reviewers, whether a second person audited, the stop rule's firings,
  date, and the marker that the file differs from the internal report only as this section defines.
- **Per application in scope**:
  - Verdicts only when every must-review item is resolved (any outcome in 8.4 resolves it); otherwise "Not yet
    reviewed".
  - "Not available: verification failed" when a per-application verify rule failed; "Not available: analysis
    incomplete (<detector> failed)" when a detector failed.
  - Each result: the outcome as in 8.4. A result with no outcome shows "Not reviewed"; the tool's unreviewed verdict is
    never shown.
  - **Remedies** are shown only on gaps whose outcome was confirmed, corrected or stated, labelled "suggested, not
    reviewed" unless the reviewer confirmed the remedy with the result.
  - **AS-IS facts** are shown labelled "read by the tool, not reviewed" (decision needed: D-7a).
- **Aspect cell** (C5, F4-5, D2), first rule that applies: "Not checked" when y = 0; High gaps; Gaps; "Reviewed x of
  y" when x < y; "Not applicable" when every result is NOT_APPLICABLE; "Reviewed, nothing confirmed" when no result has
  a confirmed, corrected or stated pass (all "Cannot confirm", disputed, or corrected to UNKNOWN or NOT_ASSESSED);
  "Partly confirmed" when any result is disputed, "Cannot confirm", or corrected to UNKNOWN or NOT_ASSESSED; "In place
  (stated)" when any pass is stated; otherwise "In place". Confirmed NOT_APPLICABLE results are neutral in these tests. A
  known gap is never hidden, and nothing makes a cell positive without a confirmed pass. "In place where checked" keeps
  its internal-report meaning only (N2). y is the aspect's results excluding controls with no detector and NOT_ASSESSED results; x counts every
  result with an outcome.
- **Derived views** (dimensions, summary row, counts, global findings, the remedy roadmap) are recomputed from review
  outcomes only: a result without an outcome contributes nothing. A view that cannot be recomputed that way is omitted.
- **Summary row** always reads "n of m applications in scope shown; k not yet reviewed; j not available".
- **Ranking** uses only applications whose must-review items are all resolved; within them, applications whose
  gaps are all disputed or not confirmable sort after those with confirmed results, and the sort columns show
  "disputes: n" (F4-8).
- **Out-of-scope applications** listed once.
- **What was not looked at** (D4): a scope summary (controls with no detector, tool runs not done, controls that are
  usually outside the repository) and, on every result resting on reference data, that data's review status.
- **Possible issues** appear only when reviewed individually; otherwise they are absent and not counted, and the scope
  summary states how many there were (D9).

A verify rule checks every count and derived number in the client file against a recomputation from the internal
results with the outcomes applied.

### 8.7 Binding and carrying forward (C5, F4-6, F4-9, F4-14)

- A mark binds to: the control's definition hash (severity, search declaration, remedy keys); the version of the
  detectors that feed the control; the state; for PRESENT, PARTIAL and ISSUE the hash of the redacted evidence text; for
  ABSENT, UNKNOWN and NOT_APPLICABLE, and also for PARTIAL (its missing part), a content hash of the files in the
  control's search scope; and the remedies shown.
  It does not bind to the global catalogue version, tool version or repository commit, so unrelated changes do not
  invalidate it.
- On a later run a mark is carried forward when every bound term is unchanged, and is shown as "carried forward from
  run <id>, confirmed <date>"; otherwise the result is presented again.
- Hashes are computed over redacted text only.
- A run with `review.json` is immutable; a rebuild writes a new run. `review.json` has a single-writer lock: a second
  `review` on the same run is refused.
- **Commit pinning**: at scan time each repository's commit is pinned in the clone with a local ref
  (`refs/app-insight/runs/<run>`), so its objects stay available offline. Verify re-reads evidence with `git show
  <sha>:<path>` and re-runs the secret detectors over a temporary export of the search-scope files, never by checking
  out the shared clone. For a local source with uncommitted changes, verify of an older run refuses, and such a run
  cannot yield a client file once its tree has changed.

### 8.8 Verification of the client file (F4-10)

`app-insight review` writes the client file under a temporary name and runs verify on it. Rules are classified:

| Run-level (any failure: the file is deleted) | Per application (that application shows "Not available: verification failed") |
|---|---|
| ACC-8, ACC-9 and the independent leak check (client file, `review.json`), CON-4, CON-6, the client-count rule, and any new rule unless classified otherwise | ACC-1 to ACC-7, ACC-10, CON-1 to CON-3, CON-5, CON-7, CON-8 |

After a per-application failure the file is regenerated without that application's content and verified again. Notes
in `review.json` are redacted at write.

### 8.9 Reference data before client use

Results resting on reference data are must-review (8.2 item 1). Before the first client use the reference data table is
reviewed by a person; gate item 3 (section 2) includes this (D-7 approved).

### 8.10 Decisions inside D-7

- **D-7a** (DECIDED 2026-11-02): AS-IS facts in the client file are shown labelled "read by the tool, not reviewed".
- **D-7b** (DECIDED 2026-11-02): a second person is required for the audit sample before a first client meeting;
  afterwards it is optional and the review statement records whether it happened.

## 9. Assessment catalogue: 17 aspects (decision D-2; review J1, J3)

Today: 13 aspects, 58 controls, 9 with no detector. Proposed: 17 aspects. New controls are in
`specs/assessment-catalogue/spec.md`. Every new control is shown to a client only once confirmed by the consultant (section
8), and only after its internal measurement (section 7.2) exists; breadth does not bypass proof.

| # | Aspect | Change | Question |
|---|---|---|---|
| 1 | Build & delivery | keep | Can a change reach production automatically and be undone? |
| 2 | Testing & safety net | keep | Would a regression be caught before it ships? |
| 3 | Security & supply chain | adds SBOM, signing, licences, branch protection (usually outside) | Are code, dependencies and secrets scanned, and is exposure known? |
| 4 | **Application security** | NEW | Is the application itself protected: who can call it, and is input and data handled safely? |
| 5 | Platform & dependencies | adds build-tool and JDK compatibility | Is the runtime, framework and build tool supported, and are libraries current? |
| 6 | Runtime resilience | adds bulkheads, deadlines, bounded pools | Does it survive slow or failing dependencies and restarts? |
| 7 | **Performance & data access** | NEW | Will it stay fast as data and load grow? |
| 8 | **Data correctness & messaging** | NEW | Can data be lost, duplicated or left inconsistent when something fails? |
| 9 | Deployment & availability | adds container security posture | Does it keep serving through rollouts, node loss and load? |
| 10 | Observability & operations | adds correlation IDs, alerts, runbooks | Would the team know it is failing, why, and what to do? |
| 11 | API & contracts | adds versioning | Can consumers rely on a published, checked contract? |
| 12 | Data management | keep | Are schema changes controlled and data recoverable? |
| 13 | Architecture & coupling | adds shared internal libraries | What does it depend on, and what depends on it? |
| 14 | Code health | detectors via semantic tier and git | Is the code easy and safe to change? |
| 15 | Knowledge & ownership | git history; doc drift | Who owns it, and could someone new work on it? |
| 16 | Configuration hygiene | keep | Is configuration externalised, consistent and free of secrets? |
| 17 | **Modernisation readiness** | NEW, target-relative | What stands between this application and a declared target platform? |

Modernisation readiness is relative to a target the consultant declares for the run (`--target`, for example
"Spring Boot 3, Java 21, Kubernetes"). With no target it shows AS-IS facts only (javax in use, local file writes) and
raises no gaps (review J1).

Severity is per control and lives in the catalogue, signed off by a person (D-6). After D-10, business criticality
may change which controls are expected; it never changes a control's state.

## 10. Remedies (R-10)

- A control maps to remedy keys per pack; a remedy may require stack values; the first pack with a fitting remedy
  wins (BUILT, commit 4f47cd7; `tests/test_verify.py::test_graceful_shutdown_on_an_old_spring_boot_is_an_upgrade`).
- **Defect**: the pipeline remedy requires `gitlab`; the engine produces `gitlab-ci`. PLANNED: the engine declares
  its vocabulary per key, and a test fails on any remedy value outside it.
- A remedy "addresses" gaps, never "closes" them; the roadmap orders two remedies only when one is a precondition of
  the other; commands are shown as code, manual steps as text (review-01 #18).

## 11. Report information architecture (R-06, R-15, R-16, R-17)

None of the items below is built unless marked.

- **Home is the Applications table**: summary row that follows the filters; stack-neutral filters (language,
  framework, build, CI, platform, support status, team, criticality); one row per application; one cell per aspect;
  sortable by any aspect column (review-03); expandable rows with the top 3 gaps.
- **No score anywhere**: the home "Overall %" and the per-application "Maturity N%" tile (`ui/core.js:64`) both go
  (review F10). Default sort: confirmed ISSUE count, then high gaps, then aspects with high gaps; a grey "checked x
  of y" column.
- **Vocabulary** (one table, review 1 F16, review 2 N18): In place, Partly in place, Not found, Not seen here
  (usually outside), Problem found, Possible issue, Undecided, Not applicable, Not checked. Client file only (one
  table, exact strings): Not reviewed; Not reviewed: could not be confirmed; Corrected by the consultant: <state>; Gap
  stated by the consultant; Disputed by the consultant; Stated by the team: <answer>; In place (stated); Not yet
  reviewed; Not available: verification failed; Not available: analysis incomplete (<detector> failed); Not in this
  review; aspect statuses "Reviewed x of y", "Reviewed, nothing confirmed", "Partly confirmed"; modes "checked individually", "confirmed with its aspect", "carried forward
  from run <id>, confirmed <date>"; facts "read by the tool, not reviewed". Client-stated facts in the AS-IS view use
  "stated by the client"; review outcomes from the client team use "Stated by the team" (F4-13). Aspect statuses: High gaps, Gaps, In place,
  In place where checked, Not checked, Not applicable.
- **Colour** (decision D-11, review J2): recommendation is colour by state with severity as weight (red only for a
  confirmed ISSUE ("Problem found"); amber for gaps, solid for high severity and hollow for others; grey hatched for undecided);
  review-03 preferred colour by severity. Mocked both ways in mock v3 and decided on the mock.
- **Findings in four places only**: Assessment, the application's Findings tab, global Findings, finding detail
  (breadcrumb keeps the application).
- **Removed**: Timeline, Change impact without a run, duplicated Configuration and Components tabs, repeated rings,
  empty widgets, the sidebar promotion.
- **Scale to 300**: counts and filtered links instead of name lists; portfolio architecture as a filterable table
  with a diagram for one application and its neighbours; paginated rows; searchable switcher; report size measured
  (6 applications give 962 KB today, so about 48 MB at 300, which needs testing: open question).
- **Scope page**: files read per area, blind spots, file roles excluded, controls with no detector, tool runs not
  done (semantic tier, vulnerability scan: listed once, not per application, review F22), controls that are
  always consultant-confirmed (usually outside the repository), reference data and its review status.
- **Built since the reviews** (commits c19fc9a, 203d685, 9479a59): portfolio-only sidebar with per-application tabs,
  "in place where checked", the "Outside this scan" panel and search records on the Assessment tab.

The design is mocked with real data from a verified run and agreed before the product changes (R-15).

## 12. Decisions

All decisions were approved by the user on 2026-11-02: D-0 to D-6 and D-8 to D-11 after round 3, D-7 after round 4 and its condition checks.

| ID | Decision | Status / recommendation |
|---|---|---|
| D-0 | Client-use gate | **DECIDED 2026-11-02 (user: "approve all")**. Section 2 |
| D-1 | Verdict vocabulary | **DECIDED 2026-11-02 (user: "approve all")**. Keep the 7 states; add `certainty` and `confirmed` as defined in 6.2; export blocked until the upstream schema can carry `level` (below-verified PRESENT must not export as VERIFIED_CONTROL, review 2 N8) |
| D-2 | Aspect set | **DECIDED 2026-11-02 (user: "approve all")**. 17 aspects, section 9; new controls shown only when consultant-confirmed |
| D-3 | Semantic tier | **DECIDED 2026-11-02 (user: "approve all")**. Prototype only. Adoption criterion fixed before it runs (review 2 N20): at least 30 candidate findings across at least 2 repositories, each checked by a person; adopt a rule only if its precision's 90% lower bound is at least 70% (it is shown as "Possible issue", never confirmed); Kotlin listed once as not covered |
| D-4 | How accuracy is proven to a client | **DECIDED 2026-11-02: consultant-confirmed first.** Statistical validation deferred (7.4) |
| D-5 | Corpus and labels | **DECIDED 2026-11-02 (user: "approve all")**. About 60 public repositories for internal measurement, weighted to the dominant stack; cloning them (an outside download) is approved; labels per 7.3 |
| D-6 | Severity ownership | **DECIDED 2026-11-02 (user: "approve all")**. A person signs off the severity table before client use (gate item 3); `critical` added; end-of-support frameworks reviewed |
| D-7 | Consultant review | **DECIDED 2026-11-02 (user)**. Section 8 as revised through round 4 and the condition checks; D-7a: AS-IS facts shown labelled "read by the tool, not reviewed"; D-7b: a second person is required for the audit sample before a first client meeting, optional and recorded afterwards |
| D-8 | Non-JVM languages | **DECIDED 2026-11-02 (user: "approve all")**. Out of this baseline |
| D-9 | One assessment model | **DECIDED 2026-11-02 (user: "approve all")**. Aspects only; maturity score removed; dimensions derived and checked. This amends rule R-12 and departs from upstream G ("separate quality/risk findings, maturity, production readiness and continuous assurance perspectives"): risk findings are kept as assessment controls with `confirmed`, maturity is removed because it disagreed with aspects four times in audit 6, and continuous assurance (re-assessment and drift) is a later change under the portfolio view. R-12 amended in `config.yaml` |
| D-10 | Criticality profiles | **DECIDED 2026-11-02 (user: "approve all")**. Defer: criticality is stated context and a filter |
| D-11 | Colour scheme | **DECIDED 2026-11-02 (user: "approve all")**. Decide on mock v3, both options mocked |
| — | Phase 1 now | **DECIDED 2026-11-02: start phase 1 in parallel with the spec revision** |

## 13. Failure paths

| Situation | Behaviour | Status |
|---|---|---|
| A detector raises | Controls it feeds NOT_ASSESSED with the reason; shown in summary and report; in the client file the application shows "Not available: analysis incomplete (<detector> failed)" | PARTIAL: failure recorded in `run_meta.failures`; controls become ABSENT or N/A today (review F6) |
| A repository cannot be cloned or read | Listed in `run.json` with the reason; no row invented | BUILT (`cli.py:88`) |
| One repository breaks extraction, safety net or resilience | That application NOT_ASSESSED; the others continue | PLANNED (no per-repo isolation in `relate.py:88-99`) |
| Two repositories with the same name | Disambiguated id; both analysed | PLANNED (aborts today, `relate.py:80-84`) |
| Two remote sources with the same last two path segments | Unique folders | PLANNED (shared slug, `sources.py:32-37`) |
| A URL carrying credentials | Refused before cloning; never stored | PLANNED (accepted today) |
| Verify fails | Summary, JSON and report header say failed; `report` and `aspects` exit non-zero; for the client file, run-level rules delete it and per-application rules mark that application "Not available" (8.8) | PLANNED, phase 1 (report written before verify, `cli.py:145-152`) |
| A rebuild or standalone verify of a run | The independent leak check re-runs the secret detectors to repopulate the literal values in memory; verify re-reads evidence at the run's recorded commit or refuses | PLANNED (review 2 N10, N11) |
| The semantic tier or a scan is not run | Listed once on the Scope page; its controls out of every count | PLANNED |
| A hostile repository (huge files, pathological XML, symlinks) | Bounded reads; linear-time XML handling; symlinks never followed, paths outside refused | BUILT (`evidence.py:116-127`, `detectors/integrations.py:393-410`) |
| A secret pattern redaction does not know | An independent check compares every written file with the literal values the secret detectors located in this run (held in memory only) and a second, broader pattern set not used for redaction | PLANNED. ACC-9 today only catches a writer that skipped redaction (review F7) |
| A blind-spot pattern fires wrongly | The control becomes UNKNOWN citing the line; measured in the seeded benchmark | BUILT for the conversion; PLANNED for measurement |
| Reference data is stale | Source and review status shown on every result that rests on it | PARTIAL: shown on About, Impact and a dashboard tooltip; not on Assessment results (`aspects.py:227, 238, 246`; review 2 R-11) |

## 14. Phasing

| Phase | Content | Exit criterion |
|---|---|---|
| 0 | Red-team round 3; decisions D-0 to D-11 | User sign-off |
| 1 (started 2026-11-02) | Client-safety and correctness: verify before report and in summary; detector failure → NOT_ASSESSED; per-repo isolation and unique ids; credential URLs refused; independent leak check; owners search text; remedy vocabulary test; absence guard for N/A and ISSUE-by-default; `usually_outside`; declared-only → PARTIAL; maturity % removed; audit-6 minor items; header "Internal: not validated" | Tests pass; verify passes on six repositories; every fix has a regression test |
| 2 | Consultant review and client file (the client-facing safeguard); internal measurement: corpus, labels, harness, first held-out table, regression gate | Review and client file working on the six repositories; measurement table v1 for the team; client-use gate passable once D-6 is signed off |
| 3 | Report: mock v3 on real data (both colour schemes), agreed, then built; Scope page | Mock signed off; browser tests pass on a machine with Chrome (the test skips without it) |
| 4 | Coverage from files (section 9 and coverage matrix PLANNED items with method F or G) | Each new control measured before it is shown |
| 5 | Semantic tier (if the D-3 prototype is adopted) | As phase 4; issues stay possible unless confirmed |

Mock v3 may be built during phase 2; the report rebuild starts once consultant review works (the client-facing
safeguard), not after statistical validation, which is deferred.

## 15. Known defects carried in

- Audit 6 (run 20261102-061233): babylon coupling "0 unresolved" while calls matched is UNKNOWN; office SAST level
  should be enforced; babylon SAST evidence omits FindBugs; context-load-only test classes dropped silently from
  summaries; weak-fit remedies (babylon unit/Cobertura; health `app_config` for aws and cash); babylon
  retries/breakers UNKNOWN where ABSENT is provable; aws messaging reason "publishes only".
- Remedy vocabulary (`gitlab` vs `gitlab-ci`).
- Review 1: owners search record names README and build that are not read; criticality column not shown; a README
  that merely mentions a CI server makes every pipeline control UNKNOWN (`build_ci.py:37-38`), a hidden-gap
  generator; Hazelcast still typed Database with role cache; `critical` severity absent from the sort order; the
  browser test skips without Chrome.
