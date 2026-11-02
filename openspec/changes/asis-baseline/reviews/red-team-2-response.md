# Response to red-team review 2

Review: `red-team-2.md`, verdict REJECT, phase 1 cleared to proceed. Code claims re-checked against 9479a59 before
acting: need-based N/A converted only for `outbound_http` and `database` (`aspects.py:423`); ACC-2 checks PRESENT only
(`verify.py:109`); a rescan resets the shared clone (`sources.py:162-166`). All confirmed.

Two user decisions on 2026-11-02 change the frame of this response:

1. **D-4: results shown to a client are consultant-confirmed first.** No "validated" claim is made to a client;
   statistical validation is deferred, with its true sizing recorded (design 7.4). This removes the basis of N1 and N2
   as client-facing risks; their corrections are kept for the internal measurement and for the later decision.
2. **Phase 1 starts now**, in parallel with this revision, as the reviewer advised. Scope corrections from N6, N7, N10,
   N14, N15, N17 were given to phase 1.

| Finding | Accepted? | What changed |
|---|---|---|
| N1 corpus cannot validate anything | Accepted | Validation deferred (D-4 decided). Sizing restated correctly in design 7.4: per class, both classes, 38-52 with one or two errors, prevalence; about 100-200 repositories for one stack. The 60-repository corpus is internal measurement only |
| N2 client wording misstates the bound | Accepted | No accuracy statement to clients. Internal wording states what is bounded, per rate, per value; predictive values and multiplicity named as prerequisites of any later client-facing claim |
| N3 label gate incoherent | Accepted | Design 7.3: person labels every case of high-risk controls plus a stratified sample; model labels only where the model also labelled the person's cases and gap-class agreement has a 90% lower bound ≥90%, per control; agreeing cases re-checked; no model-reviews-model |
| N4 `confirmed` hides every real issue | Accepted | Redefined (design 6.2): confirmed = stated by a cited line or a reference lookup on a cited value; possible = heuristic patterns and absence-inferred defaults. Table of every current ISSUE source with its value |
| N5 client file a biased subset | Accepted | Every result appears in the client file; unreviewed ones as "Not reviewed", counted like NOT_ASSESSED; status over reviewed results with "reviewed x of y"; consultant confirms by result, aspect or application; must-review items bounded to top 10 per application; R-05 exception stated with markers and a verify rule |
| N6 deploy UNKNOWN everywhere | Accepted | Deploy and rollback become UNKNOWN only with a positive outside-marker; otherwise ABSENT. Label value "not decidable from the repository"; usually-outside controls consultant-confirmed. Design and spec lists aligned (replicas removed from the usually-outside list) |
| N7 BUILT overstatements | Accepted | Need-based N/A (2 of 8), ACC-2 (PRESENT only), `repo` search area, §6.1 split into BUILT and PLANNED (†), owners duplicate removed from the matrix, reference-data review status downgraded to PARTIAL; tasks T-1.22, T-1.25 |
| N8 export overclaims | Accepted | Export blocked until the upstream schema can carry `level` |
| N9 gate omissions, phase mismatch | Accepted | Gate item 3: severity sign-off and reference-data review status; client file placed in phase 2 consistently |
| N10 leak check on rebuilds | Accepted | Detectors re-run in memory on rebuild and standalone verify (T-1.23) |
| N11 runs and marks not bound to source | Accepted | Marks bound to control, state, evidence hash, catalogue version, source revision; verify reads at the recorded commit or refuses (T-1.26, T-2.2) |
| N12 D-9 changes R-12 and upstream G implicitly | Accepted | D-9 now states the amendment and the upstream departure with reasons; R-12 is amended only if D-9 is approved; continuous assurance placed as a later change under the portfolio view |
| N13 gate vs held-out refresh | Accepted | Baseline per corpus version; inspected held-out repositories move to tuning |
| N14 PARTIAL contradiction | Accepted | PARTIAL keeps its state with a note; lead sentence fixed |
| N15 `eval_fact` declared PRESENT | Accepted | T-1.12 widened to any PRESENT at level declared |
| N16 wrong-kind gaps unmeasured | Accepted | Wrong-gap-kind rate added; secondary measures reported (they gate nothing while validation is deferred) |
| N17 check-sourced controls after a crash | Accepted | T-1.24 |
| N18 vocabulary | Accepted | Certainty words aligned (text, parsed, semantic) in matrix and design; "Set wrongly" replaced by "Problem found" |
| N19 matrix residue | Accepted | Duplicates removed (owners, Groovy/Scala, DB timeouts); alerts NOT_ASSESSED; README-mention defect noted; added: runtime model and native image, gateway role, service discovery, log shipping, local run instructions. Now 159 items |
| N20 D-3 adoption criterion | Accepted | Fixed before the prototype: ≥30 person-checked candidates over ≥2 repositories; adopt a rule if its precision's 90% lower bound is ≥70%; shown only as "Possible issue" |
| N21 consistency rules use the writer's function | Accepted | Independent table-driven recomputation in verify (T-1.27) |
| Judgement: 5% target for high severity | Accepted for the deferred validation (design 7.4) |
| Judgement: concentrate the corpus | Accepted: weighted to the dominant stack |
| Judgement: D-10 wording in §9 | Accepted: "after D-10, … may change" |
| Judgement: gate state in summary and file name | Accepted (design section 2; T-1.19) |

Open questions:

1. Consultant confirms outside the checklist: yes, by result, aspect or application (design 8).
2. Unit of a corpus case: one per (control, repository); per-workload controls aggregated first (design 7.2).
3. Reference-table ISSUEs (end of support): confirmed, labelled with the reference data's review status.
4. `user:token@` in `run.json`: phase 1 refuses credentialed URLs before they are stored (T-1.6, extended to
   `inputs`, `sources[].spec` and the clone's git config).
5. Synthetic fixtures from disputes: written by an engineer; no client names, hostnames, package names, identifiers or
   values (design 8).
6. Report size at 300 applications: T-3.8.
