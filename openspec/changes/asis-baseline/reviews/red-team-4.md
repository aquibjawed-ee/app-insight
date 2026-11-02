<!-- Independent red-team review, round 4 (focused on D-7), 2026-11-02. Reviewer: a separate agent that did not write the spec, following ~/.claude/commands/red-team-design.md. -->

# Red-team design review, round 4: D-7 consultant review (`openspec/changes/asis-baseline`, design section 8)

## (1) Mode check and review boundary

**Mode.** I had the design documents and read-only access to the committed code at HEAD `9479a59` (read only with `git show 9479a59:<path>`; the working tree is being changed by another engineer and was not used). No mechanical spec gate exists (the OpenSpec CLI is not installed; no gate output supplied), so there are no established check ids to defer to. No rubric under `~/.claude/rubrics/`. No run folders exist on this machine (`~/app-insight-workspaces/` is absent), so no state distribution of real results was available. Nothing was run, scanned, cloned or fetched; no secret value was read or printed.

**Inspected**
- `design.md` in full, with section 8 (lines 278-374) and the parts it depends on: §2 (30-48), §6.1-6.4 and 6.6 (111-207), §7.2-7.3 (230-255), §11 (418-450), §12 (452-470), §13 (472-488).
- `specs/accuracy-assurance/spec.md` in full (in-scope requirements at lines 40-124).
- `specs/report-experience/spec.md` in full (client file at 5-23, vocabulary at 45-52).
- `tasks.md` in full (T-2.1 to T-2.3a at 74-83; phase-2 condition at 69-72).
- `proposal.md:22-36`, plus a grep of the other specs and `coverage-matrix.md` for client-file and "stated" wording.
- `openspec/config.yaml` (R-01..R-20, R-12 as amended by D-9).
- `reviews/red-team-3.md` and `reviews/red-team-3-response.md` in full.
- Code at `9479a59`:
  - `app_insight/aspects.py`: `rollup` (472-494), `build_app` (497-519), lifecycle evaluators (227-251).
  - `app_insight/cli.py`: scan tail, `_rebuild`, `cmd_report`, `cmd_verify`.
  - `app_insight/sources.py:149-186` (fetch).
  - `app_insight/verify.py`: the rule list and rule sites.
  - `app_insight/packs/aspects.v1.json`, analysed by script: 58 controls, of which 15 high, 34 medium, 8 low, 1 info, and 0 critical.
  - `AGENTS.md`.

**Not inspected:** the other five specs beyond the grep, `coverage-matrix.md` beyond the grep, UI code, and engine detectors. Section 8 is not built. Every statement about its behaviour is therefore about intended behaviour, and no "built" claim in it needs verifying (it makes none).

**Assumed standard:** unchanged from rounds 1-3. The baseline governs what may be said in a client meeting, weighed by the design's own cost table (§1). Under D-4, section 8 is the only client-facing safeguard. So any path by which the client file shows a known-wrong result as confirmed, or shows an unreviewed tool verdict, is judged at the "false pass / hidden gap in front of the client" cost.

## (2) Rule ledger

| Rule | Verdict | Evidence |
|---|---|---|
| R-01 No model decides a fact, state, severity or remedy | CONFORMS | Every §8 outcome is recorded by a person (8.4: "None of these is a tool verdict … a person decides"). The must-review set is chosen by state and severity, not by model labels or measured rates (§7.2:244-246, 8.2). The audit sample is random, not judged. Fixtures are written by an engineer. No model appears anywhere in §8. |
| R-02 Positive claims cite a line; negative claims say where they looked | CONFORMS with a residual | Tool results keep their evidence and search records. Residual: "Gap, stated by the consultant" and "Stated by the team" carry a free-text note or answer, with no field for file and line or for "outside the repository" (8.4 table). These are person claims, so this is not a tool violation, but the client sees them beside cited results (F4-15). |
| R-03 No answer is never a verdict | CONFORMS with a residual | Unreviewed results show "Not reviewed", never the tool verdict (8.6:342). "Believed not a gap" counts as not reviewed, "never a pass" (8.4:319). Residual: "y" in "Reviewed x of y" is undefined, so it is unclear whether UNKNOWN, NOT_ASSESSED and pending controls are counted (F4-5). |
| R-04 Absence only inside the supported range | NOT-APPLICABLE | §8 adds no absence-derived verdict; it consumes the states §6.3 produces. |
| R-05 Same number or state everywhere | VIOLATES (design gap) | The client file is defined only per application and aspect (8.6). Derived views that the internal report holds (dimensions per D-9, portfolio aggregates, global Findings, the remedy roadmap) have no rule for whether they are recomputed from review outcomes. A dimension headline from tool states would disagree with the reviewed aspect cells beside it (F4-2). The client-count verify rule (8.6:350-351) covers counts only. |
| R-06 No combined score; ranking never improves when less is checked | CONFORMS with a residual | Apps with unresolved must-review items are out of the sort (8.6:339-341, 348). Residual: "fully reviewed" (8.6:348) and "every must-review item resolved" (8.6:339) are different sets. An application whose gaps are all "Disputed" ranks with zero gaps (F4-8). |
| R-07 Never print, copy or store a secret | CONFORMS with residuals | 8.8 verifies the client file and `review.json` and deletes the file on failure; notes are redacted at write. Residuals: (a) the leak check re-derives literals "at the recorded commit", which needs a checkout of that commit (F4-9); (b) the evidence content hash (8.7) is not said to be computed over redacted text, so a hash of a raw secret line would be stored (F4-14). |
| R-08 Nothing leaves; no credentials | CONFORMS with a residual | Fetch-by-SHA uses the user's git setup. Residual: it makes verify, and therefore client-file production, need the network. That contradicts the project context ("offline once repositories are on disk", config.yaml:11) (F4-9). |
| R-09 Clients isolated | CONFORMS with a residual | The backlog item is stored in the client workspace only, and fixtures are synthetic (8.4:327-328; accuracy spec:115-124). This answers round-3 open question 3. Residual: "no client names, hostnames, package names…" is asserted, with no mechanical check (F4-16). |
| R-10 Remedies from packs, fit to stack | CONFORMS (rule) | Remedies still come from packs. But remedies are shown in the client file without review: the "Confirmed" outcome covers "the result and its evidence", not the remedy (F4-2). |
| R-11 Reference data carries its review status | CONFORMS | 8.9 requires the table to be reviewed by a person before first client use, and makes end-of-support results must-review. §2 gate item 3 is not yet updated; 8.9 says it will be, if D-7 is approved. |
| R-12 Separate perspectives (amended by D-9) | NOT-APPLICABLE, with an evidence gap | §8 operates on assessment results. Whether the client file carries the AS-IS and portfolio perspectives at all is not stated (F4-2). |
| R-13 Every claim carries its strength | CONFORMS with a residual | Confirmation mode is shown (8.3). Person-stated outcomes are "marked as stated" but have no place in the level vocabulary. A team-stated result counts as "the stated state", including a pass (F4-15). |
| R-14 Java semantics from JVM tools | NOT-APPLICABLE | No analysis in §8. |
| R-15 One vocabulary; no guide; mock first | VIOLATES (minor) | Label strings differ across documents (F4-13): "Gap, stated by the consultant" (design 8.4, accuracy spec:71) against "Gap stated by the consultant" (design §11:430, report spec:47); "Not available: verification failed" against "Not available" (report spec:48); "Stated by the team" against the existing "stated by the client" (asis-coverage spec:37). `proposal.md:29` still says "every result visible, unreviewed ones marked". The client file is in mock v3 (T-3.1). |
| R-16 Works at 300 applications | CONFORMS (by scope) with a residual | 8.1 bounds a review to a named set ("tens"). Residual: must-review is uncapped per application, and there is no acceptance threshold for the measured minutes (F4-11). |
| R-17 A tool gap is listed once | Evidence gap | If "y" in "Reviewed x of y" counts pending (no-detector) controls, every aspect with one reads "Reviewed x of y" per application, permanently. `rollup` excludes pending from `applicable` (`aspects.py:476`), but §8 does not say which population it uses (F4-5). |
| R-18 Regression test per detector; figures name corpus and date | CONFORMS | Disputes become fixtures with a regression test (accuracy spec:115-118). The stop-rule figure cites review 2. |
| R-19 Commit only when asked | NOT-APPLICABLE | §8 writes `review.json` and client files in the client workspace, not commits. This review edited nothing. |
| R-20 BUILT cites commit and test | CONFORMS (in scope) | Every in-scope requirement is PLANNED. One residue: "practice BUILT (`engine/tests/test_accuracy.py`…)" (accuracy spec:119) cites a file but no commit. |

## (3) Verdict: APPROVE WITH CONDITIONS (D-7 may be signed once conditions C1-C5 are in the text; T-2.1 and T-2.3 must not start before)

**What would make me refuse production sign-off today?** Signing a review design under which:
- a client file can present a result the consultant has already found wrong as "confirmed", or
- a client file can carry a tool verdict nobody reviewed, or
- the cheapest way to finish a review in time for the meeting is to confirm everything.

Under D-4 there is no second line of defence.

**Does any finding meet that bar?** Four do, each with a textual anchor:

- **F4-1 (High).** A consultant-stated gap expires at the next run. The result then re-enters as an ordinary PRESENT, and a non-high PRESENT is bulk-confirmable. The known false pass can come back as "confirmed with its aspect".
- **F4-2 (High).** §8 defines the client file only per application and aspect. Remedies, dimensions, portfolio aggregates, global Findings and the roadmap have no rule. The marker "differs from the internal report only by review outcomes" implies they are carried over as computed by the tool.
- **F4-3 (High).** The outcome set has no "cannot confirm" and no "gap, but of a different kind or on different evidence". Combined with all-or-nothing application gating, the only way to get an application into the client file is to pick an outcome that may be false, usually "Confirmed".
- **F4-4 (High).** The stop rule halts the run when the consultant finds errors and has an undefined exit: "until the cause is found" (design) against "re-run or the cause is recorded" (spec). It penalises honest disputes and rewards confirming.

**Why not REJECT.** Containment is the deciding factor, as in round 3:
- Nothing in §8 is built.
- T-2.1 and T-2.3 are gated on this review (tasks:69-72), and the client-use gate cannot pass before phase 2.
- Every blocking finding has a bounded textual fix. None needs a redesign: section 8's structure (named scope, uncapped must-review, limited bulk with mode shown, unreviewed never shown, per-application verify, immutable runs, client file verified after writing) now answers most of round 3.
- The remaining defects are in edge paths: expiry, derived views, outcome completeness and the stop-rule exit.

**Conditions (all required before the user signs D-7; a reviewer checks the diff of these edits, not a full round 5):**
- **C1 (F4-1):** add to 8.2 "every result that carried a dispute or a team statement in an earlier review of the same application", re-presented with the prior outcome and note.
- **C2 (F4-2):** add to 8.6 a whitelist of what the client file contains, with every derived view either recomputed from review outcomes or omitted. Remedies are either part of the confirmation or labelled "suggested, not reviewed".
- **C3 (F4-3):** add two outcomes, "Corrected by the consultant: <state>" and "Cannot confirm". A "Cannot confirm" result shows nothing of the tool's verdict, resolves the item for application gating, and counts in neither direction.
- **C4 (F4-4):** define what firing the stop rule does and how it is cleared, deterministically, in both design and spec. Count only reason categories that indicate a tool error.
- **C5 (F4-5, F4-6):** make known gaps take precedence over "Reviewed x of y" at the aspect cell, and define "y". Remove the global catalogue version, tool version and source revision from the mark binding, which contradicts the spec's own scenario, and replace them with per-control and per-scope hashes.

The Medium and Low findings (F4-7 to F4-17) should be fixed in the same revision. They do not block signing on their own.

## (4) Findings

### Round-3 items: does revised section 8 resolve them?

| Item | Status | Basis |
|---|---|---|
| F3-2 dispute removes a false pass | **Resolved for the first review; reopened at expiry (F4-1).** | 8.4 adds "Gap, stated by the consultant" (counted as a gap) and "Disputed by the consultant" (counted as not reviewed), with a fixed reason list and expiry. The re-presentation path is undefined, and an expired stated gap becomes bulk-confirmable. |
| F3-3 unreviewed applications rank healthiest; no completeness gate | **Resolved, with residuals (F4-8).** | 8.6:339-341 and 348; §2 gate item 2 now has the completeness criterion. Residuals: no count of excluded applications in the summary row; "fully reviewed" against "must-review resolved". |
| F3-4 bulk rubber-stamping; mode hidden | **Partly (F4-7).** | Mode is recorded and shown (8.3). Bulk is limited to non-must-review PRESENT and N/A, and the cap exception is gone (8.2 "There is no cap"). An audit sample exists. But an audit disagreement replaces only that one item, the sample's seed and redraw are unconstrained, and whether a second person did the audit is not recorded. |
| F3-5 no capacity model | **Partly (F4-11).** | Named scope and a minutes measurement (8.1). There is no acceptance threshold, and "minutes per application" is not measurable under a cross-application review order. |
| F3-6 three rules for unreviewed results | **Resolved in design; residue elsewhere.** | 8.6:342-345 has one rule: never show the unreviewed verdict, and show a neutral "Reviewed x of y". Residues: `proposal.md:29` still reads "every result visible, unreviewed ones marked" (F4-13), and the precedence of the neutral status over known gaps is new (F4-5). |
| F3-7 must-review depends on measurement; ignores false passes | **Resolved, with residual (F4-12).** | 8.2 items 1-4 are seeded by state and severity, and include high PRESENT below enforced and need-based N/A (§7.2:244-246). Residual: "severity" (result or control) is undefined. |
| F3-8 client file outside verify and the leak check | **Resolved (design), with residuals (F4-9, F4-10).** | 8.8: temporary name, verify, leak check over the client file and `review.json`, delete on failure. The checkout needed for literal re-derivation is unspecified. |
| F3-9 mutable runs, shallow clones | **Partly (F4-9).** | Immutable reviewed runs (8.7:359; T-1.29). Fetch-by-SHA adds a network dependency and needs server support that is not verified. It also needs a working tree at an old commit inside the shared clone. |
| F3-10 binding too coarse | **Not resolved (F4-6).** | The finer terms were added, but catalogue version, tool version and source revision were kept. Any of these invalidates every mark, which contradicts the accuracy spec's scenario at :101-103. |
| F3-11 deploy marker | **Resolved.** | §6.6:200-203 and catalogue spec:40-42 drop the marker. |
| F3-12 no outcome for consultant-confirmed controls | **Resolved, with residual (F4-15).** | "Stated by the team" with who and when (8.4). The spec does not restrict it to undecided results as the design does, and a team-stated pass counts toward "In place". |
| F3-13 all-or-nothing verify | **Partly (F4-10).** | Per-application "Not available: verification failed" (8.6:346-347). Which rules are per-application is undefined. §13:482 and accuracy spec:11 still say a failed verify means no client file. Detector-failed applications still vanish (§6.4:185-186). |
| F3-22 tie-break | **Resolved.** | 8.2:301 gives a total order (severity, aspect, control, application id). It is moot for the cap, which is gone. |
| J: reference data reviewed before the gate | **Resolved.** | 8.9 and T-2.3a. §2 item 3 is to be amended on D-7 approval. |
| J: named subset for the first meeting | **Resolved.** | 8.1. |
| J: second-person audit | **Partly.** | "to a second person where one is available" (8.3:310). Not recorded, and not shown (F4-7). |
| J: no positive colour with unreviewed results | **Resolved, over-applied.** | 8.6:343 also turns aspects that hold known gaps neutral (F4-5). |

### Evidence-backed findings

#### F4-1: High. An expired consultant-stated gap returns as a bulk-confirmable pass
- **Claim:** after expiry, a result the consultant stated to be a gap (tool: PRESENT) can be confirmed "with its aspect" in the next review, so the known false pass reaches the client as confirmed.
- **Evidence:**
  - 8.4:323-324: a dispute "carries an expiry (the next run, or 90 days) and is presented again for re-evaluation". Where and how it is presented is not said.
  - 8.3:305 makes bulk confirmation available for "PRESENT and NOT_APPLICABLE results not covered by 8.2".
  - 8.2 items 1-4 do not include previously disputed results. A medium-severity PRESENT, or a high one at level enforced, is therefore bulk-confirmable.
  - Accuracy spec:73-74 says the same, with no presentation rule.
  - The re-presentation is also not required to show the earlier outcome and note, so a different reviewer sees only the tool's PRESENT.
- **Severity:** High. This is the §1 "false pass … signed off in front of the client", for a defect the process had already caught. It is the exact lifecycle F-097 warns about ("re-evaluation rather than silent suppression").
- **Fix:** add 8.2 item 5, "every result that carried a dispute or team statement in an earlier review of the same application and control". It is re-presented individually, with the prior outcome, note, reviewer and date. Add a scenario.

#### F4-2: High. Everything in the client file outside per-application aspect results is undefined, so unreviewed tool output reaches the client
- **Claim:** §8 governs only per-application results and aspect cells. Remedies, dimensions, portfolio aggregates and relationships, global Findings, the remedy roadmap, AS-IS facts and the Scope page have no client-file rule. The marker rule implies the client file is the internal report with outcomes applied.
- **Evidence:**
  - 8.6:350-351: "the client file differs from the internal report only by review outcomes".
  - "Confirmed" covers "the result and its evidence" (8.4:317), not the remedy. Yet the remedy is part of the mark binding (8.7:356, "the remedies shown"), so it is bound but never reviewed.
  - §15 records weak-fit remedies from audit 6.
  - Dimensions are "derived from aspect controls" (§4:74-76, D-9). If recomputed from tool states, they contradict the reviewed aspect cells (R-05). If recomputed from outcomes, nothing says how "Not reviewed" counts in them.
  - The planning view ranks "remedies … by how many gaps and applications they address" (§3:57). The design does not say whether that ranking uses reviewed gaps.
- **Severity:** High. This is the direct form of "a tool verdict nobody reviewed" in the one artifact D-4 says is consultant-confirmed. A remedy that does not fit the client's stack, shown in the meeting, is the §1 "false gap" cost.
- **Fix:** state a whitelist in 8.6:
  - per-application results and aspects per 8.6;
  - remedies either confirmed with the result ("result, evidence and remedy right") or labelled "suggested, not reviewed";
  - every count, dimension, Findings page and roadmap recomputed from review outcomes only (unreviewed results contribute nothing), or omitted;
  - AS-IS facts either omitted or labelled "read by the tool, not reviewed". This needs a user decision on whether D-4 covers facts.

  Extend the client-count verify rule to every derived number shown.

#### F4-3: High. The outcome set cannot express "wrong, but I don't know the truth" or "gap, but not this one", which pushes the reviewer to confirm
- **Claim:** for several common review situations no correct outcome exists. Because an application shows nothing until every must-review item is resolved, the reviewer must either pick a wrong outcome or drop the application from the meeting.
- **Evidence:**
  - 8.4:315-320 offers four outcomes. "Confirmed" requires "the result and its evidence are right". "Believed a gap" applies when "the tool shows in place or undecided". "Believed not a gap" applies when "the tool shows a gap". "Stated by the team" applies to undecided results only.
  - Situations with no outcome:
    - (a) the tool says "Not found", and it is in fact "Partly in place" (the wrong-gap-kind error §7.2:236 measures);
    - (b) the state is right but the evidence is a test copy (one of the dispute reason categories, 8.4:322);
    - (c) a high PRESENT below enforced (must-review item 4) whose truth the consultant cannot establish before the meeting;
    - (d) a confirmed ISSUE whose severity the consultant believes is wrong.
  - 8.6:339-341: any unresolved must-review item makes the whole application "Not yet reviewed".
- **Severity:** High. "Confirmed" is the only outcome that always applies, so the design's own gating turns uncertainty into rubber-stamping. The client file then shows "checked individually" on a result the reviewer did not believe.
- **Fix:** add two outcomes, each with a scenario:
  - "Corrected by the consultant: <state>". The reviewer picks from the seven states, a reason category is required, and the result is shown and counted as stated by the consultant.
  - "Cannot confirm". The result is shown as "Not reviewed: could not be confirmed", it resolves the item for application gating, and it counts as neither pass nor gap.

  This removes the incentive without ever showing an unreviewed verdict.

#### F4-4: High. The stop rule halts the run when the consultant finds errors, with an undefined and inconsistent exit
- **Claim:** the tripwire's only effect is to block the client file, and its release condition is undefined. An honest reviewer who finds a systematic tool error loses the meeting; a reviewer who confirms does not.
- **Evidence:**
  - 8.5:332-333: "stops the run from being used with the client until the cause is found". Accuracy spec:92: "until it is re-run or the cause is recorded". These are two different exits.
    - "Recorded" is unconstrained free text.
    - "Re-run" re-creates identical results. Disputes expire at the next run (8.4:323), so a re-run clears the evidence that fired the rule.
  - The review order is "severity, aspect, control, application id" (8.2:301), so one control's results across applications are consecutive. One systematic case trips the rule on a review of any size: for example, a platform pipeline deploying every application, which is disputed with the reason "set outside the repository", a client fact rather than a tool error.
  - The rule counts all disputes, including reason categories that are not tool errors.
- **Severity:** High. The safeguard creates the pressure it exists to detect. Its release path is either arbitrary (any recorded text) or destroys evidence (a re-run).
- **Fix:**
  - Count only tool-error reason categories ("tool missed it", "evidence is a test or a copy", "wrong application").
  - When the rule fires, define a deterministic escalation instead of a block: every result of the implicated controls becomes must-review for all applications in scope, including those already bulk-confirmed, and the audit sample for the run rises to 25%.
  - Block the client file only while that escalation is incomplete.
  - Make design and spec say the same thing, and add a scenario for clearing.

#### F4-5: Medium. "Reviewed x of y" overrides known gaps at the aspect cell, never clears after a dispute, and "y" is undefined
- **Claim:** the neutral status replaces every computed status, not just positive ones, so an aspect holding a confirmed "Problem found" reads neutral on the home table. A "believed not a gap" dispute keeps its aspect neutral permanently.
- **Evidence:**
  - 8.6:343-345: "An aspect with any unreviewed result shows the neutral status 'Reviewed x of y'". Gaps are all must-review, so an application that shows verdicts can still hold confirmed gaps beside unreviewed bulk-confirmable passes. The report spec's scenario at :20-23 shows exactly this mix but asserts only the neutral status.
  - 8.4:319: a dispute "counts as not reviewed", so x < y forever for that aspect.
  - "y" is not defined in relation to:
    - NOT_APPLICABLE;
    - NOT_ASSESSED, which nobody can meaningfully confirm;
    - pending controls (R-17), which `rollup` excludes (`aspects.py:476`);
    - medium-severity UNKNOWN, which is neither must-review nor bulk-confirmable (8.3:305).
- **Severity:** Medium. A hidden gap at aspect level on the meeting's home screen. The results themselves remain visible one click down.
- **Fix:**
  - Precedence: High gaps > Gaps > "Reviewed x of y" > positive statuses. The neutral status replaces only In place and In place where checked.
  - Count a resolved dispute as reviewed for x.
  - Define y as the aspect's results excluding pending and NOT_ASSESSED.
  - Add scenarios.

#### F4-6: Medium. The mark binding still invalidates everything on any catalogue, engine or commit change (contradicting its own scenario), and dropping those terms would make negative results unsafe to carry
- **Claim:** "tool and catalogue versions, and the source revision" are global per run and per repository, so carry-forward never happens in practice. The obvious repair, dropping them, would carry forward "Not found" confirmations after the searched files changed.
- **Evidence:**
  - 8.7:355-358 and accuracy spec:95-98 bind to "tool and catalogue versions, and source revision".
  - The catalogue has one version for all 58 controls (`aspects.v1.json` "version"; `aspects.py:519` records `catalogue.version`).
  - Accuracy spec:101-103: when "only the coverage-gate control's definition changes … marks on every other control carry forward". The catalogue version changes with it, so this scenario fails under the stated binding.
  - Any commit to an active repository changes the source revision.
  - A search-record hash (8.7:356) covers where and what was searched, not the content of those files. Without the revision term, a confirmed ABSENT would carry forward after the team added the thing in a form the detector misses.
- **Severity:** Medium. Wholesale re-review at every rescan multiplies workload, which is the main driver of F4-3 and F4-4. A naive fix creates a carried-forward false gap.
- **Fix:**
  - Replace the global terms with: the per-control definition hash; the version of the detector(s) feeding the control; for positive results, the evidence content hash; for negative and undecided results, a content hash of the files in the control's search scope.
  - Show carried-forward marks as "confirmed <date>, carried forward from run <id>", not as a fresh "checked individually" (8.3:306-307).
  - Fix the scenario and add one for a search-scope change.

#### F4-7: Medium. The audit sample cannot change anything beyond the one sampled item, and is unconstrained
- **Claim:** an audit disagreement on bulk confirmations leaves the other bulk confirmations "confirmed". The sample can be redrawn, and whether a second person audited is not recorded.
- **Evidence:**
  - 8.3:309-311: a 10% sample (at least 5), "to a second person where one is available", with a disagreement counted for the stop rule.
  - Accuracy spec:66-68: its "outcome replaces the bulk confirmation", only that one.
  - With 1 disagreement in 5, about 20% of that bulk population is wrong, and the rest still ship as "confirmed with its aspect".
  - In the stop rule's 30-result window (F4-4), audit items are diluted among must-review items.
  - Carried-forward bulk marks (8.7) are never in a new sample.
- **Severity:** Medium. The bulk population is the lower-risk one (non-must-review PRESENT and N/A), but the audit is the only independent check D-4 leaves.
- **Fix:**
  - Any audit disagreement reverts every bulk confirmation of that aspect and application to "Not reviewed" and doubles the sample.
  - Draw the sample once, with a recorded seed, and never redraw it.
  - Record the auditor and show "audited by a second person: yes/no" in the client file's review statement.
  - Include carried-forward bulk marks in the sampling frame.

#### F4-8: Medium. Excluded applications vanish from the summary without a count, and "fully reviewed" is undefined
- **Claim:** an application in scope with a confirmed critical ISSUE and one unresolved low gap shows "Not yet reviewed" and contributes nothing to the summary row. The portfolio totals then understate known, reviewed risk with no indication.
- **Evidence:**
  - 8.6:339-341: excluded "from the summary row, the counts and the sort". There is no requirement that the summary row states how many applications are excluded and why.
  - 8.6:348: "Ranking uses only fully reviewed applications". This is a different set from "every must-review item resolved" (an application with unconfirmed bulk-confirmable passes is the latter, not the former).
  - An application whose gaps are all "Disputed: believed not a gap" has zero gaps and enters the sort as healthiest.
- **Severity:** Medium. A hidden gap at portfolio level, labelled per row but not in the totals.
- **Fix:**
  - The summary row always reads "n of m applications in scope shown; k not yet reviewed, j not available".
  - Define ranking eligibility as "every must-review item resolved".
  - Sort disputed-only applications after those with confirmed results, or show "disputes: n" in the sort columns.
  - Add scenarios.

#### F4-9: Medium. Fetch-by-SHA makes verify online, depends on unverified server support, and needs a working tree the design does not provide
- **Claim:** 8.7:360-361 and 8.8:366 assume the old commit can be fetched and its files re-read, and that the secret detectors can be re-run on them. None of that is specified for an offline, shared, shallow clone.
- **Evidence:**
  - At `9479a59`, clones use `fetch --depth 1 origin <branch>` and then `reset --hard FETCH_HEAD` (`sources.py:163-165`). Workspace clones are shared per slug (AGENTS.md "repos/<slug>/").
  - Fetching an arbitrary SHA needs the server to allow it (plausible on GitHub and GitLab, not verified for others). It fails after a force-push and garbage collection, and needs the network. The project context says "offline once repositories are on disk" (config.yaml:11).
  - The literal-value leak check re-runs detectors that read a working tree, which means checking out the old commit in the shared clone that a concurrent scan may be using.
- **Severity:** Medium. The client file could not be produced offline or after a history rewrite (a safe failure, but on meeting day). A checkout in the shared clone risks a scan reading the wrong commit, which is the §1 wrong-application-content cost (plausible, not verified).
- **Fix:**
  - At scan time, pin each run's commit locally with a ref (`refs/app-insight/runs/<stamp>`) so the object stays in the shallow clone and no fetch is needed.
  - Re-read with `git show <sha>:<path>`, and run detectors over a temporary export of the search-scope files, never by checking out the shared clone.
  - Keep "refuses" for dirty local sources, and state that such runs can never yield a client file once the tree changes.

#### F4-10: Medium. Per-application against run-level verify is not classified, and two older statements still say "verify fails, no client file"
- **Evidence:**
  - 8.6:346-347 and 8.8:367-368 split failures into per-application and run-level without listing which of the 18 rules is which (`verify.py` ACC-1..10, CON-1..8; CON-4 and CON-6 concern portfolio and report artifacts).
  - §13:482 "Verify fails | No client file" and accuracy spec:11 "A failed run SHALL NOT produce a client file" are unchanged.
  - §6.4:185-186 still says "the client file is not produced for that application" for a detector failure. 8.6 gives no label for that case, so an application the consultant named in scope (8.1) can silently disappear. The round-3 response promised "listing excluded applications".
- **Severity:** Medium. Determinism of what gets published, and a silent omission from a named scope.
- **Fix:**
  - Add a table classifying each verify rule as per-application or run-level. ACC-9, CON-4, CON-6 and the client-count rule are run-level.
  - Amend §13 and accuracy spec:11.
  - Add the label "Not available: analysis incomplete (<detector> failed)" to 8.6 and the vocabulary.

#### F4-11: Medium. The review workload has no acceptance criterion, and "minutes per application" cannot be measured under the chosen order
- **Evidence:**
  - 8.2:292-293: "There is no cap; the scope (8.1) is what bounds the effort." Must-review per application is every gap of any severity, plus confirmed issues, plus high UNKNOWN, "Not seen here" and need-based N/A, plus high PRESENT below enforced.
  - With 58 controls today (15 high) and 17 aspects proposed, a legacy application plausibly has 20-40 must-review items. At 20 applications that is 400-800 individual reviews, before team statements. Reasoning-only, unverified: no run data was available.
  - The order runs across applications (8.2:301), so time is spent per control, not per application. The "minutes per application" required by 8.1:287 and accuracy spec:42 cannot be attributed directly.
  - The phase-2 exit (tasks:95-97) records a projection but sets no threshold, and nothing says what happens if the projection is infeasible.
- **Severity:** Medium. An infeasible budget is the root cause of F4-3 and F4-4 pressure. D-7 is being signed without knowing feasibility.
- **Fix:**
  - Record time per reviewed item and per bulk screen, and project by item counts.
  - State, before T-2.1, a budget (for example hours per application) and the consequence of exceeding it: a smaller scope, never a cap on must-review.

#### F4-12: Low. "Severity" in must-review selection and order is ambiguous
- **Evidence:**
  - 8.2 items 3-4 select on "a high or critical control" and order by "severity".
  - At `9479a59` the result's severity is the evaluator's override or the catalogue's (`aspects.py:504`), and it is stored only for gap states (`aspects.py:506`, `None` otherwise). For example, Spring Boot open-source end of support is PARTIAL "high" (`aspects.py:248`).
  - "critical" does not exist in the catalogue yet (T-1.15).
- **Fix:** select and order by catalogue control severity, with the result override used for gaps. State it, and add a test.

#### F4-13: Low. Vocabulary and documents still disagree
- **Evidence:**
  - `proposal.md:29`: "every result visible, unreviewed ones marked". This contradicts 8.6:342.
  - The label strings differ: "Gap, stated by the consultant" (8.4:318, accuracy spec:71) against "Gap stated by the consultant" (§11:430, report spec:47); "Not available" (report spec:48) against "Not available: verification failed".
  - "Stated by the team" (8.4) against "stated by the client" (asis-coverage spec:37) for the same kind of person-supplied fact.
  - The vocabulary browser test (report spec:50) fails on exact-string drift, so these will be caught late.
  - Whether "Possible issue" results are must-review is ambiguous: 8.2 item 2 says "every gap", ISSUE is a gap state (§6.1), but the parenthesis lists only Not found and Partly in place.
- **Fix:** one table, edited once; fix the proposal line; state that possible issues are not must-review and never shown unless confirmed individually.

#### F4-14: Low. Hashes in the mark binding could store derivatives of secrets
- **Evidence:** 8.7:356 binds to "the evidence content hash". Evidence lines for secret controls hold the secret before redaction (ACC-8 exists for that reason). A hash of a raw line containing a short secret is a stored derivative (R-07).
- **Fix:** hash the redacted text only, and state it.

#### F4-15: Low. Person-stated outcomes count as states without strength or evidence fields, and the spec does not restrict team statements
- **Evidence:**
  - 8.4:320: "Stated by the team … counts as the stated state". A stated pass therefore feeds an "In place" aspect status (8.6:344-345) on the client's own word.
  - Accuracy spec:73 does not carry the design's "for 'Not seen here' and other undecided results" restriction, so the spec would allow a team statement over a tool "Not found".
  - There is no file-and-line or "outside the repository" field for consultant-stated gaps (R-02, R-13).
- **Fix:**
  - Add the restriction to the spec.
  - Give person outcomes a fixed strength label ("stated").
  - Make a stated pass yield "In place (stated)" rather than "In place".
  - Add an optional evidence field.

#### F4-16: Low. Concurrency and sanitising are asserted without a mechanism
- **Evidence:**
  - 8.3:310 introduces a second person, but nothing locks or merges `review.json` for two concurrent reviewers, so marks can be lost.
  - 8.4:327-328 requires fixtures with "no client names, hostnames, package names, identifiers", with no check.
- **Fix:** take a single-writer lock on `review.json` (refuse a second `review` on the same run). Add a deterministic test that fails if any fixture contains a string from the client workspace's application names, package prefixes or hosts, run in the client workspace before a fixture leaves it.

#### F4-17: Low. Safety-critical behaviours lack scenarios
- **Evidence:** in-scope requirements have scenarios, but none covers:
  - expiry and re-presentation (accuracy spec:70-83);
  - deletion of the client file on a run-level failure, or the per-application label (:105-113);
  - exclusion of "Not yet reviewed" applications from sort and counts, or the display of the confirmation mode (report spec:5-23);
  - a mark invalidated by an evidence or search-scope change (:94-103);
  - the minimum of 5 in the audit sample.
- **Fix:** add one scenario per bullet. Each is a direct test case for T-2.1 to T-2.3.

### Judgement calls (opinion, not proven defects)

- **Team statements as passes.** I would not let a client's own statement turn an aspect green in the client file. Show "In place (stated)" with its own neutral-positive treatment in mock v3 (D-11).
- **Second person.** "Where available" makes the only independent check optional. For a first client meeting I would require a second person for the audit sample and the stop-rule escalation, and record a single-reviewer run as such in the client file's review statement.
- **AS-IS facts under D-4.** Whether "results shown to a client are consultant-confirmed" covers facts ("Spring Boot 1.5.10") is a user decision that F4-2 forces. I would label facts "read by the tool" rather than require their review.
- **Expiry of confirmations.** Disputes expire, confirmations never do. With the content-scoped binding of F4-6 that is defensible. Without it, I would expire confirmations at 90 days too.
- **Consultant-chosen scope.** 8.1 lets the consultant choose which applications are shown. Out-of-scope applications are listed once, so this is honest; but a client file built from the best-looking applications is possible. A one-line "chosen by: consultant / client" in the file would make the choice visible.

## (5) Open questions (evidence needed)

1. What is the distribution of must-review items per application on the six repositories? Gaps, high UNKNOWN, high PRESENT below enforced. This decides F4-11. It needs a verified run's `aspects.json` counted by state, severity and level. No run folder exists on this machine.
2. Do the client's Git servers allow fetching an arbitrary SHA (`uploadpack.allowReachableSHA1InWant` or protocol v2 defaults), and does any client repository rewrite history? This decides whether F4-9's pinned-ref fix is required or only preferable.
3. Is the client file a snapshot that is never regenerated once sent? Or can a later `review` regenerate it from carried-forward marks? This is round-3 open question 5, still unanswered. It decides whether F4-6's carried-forward provenance label is mandatory.
4. Which dispute reason categories indicate a tool error, as opposed to a client fact? The list at 8.4:322 needs that split for F4-4.
5. Will engineers write the synthetic fixtures (8.4:327) with model assistance? If so, the backlog item's client-derived text would leave the machine (R-08). The design should either forbid that or require the fixture to be written from a sanitised description only.

