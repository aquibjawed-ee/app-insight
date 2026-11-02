# Remedies and roadmap

## ADDED Requirements

### Requirement: Remedies come from packs and fit the stack
A gap SHALL be offered remedies only from the client's remedy packs, in pack order, and only those whose `requires`
values match the application's stack (CI system, build tool, framework, platform, version conditions); when no pack
remedy fits, the control's generic fix SHALL be shown (R-10).
Status: BUILT (commit 4f47cd7; `tests/test_verify.py::test_graceful_shutdown_on_an_old_spring_boot_is_an_upgrade`,
`tests/test_aspects.py`).

#### Scenario: a Jenkins application with no pipeline gap remedy
- WHEN the plugin's pipeline remedy requires GitLab
- THEN a Jenkins application gets the generic pipeline step, not `/modernise-pipeline`

### Requirement: Remedy requirements use the engine's vocabulary
Every value in a remedy's `requires` SHALL be a value the engine can produce for that key, and a test SHALL fail on
any value outside the declared vocabulary.
Status: PLANNED. Defect: the pipeline remedy requires `gitlab`, the engine produces `gitlab-ci` (found 2026-11-02).

#### Scenario: the GitLab defect
- WHEN a remedy requires `ci_system: gitlab`
- THEN the vocabulary test fails, naming the remedy, the key and the allowed values

### Requirement: Remedies state their preconditions
A remedy that needs another change first (a framework upgrade, a dependency) SHALL say so, and SHALL be offered after
that change in the roadmap order.
Status: PARTIAL (graceful shutdown on Spring Boot before 2.3 offers the upgrade remedy, commit 4f47cd7).

#### Scenario: health endpoint on an application without Actuator
- WHEN a Spring Boot application has no health endpoint and no Actuator dependency
- THEN the remedy says "add the Actuator dependency, then expose health", not "change the configuration"

### Requirement: The roadmap ranks by reach, and orders only by real dependency
The roadmap SHALL rank remedies by the number of gaps and applications they address, say "addresses", never
"closes", and draw an order between two remedies only when one is a precondition of the other.
Status: PARTIAL (ranking BUILT; wording and dependency-only ordering PLANNED, UI review A19, B16).

#### Scenario: two unrelated remedies
- WHEN a pipeline remedy and a README remedy have no dependency
- THEN they are not numbered as steps of one sequence

### Requirement: No effort, cost or value is invented
The product SHALL NOT estimate effort, cost, dates or business value for a remedy.
Status: BUILT (AGENTS.md rule 4; no such field exists in `aspects.json` or the packs).

#### Scenario: a client asks how long it takes
- WHEN the roadmap is shown
- THEN no duration appears; the consultant answers outside the tool
