<!-- Independent red-team review, round 3, 2026-11-02. Reviewer: a separate agent that did not write the spec, following ~/.claude/commands/red-team-design.md. -->

# Red-team design review, round 3: `openspec/changes/asis-baseline` (revision 3)

## (1) Mode check and review boundary

**Mode.** I had the design documents and read-only access to the committed code at HEAD `9479a59`. I read every code file with `git show 9479a59:<path>`, extracted to a scratchpad, and never from the working tree. `git status` showed only `openspec/` as untracked. No mechanical spec gate exists: the OpenSpec CLI is not installed and no gate output was supplied, so I have no established check IDs to defer to. There is no rubric under `~/.claude/rubrics/`.

**What I inspected**

- **Design (all read in full):** `proposal.md`, `design.md`, `coverage-matrix.md`, `tasks.md`, and all 8 `specs/*/spec.md`.
- **Earlier reviews:** `reviews/red-team-1-response.md`, `red-team-2.md` and `red-team-2-response.md` in full. I did not re-read `red-team-1.md`; round 2's reading of it is relied on.
- **Rules:** `openspec/config.yaml` (R-01..R-20), plus `CLAUDE.md` (which is only `@AGENTS.md`) and `AGENTS.md`, both at `9479a59`.
- **Code at 9479a59:**
  - `app_insight/aspects.py` (complete), `verify.py` (complete), `cli.py:60-200`.
  - `sources.py`: `slug`, `_git`, the update path.
  - `packs/aspects.v1.json`, analysed by script: 58 controls, version 1.4.0, status DRAFT.
  - `ui/core.js:64`.
  - UI files, searched for review-status labels.
  - `engine/scripts/evidence.py`, `discover.py:48-64`, `relate.py:74-100`, and `detectors/{security,runtime,build_ci}.py` at the cited lines.
  - `git grep` for every `"ISSUE"` producer and every `"declared"` level producer.
- **Tests:** I confirmed that every test name cited in the specs exists. I did not run any test.
- **Matrix:** recounted by script. 54 BUILT, 26 PARTIAL, 67 PLANNED, 6 NOT_ASSESSED, 6 OUT; 159 items in 25 areas. **The stated counts are correct.**
- **Upstream:** `registry/features.csv` F-045..F-099 (names and acceptance text for F-055, F-070, F-079, F-089, F-097, F-099), and a grep of ledger section G for review and waiver terms.

**Not inspected:** run folders and scan outputs, browser rendering, and detectors not named above. I re-read the ledger and `docs/16-master-requirements.md` only by targeted grep. No secret value was read or printed.

**Assumed standard (unchanged from rounds 1 and 2):** the baseline governs what the product may say in a client meeting. Severity is weighed by the design's own cost table (§1): false gap, false pass, hidden gap, inconsistency, leak, wrong application.

**User decisions treated as given:**
1. D-4 (2026-11-02): results shown to a client are consultant-confirmed first; statistical validation is deferred.
2. Phase 1 starts before sign-off.

I judge consistency with them. I do not reject the design for following them.

## (2) Rule ledger

| Rule | Verdict | Evidence |
|---|---|---|
| R-01 No model decides a fact, state, severity or remedy | CONFORMS | Product verdicts stay deterministic. §7.3 no longer has a model review a model. Model-drafted labels are gated per control on a 90% lower bound ≥90% and are used only for internal measurement. Residual: labels choose which controls are must-review (§7.2 last bullet), so label quality reaches the client safeguard indirectly (F3-7). |
| R-02 Positive claims cite a line; negative claims say where they looked | CONFORMS (design); PARTIAL (code) | The evidence spec extends search records to N/A, ISSUE-by-default and PARTIAL. ACC-2 checks PRESENT only (`verify.py:109`) and ACC-10 checks only that a record exists (`verify.py:124-127`); both are PLANNED (T-1.22) and stated honestly. |
| R-03 No answer is never a verdict | VIOLATES (client file, design gap) | Disputed results are "excluded" (design §8:284; report spec:8). Nothing says how an exclusion counts in "reviewed x of y" or in aspect status, so a disputed false pass can disappear and the aspect read in place (F3-2). Design §8:286-288 and report spec:15 disagree on the aspect status of a partly reviewed aspect (F3-6). |
| R-04 Absence only inside the supported range | CONFORMS (design) with a residual | §6.3 covers every absence-derived verdict. Residual: the deploy "positive marker" list includes "an image published with no deploy step" (§6.6:197-200), which is also the signature of manual deploys (F3-11). |
| R-05 Same number or state everywhere | CONFORMS (stated exception) with a gap | The exception is stated with markers and a verify rule (§8:289-291). But `report` and `aspects` rebuild a run in place with the current catalogue (`cli.py:166-176`), so the internal side of a reviewed run can change under the client file (F3-9). |
| R-06 No combined score; ranking never improves when less is checked | VIOLATES (client file, in spirit) | The client-file default sort is confirmed ISSUE count, then high gaps, over reviewed results only. An application with nothing reviewed has zero of both and ranks as healthiest (F3-3). |
| R-07 Never print or store a secret; check by comparing values | VIOLATES (design gap) | T-1.7 and T-1.23 cover scan, rebuild and standalone verify. `app-insight review` writes `report-client.html`, the file that leaves the building, and the design does not sequence verify or the independent leak check after it (F3-8). |
| R-08 Nothing leaves; no credentials | CONFORMS (design, PLANNED) | T-1.6; open question 4 answered in the round-2 response (refusal before storing). |
| R-09 Clients isolated | CONFORMS | §8: synthetic fixtures with no client identifiers. Residual: the "backlog item" text from a dispute note has no sanitising rule (open question 3). |
| R-10 Remedies from packs, fit to stack | CONFORMS | §10; T-1.14. |
| R-11 Reference data carries its review status | CONFORMS (design); VIOLATES (code at 9479a59, acknowledged) | T-1.25 is PLANNED. `aspects.py:227,238,246` result text carries no review status. §13 now says PARTIAL, which is correct. |
| R-12 Separate perspectives | VIOLATES as worded (amendment pending) | D-9 now records the amendment and the upstream departure (design:384). T-1.13 (maturity removal, implementing D-9) is "in progress" (tasks:53) while D-9 and the R-12 amendment are undecided (F3-14). |
| R-13 Strength stated; a heuristic is a potential issue | CONFORMS with a residual | The §6.2 redefinition is sound. The ISSUE-source table omits one producer (F3-19). |
| R-14 Java semantics from JVM tools | CONFORMS | D-3 / T-5.1. |
| R-15 One vocabulary; no guide; mock first | VIOLATES (minor) | Report spec:38 still lists "Set wrongly" and lacks "Problem found" and "Not reviewed", against design §11 (F3-16). No aspect status exists for a partly reviewed aspect. The phase-1 UI edits (maturity tile, header) are not structural, so mock-first is not breached. |
| R-16 Works at 300 applications | VIOLATES (design) | There is no capacity model for review: up to 3,000 non-bulk items plus about 5,100 aspect confirmations, no time budget and no application scoping (F3-5). Report size is still open (T-3.8). |
| R-17 A tool gap is listed once | CONFORMS | Scope page; catalogue spec:110-118. |
| R-18 Regression test per detector; figures name corpus and date | CONFORMS | §7.6 restates the audit-6 figure with provenance. The disputes spec requires regression fixtures. |
| R-19 Commit only when asked | CONFORMS | `openspec/` is untracked; HEAD is unchanged. |
| R-20 BUILT cites commit and test | VIOLATES | 54 BUILT matrix rows name no test, yet tasks:53 says T-1.2 and T-1.3 are "done with the spec". The `understands` BUILT claim cites the wrong test file. Several spec BUILT rows cite no test (F3-17). |
| AGENTS 1 Ask for the client; never mix | CONFORMS | Operation spec. |
| AGENTS 2 No credentials on command line or in lists | CONFORMS (design, PLANNED) | T-1.6. |
| AGENTS 3 Read the summary; UNKNOWN and NOT_ASSESSED never a pass | CONFORMS (design, PLANNED) | T-1.1 and the operation spec. `summarise()` (`cli.py:68-89`) still lacks the verify result. The gate state in `summary --json` (design:33) has no task (F3-21). |
| AGENTS 4 No invented remedies or effort | CONFORMS | Remedies spec. |
| AGENTS 5 Never edit target repositories | CONFORMS | Operation spec. |
| AGENTS 6 Point to report.html | NOT-APPLICABLE | Agent reporting changes only in summary fields. The client file is a consultant artifact, not an agent pointer. |
| AGENTS "Rebuild the HTML only" (`report`) | VIOLATES (code, unaddressed by design) | AGENTS.md documents `report` as HTML-only. `cmd_report` calls `_rebuild`, which re-runs `A.build` with the current catalogue (`cli.py:173-175, 185-186`). It matters now that runs carry review marks (F3-9). |
| AGENTS "Changing": run both suites | CONFORMS | Phase-1 exit in tasks:59 (the browser test must not be skipped). |
| AGENTS "Changing": new control pending until a detector exists | CONFORMS | Catalogue spec; T-4.9. |
| AGENTS "Changing": no non-stdlib dependency without agreement | CONFORMS | D-3 needs agreement before a JDK and tool are used. |
| CLAUDE.md (`@AGENTS.md` only) | — | Covered by the AGENTS rows. |

## (3) Verdict: APPROVE WITH CONDITIONS, with D-7 (section 8) held back from sign-off

**What would make me refuse production sign-off today?** Signing a decision that puts a client in front of a result that is wrong, unreviewed or hidden without the file saying so. A second ground is a decision that makes phase-1 code (already in progress) introduce a systematic false verdict.

**Does any finding meet that bar?**

- **F3-1 (High) meets it, and is a one-sentence fix.** The widened "declared-only → PARTIAL" rule (evidence spec:113-116) would turn every "no literal secret found" result into a gap. That covers two high-severity controls on every application, plus "graceful by default" on Spring Boot ≥ 3.4. T-1.12 is in progress, and tasks.md still carries the narrow wording, so the engineer has two contradictory instructions.
- **F3-2 to F3-7 (three High, three Medium) meet it, all inside §8 (D-7) and the report spec's client-file requirement.** The consultant review is now the only client-facing safeguard (D-4). As written:
  - a known false pass can be removed silently through "dispute → exclude" (F3-2);
  - an unreviewed application ranks as the healthiest (F3-3);
  - nothing stops a client file being produced while must-review items are open (F3-3);
  - bulk confirmation has no control against rubber-stamping, and the client file cannot tell bulk from individual confirmation (F3-4);
  - the risk-based must-review set is empty until measurement exists, and ignores false passes (F3-7).
- **Containment is the deciding factor.** None of §8 is built. It is phase 2 (T-2.1-T-2.3), and the client-use gate cannot pass before phase 2. Every other decision whose earlier failure drove the round-2 REJECT has been fixed:
  - the statistical claims are deferred and correctly sized (N1, N2);
  - the label gate is coherent (N3);
  - the meaning of `confirmed` no longer hides real issues (N4);
  - the client file is no longer a silent subset (N5).

  Those decisions can now be signed without signing anything unwritten. The remaining blocking defects sit in one section that is not yet implemented and is behind a gate. Rejecting the whole baseline a third time would hold up D-0, D-1, D-2, D-3, D-5, D-6 and D-8-D-11 over §8 alone.

**Conditions (all required):**

1. **Before T-1.12 merges:** restrict "declared → PARTIAL" to dependency declarations (`aspects.py:294`) and INFERRED facts (`aspects.py:261`). Give negative scans and platform defaults a different level, or exempt them. Make tasks.md T-1.12 and the spec say the same thing, and add regression tests for `security.secrets_in_code`, `config.secrets_externalised` and `runtime.graceful_shutdown` on Boot ≥ 3.4 (F3-1).
2. **D-7 is not signed in phase 0.** Revise §8 and the report spec's client-file requirement for F3-2 to F3-7 and F3-10 to F3-13. A focused round-4 review of §8, the report spec and the accuracy spec's review requirements must pass **before T-2.1 or T-2.3 starts**. This is narrow and does not hold up phase 1 or the other decisions.
3. **Before the client file is built:** sequence verify and the independent leak check after `app-insight review` writes the client file (F3-8). Make reviewed runs immutable (F3-9).
4. **With the next document revision:** fix the document contradictions and status errors in F3-14 to F3-22. Most are one-line edits.

## (4) Findings

### Round-2 findings: does revision 3 resolve them?

| R2 | Status in revision 3 | Basis |
|---|---|---|
| N1 corpus cannot validate | **Resolved (by D-4).** | §7.4 restates the sizing: both classes, 22/38/52 at 10%/90%, prevalence, 100-200 repositories, 45 at 5%. These figures match round 2's recomputation. No client-facing validation remains. |
| N2 client wording | **Resolved; one spec residue.** | No client claim is made. The accuracy spec (line 76) words the bound as "at most X% of N held-out repositories", the wrong denominator (it should be truth-gap cases); design §7.2 is right. Internal only (F3-22). |
| N3 label gate | **Resolved; residual circularity.** | Per-control lower-bound gate, overlap defined, agreeing cases re-checked, no model reviewing a model. "Every case of the controls the checklist treats as high-risk" depends on measured error rates that need those labels first (F3-7). |
| N4 `confirmed` too narrow | **Resolved; table incomplete.** | §6.2 redefinition plus a table of sources. The vulnerability-scan ISSUE (`aspects.py:316-320`) is missing from the table (F3-19). |
| N5 client file a biased subset | **Partly; the replacement introduces F3-2, F3-3, F3-6.** | Every result is now visible and the census is bounded. New problems: disputes are removed; aspect status for partial review contradicts itself; ranking rewards unreviewed applications; there is no completeness gate. |
| N6 deploy UNKNOWN everywhere | **Mostly resolved.** | Design §6.6 and catalogue spec:37-42 aligned. Residual: one marker is not positive evidence (F3-11). The matrix still states the old rule (`coverage-matrix.md:192`, F3-15). |
| N7 BUILT overstatements | **Mostly resolved; new ones.** | The six listed items are corrected and confirmed in code: `aspects.py:423` (2 of 8), `verify.py:109`, `aspects.py:384`. New: the `understands` test is cited in the wrong file; the matrix BUILT rows still have no test ids; T-1.2 and T-1.3 are claimed "done" (F3-17). |
| N8 export overclaims | **Partly.** | Export is blocked (D-1, design:376), but the mapping table still maps "PRESENT at a lower level → VERIFIED_CONTROL" (evidence spec:158), contradicting D-1's "must not" (F3-18). |
| N9 gate omissions, phase mismatch | **Resolved; wrong task id.** | Gate item 3 is added. Design:38 cites "T-2.9" (the regression gate) for the client file, which is T-2.3 (F3-21). |
| N10 leak check on rebuilds | **Partly.** | T-1.23 covers rebuild and standalone verify, but not the client-file writer (F3-8). Re-running the detectors on a clone that has moved on yields different literal values (F3-9). |
| N11 marks and runs not bound to source | **Partly.** | The binding is specified (§8:292-294). But clones are shallow, `fetch --depth 1` then `reset --hard FETCH_HEAD` (`sources.py:162-164`), so "re-read at the recorded commit" will normally refuse after any rescan. Dirty local sources cannot be re-read at a commit. Runs are rebuilt in place (F3-9). The binding is too coarse to carry forward (F3-10). |
| N12 D-9 implicit | **Resolved in text; process residue.** | D-9 states the amendment and the departure. T-1.13 implements D-9 before it is decided (F3-14). |
| N13 regression gate | **Resolved.** | §7.5 and the accuracy spec:96-104. |
| N14 PARTIAL contradiction | **Resolved in design; spec residue.** | Evidence spec:32 still says any absence-derived verdict "SHALL instead be UNKNOWN", which includes PARTIAL by its own definition at :18-19 (F3-20). |
| N15 `eval_fact` declared PRESENT | **Overcorrected; new High.** | The spec widened to "any result", which catches negative scans and platform defaults (F3-1). Tasks.md T-1.12 is not widened. |
| N16 wrong-kind gaps | **Resolved.** | §7.2 and T-2.7. |
| N17 check-sourced crash reason | **Resolved (PLANNED).** | T-1.24. |
| N18 vocabulary | **Partly.** | Design fixed; the report spec is not (F3-16). |
| N19 matrix residue | **Resolved.** | Recount confirmed at 159. The duplicates are gone, alerts are NOT_ASSESSED, and the README defect is noted (A12:175). |
| N20 D-3 criterion | **Resolved; one ambiguity.** | "At least 30 candidates" does not say whether that is per rule or in total; per rule is needed for a per-rule precision bound (F3-22). |
| N21 writer's rollup in verify | **Resolved (PLANNED).** | T-1.27, not yet started. |
| J: 5% for high severity | **Resolved** | For the deferred validation (§7.4). |
| J: concentrate the corpus | **Resolved** | §7.2 and D-5. |
| J: D-10 wording | **Resolved** | §9: "After D-10 … may change". |
| J: gate state in summary and file name | **Partly** | Design:32-33 states it; T-1.19 covers only the header, and no task covers the file name or `summary --json` gate state (F3-21). |

### Evidence-backed findings

#### F3-1 — High: "any PRESENT at level declared becomes PARTIAL" turns negative scans and platform defaults into gaps on every application
- **Claim:** the widened rule makes "No literal secret found" a PARTIAL gap. That hits two high-severity controls for every application, and also turns "graceful by default since Spring Boot 3.4" into a gap.
- **Evidence:**
  - Evidence spec:113-116: "Any result that would be PRESENT at level declared … SHALL be PARTIAL at level declared".
  - At `9479a59`, PRESENT at level `declared` is produced by:
    - `detectors/security.py:142`, the negative scan for `security.secrets_in_code` and `config.secrets_externalised`, both `high`;
    - `detectors/runtime.py:324-325`, Boot ≥ 3.4 graceful default;
    - `aspects.py:261` and `:294`.
  - Tasks.md:35 still reads "Declared-only dependency → PARTIAL". The round-2 response says "T-1.12 widened to any PRESENT at level declared". T-1.12 is "in progress" (tasks:53).
- **Severity:** High. A systematic false gap on high-severity security controls in every client application is the §1 "false gap" cost at portfolio scale. It is being implemented now, against contradictory instructions.
- **Fix:**
  - Scope the rule to dependency declarations and INFERRED facts.
  - Give negative scans a level that is not `declared` (for example `configured` with "scanned N files"), and treat a platform default as its own case: keep it PRESENT with the default named, or use PARTIAL by design, but decide which.
  - Align tasks.md, the spec and the response.
  - Add three regression tests.

#### F3-2 — High: a disputed result is removed, so a consultant-identified false pass disappears from the client file
- **Claim:** dispute → exclude has no corrected outcome and no defined effect on aspect status or "reviewed x of y". A known risk can therefore vanish from the meeting.
- **Evidence:**
  - Design §8:284: "a disputed result is excluded and its note kept".
  - Report spec:8: "disputed results excluded with the count of exclusions shown". The design does not mention this count.
  - The accuracy spec scenario (:67-69) covers only a false gap.
  - Disputing a PRESENT the consultant knows is wrong (for example "Timeouts set" when one of three clients has none, the §1 false-pass example) removes the only row about that control. The aspect's status over the remaining reviewed results can then read "In place".
  - Upstream F-097 ("justified expiry and re-evaluation rather than silent suppression") and F-089 (time-boxed exceptions) describe exactly this lifecycle; neither is referenced.
- **Severity:** High. Under D-4 the consultant is the safeguard; this path converts the consultant catching a false pass into a hidden gap.
- **Fix:**
  - A disputed result stays visible as "Disputed by the consultant", with the direction (believed gap / believed in place) and a short reason category.
  - A believed gap counts as a gap ("stated by the consultant", which is a person, not a model, so R-01 holds).
  - A believed in-place result counts as not reviewed.
  - Define how disputes enter "reviewed x of y".
  - Disputes carry an expiry and are re-evaluated on the next run (F-097).

#### F3-3 — High: the client file ranks unreviewed applications as healthiest, and nothing requires the must-review set to be finished
- **Claim:** client-file counts and sort are over reviewed results only, and the gate has no completeness criterion. A partly reviewed portfolio therefore presents its least-examined applications as its best.
- **Evidence:**
  - Design §8:286-288: unreviewed results are "Not reviewed … counted like NOT_ASSESSED".
  - Report spec:29-30: default order is confirmed ISSUE count, then high gaps.
  - Gate item 2 (design:38) requires only that "a consultant reviewed it". The §8 bullets and the accuracy spec:41-46 set no requirement that every must-review item of a shown application is resolved before the client file is generated.
  - An application whose 10 must-review items were not reached shows 0 issues and 0 high gaps, and sorts last (best).
  - This is the review-time analogue of R-06's "a percentage that rises when less is checked".
- **Severity:** High. It produces the §1 "hidden gap" and "inconsistency" costs at the meeting's home screen.
- **Fix:**
  - An application enters the client file's verdict views only when its must-review set is fully resolved. Otherwise its row reads "Not yet reviewed" at application level and is excluded from the summary row and the sort.
  - Or sort by review completeness first.
  - Make "all must-review items resolved for every application shown" an explicit gate item.

#### F3-4 — High: bulk confirmation has no control against rubber-stamping, and the client file hides how a result was confirmed
- **Claim:** the design promises that "confirming an aspect means having looked at each of its results and its evidence" and gives no mechanism. The stop rule is diluted by bulk confirmations, and the per-application cap contradicts "never confirmable in bulk".
- **Evidence:**
  - §8:278-279 states the aspect-confirmation promise; the accuracy spec:41-46 records only reviewer and time.
  - §8:280-283: must-review items are "never confirmable in bulk … bounded per application to the top 10 by severity; the rest … confirmed by aspect". So the 11th and later confirmed ISSUE or high gap is bulk-confirmable.
  - The stop rule counts disputes "in any 30 consecutive reviewed results" (§8:284-285). One application-level confirmation adds about 60 undisputed results, so the rule effectively fires only inside must-review sequences.
  - Round 2 showed the rule accepts a run 41% of the time at a 10% dispute rate.
  - Design:43-44 says the client file shows "that the consultant confirmed it", with no distinction between individual and bulk confirmation.
- **Severity:** High. D-4 makes this the only client-facing safeguard, and the design gives the client file's "confirmed" mark the same weight whether it was checked or clicked through.
- **Fix:**
  - Record the confirmation mode per result (individual, aspect, application) and show it in the client file ("checked individually" vs "confirmed with its aspect").
  - Allow bulk confirmation only for PRESENT and N/A results of controls that are not must-review.
  - Run the stop rule over individually reviewed results plus a random audit sample of bulk-confirmed results, re-reviewed individually (by a second person where available).
  - Remove the cap's exception for confirmed ISSUEs, or state it explicitly as an accepted risk.

#### F3-5 — Medium: no capacity model for consultant review at 300 applications (R-16)
- **Claim:** the design asserts that review works at 300 applications without a time budget or a scoping rule.
- **Evidence:**
  - Up to 10 non-bulk items × 300 = 3,000 individual confirmations.
  - 17 aspects × 300 = 5,100 aspect screens, each requiring "having looked at each of its results and its evidence".
  - No phase-2 exit criterion measures review time. The phase-2 exit (tasks:79-80) is "review and client file working on the six repositories".
  - Nothing lets the consultant scope a client file to the applications the meeting will discuss.
- **Severity:** Medium. An infeasible review budget is the main driver of F3-4's rubber-stamping and of pressure to bypass the gate.
- **Fix:**
  - Phase-2 exit records minutes per application on the six repositories and projects to 300.
  - Let the client file be generated for a named subset of applications, with the rest listed once as "not in this review".
  - State the expected review scope for the first meeting.

#### F3-6 — Medium: the client file's treatment of unreviewed results is defined three different ways
- **Evidence:**
  - Proposal:31 says the client file has "every result visible, unreviewed ones marked", which implies the tool's state is shown with a mark.
  - Design §8:286 says unreviewed results appear "as 'Not reviewed' … counted like NOT_ASSESSED", which implies the state is replaced.
  - On aspect status, design §8:287-288 gives "its status over reviewed results plus 'reviewed x of y'" (for example "In place, reviewed 1 of 2"). Report spec:15 says the aspect "reads 'reviewed 1 of 2', never 'In place'".
  - Counting like NOT_ASSESSED through today's rollup gives "In place where checked" (`aspects.py:489-490`), a third answer.
  - The vocabulary (§11, report spec:38-40) has no aspect status for partial review.
- **Severity:** Medium. Whether unreviewed tool verdicts reach the client is the central safeguard question, and three readings exist.
- **Fix:** decide one rule. My recommendation: replace the state and never show the tool verdict unreviewed. Aspect status becomes a distinct neutral "Reviewed x of y" whenever x < y. Add it to the one vocabulary table.

#### F3-7 — Medium: the risk-based must-review selection is empty until measurement exists, circular with labelling, and ignores false passes
- **Evidence:**
  - Must-review includes "every result of a control whose measured error rate is high" (§8:281). "High" has no threshold, and no measurement exists before phase 2 completes.
  - Controls on stacks absent from the corpus, and every new control, are never "measured high", so they are not must-review.
  - §7.3:246 has a person label "every case of the controls the consultant checklist treats as high-risk". That set is defined by the measured error rates the labels produce.
  - Must-review targets gaps, confirmed issues and high-severity UNKNOWN. A high-severity PRESENT (for example below `enforced`) or an N/A-by-need on a high-severity control is never must-review, although §1 names both ("Timeouts set", "not applicable: no HTTP client") as the false-pass cost.
- **Severity:** Medium. The safeguard is weakest exactly where the tool is least known.
- **Fix:**
  - "Unmeasured, or upper bound above T%" → must-review, with T stated.
  - Seed the person-labelled set from severity (all high-severity controls) rather than from measured rates.
  - Add high-severity PRESENT below `enforced` and N/A-by-need on high-severity controls to must-review, or to a mandatory sample.

#### F3-8 — Medium: the client file, the artifact that leaves the building, is written outside every verify and leak-check path
- **Evidence:**
  - Gate item 1: "verify ran before any report was written" (design:37).
  - T-1.7 and T-1.23 cover scan, rebuild and standalone verify. `app-insight review` writes the client file later (§5 architecture, report spec:7), and no task or §13 row runs verify, ACC-9 or the literal-value check after it.
  - The R-05 client-count verify rule (§8:290-291) has no stated trigger.
  - `review.json` holds free-text consultant notes, and verify's file walk would scan it (`verify.py:154-174`) only if verify runs.
- **Severity:** Medium. The content is mostly already-redacted data, so the residual is new writer code plus free text. But the §1 "leak" row is the costliest error, and this is the file that is emailed.
- **Fix:** `review` runs verify, including the independent leak check and the client-count rule, after writing the client file, and deletes the file on failure. Add a §13 row and a task.

#### F3-9 — Medium: runs are mutable in place and clones are shallow, so "bound to what was reviewed" cannot hold as specified
- **Evidence:**
  - `report` and `aspects` both call `_rebuild`, which re-runs `A.build` with the current catalogue and overwrites the run's `aspects.json` and `report.html` (`cli.py:166-176, 185-186`). AGENTS.md documents `report` as "Rebuild the HTML only".
  - Remote sources are `fetch --depth 1` and then `reset --hard FETCH_HEAD` (`sources.py:162-164`), so after any rescan the recorded commit is not in the clone. T-1.26's "re-read at the recorded commit, or refuse" will normally refuse.
  - T-1.23's detector re-run on a rebuild runs on the newer checkout, so its "literal values" are not the run's values.
  - Local-path sources with uncommitted changes (`sources.py`, `changed_files`) cannot be re-read "at a commit" at all.
- **Severity:** Medium. A reviewed run can be silently changed under its client file, or become permanently unverifiable.
- **Fix:**
  - Treat a run with `review.json` as immutable: a rebuild writes a new run.
  - Fetch the recorded commit by SHA (`git fetch --depth 1 origin <sha>`), or keep a per-run snapshot.
  - For dirty local sources, state that verify of an older run refuses.
  - Make `report` HTML-only, or correct AGENTS.md.

#### F3-10 — Medium: the mark binding is too coarse to carry forward, and incomplete
- **Evidence:**
  - Marks bind to "catalogue version, source revision" (§8:292). Any catalogue bump, even one unrelated control, and any new commit in a repository invalidate every mark for that repository or for all 300.
  - Nothing carries confirmations across runs (re-assessment, §3).
  - The binding omits the remedy pack version (remedies are shown in the client file) and the engine or tool version (summary and search record can change at the same revision).
- **Severity:** Medium. Wholesale re-review at every rescan multiplies F3-5 and F3-4, while unbound remedy text reaches the client unreviewed.
- **Fix:**
  - Bind to a per-control definition hash (including severity), the state, the evidence content hash (or search-record hash for "Not found"), the remedy keys, and the tool version.
  - Carry a mark forward when all of these are unchanged.

#### F3-11 — Medium: one deploy "positive marker" is the signature of manual deployment
- **Evidence:** design §6.6:197-200 and catalogue spec:40-42 list "an image published with no deploy step" as showing that deployment happens elsewhere. A pipeline that builds and pushes an image while a person deploys it has exactly that shape, and it is the gap §6.6 calls the one "clients most often have".
- **Severity:** Medium. It reintroduces N6 for a common shape. It is mitigated because "every UNKNOWN that hides a high-severity control" is must-review (§8:282).
- **Fix:** drop that marker, or require a second marker (a manifest repository named, an image-updater annotation, a deploy job in a referenced repository).

#### F3-12 — Medium: "always consultant-confirmed" controls have no outcome to record
- **Evidence:**
  - Usually-outside controls are UNKNOWN "Not seen here; confirm with the team" and "always consultant-confirmed" (design §6.6:201-204; catalogue spec:38-40).
  - Review can only confirm (which confirms "unknown") or dispute (which excludes the row).
  - There is no way to record the team's answer ("Dependabot is on at organisation level", "deploys from the platform pipeline"). The asis-coverage spec already defines a "stated by the client" pattern (:36-44) that fits.
- **Severity:** Medium. The promise to confirm with the team has no data model, so these rows stay "Not seen here" or vanish.
- **Fix:** add a "stated by the team" outcome in `review.json`, with who stated it and when, shown as such. It is never a tool verdict, so R-01 holds.

#### F3-13 — Medium: an all-or-nothing verify blocks the whole portfolio's client file
- **Evidence:**
  - §13:399: "Verify fails | No client file".
  - Detector failure is already handled per application ("the client file is not produced for that application", design:182).
  - At 300 applications, one ACC-1 drift in one repository blocks the meeting for all 300, which creates pressure to bypass the gate.
- **Fix:**
  - Per-application verify outcome: failing applications are listed in the client file as "not available: verification failed" and kept out of every count.
  - Run-level rules (ACC-9 leak, CON-4 and CON-6 for portfolio artifacts) stay run-blocking.

#### F3-14 — Low: phase 1 implements undecided decisions; the task list contradicts the user decision
- **Evidence:**
  - Tasks.md:3 reads "Nothing here starts before sign-off"; tasks:53 reads "T-1.1 to T-1.20 … in progress".
  - T-1.13 implements D-9 and T-1.19 implements D-0, both undecided (T-0.4). Meanwhile R-12 is "amended only if D-9 is approved".
  - This follows the user's decision, and the changes are reversible.
- **Fix:** reword tasks:3 to "Phase 2 onwards starts after sign-off". Note that T-1.13 is reverted if D-9 is rejected.

#### F3-15 — Low: D-4 and N6 not carried into the coverage matrix
- **Evidence:**
  - `coverage-matrix.md:21-22`: whether a result may be shown to a client "is decided only by the measurement in design.md section 7". This contradicts D-4.
  - `:192`: deploy "becomes UNKNOWN via `usually_outside`", the rule N6 replaced.
  - `:24`: "corrected after red-team review 1".
- **Fix:** three one-line edits.

#### F3-16 — Low: vocabulary still not one
- **Evidence:** report spec:38-40 still lists "Set wrongly", omits "Problem found" and "Not reviewed", and has no partial-review aspect status. Design §11 is updated; the response to N18 says "replaced".
- **Fix:** sync the report spec to design §11, plus F3-6's status.

#### F3-17 — Low: R-20 residue
- **Evidence:**
  - Tasks:53 says T-1.2 and T-1.3 are "done with the spec", but both are unchecked. No recount script exists, and none of the 54 BUILT matrix rows names a test.
  - Catalogue spec:56 cites `engine/tests/test_accuracy.py` for `understands`. The test is `tests/test_aspects.py:114-119` (`test_a_spring_only_check_says_not_recognised_for_another_framework`).
  - These spec BUILT rows cite no test:
    - "Deterministic", although `engine/tests/test_discovery.py:840` `test_determinism` exists;
    - ACC-5;
    - `graph/resolve.py`;
    - "No effort".
- **Fix:** correct the claim in tasks:53, cite the right test files, and complete T-1.3 or mark those rows "BUILT, test PLANNED".

#### F3-18 — Low: the export mapping row contradicts D-1
- **Evidence:** evidence spec:158 maps "PRESENT at a lower level → VERIFIED_CONTROL, with `level`". D-1 (design:376) says below-verified PRESENT "must not export as VERIFIED_CONTROL". Export is blocked, but the row is what will ship once the block lifts.
- **Fix:** map it to POTENTIAL_ISSUE or INSUFFICIENT_EVIDENCE, or mark the row "only once the upstream `level` exists and is mandatory".

#### F3-19 — Low: the ISSUE-source table is not complete
- **Evidence:** `eval_security_scan` returns ISSUE on a "concern" vulnerability scan (`aspects.py:316-320`, `security.exposure_known`). That source is missing from §6.2:137-147, which the round-2 response presents as "every current ISSUE source".
- **Fix:** add the row (confirmed: yes, at certainty of the tool).

#### F3-20 — Low: the evidence spec contradicts itself on PARTIAL
- **Evidence:** evidence spec:32 says a verdict derived from not finding something "SHALL instead be UNKNOWN". :18-19 includes "a PARTIAL that rests on a missing part" in that class, while :38-39 and design §6.3 keep PARTIAL with a note.
- **Fix:** restrict :32 to ABSENT, N/A by need and ISSUE by default.

#### F3-21 — Low: cross-references and task gaps
- **Evidence:**
  - Design:38 cites "T-2.9" for the client file, but it is T-2.3.
  - The gate state in `summary --json` and "internal" in the file name (design:32-33) have no task.
  - The design §14 phase-1 content and exit (:412) differ from tasks:16-59: T-1.11, T-1.14-T-1.18 and T-1.22-T-1.27 are not listed, and the browser-test condition is missing.
  - Design:182 ("client file not produced for that application") conflicts with §8:288 ("Nothing is left out") unless the application is listed as excluded.
- **Fix:** edit the references, add the two task items, and list excluded applications in the client file.

#### F3-22 — Low: statistics wording residue and ambiguity
- **Evidence:**
  - Accuracy spec:76 reads "at most X% of N held-out repositories". The bound is over truth-gap cases, not over repositories. The design's §7.2 wording is correct.
  - D-3's "at least 30 candidate findings" does not say whether that is per rule or in total. At n=30 a 70% lower bound needs about 25 of 30 correct, so the count must be per rule.
  - "Top 10 by severity" has no tie-break, so the must-review set is not deterministic when many results share a severity.
- **Fix:** reword the spec sentence, make 30 per rule, and add a tie-break (severity, then control order, then id).

### Judgment calls (opinion, not proven defects)

- **Confirmed ISSUE on unreviewed reference data.** §6.2 makes an end-of-support result a red "Problem found" while the lifecycle data is "unreviewed". The gate accepts a label instead of a review. The table is small; I would require it reviewed before the gate (D-6 scope), not just labelled.
- **Scope of the first client meeting under D-4.** Given F3-5, I would recommend the first client file cover a fully reviewed subset of applications the client names (tens, not 300), with the rest listed once. This is consistent with D-4 and does not oppose it.
- **Consultant review as the sole safeguard.** D-4 is a user decision and I do not reject the design for it. The design has one reviewer checking their own work with no independent sample. A second-person audit of a small random sample of bulk confirmations (F3-4) is the cheapest independent check available until statistical validation exists.
- **"In place where checked" in the client file.** Even if F3-6 is resolved otherwise, I would not use a positive colour for any aspect that holds unreviewed results.
- **Phase 1 before sign-off.** This is a user decision, followed consistently, except tasks:3 (F3-14) and the T-1.12 spec conflict (F3-1).

## (5) Open questions (evidence needed)

1. Do the runtime detectors read profile-specific configuration (`application-local.yml`, `application-test.yml`)? If so, "Timeout disabled" from a dev profile is a confirmed high-severity ISSUE. The evidence that would decide it is the `cfg` source list in `detectors/runtime.py` and a fixture.
2. Does `shared_database` (`aspects.py:345-358`, `identity == "connection"`) treat two applications pointing at a default `localhost` URL as sharing a database? That would be a confirmed false ISSUE. It needs a fixture.
3. Where does the "backlog item" from a dispute live, and who may read it? Its text is a derivative of client code (R-09).
4. What time per application does review take on the six repositories? (F3-5)
5. Is the client file a snapshot that, once sent, is never regenerated from a later run? Or can marks carry forward into a new client file (F3-10)?
6. What is the report size and render time at 300 applications (T-3.8)? The client file adds a second file of similar size.

