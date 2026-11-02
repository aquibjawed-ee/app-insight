<!-- Independent red-team review, round 2, 2026-11-02. Reviewer: a separate agent that did not write the spec, following ~/.claude/commands/red-team-design.md. -->

# Red-team design review, round 2: `openspec/changes/asis-baseline` (revision 2)

## (1) Mode check and review boundary

**Mode:** the design documents plus full read-only access to the repository at HEAD `9479a59`. The `openspec/` folder is untracked, and `git status` shows nothing else changed. There is no mechanical spec gate: the OpenSpec CLI is not installed and no gate output was supplied, so there are no established check IDs to defer to. There is no rubric under `~/.claude/rubrics/`.

**What I inspected**
- **Design:** `proposal.md`, `design.md`, `coverage-matrix.md`, `tasks.md`, all 8 `specs/*/spec.md`, `reviews/red-team-1.md` and `reviews/red-team-1-response.md`, all in full.
- **Rules:** `openspec/config.yaml` (R-01..R-20), `CLAUDE.md` (which only includes `@AGENTS.md`), and `AGENTS.md`.
- **Product code:**
  - `app_insight/aspects.py`: `applies`, `eval_criterion`, `eval_ha`, `eval_lifecycle`, `eval_fact`, `eval_check`, `eval_dependency`, `eval_security_scan`, `searched`, `blind_for`, `evaluate`, `_understood`, `rollup`.
  - `app_insight/verify.py` (complete rule set and check body).
  - `app_insight/cli.py:60-200`.
  - `app_insight/sources.py`: slug, `expand`, `_git`, `fetch`.
  - `app_insight/packs/aspects.v1.json`, analysed by script: 58 controls, 9 pending, 8 with `understands`, 44 with `search`.
  - `app_insight/ui/core.js:64`, plus `dashboard.js`, `assessment.js` and `about.js` (searched for review-status labels).
- **Engine code:**
  - `engine/scripts/discover.py:50-62`, `relate.py:76-100`, `evidence.py` (`SKIP_DIRS`, `walk`, `read_lines`, `verify`).
  - `detectors/{build_ci,identity,integrations,security,runtime}.py`, at the cited lines.
  - `engine/rules/*.json` review blocks.
- **Tests:** I did not run them. I counted them with `unittest` discovery without running any (engine 312, product 51: both match design §7.1). I also confirmed that every test name cited in the specs exists, including `ScopeTest` with 8 tests.
- **Upstream:** ledger section G (in full), `registry/features.csv` F-045..F-099, and `contracts/assessment-finding.schema.json`.
- **Earlier reviews:** `review-03.md` ("what both reviewers missed"). I relied on round 1's reading of reviews 01-09 and did not re-read them in full.
- **Statistics:** recomputed from first principles with a stdlib script (exact binomial CDF, bisection).

**Not inspected:** scan outputs or run folders (I opened none), the browser rendering, `docs/17-architecture-addendum.md`, and the detectors not named above. No secret value was read or printed.

**Assumed standard (same as round 1):** the baseline governs what the product may say in a client meeting. Severity is weighed by the design's own cost table (§1): false gap, false pass, hidden gap, inconsistency, leak, wrong application. Critical is reserved for confidentiality or security breaches.

## (2) Rule ledger

| Rule | Verdict | Evidence |
|---|---|---|
| R-01 No model decides a fact, state, severity or remedy | VIOLATES (validation layer) | §7.5: the person labels ≥300 cases; "the remaining labels may be drafted by a model … then checked by a second model reviewer". The reference states for almost every corpus case are therefore decided by a model, and "validated" (shown to the client, §7.3) is computed from them. A model checking a model's output is not justified as semantic. See N3. |
| R-02 Positive claims cite a line; negative claims say where they looked | CONFORMS (design), PARTIAL (code) | Spec evidence-and-verdicts:17-21 extends search records to N/A, ISSUE-by-default and PARTIAL-by-missing-part. But ACC-10 (`verify.py:126`) only checks that `for`/`in` exist, so "names only places actually read" has no check. For the `repo` area, `searched()` (`aspects.py:384-385`) records no count and no file names, although the spec claims "number and names" as BUILT. See N7. |
| R-03 No answer is never a verdict | VIOLATES (new, in design) | The client file recomputes aspect status from the visible subset only (§2.2, §8). Gaps that were never reviewed are removed, so an aspect can read "In place" because results were left out (N5). Separately, §6.2 removes every unconfirmed ISSUE from status and counts (N4). |
| R-04 Absence only inside the supported range | CONFORMS (design, PLANNED) with a residual | §6.3 now covers every absence-derived verdict. The residual: 50 of 58 controls still have no `understands`, and the new `depends_on` is not tied to it (a control that depends on the framework need not declare `understands`). §6.3(1) BUILT is overstated (N7). |
| R-05 Same number or state everywhere | VIOLATES (by design) | The internal report and the client file deliberately carry different aspect statuses and counts for the same application (§2.2, §8: "all counts recomputed"). No stated exception and no on-page marker (N5). CON-1/2/4 recompute with the writer's own `A.rollup` (`verify.py:135`), so they detect drift, not wrong logic (N21). |
| R-06 No combined score | CONFORMS (design) | D-9 and §11 remove "Overall %" and "Maturity N%" (`ui/core.js:64`, still in code, PLANNED as T-1.13). "Checked x of y" is a count, not a score. |
| R-07 Never print or store a secret; check by comparing values | CONFORMS (design) with a failure-path gap | The independent literal-value check is specified. Values "held in memory only" exist only during `scan`. `report` and `aspects` rebuilds (`cli.py:174-175`) and `verify` on demand cannot run it (N10). |
| R-08 Nothing leaves; no credentials | CONFORMS (design, PLANNED); VIOLATES (code) | Refusal is PLANNED (T-1.6). The code also stores the raw CLI `inputs` (`cli.py:130`) and writes the remote URL into the clone's git config. T-1.6 names only "source URLs"; it must cover `run.json.inputs` and `.git/config` too. |
| R-09 Clients isolated | CONFORMS | §8 now says a dispute becomes a synthetic, client-free fixture. Who writes it, and what may not be copied (package names, hostnames), is unstated; see open questions. |
| R-10 Remedies from packs, fit to stack | CONFORMS | §10; `gitlab`/`gitlab-ci` defect (T-1.14). |
| R-11 Reference data carries source and review status wherever shown | VIOLATES (code; design claims BUILT) | §13: "Reference data is stale \| Source and review status shown \| BUILT". The Assessment result text "Spring Boot %s: all support ended" (`aspects.py:246`, also `:238`, `:227`) carries no review status, and `ui/assessment.js` has no review label. The status appears only in About, an Impact page, and a dashboard tooltip. `lifecycle.v1.json` is `"status": "unreviewed"`. |
| R-12 Discovery, assessment, risk findings, portfolio and remedies are separate perspectives | VIOLATES (as worded) | §4 has three perspectives and folds risk findings into assessment (D-9). The rule text, and upstream G DECIDED ("Separate discovery, quality/risk findings, maturity, production readiness and continuous assurance perspectives"), say otherwise. A defensible decision, but taken without amending the rule or recording the upstream departure (N12). |
| R-13 Strength stated; a heuristic is a potential issue | CONFORMS (in letter), mis-specified | §6.2 defines `confirmed` so narrowly that deterministic, cited facts (a committed secret, an end-of-life framework, a timeout set to 0) become "possible" (N4). |
| R-14 Java semantics from JVM tools | CONFORMS | D-3: a PMD and JavaParser prototype. |
| R-15 No "how to read" guide; one vocabulary; mock first | VIOLATES (minor) | Certainty is "syntactic/semantic" in the matrix (coverage-matrix:9-14) but "text/parsed/semantic" in design §6.2. "Set wrongly" labels every ISSUE, including end of support and a shared database (N18). |
| R-16 Works at 300 applications | VIOLATES (design) | The checklist reviews "every confirmed ISSUE and high-severity gap on a non-validated stack". Audits found 46-52 high gaps across 6 applications, which projects to about 2,300-2,600 items at 300 applications, with no bound (N5). Report size of about 48 MB is still open (T-3.8). |
| R-17 A tool gap is listed once | CONFORMS (design) | Scope page; spec assessment-catalogue:104-112. |
| R-18 Regression test per detector; figures name corpus and date | CONFORMS | §7.7 restates the audit-6 figure with run, code and "model-audited". Test counts 312 and 51 confirmed by discovery. |
| R-19 Commit only when asked | CONFORMS | `openspec/` untracked. |
| R-20 BUILT cites commit and test | VIOLATES | False or overstated BUILT claims remain (N7): §6.1 is headed BUILT but contains PLANNED semantics; §6.3(1) "need-based N/A on 8 controls" is actually 2 in code; ACC-2 is claimed for PARTIAL and ISSUE but checks only PRESENT; matrix A22 "Owners BUILT" contradicts A1 PARTIAL; R-11 is claimed BUILT. Several BUILT rows still cite no test (ACC-5, "Deterministic", `graph/resolve.py`), which T-1.3 acknowledges. |
| AGENTS 1 Ask client; never mix | CONFORMS | operation spec. |
| AGENTS 2 No credentials on the command line or in lists | VIOLATES (code, PLANNED) | As R-08. |
| AGENTS 3 Read the summary; UNKNOWN and NOT_ASSESSED never a pass | CONFORMS (design, PLANNED) | T-1.1 and the operation spec "Agents can read the outcome". `summarise()` (`cli.py:68-89`) still lacks verify. |
| AGENTS 4 No invented remedies or effort | CONFORMS | remedies spec. |
| AGENTS 5 Never edit target repositories | CONFORMS | operation spec, fingerprint check for tool runs. |
| AGENTS 6 Point to report.html | NOT-APPLICABLE | Agent reporting is unchanged apart from summary fields. |
| AGENTS "Changing": run both suites | CONFORMS | Phase 1 exit criterion, browser test not skipped. |
| AGENTS "Changing": new control pending until a detector exists | CONFORMS | T-4.9 and the catalogue spec. |
| AGENTS "Changing": no non-stdlib dependency without agreement | CONFORMS | D-3 asks for agreement. Exact binomial bounds are computable with stdlib `math.comb`. |
| CLAUDE.md (`@AGENTS.md` only) | — | Covered by the AGENTS rows. |

## (3) Verdict: REJECT revision 2 as the baseline; phase 1 may proceed

**What would make me refuse production sign-off today?** Phase 0 asks the user to sign D-0..D-11. I would refuse if signing them committed the product either to a validation scheme that cannot validate anything with the corpus it buys, or to client-facing statements and verdict semantics that hide real risks. Four findings meet that bar. Each sits on the design's central promise, "say only what is proven" (§1), not at an edge.

1. **N1: the corpus cannot do what §7.4 and D-5 say.** Validation needs ≥22 error-free held-out cases for **each** of two rates, with different denominators. That means at least 44 held-out cases per (control, stack value), or about 88 repositories carrying that value at a 50% split. About 60 repositories therefore validates no control on any value, not "one or two common stacks". So the phase-2 exit ("client-use gate passable for the validated stack") cannot be met as sized.
2. **N2: the sentence shown to the client is not what is measured.** "Validated: fewer than 1 in 10 wrong, 90% confidence" bounds error rates conditional on the true state. It does not bound the chance that a shown "In place" is wrong. Both bounds are claimed at 90% each, and validation is marginal per dimension. The statement would be quoted to a client without support: the exact failure mode round-1 F1 was raised for.
3. **N4: `confirmed` is defined so narrowly that every ISSUE the product finds today becomes a "possible issue".** That covers committed secrets, end-of-life frameworks and disabled timeouts. Under §6.2 and the report spec, possible issues are excluded from issue counts, "High gaps", the home sort, red colouring and the consultant checklist. The redesign's own rules turn true issues into hidden ones.
4. **N5: the client file is a biased subset.** Before validation exists (always, given N1), only high gaps plus 30 sampled results reach consultant review, and only reviewed results enter the file. Aspect statuses recomputed from that subset can read "In place" because gaps were left out (R-03), and disagree with the internal report (R-05).

**Why REJECT rather than APPROVE WITH CONDITIONS:** the same reasoning as round 1. The fixes change D-1 (the meaning of `confirmed`), D-4 (target and wording), D-5 (corpus size and labelling protocol) and D-7 (client-file semantics). These are the decisions phase 0 signs. Approving "as amended" would sign decisions not yet written.

**Containment is good, and the resubmission is narrow:** §6.2 (the confirmed definition), §7.3-7.6 (sizing, claim text, labels, gate), §2 and §8 (client-file semantics), plus the status corrections in N7. Round 1's structural asks are met: held-out split, both error rates, a client-use gate, `usually_outside`, one assessment model, and synthetic fixtures for disputes. **Phase 1 (T-1.1 to T-1.21) does not depend on the rejected decisions and can start now**, except T-1.8/T-1.9 scope (see N6) and T-1.12 scope (N15). It is mostly code fixing defects the code confirms.

## (4) Findings

### Round-1 findings: does revision 2 resolve them?

| R1 | Status in revision 2 | Basis |
|---|---|---|
| F1 threshold unreachable; "1 in 50" | **Partly.** | Bound form and the sample-size table are correct (verified below), and "1 in 50" is withdrawn. The derivation of corpus size is wrong (N1), and the client-facing wording misstates the bound (N2). |
| F2 error classes unmeasured | **Mostly.** | False-pass rate now includes UNKNOWN and N/A, false-gap rate includes PARTIAL and ISSUE, and the README hidden-gap generator has a task (T-1.11). Residual: wrong-kind gaps (truth PARTIAL, tool "Not found") are in neither rate, and reason, level, evidence and remedy measures do not gate validation (N16). |
| F3 absence guard ABSENT-only | **Resolved in design (PLANNED).** | One internal contradiction on PARTIAL (N14). The BUILT part is overstated (N7). |
| F4 labels not independent; in-sample | **Partly.** | Held-out split, person labels and strata fixed in advance are added. The label-quality gate is incoherent: the overlap is empty by construction, the per-stratum n is about 11, agreement is pooled over controls, a model reviews a model (N3). Strata are nominal at 60 repositories (28 values). |
| F5 verify not surfaced; no client gate | **Resolved in design.** | §2, T-1.1, T-1.19. Residuals: §2 says the client file comes in phase 1 while tasks put it in phase 2 (T-2.9); gate item 3 is vacuous when nothing is validated; the gate omits severity and reference-data sign-off (N9). |
| F6 false BUILT claims | **Partly.** | The listed items were downgraded and all re-checked claims hold (both test counts confirmed). New or remaining false claims are in N7. |
| F7 leak check uses its own oracle | **Resolved in design.** | Gap on the rebuild path (N10). |
| F8 client code into corpus | **Resolved.** | §8. |
| F9 platform settings as false gaps | **Resolved, but overcorrected.** | "Deployment when no deploy step is found" becomes UNKNOWN for every such repository, a hidden-gap generator on a high-severity control. There is no labelling policy for these controls (N6). |
| F10 three assessment models | **Resolved in design (D-9).** | Conflicts with the R-12 text and upstream G; needs explicit amendment (N12). |
| F11 matrix gaps | **Mostly.** | 19 items added; recount confirmed (57/25/64/5/6 = 157, 25 areas). Residual inconsistencies and plausible omissions are in N19. |
| F12 upstream decisions | **Mostly.** | D-10, D-1 mapping table, and rule, version and revision per finding are added. The mapping overclaims (N8). |
| F13 client/consultant boundary | **Partly; introduced N5.** | Separate file, data removed and stop rule are added. The census part is unbounded at 300, and the subset bias is new. |
| F14 scale failure paths | **Resolved in design (PLANNED).** | Also cover `discover.build` in the per-repo loop (`relate.py:76-79`), which is outside any per-repo isolation too. |
| F15 semantic tier | **Resolved.** | The adoption criterion is unstated (N20). |
| F16 "missing" | **Resolved.** | |
| F17 perspective contradictions | **Resolved.** | A0-A24 each have an AS-IS home. |
| F18 declared-only PRESENT | **Partly.** | Covers `eval_dependency` (`aspects.py:294`) only, not `eval_fact` (N15). |
| F19 figure provenance | **Resolved.** | |
| F20 two gate definitions | **Resolved in text.** | New conflict with held-out refresh (N13). |
| F21 agreed items | **Resolved (tasks).** | |
| F22 tool-not-run per app | **Resolved in design.** | |
| J1-J4 | **Resolved or recorded.** | J2 is recorded as D-11. |

### Statistics check (§7), recomputed

- **Zero-error n**, one-sided Clopper-Pearson (n ≥ ln(1−c)/ln(1−p)): 2%/95% → 149; 5%/90% → 45; 10%/90% → 22. **The §7.3 table is correct.** Spec scenario "12 cases, no errors → about 17%": exact 17.5%, **correct**.
- **With 1 or 2 errors**, the cases needed are: at 10%/90%, 38 and 52; at 5%/90%, 77 and 105.
- **Validation is brittle at the minimum:**
  - P(0 errors in 22 | true rate 2%) = 0.64 per rate. Two independent rates, both needing error-free: about 0.41.
  - A control with a 2% true error rate therefore fails validation more often than not at n=22.
- **Consultant stop rule** (accept when ≤2 disputes in 30): P(accept) = 0.81 at a 5% true dispute rate, 0.41 at 10%, 0.15 at 15%, 0.04 at 20%. The 90% upper bound at 2/30 is 16.8%. So a run is used with a client 41% of the time when one in ten sampled results is wrong. That is looser than the 10% target applied to validated results.
- **Label agreement:** 11/11 agreement has a 90% lower bound of 81%. 19/20 (95% point) has a lower bound of 82%.

### Evidence-backed findings

#### N1 — High: about 60 repositories cannot validate any (control, value); §7.4's sizing ignores the two-denominator rule
- **Claim:** under §7.3's own rule, validation needs ≥22 error-free held-out cases in **each** truth class. So "about 50-60 repositories per common value" and "about 60 … reaches the target for one or two common stacks" are false.
- **Evidence:**
  - The false-pass rate's denominator is "truth is a gap"; the false-gap rate's denominator is "truth is PRESENT or NOT_APPLICABLE" (§7.2). "Both … at or below the target" (§7.3).
  - So per (control, value) the minimum is 22 + 22 = 44 held-out cases, at 50% gap prevalence. At a 50% split that is ≥88 repositories with that value, assuming every repository yields one applicable case.
  - At realistic prevalence the rarer class dominates. A control whose gap is rare in public code (CI build, about 10% prevalence) needs about 220 held-out repositories for its false-pass bound, and the false-pass bound is the one that matters most to a client.
  - §7.4 also says "applicable cases" for the 22. That is inconsistent with N/A-truth cases sitting in the false-gap denominator.
  - Even under a one-denominator reading, 44 Maven repositories leave 16 for every other build value, so at most one value per dimension can validate, not two.
  - And 28 stratum values (§7.4) across 60 repositories leave most strata with 1-3 repositories.
- **Severity:** High. The phase-2 exit criterion and the client-use gate rest on validated controls. As sized, none exist, so either the client view is permanently consultant-only (see N5) or the threshold will be relaxed ad hoc.
- **Fix:**
  - Derive the corpus per (control, value) from both class counts at the expected prevalence, and plan for 1-2 errors (38-52 per class at 10%/90%), not zero.
  - State the resulting size. Expect well over 100 repositories for one stack.
  - Alternatively, validate the false-pass rate only where the gap class is reachable, and say which controls cannot be validated from public code.
  - Re-state D-5 accordingly.

#### N2 — High: the validated wording shown to clients misstates what is bounded
- **Claim:** "Validated: fewer than 1 in 10 wrong, 90% confidence" (§7.3) is not what §7.2-7.3 measure.
- **Evidence:**
  - The rates are conditional on the true state. The meeting needs the chance that a shown result is wrong, which depends on prevalence.
  - Example: gap prevalence 70%, false-pass rate 10%, false-gap rate 10%. P(truth gap | shown "In place") = 0.07/0.34 ≈ 21%.
  - Two bounds at 90% each give about 81% joint confidence (Bonferroni ≥80%), not 90%.
  - "An application is validated … when every dimension value it has … is validated" (§7.3) intersects marginal results. It establishes no bound for the combination (for example Maven with a Jenkins shared library).
  - With about 50 controls × 28 values, the multiplicity is uncontrolled.
- **Severity:** High. An unsupported accuracy statement made to the client is exactly the round-1 F1 failure, now in the product's own text.
- **Fix:**
  - Word it as what is measured: "on N held-out repositories using <value>, this check missed a real gap in at most X% of cases and raised a false gap in at most Y% of cases (each 90% one-sided)".
  - Or measure predictive values (wrong given shown) on the held-out set and state those.
  - Name the multiplicity policy, and say validation is per dimension, not per combination.

#### N3 — High: the label-quality gate cannot work as written
- **Claim:** the 95% agreement acceptance of model-drafted labels (§7.5) is undefined, statistically empty and pooled at the wrong level.
- **Evidence:**
  - "The remaining labels may be drafted by a model" makes model and person labels disjoint, so "the overlapping sample" is empty unless the model also labels the person's 300. That is not stated.
  - 300 cases over 28 stratum values is about 11 per value. The spec scenario's "91%" is 10 of 11. An 11/11 pass still allows true agreement of 81% (90% lower bound).
  - Agreement is pooled across controls. Validation is per control and is driven by the rare truth-gap class: about 50 controls means about 6 person-labelled cases each.
  - Label noise against a zero-error criterion: with 5% uncorrelated noise, a perfect tool shows ≥1 apparent error in 22 cases with probability 0.68.
  - If only tool-vs-label disagreements are sent to a person ("held out until a person settles them"), labels that agree with a wrong tool are never re-checked. That biases accuracy upward.
  - "Checked by a second model reviewer" is a model checking a model, with no stated semantic necessity. See R-01.
- **Severity:** High. The validated status shown to clients rests on these labels.
- **Fix:**
  - Have the person label every case that decides validation for the controls targeted first, or define the overlap explicitly (the model also labels the 300).
  - Gate per control on the gap class with a lower confidence bound, not a pooled point estimate.
  - Re-adjudicate a random sample of agreeing cases too.
  - Drop the second-model review or state why it is semantic.

#### N4 — High: the definition of `confirmed` turns every current ISSUE into a hidden "possible issue"
- **Claim:** §6.2 says `confirmed: true` "only when a tool result or a semantic rule proves it and every source that could change it is in scope". With the report rules, that removes deterministic, cited issues from every ranking and status.
- **Evidence:** today's ISSUE sources are a regex secret detector (`detectors/security.py:137`), configuration values (`detectors/runtime.py:169`, `:288`, `:313`), and reference-table lookups (`aspects.py:227`, `:238`, `:246`). None is a "tool result or semantic rule", and environment variables can override any Spring property. Under the specs, possible issues:
  - do not count in issue counts, "High gaps" or the sort (evidence spec:113-116; report spec:27-28);
  - do not raise aspect status (catalogue spec:7-8);
  - are not red (report spec:47-48);
  - are not in the consultant checklist (§8: "every confirmed ISSUE").

  So a committed secret or Spring Boot 1.5 leaves the aspect "In place" and is absent from the client file unless randomly sampled. This also contradicts upstream G ("high-severity assessment families") and §6.1 ("ISSUE | a fact read shows a problem").
- **Severity:** High. A designed-in false pass on the most decidable risks.
- **Fix:** confirmed = certainty `text` or better on a cited line whose value is not overridable inside the scan's supported range, with blind spots handled by §6.3. Reserve "possible" for heuristic patterns (N+1, outbox, loops). Enumerate the current ISSUE sources and their `confirmed` value in the spec.

#### N5 — High: the client file is a biased subset, recomputed into statuses that can hide gaps
- **Claim:** the §2 plus §8 rules make the client file contain mostly high gaps, and recomputing aspect status from it breaks R-03 and R-05.
- **Evidence:**
  - Only validated or consultant-confirmed results are shown (§2.2).
  - The checklist covers high gaps and confirmed ISSUEs plus "a random sample of 30 other non-validated results" (§8).
  - "All counts recomputed" from the visible set.
  - With nothing validated (N1), PRESENT and medium or low gaps reach the file only via the sample of 30 per run. Across 300 applications the client sees gaps, almost no "In place", and aspect statuses that are either "High gaps" or computed from a handful of controls.
  - An aspect whose medium gaps were unreviewed but one PRESENT was sampled reads "In place": a no-answer counted as a pass.
  - The internal report shows different statuses for the same application (R-05).
  - The census part is unbounded: audits found 46-52 high gaps across 6 applications, about 2,500 at 300 (R-16).
  - Gate item 3 ("measurement table … for every control the client file shows as validated") is vacuously satisfied when none is validated.
- **Severity:** High. The gate meant to protect the meeting produces a misleading meeting picture: gaps over-represented, passes hidden, statuses inconsistent across files.
- **Fix:**
  - A result not shown is a visible "not reviewed" in the client file, counted like NOT_ASSESSED. Aspect status there is "Reviewed: x of y"; it is never computed as if the omitted results were absent.
  - Let the consultant confirm by aspect or application, not only from the checklist.
  - Bound the census per application (for example top-k by severity) with the rest in the sample.
  - State the R-05 exception explicitly, with a marker on both reports.

#### N6 — High: `usually_outside` on "deployment when no deploy step is found" turns the high-severity deploy gap into UNKNOWN everywhere, and 7.2 cannot score it
- **Claim:** catalogue spec:37-41 makes `delivery.deploy` (severity high) UNKNOWN whenever no CI deploy step and no runbook are found. The delivery aspect then rolls up to "In place where checked" (`aspects.py:489-490`) for applications with no deploy automation.
- **Evidence:**
  - Design §1 lists "Hidden gap" as a cost.
  - Design §6.6 and the spec lists differ: the design includes replicas, the spec does not.
  - The labelling protocol does not say what truth is for an outside-the-repository control. If the labeller marks ABSENT from the repository, every such UNKNOWN is a false pass by §7.2 and the control can never validate. If marked UNKNOWN, it is 0/0 and also never validated.
- **Severity:** High. It is systematic across estates, and it hides the one gap clients most often have.
- **Fix:**
  - Apply `usually_outside` to deployment only when a positive marker exists (GitOps manifests, image-updater, a CI step that pushes to a manifest repository, an image published with no deploy). Otherwise keep ABSENT with the search record.
  - Define label truth for usually-outside controls ("not decidable from the repository" is a label value, and those controls are consultant-only, said so on the Scope page).
  - Align the design and spec lists.

#### N7 — Medium: false or overstated BUILT claims remain (R-20)
- **§6.3(1) and evidence spec:34**, "BUILT for ABSENT and need-based N/A on 8 controls". `_understood` converts N/A only when `needs in ("outbound_http","database")` (`aspects.py:423`). Of the 8 controls, only `runtime.http_timeouts` and `runtime.retries_breakers` qualify. The other need-based ones (`db_timeouts` needs `sql_database`, `messaging_errors` needs `messaging`, `api.openapi` needs `http_endpoints`) keep N/A for unrecognised frameworks.
- **Evidence spec:5-10**, "PRESENT, PARTIAL or ISSUE SHALL cite … BUILT (ACC-1, ACC-2)". ACC-2 checks `st == "PRESENT"` only (`verify.py:109`).
- **Evidence spec:17-21**, search record "with the number and names of the files searched", BUILT for ABSENT. For the `repo` area, `searched()` emits `count: None, files: []` (`aspects.py:384`), which affects `knowledge.owners` and `security.dependency_updates`. ACC-10 checks only that the record exists (`verify.py:126`).
- **§6.1**, headed "BUILT", but includes PLANNED semantics: declared-only is PARTIAL, N/A carries a search record, ISSUE has `confirmed`.
- **coverage-matrix:287**, "Owners | BUILT", against :43 "Owners | PARTIAL".
- **§13**, "Reference data … review status shown | BUILT". Not on the Assessment results (R-11 row).
- **Fix:** downgrade each claim to its actual state; add a test that a need-based N/A on each `understands` control becomes UNKNOWN; extend ACC-2 to PARTIAL and ISSUE; add a verify or catalogue test that `search.for` names only areas the source detector reads.

#### N8 — Medium: the export mapping overclaims in the direction that is lost
- **Evidence:** evidence spec:147-148 maps "PRESENT at a lower level" to `VERIFIED_CONTROL`, with `level` as an extension field. The upstream schema is `additionalProperties: false`, so the field is dropped and a declared or configured PRESENT exports as verified. It is "lossy and says so" (spec:156-157), but the loss turns "configured" into "verified".
- **Fix:** export below-verified PRESENT as `POTENTIAL_ISSUE` or `INSUFFICIENT_EVIDENCE` until the upstream schema gains `level`, or block export until then.

#### N9 — Medium: client-use gate omissions and phase mismatch
- **Evidence:**
  - §2 lists three conditions. It does not require the D-6 severity sign-off (the catalogue `status` is "DRAFT", and severity drives "High gaps", the sort and the checklist census). It does not require reviewed reference data for end-of-life claims (both `engine/rules` files are `unreviewed`).
  - §2: "until phase 1 (items 1, 2)". But the client file is T-2.9 (phase 2), and phase 1's exit criterion does not mention it.
- **Fix:** add severity sign-off and the reference-data review status (or an "unreviewed" label on every such result in the client file) to the gate; correct the phase reference.

#### N10 — Medium: the independent leak check has no rebuild path
- **Evidence:** the literal values are "held in memory only" (§13; accuracy spec:18-21). `report` and `aspects` regenerate `report.html` and `aspects.json` outside a scan (`cli.py:166-187`), and `verify` runs standalone. None has the values.
- **Fix:** rebuilds and standalone verify re-run the secret detectors to repopulate the values, or refuse to write when they cannot. State which.

#### N11 — Medium: runs and confirmations are not bound to the source they describe
- **Evidence:**
  - Clones are shared per workspace and `reset --hard FETCH_HEAD` on the next scan (`sources.py:162-166`). ACC-1 on a rebuild or verify of an older run re-reads the newer checkout (`verify.py` uses the manifest repo path).
  - `aspects` rebuilds an old run with the current catalogue and packs (`cli.py:166-175`).
  - `review.json` marks (§8) bind to nothing stated. A confirmation survives a rebuild that changed the result.
  - Upstream F-070 ("evidence freshness") and F-079 ("evidence invalidation") are not addressed.
- **Fix:**
  - Bind each mark to (control, state, evidence snippet hash, catalogue version, source revision) and invalidate it on any change.
  - Make the client file require all marks current.
  - Re-read evidence at the run's recorded commit, or refuse verify when HEAD differs.

#### N12 — Medium: D-9 changes a project rule and an upstream DECIDED item implicitly
- **Evidence:** R-12 lists "risk findings" and "remedies" as separate perspectives. Upstream G DECIDED separates "quality/risk findings, maturity, production readiness and continuous assurance". §4 has three perspectives, and D-9 removes maturity.
- **Fix:** amend R-12 in `config.yaml` with the user's decision and date, and record the upstream departure and its reason in D-9. Continuous assurance (re-assessment, §3) needs a stated home.

#### N13 — Low: the regression gate conflicts with held-out refresh and reuses the held-out set
- **Evidence:** "fails … when its false-pass or false-gap count rises at all" (§7.6). Adding held-out repositories after 5 rounds (§7.4) raises counts with no code change. The gate consults the held-out set on every change, so every change is "accepted against" it.
- **Fix:** compare counts against a baseline per corpus version, count gate runs toward the refresh, and retire contaminated held-out repositories to tuning.

#### N14 — Low: §6.3 contradicts itself on PARTIAL
- **Evidence:** the lead text says each of the four absence-derived verdicts, including "PARTIAL by a missing part", "becomes UNKNOWN". Item 2 and evidence spec:34 say "PARTIAL gets a note".
- **Fix:** keep PARTIAL with a note (the found part is a fact) and fix the lead sentence.

#### N15 — Low: declared-only PRESENT also comes from `eval_fact`
- **Evidence:** `aspects.py:261` returns PRESENT at level "declared" for an INFERRED fact. T-1.12 and the evidence spec cover only dependency declarations (`aspects.py:294`).
- **Fix:** widen T-1.12 to any PRESENT at level declared.

#### N16 — Low: wrong-kind gaps and the secondary measures do not gate validation
- **Evidence:** truth PARTIAL vs tool ABSENT ("Not found" shown when partly in place) is neither a false pass nor a false gap (§7.2). Reason, level, evidence relevance and remedy fit are measured but not part of §7.3.
- **Fix:** add a "wrong gap kind" rate, and require level and reason agreement above a stated floor for validation.

#### N17 — Low: the detector-failure status in §13 is inaccurate for `check` controls
- **Evidence:** the 9 `check`-sourced controls already go NOT_ASSESSED when their detector's section is empty, with the reason "it predates the … detector; scan again" (`aspects.py:274`). That is a false reason after a crash.
- **Fix:** include them in T-1.4.

#### N18 — Low: one vocabulary is not yet one
- **Evidence:** certainty "syntactic/semantic" (coverage-matrix:11-14) vs "text/parsed/semantic" (§6.2). "Set wrongly" (§11) labels every ISSUE, including end of support and a shared database, which are not settings.
- **Fix:** one certainty vocabulary, and an ISSUE label that fits all its sources (for example "Problem found").

#### N19 — Low: matrix residue
- Duplicate rows inflate the 157: Owners (A1/A22), Groovy/Scala (A2 twice), database timeouts (A8/A16).
- "Alerts, dashboards, SLOs | PARTIAL", but the control is `pending` (should be NOT_ASSESSED).
- A12 "Pipeline outside the repository (named in README) | BUILT" without the T-1.11 defect.
- Plausibly missing AS-IS items (reasoning-only): service discovery and registry (Eureka, Consul as discovery), edge or API gateway role, reactive vs servlet runtime model, native image, log shipping, local run and onboarding instructions.
- **Fix:** de-duplicate, correct the statuses, and add or explicitly exclude those items.

#### N20 — Low: D-3 has no adoption criterion
- **Evidence:** "Decide on adoption from the prototype's measured precision" on 2 repositories, with no precision target and no minimum number of candidates.
- **Fix:** state the target and n before the prototype runs (the same exact-bound logic as §7.3).

#### N21 — Low: the consistency rules recompute with the writer's own function
- **Evidence:** CON-1, CON-2 and CON-4 call `A.rollup` (`verify.py:135`), the function that produced the stored values. A rollup logic error passes. The planned client-file CON rule risks the same.
- **Fix:** an independent recomputation (a small table-driven reimplementation in verify), the same remedy as for ACC-9.

### Judgment calls (opinion, not proven defects)
- **10% at 90% for every control regardless of severity.** For high-severity controls shown in the meeting I would target 5%, and accept 10% only for medium and low severity.
- **Stratifying across 28 values at about 60 repositories is nominal.** I would concentrate the first corpus on the single stack dominant in the first client's estate and say so, rather than claim coverage of strata that hold 1-3 repositories.
- **D-10 vs §9.** §9 asserts "Business criticality changes which controls are expected (decision D-10)" while D-10 recommends deferral. I would reword §9 to "will change, after D-10".
- **The internal report's only control is a header label.** Acceptable as process, but the internal file holds everything. I would add the gate state to `summary --json` and the file name.

## (5) Open questions (evidence needed)
1. Can a consultant confirm results outside the checklist (by aspect or by application)? If not, N5 stands as written; if yes, specify how.
2. What is the unit of a corpus case: one per (control, repository), or per module or workload? Per-workload cases would change N1's arithmetic.
3. Are reference-table ISSUEs (end of support) intended to be `confirmed`? §6.2 says no; N4 assumes the text means what it says.
4. Does `evidence.redact` mask `user:token@` in `run.json.inputs` and `sources[].spec`? Not checked; ACC-9 depends on it.
5. Who writes the synthetic fixtures from disputes, and what is forbidden (identifiers, hostnames, package names)? This affects R-09.
6. Report size and render at 300 applications: still unmeasured (T-3.8).

