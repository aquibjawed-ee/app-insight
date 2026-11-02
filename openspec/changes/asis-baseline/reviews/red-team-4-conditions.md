# Round-4 conditions check: D-7 edits (asis-baseline)

**What I checked:** the round-4 diff (`round4-edits.diff`), the current design.md (§2, §6.4, §8.1–8.10, §11, §12, §13), the current `specs/accuracy-assurance/spec.md` and `specs/report-experience/spec.md`, tasks.md (phase 2), and proposal.md. I also grepped the other specs for stale wording.

I read the verify rule ids at `9479a59` with `git show` and nothing else. Nothing was edited or run.

## Conditions

**C1 (F4-1, a result disputed in an earlier review comes back): PARTLY MET**
- What meets it:
  - design 8.2 item 5: "Every result that carried a dispute, a correction or a team statement in an earlier review of the same application and control, presented with the prior outcome, note, reviewer and date".
  - The accuracy spec scenario "a known false pass after expiry" covers the exact F4-1 case: "Gap stated by the consultant" on a PRESENT result.
- Gap 1: the edits renamed the outcome to "Gap stated by the consultant", a separate row in 8.4 that is no longer a "dispute". Item 5 and the spec requirement ("every result with a dispute, correction or team statement") therefore do not name the F4-1 outcome. Only the scenario covers it.
- Gap 2: "Cannot confirm" is missing from item 5, although 8.4 says it "expire[s] … and [is] re-presented under 8.2 item 5". A doubted non-must-review PRESENT can therefore be bulk-confirmed on the next run.
- Fix: make item 5 read "every result that carried any outcome other than Confirmed", in both the design and the spec.

**C2 (F4-2, a whitelist of client-file contents): MET**
- design 8.6: "The client file contains exactly the following; anything else from the internal report is not in it."
- Derived views: "recomputed from review outcomes only: a result without an outcome contributes nothing. A view that cannot be recomputed that way is omitted."
- Remedies: "labelled 'suggested, not reviewed' unless the reviewer confirmed the remedy with the result".
- AS-IS facts are labelled "read by the tool, not reviewed" (D-7a). The verify rule covers "every count and derived number".
- The report spec matches. See defects D4 and D10 for residuals.

**C3 (F4-3, two new outcomes): MET**
- design 8.4 table: "Corrected by the consultant | any result; a state from the seven and a reason category are required".
- And: "Cannot confirm | … | 'Not reviewed: could not be confirmed' (the tool's verdict is not shown) | resolved, neither pass nor gap".
- 8.6 says "any outcome in 8.4 resolves it". The spec scenarios "right state, wrong evidence" and "truth unknown before the meeting" are present.

**C4 (F4-4, a deterministic stop rule): PARTLY MET**
- What meets it:
  - design 8.5: "The rule counts only outcomes with a tool-error reason", with a two-step escalation.
  - "cannot be produced while that escalation is incomplete; once it is complete, the rule is cleared … A re-run does not clear it."
  - The spec matches, with scenarios for a systematic error and for a client fact.
- What fails: "Gap stated by the consultant" carries a note but no reason category (8.4 table). It therefore never counts. That outcome is how a consultant records a false pass, the costliest tool error.
  - Before these edits, "Disputed: believed a gap" counted.
  - An audit-sample false pass recorded this way also no longer counts.
  - See D1.

**C5 (F4-5 and F4-6, aspect precedence and mark binding): MET**
- Precedence, design 8.6: "High gaps, then Gaps, then 'Reviewed x of y', then In place or In place where checked. So a known gap is never hidden".
- y and x are defined: "y is the aspect's results excluding controls with no detector and NOT_ASSESSED results; x counts every result with an outcome".
- Binding, design 8.7: per-control definition hash, detector versions, a redacted evidence hash or a search-scope content hash, and "It does not bind to the global catalogue version, tool version or repository commit".
- Carried-forward marks are labelled. The spec scenario "a catalogue change to one control" now holds, and "the searched files changed" was added.
- See D2 for a residual in the precedence rule.

## F4-6 to F4-17

| Finding | Status | Note |
|---|---|---|
| F4-6 | resolved | As in C5. Small gap: PARTIAL is bound only to its evidence hash, not to the search scope of its missing part (D12). |
| F4-7 | resolved (residual) | Seed, no redraw, carried-forward marks in the sample, second person, revert and double are all in. "Never redrawn" is not reconciled with "doubles the sample" and "rises to 25%", and "disagreement" is undefined (D5). |
| F4-8 | resolved | Summary row, ranking eligibility, disputed-only apps sorted after, "disputes: n". No scenario for the ranking rule (D11). |
| F4-9 | resolved | Pinned local refs, `git show`, temporary export, no checkout of the shared clone. |
| F4-10 | partly | The table is added, and §13, §6.4 and the accuracy spec's first requirement are amended. But the table puts ACC-8 (a secret shown unredacted) in the per-application column, and it never says the file is regenerated without the failing application (D3). |
| F4-11 | partly | 8.1 and T-2.0 now record time per item and set a budget. The tasks phase-2 Exit still says "review minutes per application recorded and projected to 300" (D8). |
| F4-12 | resolved | The design names catalogue control severity, with the evaluator override for gaps. The spec drops the override clause and no test is named (D8). |
| F4-13 | partly | §11 has one exact-string table; the proposal line, the client/team split and the possible-issue rule are fixed. Two new drifts: §6.4 says "Not available: analysis incomplete" without "(<detector> failed)", and "possible issues never in the client file" conflicts with "a result with no outcome shows Not reviewed" (D8, D9). |
| F4-14 | resolved | "Hashes are computed over redacted text only." |
| F4-15 | resolved (residual) | Strength "stated", optional evidence, team statements on undecided results only (the spec too), and "In place (stated)" for single results. The aspect level is not covered: team-stated passes still roll up to plain "In place" (D2). |
| F4-16 | resolved | Single-writer lock and the sanitising test (T-2.3b), with scenarios for both. |
| F4-17 | resolved | All the listed scenarios were added. New behaviours still lack scenarios (D11). |

## Defects introduced or left by the edits

**D1 (High). A consultant-found false pass no longer counts for the stop rule, and no backlog item is created for it.**
- 8.5 counts only outcomes with a tool-error reason. The 8.4 row "Gap stated by the consultant" has "with the note" and no reason category.
- 8.4 also says only "A dispute or correction with a tool-error reason creates a backlog item".
- So three false passes on one bulk-confirmable control, for example a medium "Timeouts set" at level enforced, never trigger the escalation. Only the single audited aspect and application reverts (8.3). Other applications' bulk confirmations of that control ship as "confirmed with its aspect".
- This is a regression from the pre-edit text and undermines C4. It is the "false pass in front of the client" path that round 4 rated High.
- Fix: "Gap stated by the consultant" always counts as a tool error for 8.5 and always creates a backlog item, or require a reason category on it, adding "tool reported it in place wrongly". Add a scenario where three stated gaps on one control fire the rule.

**D2 (Medium). The aspect precedence is incomplete, and the cheapest outcome can turn a cell positive.**
- x counts "Cannot confirm" and disputes. Take an aspect with one confirmed pass and three "Cannot confirm": x = y = 4 and there are no gaps, so the 4-tier rule falls through to "In place". The aspect reads "In place" over results nobody could confirm.
- "Cannot confirm" needs no reason and no note. It is now the lowest-effort way to turn "Reviewed x of y" into a positive cell, which works against 8's "never pushes the reviewer".
- The rule has no tier for these cases:
  - an aspect whose reviewed results are all NOT_APPLICABLE;
  - y = 0 (every control has no detector or is NOT_ASSESSED);
  - passes that are only team-stated, which give plain "In place" although the judgement call adopted "In place (stated)".
- The report spec precedence lists only "High gaps, Gaps, Reviewed x of y, In place".
- Fix: complete the tiers deterministically:
  - "In place" only when every result counted in y has a pass outcome that is not stated;
  - "In place where checked" when any result is disputed or "Cannot confirm";
  - "In place (stated)" when any pass is stated;
  - "Not applicable" when all results are NOT_APPLICABLE;
  - "Not checked" when y = 0.
- Add scenarios for each tier.

**D3 (Medium). The verify-rule classification lets a secret-bearing failure be handled per application.**
- At `9479a59`, ACC-8 is "a cited line about a secret shows the secret instead of [REDACTED]". 8.8 classes it as per-application, so the file is kept with that application marked "Not available".
- Nothing says the file is regenerated without the failing application's content and verified again.
- Rules added in phase 1 default to per-application.
- The run-level literal-value leak check probably catches the same value, so this is Medium, not High.
- Fix: move ACC-8 to run-level, and make run-level the default for new rules. State that a per-application failure regenerates the file without that application and verifies it again.

**D4 (Medium). The whitelist drops "what was not looked at".**
- "Exactly the following" leaves out the Scope content (§11): controls with no detector (also excluded from y), tool runs not done, and usually-outside controls.
- It also leaves out the per-result reference-data review status that §2 gate item 3 requires.
- The client file therefore never says what was not checked, which goes against §1's "say plainly what was not looked at" and R-17.
- Fix: add a one-line Scope summary and the reference-data status to the 8.6 whitelist and the report spec.

**D5 (Low). The audit sample is not deterministic.**
- "Drawn once … never redrawn" conflicts with "doubles the sample" and "rises to 25%".
- It is not said whether a "Cannot confirm" in the sample counts as a disagreement.
- Fix: extend the draw from the same seed, and define a disagreement as any outcome other than Confirmed.

**D6 (Low).** "Implicated controls" (8.5) is undefined when the three tool-error outcomes fall on different controls. Fix: every control that has at least one counted outcome in the window.

**D7 (Low).** The reason-category line in 8.4 is ambiguous: "…wrong kind or severity (tool errors) — set outside the repository; client fact (not tool errors) — other, with a note". It is unclear whether "other" is a tool error. The spec requires each category to be marked. Fix: make it a two-column list.

**D8 (Low). Stale or mismatched text.**
- tasks phase-2 condition paragraph ("pass a focused round-4 review") and Exit ("minutes per application … projected to 300").
- §2 gate item 2 still says "under a focused round-4 review".
- §6.4 label is missing "(<detector> failed)".
- The accuracy spec omits the evaluator-override clause for severity.
- The 8.3 bulk screen dropped "or search record", which NOT_APPLICABLE results need.

**D9 (Low).**
- Medium-severity UNKNOWN results and possible issues have no review path: they are neither must-review nor bulk-confirmable. The UNKNOWN ones sit in y, so the cell stays "Reviewed x of y" for good.
- "Possible issues … never in the client file" conflicts with "a result with no outcome shows 'Not reviewed'".

**D10 (Low).** There is no field or outcome for "remedy confirmed with the result". 8.4 "Confirmed" covers only the result, so the condition behind "suggested, not reviewed" cannot be recorded.

**D11 (Low). Behaviours with no scenario:**
- reducing a scope that is over budget;
- the AS-IS fact label;
- the "j not available" count in the summary row;
- ranking of disputed-only applications;
- a re-run not clearing the stop rule;
- the carried-forward label;
- outcomes that expire after 90 days within the same run.

**D12 (Low).** A PARTIAL mark carries forward on its evidence hash alone, even if the search scope of its missing part changed.

**Checked and found clean:**
- No path shows an unreviewed tool verdict as a result. Carried-forward marks are labelled, remedies and AS-IS facts are labelled, and audit reverts go to "Not reviewed".
- §13 and the accuracy spec's first requirement now agree with 8.8.
- D-7 in §12 correctly says the decision is pending.

## Verdict

CONDITIONS NOT MET. Two short edits are the minimum before D-7 goes to the user:
1. In 8.2 item 5 and the matching spec requirement, write "every result that carried any outcome other than Confirmed".
2. Make "Gap stated by the consultant" count as a tool error for the stop rule (8.5) and create a backlog item (8.4), with a scenario.

D2, D3 and D4 should be fixed in the same revision. A reviewer can check them from the diff alone.
