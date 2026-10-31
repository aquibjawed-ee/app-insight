# Evidence rules

1. A fact value is only `CONFIRMED` when at least one evidence item backs it: a file line (`path`, `line_start`, exact
   stripped `snippet`) or a captured command (`cmd`, `snippet`). Derived facts (e.g. `tests.coverage_state`) carry the
   evidence of their inputs and say how they were derived in `note`.
2. `NOT_FOUND` means the detector searched and found nothing. It is a bounded statement about the scanned files, never
   proof of absence. In the maturity layer it becomes `NO_EVIDENCE` ("No evidence of ..."), distinct from `NOT_MET`,
   which needs positive evidence (tests skipped via `-DskipTests`, OpenAPI disabled by config). Both score 0, but the
   report counts `no_evidence` separately so a score is not read as proven failure.
3. `UNKNOWN` means the answer cannot be had offline (remote CI template, no report on disk, detector failure).
   It is never rendered as "no" and never scored as a failure; the maturity criterion becomes `UNKNOWN` and is
   excluded from the score denominator.
4. `INFERRED` is allowed only where the code says so (`api.openapi_exposure`, `identity.app_id` without a remote).
5. `discover.py` re-reads every cited line after detection (`evidence.verify`). `validate.py check --repo` repeats this
   later, and compares the facts fingerprint, so edits to facts after generation are caught.
6. Nothing in `scripts/` calls a model, and nothing reads the network.
7. Untrusted-repo safety: symlinks (files and directories) are never read, XML with DTD/entity declarations is refused,
   and evidence snippets mask secret-looking literals (`password=...`, tokens, `Authorization:` values). `$VAR`
   references are kept. Redaction is applied identically when re-verifying, so redacted evidence still verifies.
8. `run_meta.inventory_fingerprint` hashes every scanned file's path and bytes. `validate.py check --repo` reports
   `STALE` when the repository no longer matches, so a later stage can tell a discovery has aged.
9. `run_meta.completeness` and `limitations` state what the scan did not do (no build, tests, CI or runtime) and travel
   with the data into the UI.
10. Commented-out lines (`#`, `//`, XML `<!-- -->`) are not evidence.
