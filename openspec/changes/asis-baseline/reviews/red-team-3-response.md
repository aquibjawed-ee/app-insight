# Response to red-team review 3

Review: `red-team-3.md`, verdict **APPROVE WITH CONDITIONS**, D-7 (consultant review, design section 8) held back.

| Condition | Action |
|---|---|
| 1. Narrow T-1.12 before it merges (F3-1) | Sent to the phase-1 implementer immediately (2026-11-02): only dependency declarations and INFERRED facts become PARTIAL; negative secret scans and the Spring Boot 3.4+ graceful default stay PRESENT; three regression tests. Spec, task and design aligned. The deploy marker "image published with no deploy step" also removed (F3-11) |
| 2. D-7 not signed in phase 0; focused round 4 before T-2.1/T-2.3 | Recorded in design section 12, section 2 and tasks. Section 8 will be revised for F3-2 to F3-13 (disputes stay visible with direction and expiry; unreviewed applications kept out of ranking; confirmation mode recorded and shown, bulk only for non-must-review PRESENT/N/A, audit sample of bulk confirmations; capacity measured and client file scoped to named applications; one rule for unreviewed results; must-review seeded by severity and unmeasured controls; "stated by the team" outcome; per-application verify outcome; finer mark binding) |
| 3. Verify and leak check after the client file; reviewed runs immutable (F3-8, F3-9) | Tasks: condition note before T-2.1; T-1.29 (`report` HTML-only or AGENTS.md corrected; runs with `review.json` never rebuilt in place) |
| 4. Document fixes F3-14 to F3-22 | Done: tasks preamble (phase 1 by user decision; T-1.13 reverted if D-9 rejected); matrix D-4 and deploy wording; report-spec vocabulary; T-1.2/T-1.3 claim corrected; `understands` and determinism tests cited correctly; export row maps below-verified PRESENT to INSUFFICIENT_EVIDENCE; vulnerability-scan ISSUE added to the table; evidence spec PARTIAL wording; gate references T-2.3; gate state and file name task T-1.28; accuracy wording denominator; D-3 30 candidates per rule. Not yet done: tie-break for "top 10" and listing excluded applications in the client file (both part of the section 8 revision); design section 14's phase-1 summary is a summary, tasks.md is authoritative |

Judgement calls: reviewing the reference data before the gate, a named subset of applications for the first meeting,
a second-person audit sample of bulk confirmations, and no positive colour for an aspect with unreviewed results: all
taken into the section 8 revision for the user to decide.

Open questions 1 (profile-specific configuration in runtime detectors) and 2 (`localhost` URLs counted as a shared
database) are possible confirmed false ISSUEs; added to phase 1 as checks with fixtures when the implementer reports.
