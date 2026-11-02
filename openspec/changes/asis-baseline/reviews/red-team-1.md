<!-- Independent red-team review, round 1, 2026-11-02. Reviewer: a separate agent that did not write the spec, following ~/.claude/commands/red-team-design.md. Saved verbatim. -->

# Red-team design review: `openspec/changes/asis-baseline` (app-insight AS-IS baseline)

## (1) Mode check and review boundary

**Mode:** design documents plus full read-only repository access. No mechanical gate exists for this spec: `openspec/config.yaml` says the OpenSpec CLI is not installed, and no gate script output was supplied. So there are no established check IDs to defer to. There is no rubric under `~/.claude/rubrics/`.

**What I inspected**
- **Design:** `proposal.md`, `design.md`, `coverage-matrix.md`, `tasks.md`, and all 8 `specs/*/spec.md`.
- **Project rules:** `openspec/config.yaml` (R-01..R-20), `CLAUDE.md` (which only includes `AGENTS.md`), and `AGENTS.md`.
- **Code at HEAD `9479a59`:**
  - `app_insight/{cli,verify,aspects,sources,report}.py`
  - `app_insight/packs/aspects.v1.json` and `packs/remedies/*.json`
  - `app_insight/ui/{core,assessment,discovery}.js`
  - `engine/scripts/{discover,relate,maturity,evidence,scan}.py`
  - `engine/scripts/detectors/{identity,build_ci,security,scope}.py`
  - `engine/scripts/graph/{resilience,contracts,model}.py`
  - `engine/benchmark/README.md`
  - Test files: names and counts only. I ran no tests.
- **History:** `git log` (7 commits).
- **Upstream:** `capture/01-FULL-DECISION-LEDGER.md` (all sections, G in full), `docs/16-master-requirements.md`, `registry/features.csv` F-045..F-099, `contracts/assessment-finding.schema.json`.
- **Prior reviews:** `review-01.md` .. `review-09.md`, read in full.
- **Latest scan output:** run `20261102-113035` — `run.json`, `verify.json`, and per-app `aspects.json` / `discovery.json` / `dimensions.json` / `relationships.json`, read with scripts that print states only, never values.
- **Source repo:** directory listing of `office-integration-master/bin/` only. No secret value was printed.

**Not inspected or not run:** the test suites, any scan, the browser rendering, `docs/17-architecture-addendum.md`, the engine detectors I don't cite above, and the mock files. Any claim that depends on these is marked unverified.

**Assumed standard:** "production baseline" here means a spec that, once signed off, governs what the product may say in a client meeting. So a defect's weight comes from the design's own cost model (design.md §1): a false gap, false pass, wrong reason, inconsistency or leak in front of the client. There is no data-loss dimension. Critical is reserved for confidentiality or security breaches.

## (2) Rule ledger

| Rule | Verdict | Evidence |
|---|---|---|
| R-01 No model decides fact/state/severity/remedy | CONFORMS (runtime) | Verdicts come from catalogue, detectors and tools (design §4, D-3). One caveat: which results the client sees ("validated") is computed against corpus labels a model drafts (design §7.2, D-5). That is not a verdict, but it is model-influenced gating (see F4). |
| R-02 Positive claims cite a line; absence says where it looked | VIOLATES | (a) NOT_APPLICABLE results such as "no database found" (`aspects.py:119-124`) are negative claims with no search record, and the design does not require one (§5.4 covers ABSENT only). (b) The search record for `knowledge.owners` says it looked at "README or build" (`aspects.v1.json:96`). The detector reads CODEOWNERS only (`detectors/identity.py:14-18`). The latest run shows this false record for office and identity (F6). |
| R-03 No answer is never a verdict | VIOLATES (implementation vs claimed BUILT) | A crashed detector leaves `doc[name] = {}` (`discover.py:56-60`). `eval_fact` and `eval_dependency` then return ABSENT (`aspects.py:266, 286`), not NOT_ASSESSED as design §11 claims (F6). How hidden or disputed items affect the rollups is undefined (F13). |
| R-04 Absence only inside the supported range and where the repo doesn't point outside | VIOLATES | §5.4 guards ABSENT only. ISSUE, PARTIAL and NOT_APPLICABLE derived from absence bypass the guard (`aspects.py:401-415`; the open-in-view scenario). 50 of 58 controls have no `understands`, so they are treated as framework-neutral by default. Platform-native settings and GitOps deploys are never "pointed to" (F3, F9). |
| R-05 Same number everywhere | VIOLATES (open) | The consultant and client views show different sets, with no rule for rollup, sort or summary-row effects (§7.3-7.4). Maturity, dimensions and aspects are three parallel models (F10). Audit-6 inconsistencies remain (§13). |
| R-06 No combined score | VIOLATES (current product; design silent) | The report shows a per-app "Maturity N%" tile (`ui/core.js:64`; `discovery.json` `maturity.score`/`band`). Design §9 removes only the home "Overall %". |
| R-07 Never print/store a secret; check outputs by comparing values | VIOLATES | ACC-9 checks outputs with the same `evidence.redact` used to write them (`verify.py:161-172`), so it cannot catch a pattern redaction misses. Design §11 claims it does. There is no value comparison (F7). "Disputed item becomes a corpus case" risks copying client secrets (F8). |
| R-08 No build/run in target; nothing leaves; no credentials on the command line | VIOLATES (enforcement) | Spec operation-and-safety:18 claims BUILT. `sources.py:22,112-116` accepts any `https://` URL, including `user:token@`, with no rejection, and stores it in `run.json` `spec` and the clone's git config. The opt-in Trivy run downloads a database (`scan.py:6-7`). The semantic tier's tool acquisition is not addressed. |
| R-09 Clients isolated | VIOLATES (as worded) | design.md:201 "A disputed item becomes a corpus case"; accuracy spec:73 "the case is added to the corpus backlog". Client code would enter a cross-client corpus (F8). Workspaces themselves are isolated (`cli.py:42-44`). |
| R-10 Remedies from packs, fit to stack | CONFORMS (design) | §8 and remedies spec. The known `gitlab`/`gitlab-ci` defect is confirmed (`modernise-plugin.v1.json` requires `['gitlab','none']`; `build_ci.py:15` emits `gitlab-ci`) and planned as T-1.1. |
| R-11 Reference data carries source and review status | CONFORMS | coverage-matrix A2 notes UNREVIEWED; catalogue spec on modernisation reference data. |
| R-12 Perspectives separate; AS-IS without verdicts | VIOLATES (internal) | §3 makes risk findings a separate perspective, but §6 puts them in assessment aspects 7 and 8. The AS-IS view covers only "A1-A13 and A22" (asis-coverage spec:27), while the matrix calls all 24 areas AS-IS. Maturity and dimensions have no place in the four perspectives (F10, F17). |
| R-13 Strength stated; heuristic = potential | VIOLATES | §5.3 says only a tool or semantic rule sets `confirmed: true`. The open-in-view scenario (catalogue spec:53-56) is "ISSUE (confirmed: the default is on)", from absence of a setting in the files read. |
| R-14 Java semantics from JVM tools | CONFORMS | D-3 (PMD, JavaParser). Feasibility gaps in F15. |
| R-15 No how-to-read guide; one vocabulary; mock first | CONFORMS with defect | §9 and T-3.1. But the cell label "missing" for ABSENT contradicts the state's own definition (F16). |
| R-16 Works at 300 applications | VIOLATES | One duplicate app id aborts the whole run (`relate.py:80-84`). Per-repo exceptions in extract, safetynet and resilience are not isolated (`relate.py:88-99`). Clone slug collisions (`sources.py:32-37`). Spot-check workload is unbounded (F13, F14). |
| R-17 Tool gap listed once, not per app | VIOLATES (minor) | §11: "semantic analysis not run" becomes NOT_ASSESSED per application. A missing tier or scan is a tool gap, not a fact about the client (F22). |
| R-18 New detector has a regression test; figures name corpus and date | VIOLATES | proposal.md:7 "68% to 97.9% on six repositories" gives no run, commit or date, and is PRESENT-only. It was measured on run 20261102-061233, before `203d685` and `9479a59` (F19). |
| R-19 Commit only when asked | CONFORMS | `openspec/` is untracked (`git status`); nothing committed. |
| R-20 Built cites commit and test | VIOLATES | Many BUILT items cite neither: §5.2 "Level (BUILT)", §5.5 applicability "(BUILT)", 57 matrix BUILT rows cite discovery keys only, remedies spec "BUILT (commit 4f47cd7)" with no test. Several BUILT claims are false (F6). |
| AGENTS 1 Ask client name / never mix | CONFORMS | operation spec R-09 requirement. |
| AGENTS 2 No credentials on command line or in lists | VIOLATES (enforcement) | As R-08: the rule is instruction-only; the code accepts credentialed URLs. |
| AGENTS 3 Read the summary; NOT_ASSESSED/UNKNOWN never a pass | VIOLATES | `summarise()` (`cli.py:68-89`) and `summary --json` carry no verify result and no detector failures. An agent following AGENTS.md cannot see that a run failed (F5). |
| AGENTS 4 No invented remedies/effort | CONFORMS | remedies spec "No effort, cost or value". |
| AGENTS 5 Never edit target repos | CONFORMS | T-5.1 inventory fingerprint before and after. |
| AGENTS 6 Point to `report.html` | NOT-APPLICABLE | The design doesn't change agent reporting. |
| AGENTS "Changing": run both suites | CONFORMS | Phase 1 exit "Tests pass". |
| AGENTS "Changing": new control stays pending until a detector exists | CONFORMS | T-4.10, catalogue spec. |
| AGENTS "Changing": no non-stdlib dependency without agreement | CONFORMS | D-3 asks for agreement on the JDK and JVM tools. |
| CLAUDE.md (`@AGENTS.md` only) | — | Covered by the AGENTS rows. |

## (3) Verdict: REJECT this revision (resubmit; most fixes are document-level)

**What would make me refuse production sign-off today?** A baseline whose central promise — "say only what is proven" (§1), "accuracy proven by measurement, not asserted" (proposal) — defines "proven" in a way that cannot prove it, and that marks as BUILT things the code does not do.

Three findings meet that bar, and they hit the production-critical invariant itself rather than an edge:

1. **F1, F2, F4 — the accuracy design does not bound false passes or false gaps.**
   - The minimum corpus (≥3 repos per stratum) cannot reach the validation floor (≥5 cases).
   - "≥98% on ≥5 cases" means "zero errors in 5". That supports an error-rate upper bound of about 45%, not the "about one in 50" D-4 cites.
   - Hidden gaps (a wrong UNKNOWN or NOT_APPLICABLE), PARTIAL, level, evidence and remedy errors are not measured. These made up most of audits 4-9's errors.
   - Labels come from the same model family as the tool. Fixes are measured in-sample with no held-out set.
2. **F5 and F6 — status claims are false at the points that decide what a client sees.**
   - The verify result is not in the summary or the report, and `report.html` and `latest` are written before verify runs. Yet the design states "A failed run is not shown to a client".
   - A crashed detector yields ABSENT, not NOT_ASSESSED.
   - The owners search record tells the client it searched places it did not.
3. **F5 — the phasing has no client-use gate.** Nothing stops today's product, or a phase-3 report built before phase 2 has measured anything, from going into a meeting.

**Why REJECT rather than APPROVE WITH CONDITIONS:** Phase 0 *is* the sign-off of D-4 and D-5 (tasks T-0.2, T-0.3). Approving with conditions would mean approving D-4/D-5 "as amended". But the amendment is a redesign of §7, not a parameter change, so it needs its own review. The containment is good: the architecture, verdict model, R-12 separation and remedy model are sound enough to keep. So the resubmission is a revised §7, corrected statuses, and the matrix additions below, not a new design.

**What would turn this into APPROVE WITH CONDITIONS**
- A revised §7 that:
  - states what bound it targets, as an error-rate upper bound per control at a stated confidence;
  - derives n from that bound;
  - defines how a stratum is composed;
  - measures hidden-gap rates, PARTIAL, level and reason;
  - has a held-out split;
  - sets label-quality acceptance against the human sample.
- Every BUILT row re-verified with commit + test, and the false ones downgraded.
- An explicit "client-ready" exit criterion before any meeting use.
- The F9 class (out-of-repo platform settings) handled in the verdict model.

## (4) Findings: evidence-backed

The design's own §13 "Known defects carried in" is complete for audit 6 (review-09). F10, F11 and F21 below extend it with items from earlier audits and reviews. Nothing here restates §13.

### F1 — High: the validation threshold cannot be met by the specified corpus and cannot support D-4's stated rationale
- **Claim:** The design's minimum corpus makes "validated" unreachable for any per-application control, and "validated" does not bound the error rate the design claims.
- **Evidence:**
  - Accuracy spec:15 "at least 3 repositories in each stratum" vs spec:46 "at least 5 labelled cases there". A once-per-application control gives at most 3 cases on a 3-repo stratum. Applicability (database, messaging) reduces that further.
  - D-4 (design.md:246): "High enough that a client meeting sees about one wrong claim per 50". With n < 50, one error drops below 98%, so "validated" means 0 errors in n ≥ 5. For 0/5 the 95% upper bound on the error rate is 1 − 0.05^(1/5) ≈ 45%. Supporting ≤2% at 95% needs about 150 error-free cases per control per stratum (rule of three).
  - "Both precisions" with no ABSENT cases is 0/0, so undefined.
  - A real application sits in 5 strata at once (build, framework, language, CI, deploy). "Validated on the application's stratum" (design.md:190) does not say whether all 5, any of them, or the combination is required.
- **Severity:** High. Either nothing is ever validated, and the client view is empty or wholly consultant-confirmed, or the threshold is relaxed ad hoc. Either way the "1 in 50" figure would be quoted to clients without basis (R-18 spirit).
- **Fix:**
  - State the target as a one-sided upper confidence bound on false-pass and false-gap rates per control (e.g. ≤5% at 90%).
  - Derive per-stratum n from that bound, and size the corpus from n × applicability.
  - Define validation over marginal strata explicitly, e.g. "validated on every dimension value the app has".
  - Delete the "1 in 50" sentence.

### F2 — High: what is measured excludes most of the error classes the audits actually found
- **Claim:** The corpus measures state precision for PRESENT, ABSENT and ISSUE only, so wrong UNKNOWN/NOT_APPLICABLE (hidden gaps), PARTIAL, level, evidence, reason, remedy fit and recall go unmeasured.
- **Evidence:**
  - design.md:185 and accuracy spec:37 measure "PRESENT precision, ABSENT precision, ISSUE precision, the share of undecided answers". The undecided share is a rate, not a correctness measure.
  - Audit error taxonomy (review-04 table): false negative 11, false positive 7, wrong summary 5, wrong level 3, wrong evidence 5, wrong remedy 3, wrong reason/decidable-not-decided 2, inconsistency 8.
  - Audit 6 (review-09) measured "UNKNOWN/NOT_ASSESSED/N/A 161 → 156 correct" and "first remedy 139 → 135". The corpus design drops measurements the audits already made.
  - The design's own §1 cost table lists "Wrong reason … the gap is hidden behind an unknown" as a cost.
  - A concrete hidden-gap generator: `build_ci.py:37-38` greps the README for `jenkins|teamcity|…|gitlab ci` (one match). That sets `ci_system=["external"]`, and `aspects.py:144-148` turns every pipeline control ABSENT into UNKNOWN. A README that merely mentions Jenkins hides the whole delivery aspect's gaps, and no measurement would detect it.
- **Severity:** High. False passes via UNKNOWN or NOT_APPLICABLE are exactly what R-03 protects against, and they would never show up in "precision".
- **Fix:** Measure, per control and stratum:
  - false-pass rate = truth is a gap, tool says PRESENT, UNKNOWN or NOT_APPLICABLE;
  - false-gap rate = truth is PRESENT/N/A, tool says ABSENT, PARTIAL or ISSUE;
  - level agreement and reason correctness for every undecided result;
  - remedy fit.

  Report recall alongside precision. Validate on the two error rates, not on precision alone.

### F3 — High: the absence guard (§5.4, R-04) covers ABSENT only; other negative-derived verdicts bypass it
- **Claim:** NOT_APPLICABLE "no database / no outbound HTTP" and ISSUE/PARTIAL derived from a setting's absence are not subject to blind spots, `understands`, search records or the corpus guard.
- **Evidence:**
  - `aspects.py:119-124` (`applies`) yields NOT_APPLICABLE from detector absence. `_understood` (`aspects.py:422`) converts this only for the 8 controls with `understands`.
  - `evaluate` (`aspects.py:405-410`) converts ABSENT to UNKNOWN on blind spots, but leaves PARTIAL as a gap with a note.
  - Catalogue spec:53-56 open-in-view: "ISSUE (confirmed: the default is on)". This is an absence-derived verdict. The setting can come from an environment variable, a config server or a profile, and it contradicts §5.3 ("only a tool result or a semantic rule … sets confirmed").
  - Audit 4 #5 is this class: aws-integration timeouts were N/A, "no outbound HTTP client", hiding a critical gap.
- **Severity:** High. False passes (N/A) and false "confirmed" issues bypass the one mechanism built to stop them.
- **Fix:**
  - Extend §5.4 to "any verdict derived from not finding something": NOT_APPLICABLE-by-need, ISSUE-by-default, PARTIAL-by-missing-setting. Each carries a search record and goes UNKNOWN on a blind spot.
  - Make open-in-view `confirmed: false` unless every configuration source is in scope.
  - Add a verify rule for N/A-by-need with a blind spot or unrecognised framework.

### F4 — High: corpus labels and measurement are not independent of the tool and are in-sample
- **Claim:** As designed, measured precision will overstate real-client precision.
- **Evidence:**
  - D-5 (design.md:247): "labels drafted by reading the code, cross-checked by an independent reviewer … The tool and its reviewers are the same model family; a human sample is the only check that is independent". Upstream ledger A DECIDED: "Models never self-certify"; H DECIDED: "independent grading".
  - There is no acceptance criterion for the 10% human sample: no rule like "if humans disagree with more than X% of labels, re-label".
  - T-2.7: "Fix every false pass and false gap the first measurement shows … re-measure" on the same corpus, with no held-out split, so the regression gate and the published table both measure the training set.
  - The corpus is public OSS (D-5), but the enterprise blind-spot strata — the ones that broke audits 4-6 (company parent POM, Jenkins shared library, GitLab remote include, config server) — get only "at least one each" (spec:18-19). That is below the stratum's own ≥3 and the validation ≥5.
  - Spring Boot 1.x is not a stratum, although 1 of 6 audited repos is Boot 1.5.
  - CircleCI, Bitbucket, Nomad and Ktor are claimed BUILT (matrix A6, A12, A13) but have no stratum.
- **Severity:** High. Correlated labeller and tool blind spots plus in-sample tuning produce exactly the "it worked on our corpus" overconfidence the change is meant to remove.
- **Fix:**
  - Split the corpus into tuning and frozen held-out sets, and report only held-out numbers.
  - Make human labelling primary on a stated sample size, with an agreement threshold that triggers re-labelling.
  - Fix stratum selection before any tool run.
  - Raise the enterprise blind-spot strata to the same n.
  - Add Spring Boot 1.x and every CI/deploy system the matrix claims BUILT, or downgrade those claims.

### F5 — High: verify failure is not surfaced, and there is no client-use gate in the phasing
- **Claim:** A failed or unvalidated run can reach a client today and after phases 1 and 3. Design §4's "A failed run is not shown to a client" has no mechanism.
- **Evidence:**
  - `cli.py:145-152` writes `report.html` and updates `latest` *before* `V.write(run_dir)`.
  - `summarise()` (`cli.py:68-89`) has no verify field, so `summary --json` (the AGENTS.md rule-3 interface) never shows a failure.
  - `cmd_report` and `cmd_aspects` (`cli.py:179-188`) rerun verify, ignore the result and return 0.
  - The accuracy spec:7-8 claim "marked failed in its summary … Status: BUILT for the gate" is therefore overstated.
  - Phasing (design.md:265-277): no phase's exit criterion says "may be used in a client meeting". Phase 3 "can run alongside phase 2". Phase 1's exit is "verify passes on six repos", which §7.1 says cannot catch false "not found" or wrong passes. Nothing restricts use of the current product now.
- **Severity:** High. This is the direct path from an unproven claim to the meeting.
- **Fix:**
  - Run verify before the report is written and before `latest` is updated.
  - Put `verify.ok` and the failed rules in `summarise()`, its JSON and the report header.
  - Make `report` and `aspects` exit non-zero on failure.
  - Add a phase-0 decision: "not for client use until phase 2 publishes held-out numbers for the controls shown, and the client view enforces it".

### F6 — High: several BUILT claims are false in the code
- **Claim:** The baseline would lock in statuses the implementation contradicts.
- **Evidence:**
  - **Detector failure (design §11; operation spec:45).** The claim: "the controls that read it are NOT_ASSESSED, the run summary says so (BUILT …)". In the code, `discover.py:56-60` sets `doc[name] = {}` and records `run_meta.failures`. `app_insight` never reads `failures`; there are no matches in `app_insight/*.py`. `_fact` returns `{}` → `eval_fact` returns ABSENT (`aspects.py:266`) and `eval_dependency` returns ABSENT (`aspects.py:286`). A `stack` crash empties the dependencies, so every need-based control becomes N/A. Maturity-based controls do go UNKNOWN (`maturity.py:10-18`). Net effect: a crash produces false gaps and false N/A, and exit code 0.
  - **Owners (matrix A1, "CODEOWNERS, README, build | BUILT").** `detectors/identity.py:14-18` reads CODEOWNERS only. The catalogue search text "a CODEOWNERS file or an owner named in the README or build" (`aspects.v1.json:96`) is shown as the "where it looked" record. The latest run shows it for office and identity (ABSENT, medium), so a false search record reaches the client (R-02).
  - **Criticality (matrix A1; asis-coverage spec:40 "BUILT for team and criticality").** The list-file `criticality` column is carried into the data blob (`report.py:43`), but no UI file reads `source.criticality`. Only `source.team` is shown (`assessment.js:58`). The criticality dimension reads only the `--criticality` file (`relate.py:86`).
  - **Credentials (operation spec:18 BUILT).** No rejection in `sources.py` (see the R-08 row).
  - **Counts.** "15 rules today, 17 after 9479a59" (design.md:80) and "17 rules" (design.md:166), but the code has 18 (`verify.py:24-41`), matching the spec's ACC-1..10 + CON-1..8. "engine 312": a static count of `def test_` in `engine/tests` gives 288 (unverified; inheritance could explain it).
- **Severity:** High as a set, because R-20 exists precisely so a baseline does not certify unbuilt behaviour, and the first two items produce wrong client-facing claims.
- **Fix:**
  - Downgrade each item to PARTIAL or PLANNED with the actual behaviour.
  - Add T-1 tasks: map `run_meta.failures` to NOT_ASSESSED for the controls fed by that detector; correct `search.for` for owners, or extend the detector.
  - Make R-20 checkable: every BUILT row names commit and test id.

### F7 — High: the leak failure path relies on a check that cannot detect what it claims
- **Claim:** ACC-9 cannot catch a secret pattern that redaction misses, because it uses the same redaction function as its oracle.
- **Evidence:** `verify.py:161-172` sets `leaked = evidence.redact_tree(blob) != blob`. Design §11 row: "A secret pattern is missed by redaction | ACC-9 scans every written file; a run with a hit fails (BUILT)". R-07 requires checking "by comparing values". Review-06 #1 was a real leak through exactly such a pattern gap (a Slack webhook). The product does not compare against the literal values its own secret detectors located.
- **Severity:** High. A leak in a mailed report is a security incident (design §1), and the stated safeguard is illusory for the failure it is named after.
- **Fix:**
  - Add an independent oracle: compare every written file against the literal values the secret detectors found in this run, held in memory only, plus a second, broader pattern set not used for redaction.
  - Reword §11 to say what ACC-9 actually covers: writers that skipped redaction.

### F8 — High (confidentiality): "a disputed item becomes a corpus case" moves client code into a cross-client corpus
- **Evidence:** design.md:201; accuracy spec:73 ("the case is added to the corpus backlog"). The corpus is a "fixed folder" shared across runs (design.md:181). R-09 forbids mixing clients. The audited client repos hold committed secrets (reviews 04-09).
- **Severity:** High (Critical if implemented literally). Client source and secrets would enter a reusable artefact.
- **Fix:** State that a disputed item becomes a synthetic, client-free fixture that reproduces the shape, as `engine/tests/test_accuracy.py` audit classes already do. Client code never leaves the client workspace.

### F9 — High: settings that live in the platform, never named by the repo, are structurally false gaps
- **Claim:** R-04's protection ("only where the repository does not point outside itself") cannot fire for org- or platform-level controls, because nothing in the repository names them.
- **Evidence:**
  - `security.secret_scanning` searches CI and build files only, with `blind_to: ["ci"]` (catalogue). GitHub secret scanning and push protection, org-level Dependabot, and central Renovate presets are platform settings.
  - There is no GitOps/Argo CD/Flux detection or blind spot (grep of `detectors/`, `graph/resilience.py`), yet `delivery.deploy` (high) searches `ci, docs`. The matrix (A13:168) says a deployment in another repo is "shown as NOT_ASSESSED", but the high-severity deploy control will be ABSENT.
  - Branch protection and required reviews appear nowhere in the matrix.
  - Review-03 (agreed): "For controls that usually live outside the repo (replicas, alerts, Dependabot or Renovate, secret scanning in GitHub or GitLab settings, backups), emit UNKNOWN ('not seen here, confirm') rather than ABSENT. That fixes the cause". This agreed item was dropped without decision.
- **Severity:** High. These are the "false gap insults the team" cases (§1), and they are systematic across GitHub/GitLab estates.
- **Fix:**
  - Add a catalogue attribute (e.g. `usually_outside: platform|gitops|org`) that caps such controls at UNKNOWN "not seen in the repository; confirm with the team" unless positively found.
  - Add those items to the matrix as X with that behaviour.
  - Add GitOps markers (Argo/Flux manifests, image-updater, "update manifest repo" steps) as blind spots.

### F10 — High: three overlapping assessment models are left unrationalised, and one shows a percentage score
- **Evidence:**
  - `discovery.json` `maturity` has `score` and `band` (latest run: office 50.0, "Medium"). `dimensions.json` has 9 dimensions, including `engineering_maturity` "Medium (50.0%)". `aspects.json` has 13 aspects.
  - The report shows a per-app KPI `"Maturity", t: Math.round(s.mat.score) + "%"` (`ui/core.js:64`). This violates R-06, and design §9 removes only the home "Overall %".
  - Audit 6 #1, #2, #3, #5 and audit 4 #39 were all maturity/dimension vs aspect disagreements. Design §13 carries one symptom (babylon coupling), not the cause.
  - None of the four perspectives in §3 owns maturity or dimensions.
- **Severity:** High. R-05 and R-06 violations are built into the architecture. Each new aspect adds another way for the layers to disagree.
- **Fix:** Decide (a new D-9) that aspects are the only assessment model. Dimensions become derived views computed from aspect controls, or AS-IS facts. The maturity score and band are removed from the report, and a verify rule (CON) checks every dimension headline against its controls.

### F11 — Medium: the AS-IS coverage matrix is incomplete against upstream DECIDED scope and JVM consultant expectations, and mis-states some statuses
- **Claim:** The matrix promises "every item is listed here with a status" (coverage-matrix.md:3-4). These items are absent entirely, neither PLANNED nor OUT.
- **Upstream (master requirements; ledger G):**
  - "app boundaries": deployable units per repository, an application spanning repositories; identity is assumed to equal one repo;
  - "code-to-doc relationships" / doc drift (F-052);
  - Kafka producer semantics (F-057: acks, idempotent producer);
  - "index issues, … lock contention, … cache stampede/invalidation, full scans" (G performance & data);
  - "concurrency/deadlocks" (G data integrity).
- **JVM modernisation:**
  - build-tool / JDK compatibility and support (babylon is on Gradle 2.14, which cannot run on Java 9+; A2 covers support for Java and framework only);
  - internal shared libraries and their versions across the portfolio (upgrade-wave planning; the graph covers runtime calls only);
  - web-tier technology (JSP/JSF/Struts/GWT/Thymeleaf, an embedded SPA);
  - container and deployment security posture (non-root, `securityContext`, network policy);
  - JDK vendor and licensing (base image vendor);
  - database vendor/version and SQL dialect lock-in;
  - PII and data classification;
  - API versioning and compatibility (F-048/F-050);
  - branch protection and review rules (X).
- **File roles:** generated sources and build output are not classified. `bin/` (the Eclipse output folder) is not in `SKIP_DIRS`/`BUILD_DIRS` (`evidence.py:16-17`). Office's configuration files read include `bin/main/logback-spring.xml`, a stale copy, in the latest run. Review-03 "What both reviewers missed" #2 asked for a file-role classifier; it exists only for deployment files (`graph/resilience.py:47-49`).
- **Mis-statused:**
  - A1 Owners → PARTIAL (F6).
  - A1 Criticality → PARTIAL (F6).
  - A13 "Deployment held in another repository … shown as NOT_ASSESSED" is wrong for `delivery.deploy` (F9).
  - A14 "Test quality (assertions …) | T": assertion presence is F-decidable, and `safetynet` already reports `mapped_no_assertion_seen`.
- **Severity:** Medium. Breadth gaps listed on the Scope page are acceptable. Silently absent ones break the user's explicit "try not to miss any of the AS-IS" requirement.
- **Fix:** Add the items above with method and status (most PLANNED, X or OUT), correct the five statuses, and add a general file-role rule (build output, generated, test fixture, example) to the evidence model.

### F12 — Medium: upstream decisions dropped or left undefined without being recorded
- **Evidence:**
  - **Criticality profiles.** F-055 ("service type, criticality and evidence determine applicable controls"), F-099 ("no one-size"), and master requirements "Profile by app kind/criticality". The baseline fixes severity "the same for every application" (catalogue spec:94) and has no criticality profile.
  - **D-1.** "Map to the upstream enum in the export" (design.md:243), but there is no mapping table. ABSENT, PARTIAL, and PRESENT at levels below verified have no upstream counterpart (`assessment-finding.schema.json` enum). Upstream also requires `ruleId`/`ruleVersion`/`sourceRevision` per finding; only the catalogue version exists. `sourceRevision` is ambiguous on a dirty tree (identity: 12 uncommitted files in `run.json`).
  - **F-072 seeded corpus.** The existing `engine/benchmark` (217 fixtures, hand-written labels, fact recall and a false-MET gate) is absent from §7.1's accuracy layers and from the plan, although it is the only place recall is measured today.
- **Severity:** Medium.
- **Fix:**
  - Record each as an explicit decision: adopt, defer with reason, or reject.
  - Give D-1 a full mapping table.
  - Put the benchmark in §7.1 and extend it to aspect controls as the seeded, recall-measuring complement to the corpus.

### F13 — Medium: the consultant/client view boundary and the spot-check are undefined
- **Evidence:**
  - D-7: "Static report … client view hides unreviewed non-validated items". The report is one self-contained file with all data in `const D` (`verify.py:60`), and §1 assumes "a report sent by email". It is unspecified whether hidden items are absent from the client file or merely filtered in the UI.
  - Unspecified whether hidden or disputed items count in aspect status, the "High gaps" sort, the summary row or the portfolio (R-05; CON-2/CON-4 recompute from all controls).
  - Spot-check scope (design.md:198) is "every high-severity gap, every ISSUE, every result on a non-validated stratum, and a random sample of the rest". At 300 apps this is thousands of items (6 apps had 46-52 high gaps and 13 ISSUE in audits 5-6), and before phase 2 every result is non-validated. The random sample has no size and no decision rule.
- **Severity:** Medium.
- **Fix:**
  - Generate a separate client file with hidden items removed from the data, and recompute every count from the visible set (a CON rule).
  - Bound the checklist: high/ISSUE plus a sample sized from the validation status.
  - Add a stop rule (e.g. over 2 disputes in a sample of 30 → the run is not presented).

### F14 — Medium: portfolio-scale failure paths contradict the spec
- **Evidence:**
  - Operation spec:58: "a single repository's failure does not stop the others". But duplicate application ids abort the whole analysis (`relate.py:80-84`, return 2), which is likely with names like `api` or `service` across 300 repos.
  - `extract`, `safetynet.map_application` and `resilience.assess` (`relate.py:88-99`) have no per-repo try/except.
  - The clone slug uses the last two path segments (`sources.py:32-37`), so `teamA/payments/api` and `teamB/payments/api` share a folder while cloning in parallel (`fetch_all`, 4 workers). The likely result is a race or the wrong repository analysed under another name.
- **Severity:** Medium. Wrong-application attribution is a serious trust failure but needs a name collision to occur.
- **Fix:** Use a unique id (host plus full path); isolate per-repo failures into `run.json` with NOT_ASSESSED; turn a duplicate id into a disambiguated id, not an abort. Add these rows to §11.

### F15 — Medium (plausible / not verified): D-3's semantic tier probably cannot reach "semantic" certainty as defined, and does not cover Kotlin
- **Evidence:**
  - The matrix defines S as "parsed, types resolved" (coverage-matrix.md:12).
  - D-3: "run against source only, never building the project". JavaParser symbol resolution and PMD type resolution need the dependency classpath to resolve library types (`JpaRepository`, `KafkaTemplate`, `Closeable`). Getting it needs dependency download or a build (R-08). This is reasoning, not verified.
  - 3 of the 6 audited repos are Kotlin (prom-graf, aws-integration, cash-events), and JavaParser does not parse Kotlin. The design never says Kotlin apps get NOT_ASSESSED for the whole tier.
- **Fix:** Add to D-3 the classpath strategy (with its network implication under R-08) and Kotlin's status. Prototype on 2 repos before approving D-3.

### F16 — Medium: home vocabulary "missing" contradicts the ABSENT definition
- **Evidence:** design.md:220 "showing in place / partial / missing / not checked / issue"; report spec:25 "amber hollow for missing". Against: design.md:93 "ABSENT | searched and not found", and AGENTS.md rule 3 "`ABSENT` means 'not found in the files read', not 'missing in production'".
- **Fix:** Use "not found" (and "not seen here" for F9-class controls) in the one vocabulary table.

### F17 — Medium: internal contradictions on perspective boundaries
- **Evidence:**
  - §3 says risk findings are a separate perspective, while §6 makes them aspects 7 and 8 of the assessment.
  - The asis-coverage spec:27 AS-IS view shows only A1-A13 and A22, while the matrix header says all 24 areas are "what an application's AS-IS consists of". Testing inventory (A14), observability tooling (A19) and supply chain (A23) are AS-IS facts with no AS-IS home.
- **Fix:** Pick one model for risk findings (aspect controls with `confirmed`, as §5.3 implies) and update §3. List the AS-IS view's areas from the matrix, or justify each exclusion.

### F18 — Medium: dependency presence alone counts as "in place", contrary to upstream DECIDED
- **Evidence:** Ledger G DECIDED: "Assess effectiveness and CI enforcement, not dependency presence alone". `aspects.py:293` returns PRESENT "(dependency declared; no configuration found)" for `observability.tracing`, which has no `configured_by` and so is always declared-only, and for `data.migrations` on a library match alone. `rollup` counts any PRESENT as "in place".
- **Fix:** Declared-only becomes PARTIAL, or "in place where checked" with level declared excluded from "in place". Record it in D-2.

### F19 — Low: the headline accuracy figure lacks corpus, date and code version (R-18)
- **Evidence:** proposal.md:7 "68% to 97.9%". The 97.9% is PRESENT-only, on 48 claims (review-09), at run 20261102-061233, before `203d685` and `9479a59`. The latest run (`20261102-113035`) used catalogue 1.3.0 (now 1.4.0) and has no independent audit. Two of the six scanned trees were dirty (`run.json`: 12 and 8 changed files).
- **Fix:** Quote it as "PRESENT state precision 47/48, audit 6, run 20261102-061233, code 203d685^, model-audited", or drop it.

### F20 — Low: the regression gate is defined two ways
- **Evidence:** design.md:193 "a drop in any validated control's precision fails"; accuracy spec:56 "a drop below the threshold".
- **Fix:** Choose one, preferably the bound from F1 computed on the held-out set.

### F21 — Low: agreed or open review items not carried
- Review-03: "let the user sort by any single aspect column" — absent.
- Review-01 #18: "show commands as code" — absent.
- Review-02 #14 / review-03 B14: "treat Hazelcast as a cache". The graph node is still `type: Database`, `role: cache` (latest office `relationships.json`).
- D-6 "high or critical", but `SEVERITY_ORDER` (`aspects.py:18`) has no `critical`, so it would sort last in `summarise()`.
- The browser test silently skips without Chrome (`tests/test_report.py:45`) while the spec states BUILT.
- **Fix:** Add these to §13 or T-3 tasks.

### F22 — Low: tool-not-run results shown per application (R-17)
- **Evidence:** design §11 "semantic tier missing → NOT_ASSESSED: 'semantic analysis not run'"; `eval_security_scan` per app.
- **Fix:** List a tier or scan that was not run once on the Scope page, and keep it out of per-app cells.

## (4b) Judgement calls (opinion, not proven defects)

- **J1:** Modernisation readiness as gaps. The javax scenario (catalogue spec:74-76) makes "jakarta migration needed" PARTIAL for every Spring Boot 2 app. That is a TO-BE target expressed as a current gap, while TO-BE is out of scope (proposal). I would make it an AS-IS fact plus a risk finding, unless the consultant declares a target.
- **J2:** Colour by meaning versus by severity. A high-severity ABSENT ("no authentication") shows amber while a low-severity ISSUE shows red. Review-03 recommended colouring by severity. The design chose review-01's scheme without recording the disagreement.
- **J3:** Breadth before proof. Widening to 17 aspects (D-2) before the existing 58 controls are measured contradicts §1's "Breadth comes second". I would approve D-2 as the catalogue's shape but gate each new aspect's display on F1's bound.
- **J4:** Phase 3 alongside phase 2. I would put the minimal client-view gate (F5, F13) before any report redesign, and the redesign after the first held-out numbers.

## (5) Open questions (evidence needed)

1. **Engine test count.** Is 312 correct? The static count is 288 `def test_`. A test-runner listing would settle it.
2. **Report size at 300 apps.** 6 apps produce a 962 KB `report.html`, which scales linearly to about 48 MB. Does it load acceptably? The existing 200-app synthetic test (`tests/test_report_scale.py:71`) measures rendering, but I did not run it and do not know the data volume it uses.
3. **Semantic-tier precision without a classpath.** Can PMD `CloseResource` and a JavaParser analyser reach acceptable precision offline? A two-repository prototype would show it.
4. **Audit-5 items.** Did the fixes for review-08 #12 (zone spread on VM fleets) and its generic-remedy items survive? In the latest run, zone spread is UNKNOWN (acceptable) and cash migrations now offer "Version the database schema". Not checked on the other apps.
5. **Verify on the current code.** Does `verify` pass on a fresh run of HEAD `9479a59`? The latest run predates it (catalogue 1.3.0), so the ACC-10 and CON-8 BUILT claims have unit tests but no real-run evidence.

