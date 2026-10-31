# app-discovery accuracy benchmark

Independent of the discovery output. Stdlib only, no production dependencies; the engine is imported read-only.

```bash
python3 benchmark/run_benchmark.py --out <dir>        # report.json + report.md; exit 1 if a gate fails
python3 benchmark/visual_check.py --out <dir> [--screenshots]   # rendered-DOM regression check of the HTML view: selected tab, non-empty tab, no undefined/NaN/null text, no script error, cell counts, and no horizontal scroll at 1440px (needs Chrome)
```

## Ground truth
Each case is `fixtures/<name>/{repo/, case.json}`. `repo/` is a small real project; `case.json` is what a careful reviewer who reads
those files would conclude (categories: positive, negative, contradictory, insufficient). Expectations are written by hand from
the files. **There is no command that writes or refreshes them from engine output, and a failing expectation is never edited to
match the engine.** Fix the engine, or mark the expectation `"unsupported": "<reason>"` so it is reported as a documented
limitation. If an unsupported expectation starts passing the report says so, so the label gets reviewed.

Expectation kinds: `facts` (value, `path` into a value, `value_includes`, `status` allowed list, note checks), `criteria`
(allowed results, or `absent` for not-applicable), `never_met` / `never_met_all` (false-MET guards), `forbid_in_output`
(redaction and symlink safety), `citation_modules`. `setup` can add a remote, a commit, uncommitted files, files older than the
commit, and symlinks to outside the repository. Each expectation names a `rule` so failures group by rule as well as detector.

## Measures (reported separately)
| measure | definition |
|---|---|
| fact precision | of the positive claims (CONFIRMED/INFERRED and a non-empty value) the engine makes about labelled facts, the share that match the label |
| fact recall | of the labelled facts that are expected to be found, the share found correctly (documented-unsupported ones count as misses) |
| MET precision / recall | same, for criteria scored MET; **false MET** is any MET where the label does not allow MET (hard gate) |
| evidence integrity | share of CONFIRMED facts, over every fact in every document (not only labelled ones), that cite verifying evidence or have a valid derivation chain; bounded NOT_FOUND observations count as support |
| determinism | a second run on a fresh copy of the same repository is identical apart from `generated_at` |

Gates (exit 1 if any fails): no expectation failures, no false MET, no unsupported CONFIRMED fact, no invalid citation,
schema and provenance valid on every document, deterministic replay.

## Known limits of the benchmark
- 32 small synthetic repositories: they test rules, not the variety of real codebases. Treat a pass as "no known rule regressions".
- Labels cover the facts a case is about, not every fact; integrity and determinism are checked on everything.
- The 50% partial-run cut-off and the staleness rule are policy choices, so their fixtures test consistency with the policy.
