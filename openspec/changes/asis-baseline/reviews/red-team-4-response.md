# Response to red-team review 4 (focused on D-7)

Review: `red-team-4.md`, verdict APPROVE WITH CONDITIONS: D-7 may be signed once C1-C5 are in the text and a reviewer
has checked the diff of these edits. All findings accepted.

| Finding | Where |
|---|---|
| C1 / F4-1 expired stated gap returns as a bulk pass | design 8.2 item 5; accuracy spec "Must-review", scenario "a known false pass after expiry" |
| C2 / F4-2 everything outside aspect results undefined | design 8.6 whitelist: review statement, outcomes, remedies only on reviewed gaps and labelled, AS-IS facts labelled (D-7a), derived views recomputed or omitted, verify rule over every derived number; report spec |
| C3 / F4-3 no outcome for "wrong but unknown" or "gap of another kind" | design 8.4: "Corrected by the consultant: <state>" and "Cannot confirm"; scenarios |
| C4 / F4-4 stop rule penalises honest disputes | design 8.5: counts tool-error reasons only; deterministic escalation; cleared when escalation completes; a re-run does not clear it; design and spec aligned; scenarios |
| C5 / F4-5 neutral status hides known gaps; y undefined | design 8.6 precedence and definition of x and y; scenarios |
| C5 / F4-6 binding contradicts its scenario; negative carry-forward unsafe | design 8.7: per-control definition hash, detector versions, redacted evidence hash or search-scope content hash; no global versions; carried-forward label; scenarios |
| F4-7 audit sample | design 8.3: seed, no redraw, carried-forward included, second person recorded, revert aspect on disagreement and double |
| F4-8 excluded apps vanish from summary | design 8.6 summary row; ranking eligibility; disputed-only apps sorted after |
| F4-9 fetch-by-SHA online and checkout in shared clone | design 8.7: local refs pinned at scan time; `git show` and temporary exports |
| F4-10 rule classification; stale statements | design 8.8 table; §13 rows, §6.4 and accuracy spec first requirement amended; "analysis incomplete" label |
| F4-11 workload | design 8.1: time per item and screen, budget set before T-2.1 (T-2.0), scope reduced not must-review |
| F4-12 severity ambiguous | design 8.2: catalogue control severity |
| F4-13 vocabulary | design §11 exact strings; proposal line fixed; "stated by the client" vs "Stated by the team" separated; possible issues not must-review and never shown unless reviewed |
| F4-14 hashes of secrets | design 8.7: over redacted text only |
| F4-15 person outcomes as states | strength "stated", optional evidence field, team statements on undecided only (spec too), "In place (stated)" |
| F4-16 concurrency and sanitising | single-writer lock; sanitising test (T-2.3b); no model assistance on client-derived text |
| F4-17 missing scenarios | added for expiry, deletion, per-application failure, exclusion from counts, mode display, search-scope change, audit minimum, concurrency, fixture sanitising |

Judgement calls: "In place (stated)" adopted; second person and AS-IS facts put to the user as D-7a and D-7b; client
file names who chose the scope; confirmations carried forward only under the content-scoped binding.

Open questions: 1 answered by T-2.0; 2 removed by local pinned refs; 3 a client file is a snapshot of one review, a
later review produces a new one with carried-forward marks labelled; 4 the reason list is split in 8.4; 5 answered in 8.4.

## Condition checks

- First check (`red-team-4-conditions.md`): CONDITIONS NOT MET (C1, C4 partly). Fixed: 8.2 item 5 covers any outcome
  other than Confirmed; consultant-stated gaps count for the stop rule and create backlog items; D2-D12.
- Re-check (`red-team-4-conditions-recheck.md`): **CONDITIONS MET**. Its N1-N5 were then fixed before the decision:
  tool error decided by the change, not the reason picked (N1); no positive aspect status without a confirmed pass, and
  "In place where checked" kept for its internal meaning (N2); stop-rule firing carries to the next review (N3); spec
  sentence (N4); T-2.0 counts item 7 (N5).
