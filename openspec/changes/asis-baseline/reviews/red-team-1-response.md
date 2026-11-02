# Response to red-team review 1

Review: `red-team-1.md`, verdict REJECT. Every code claim in the review that the response relies on was re-checked
against commit 9479a59 before acting: report and `latest` written before verify (`cli.py:145-152`); owners read
from CODEOWNERS only (`detectors/identity.py:14-18`); `criticality` not read by any UI file; "Maturity N%" tile
(`ui/core.js:64`); duplicate id aborts (`relate.py:80-84`); clone slug from two segments (`sources.py:32-37`); ACC-9
oracle is the redaction function (`verify.py:161-172`); `bin/` not skipped (`evidence.py:16-17`). All confirmed.

| Finding | Accepted? | What changed |
|---|---|---|
| F1 threshold unreachable, "1 in 50" baseless | Accepted | Design 7.3 rewritten: exact one-sided bounds on both error rates; sample sizes table; "1 in 50" withdrawn; `depends_on` defines which stack values a control is measured on; 0/0 is not validated; corpus size derived (7.4) |
| F2 hidden gaps and other error classes unmeasured | Accepted | Design 7.2: false-pass rate includes UNKNOWN and N/A; false-gap rate includes PARTIAL and ISSUE; reason, level, evidence and remedy fit measured. README-mention hidden-gap generator added as defect and task T-1.11 |
| F3 absence guard covers ABSENT only | Accepted | Design 6.3 extends the guard to N/A by need, ISSUE by default, PARTIAL by missing part; open-in-view is `confirmed: false`; T-1.8 |
| F4 labels not independent; in-sample | Accepted | Design 7.4-7.5: held-out split by hash before labelling; person's labels (≥300 cases) are the reference; model labels only at ≥95% agreement; Spring Boot 1.x and every parsed CI system and platform are strata; enterprise patterns measured with seeded fixtures (not reachable with public code at n=22, said so) |
| F5 verify not surfaced; no client-use gate | Accepted | Design section 2 (client-use gate, D-0); T-1.1, T-1.19; phasing exit criteria name the gate |
| F6 false BUILT claims | Accepted | Owners, criticality, credentials, detector failure, failure paths downgraded in matrix, design and specs; rule count corrected to 18; engine test count stands at 312 (runner output "Ran 312 tests" on 9479a59; the static count differs because of inherited tests); T-1.3 adds test ids to every BUILT row |
| F7 leak check uses its own oracle | Accepted | Design 13 reworded to what ACC-9 covers; independent literal-value and second-pattern check specified (accuracy spec), T-1.7 |
| F8 client code into the corpus | Accepted | Design 8: a dispute becomes a synthetic, client-free fixture; client code never leaves the workspace |
| F9 platform-level settings as false gaps | Accepted | Design 6.6 `usually_outside` (restores the review-03 agreement that had been dropped); GitOps blind spots; branch protection added to the matrix; T-1.9 |
| F10 three assessment models; maturity % | Accepted | Decision D-9: aspects only; maturity score leaves the report; dimensions derived and checked by verify; T-1.13 |
| F11 matrix gaps and mis-statuses | Accepted | 19 items added (application boundary, JDK vendor, build tool vs JDK, internal shared libraries, web tier, API versioning, DB version and dialect, data classification, producer settings, branch protection, GitOps, container security posture, assertions, indexes/full scans/locks/stampede (OUT), concurrency, doc drift, Groovy/Scala, file roles area A0); five statuses corrected. Now 157 items in 25 areas |
| F12 upstream decisions dropped | Accepted | D-10 (criticality profiles deferred with reason); D-1 mapping table in the evidence spec, with the upstream schema's `additionalProperties: false` noted as lossy; rule id, version and source revision per finding; `engine/benchmark` added to 7.1 and T-2.6 |
| F13 client/consultant boundary and spot-check undefined | Accepted | Separate client file, data removed not filtered, counts recomputed, verify rule; checklist bounded (high/ISSUE on non-validated stacks + sample of 30); stop rule (>2 disputes) |
| F14 scale failure paths | Accepted | Unique folders and ids, per-repo isolation; failure-path rows added; T-1.5 |
| F15 semantic tier feasibility; Kotlin | Accepted | D-3 is now a prototype decision only; certainty `parsed` without a classpath; Kotlin listed once as not covered; adoption from measured precision |
| F16 "missing" contradicts ABSENT | Accepted | Vocabulary: "Not found", "Not seen here" |
| F17 perspective contradictions | Accepted | Three perspectives; risk rules are assessment controls with `confirmed`; AS-IS view has a place for every area (A0-A24) |
| F18 dependency presence counted as in place | Accepted | Declared-only becomes PARTIAL; T-1.12 |
| F19 headline figure without provenance | Accepted | Restated with measure, audit, run, code and "not a validated rate" |
| F20 two gate definitions | Accepted | One definition (7.6) |
| F21 agreed items not carried | Accepted | Sort by any aspect column, commands as code, Hazelcast as cache, `critical` severity, browser-test skip, all in specs and tasks |
| F22 tool-not-run per application | Accepted | Listed once on Scope; out of counts |
| J1 modernisation as a TO-BE gap | Accepted | Readiness relative to a declared target; no target means facts only |
| J2 colour by state vs severity | Partly | Recorded as D-11; both schemes mocked on mock v3 and decided there; recommendation now encodes severity as solid vs hollow amber |
| J3 breadth before proof | Accepted | New controls shown only when validated or confirmed |
| J4 report rebuild before measurement | Accepted | Mock v3 may run during phase 2; rebuild after measurement table v1 |

Open questions from the review:

1. Engine test count: 312 per the test runner on 9479a59.
2. Report size at 300 applications: not measured; T-3.8.
3. Semantic precision without a classpath: the D-3 prototype answers it.
4. Audit-5 items: re-checked by T-1.21 rescan.
5. Verify on HEAD: the six-repository run 20261102-113035 was made after the code changes of 9479a59 but before the
   catalogue version bump to 1.4.0; T-1.21 re-runs on the final code.
