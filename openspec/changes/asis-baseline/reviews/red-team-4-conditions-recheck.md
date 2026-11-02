# Conditions re-check: D-7 edits, second pass

I read `conditions-edits.diff`, which applies to design.md, the accuracy-assurance spec, the report-experience spec and tasks.md, on top of the round-4 edits I checked before. I edited and ran nothing.

## Your four checks

**(1) 8.2 item 5 covers any outcome other than Confirmed: MET**
- Design 8.2 item 5: "Every result that carried any outcome other than Confirmed in an earlier review of the same application and control, presented with the prior outcome, note, reviewer and date".
- The accuracy spec "Must-review" requirement says the same, but the sentence is garbled: "every result with a dispute, any outcome other than Confirmed in an earlier review". The meaning is clear, so this is Low (N4).
- This also covers "Gap stated by the consultant" and "Cannot confirm". **C1 is now MET.**

**(2) "Gap stated by the consultant" counts for the stop rule and creates a backlog item: MET**
- Design 8.4 table: "always a tool error for the stop rule (reason 'tool reported it in place wrongly' or 'tool could not decide it')".
- Design 8.4: "Every outcome with a tool-error reason (including every 'Gap stated by the consultant') creates a backlog item".
- The spec requirement reads "(every 'Gap stated by the consultant' counts as one)", and the scenario "three false passes on one control" asserts the rule fires and three backlog items are created.
- **D1 is resolved and C4 is now MET.** See N1 for a remaining loophole.

**(3) D2, D3 and D4**

| Defect | Status | Basis |
|---|---|---|
| D2 | **partly** | The 8.6 aspect cell is now an ordered rule: Not checked when y = 0, High gaps, Gaps, "Reviewed x of y", Not applicable, In place where checked, In place (stated), In place. There are scenarios for "1 confirmed + 3 Cannot confirm → In place where checked" and for a team-stated pass. The residual is N2. |
| D3 | resolved | 8.8 makes ACC-8 run-level, plus "any new rule unless classified otherwise". It adds "After a per-application failure the file is regenerated without that application's content and verified again", and the spec matches. |
| D4 | resolved | 8.6 adds "What was not looked at" (scope summary, plus reference-data status on every result that rests on that data). The report spec matches. |

**(4) D5 to D12**

| Defect | Status | Basis |
|---|---|---|
| D5 | resolved | The sample is "only ever extended from that seed", and "a disagreement is any outcome other than Confirmed". Design and spec agree. |
| D6 | resolved | Implicated controls are "every control with at least one counted outcome in the window". |
| D7 | resolved | The reason categories are now a two-column table. "other, with a note" counts as not a tool error, which feeds N1. |
| D8 | resolved | §2 gate item 2, the §6.4 label, the severity override in the spec, "or search record" in 8.3, the tasks paragraph and the tasks Exit are all fixed. |
| D9 | resolved | 8.2 item 7 makes every other UNKNOWN or "Not seen here" result must-review. Possible issues are absent unless reviewed, and are counted in the scope summary. |
| D10 | resolved | "Confirmed … for a gap, the reviewer also marks whether the remedy was confirmed". |
| D11 | partly | Scenarios were added for the budget, AS-IS facts, the "j not available" count, disputed-only ranking, a re-run and the carried-forward label. Outcomes that expire after 90 days within the same run still have no rule and no scenario. |
| D12 | resolved | PARTIAL marks now also bind to the search-scope hash ("its missing part"), in design and spec. |

## (5) Defects these edits introduced or left

**N1 (Medium). Whether the stop rule counts a false pass depends on which outcome the reviewer picks.**
- A false pass can still be recorded as "Corrected by the consultant: Not found" with the reason "other, with a note" or "client fact". That outcome is not counted, creates no backlog item and does not escalate.
- In the other direction, "tool could not decide it" makes every "Gap stated" on a "Not seen here" result a tool error. A consultant who honestly states three branch-protection gaps that the tool cannot see by design therefore fires the rule and creates fixtures for correct tool behaviour. That is the F4-4 penalty again, on a smaller scale.
- Fix: decide tool error by the transition, not by the outcome. A tool PRESENT or NOT_APPLICABLE that a person changes to a gap state always counts. A tool UNKNOWN on a `usually_outside` control that a person changes to a gap never counts. Add one scenario for each.

**N2 (Medium). "In place where checked" can show with no confirmed pass.**
- Under the 8.6 rule, an aspect whose results are all "Cannot confirm", or all disputed, reads "In place where checked". That is a positive status over nothing confirmed in place.
- The rule also has no tier for a result corrected to UNKNOWN or NOT_ASSESSED.
- The final tier's parenthesis, "every result counted in y has a confirmed or corrected pass", is not true of a mix of passes and NOT_APPLICABLE results, yet "otherwise In place" assigns it.
- Fix:
  - "In place where checked" only when at least one result has a confirmed, corrected or stated pass. Otherwise use the neutral "Reviewed x of y" or "Not checked".
  - Treat confirmed NOT_APPLICABLE as neutral in the "In place" test.
  - Say how corrected UNKNOWN and NOT_ASSESSED count.
  - Add an all-"Cannot confirm" scenario.
- Low, in the same area: the client file now uses "In place where checked" for "some results disputed or not confirmable". The internal report already uses that label to mean "in place where the tool could check" (§11 "Built since the reviews"), so one label carries two meanings.

**N3 (Low). The re-run scenario promises more than the design defines.**
- The spec scenario says "the escalation still applies" after a new scan.
- Design 8.5 says only that "the outcomes are re-presented under 8.2 item 5". It does not say the item-6 must-review set or the 25% audit carries to the new run's review.
- Fix: state that the firing is carried to the next review of the same scope, or reword the scenario to match 8.5.

**N4 (Low).** The garbled spec sentence noted under (1).

**N5 (Low). Workload grows.**
- Item 7 makes every UNKNOWN and "Not seen here" result must-review, including the usually-outside controls on every application.
- T-2.0's budget and the "reduce scope" rule cover this, so it does not block. T-2.0 should count item-7 results explicitly.

**Checked and found clean:** no path now lets an unreviewed tool verdict into the client file, hides a confirmed gap at the aspect, summary or ranking level, or leaves a secret-rule failure handled per application. §2, §6.4, §11, §12, §13, tasks.md and both specs now agree with section 8, apart from N3 and N4.

## Verdict

CONDITIONS MET (D-7 can be put to the user). C1 to C5 are all in the text. N1 and N2 are Medium and should be fixed before T-2.1 starts. N3 to N5 are Low.
