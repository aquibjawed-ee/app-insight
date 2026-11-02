# Ingestion, operation and safety

## ADDED Requirements

### Requirement: Any mix of inputs, per client workspace
The CLI SHALL accept repository paths, folders of repositories, remote URLs and list files (.csv, .tsv, .xlsx, .txt),
and SHALL keep each client in its own workspace with its runs, clones and remedy packs (R-09).
Status: BUILT (commit f15ec0d; `app_insight/sources.py`, `cli.py:42-44`; `tests/test_sources.py`).

#### Scenario: two clients
- WHEN scans run for client A and client B
- THEN their clones, runs and reports are under different workspace folders and no run mixes them

### Requirement: Every source gets its own folder and identity
Each remote source SHALL be cloned into a folder unique to its host and full path, and each application SHALL have a
unique id; two repositories with the same name SHALL both be analysed under disambiguated ids.
Status: PLANNED. Today the clone folder uses the last two path segments (`sources.py:32-37`), so `teamA/payments/api`
and `teamB/payments/api` share one, and a duplicate application id stops the whole analysis (`relate.py:80-84`).

#### Scenario: two repositories called api
- WHEN `gitlab.acme/payments/api` and `gitlab.acme/orders/api` are scanned together
- THEN both are cloned to separate folders and appear as two applications with distinct ids

### Requirement: No credentials handled, nothing leaves the machine
Clones SHALL use the user's own git configuration with prompts disabled. A source URL carrying credentials
(`user:token@`) SHALL be refused before cloning and never stored. The product SHALL NOT send data to a network
service, and the report SHALL load no network resource. Optional tool runs that need a download (a vulnerability
database) SHALL say so and run only when asked (R-08).
Status: PARTIAL. BUILT: prompts disabled (`sources.py:135`), report has no network resources
(`tests/test_report.py`). PLANNED: refusing credentialed URLs (accepted and stored in `run.json` today).

#### Scenario: a URL with a token
- WHEN a list file holds `https://user:abc@gitlab.acme/payments/api.git`
- THEN that source is refused with "remove the credentials from the URL; clones use your git setup", and the token
  appears in no file

### Requirement: Target repositories are never changed or executed
The product SHALL only read target repositories: no build, no test run, no script execution, no writes. Optional tool
runs SHALL read source only, write outside the repository, and be checked by comparing the inventory fingerprint
before and after.
Status: BUILT for the engine (writes only to `--out`); PLANNED: the fingerprint check for tool runs.

#### Scenario: the semantic prototype runs
- WHEN the semantic analyser runs on a repository
- THEN the repository's inventory fingerprint is unchanged

### Requirement: Deterministic and model-agnostic
The same inputs at the same commits SHALL produce the same outputs apart from the run time, whoever runs it (R-01).
Status: BUILT (no model calls; `engine/tests/test_discovery.py::test_determinism`).

#### Scenario: two runs
- WHEN the same repositories are scanned twice with a fixed time
- THEN the analysis files are identical

### Requirement: Failures are visible and contained
A failed source, a failed detector, a failure in extraction, safety-net mapping or resilience for one repository, a
failed tool run and a failed verify SHALL each be named in the run summary, `summary --json` and the report; one
repository's failure SHALL NOT stop the others; the controls a failure feeds SHALL be NOT_ASSESSED.
Status: PARTIAL. BUILT: failed sources in the summary (`cli.py:88`), detector failures recorded in
`run_meta.failures`. PLANNED: per-repository isolation in `relate.py:88-99`; verify and detector failures in the
summary and report.

#### Scenario: resilience analysis raises on one repository
- WHEN resilience assessment raises for one of 300 repositories
- THEN the other 299 are reported, and that application's availability controls are NOT_ASSESSED with the reason

### Requirement: Agents can read the outcome
`summary --json` SHALL include the verify result, the rules broken, detector failures, failed sources and whether a
client file exists, so an agent following AGENTS.md rule 3 sees a failed run.
Status: PLANNED (`cli.py:68-89` carries none of these today).

#### Scenario: an agent reports a run
- WHEN verify failed on CON-3
- THEN `summary --json` has `"verify": {"ok": false, "rules": ["CON-3"]}`

### Requirement: It runs at portfolio scale
A scan of 300 repositories SHALL complete on a consultant's laptop; run time, peak memory and report size for a
reference portfolio SHALL be measured and recorded.
Status: PLANNED (a 200-application render test exists, `tests/test_report_scale.py`; no scan-time measurement).

#### Scenario: a 300-repository list
- WHEN a list of 300 repositories is scanned
- THEN the run completes and records duration, peak memory and report size
