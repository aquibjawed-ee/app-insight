# Assessment catalogue

## ADDED Requirements

### Requirement: Seventeen aspects, each a question a client recognises
The catalogue SHALL hold the 17 aspects of design section 9, each with one question. An aspect's status SHALL be the
worst of its decided controls (high gaps, gaps, in place where checked, in place), never a score; possible issues
SHALL NOT raise it.
Status: PARTIAL (13 aspects BUILT, commit 4f47cd7, `tests/test_aspects.py::AspectsTest.test_catalogue_is_consistent`,
`tests/test_aspects.py::AspectsTest.test_an_aspect_with_unchecked_controls_is_never_plain_in_place`; 4 new aspects PLANNED, decision D-2).

#### Scenario: an aspect with nothing decided
- WHEN every applicable control of an aspect is UNKNOWN or NOT_ASSESSED
- THEN the aspect is "not checked", not "in place"

### Requirement: Aspects are the only assessment model
The maturity score and band SHALL NOT be shown in the report; every dimension shown SHALL be derived from aspect
controls or AS-IS facts, and verify SHALL fail when a dimension headline disagrees with the controls it summarises.
Status: PLANNED (decision D-9). Today `ui/core.js:64` shows "Maturity N%", and audit 6 found four
dimension-versus-aspect disagreements.

#### Scenario: coupling headline
- WHEN calls matched is UNKNOWN for an application
- THEN the coupling dimension does not say "0 unresolved", and verify fails if it does

### Requirement: Every control declares where it looks, what can hide it, and what it depends on
Every control with a detector SHALL declare `search.in`, `search.for` (only places actually read), `search.blind_to`
when narrower, `depends_on` (the stack dimensions that change how it is detected: build tool, framework, language, CI
system, platform), and `usually_outside` when the setting usually lives outside the repository. A catalogue test SHALL
fail on a missing declaration.
Status: PARTIAL (`search` declared for every control that can be ABSENT, commit 9479a59; `depends_on`,
`usually_outside` and the test PLANNED).

#### Scenario: a new control without declarations
- WHEN a control is added with a detector and no `depends_on`
- THEN the catalogue test fails and names the control

### Requirement: Controls that usually live outside the repository
Secret scanning, dependency update automation, branch protection, backups, and alerting and SLOs SHALL carry
`usually_outside`; with nothing found they are UNKNOWN, "Not seen in the repository; confirm with the team", and are
always consultant-confirmed. Deploy and rollback SHALL become UNKNOWN only when a positive marker shows deployment
happens elsewhere (Argo CD or Flux manifests, image-updater settings, a CI step that pushes to a manifest repository,
and not an image published with no deploy step, which is also the shape of a manual deploy); otherwise they stay ABSENT with the search record.
Status: PLANNED, phase 1 T-1.9 (review-03 agreement; red-team 1 F9, 2 N6).

#### Scenario: no deploy automation and no marker
- WHEN a service has no CI deploy step, no runbook and no GitOps marker
- THEN "Automated deploy" is "Not found" with its search record, a high-severity gap

#### Scenario: Dependabot enabled at organisation level
- WHEN no Dependabot or Renovate file exists in the repository
- THEN dependency updates is UNKNOWN "not seen here, confirm", not a medium gap

### Requirement: Framework-bound controls declare the frameworks they understand
A control whose detector reads one framework's conventions SHALL list them in `understands`; outside them the result
is UNKNOWN, "Not recognised for <framework>".
Status: BUILT (8 controls, commits 4f47cd7, 9479a59; `tests/test_aspects.py::AspectsTest.test_a_spring_only_check_says_not_recognised_for_another_framework`).

#### Scenario: a Micronaut service and structured logging
- WHEN structured logging understands Spring Boot and Spring only
- THEN a Micronaut service gets UNKNOWN, "Not recognised for Micronaut"

### Requirement: New controls for Application security
The catalogue SHALL add: authentication mechanism configured; endpoints without access rules; route or method
authorisation present; CORS and CSRF configuration; management endpoints exposed without authentication; TLS
verification disabled in code; weak hashing or insecure random in security code; SQL built by string concatenation.
Configuration facts are certainty `text`; code patterns are possible issues unless the semantic tier confirms them.
A gateway, service mesh or platform authentication named in the repository is a blind spot for the authentication
controls.
Status: PLANNED.

#### Scenario: no security framework on a service with endpoints
- WHEN a Spring Boot service exposes endpoints and has no security dependency or filter chain
- THEN "Authentication mechanism configured" is ABSENT with its search record
- AND if an API gateway or service mesh is named in the repository it is UNKNOWN instead

### Requirement: New controls for Performance and data access
The catalogue SHALL add: open session in view left on; eager fetching on collections; N+1 query candidates; list
endpoints without pagination; resources not closed; unbounded thread pools and queues; caches without expiry or size.
All SHALL be possible issues (open session in view: the default is on unless set outside the files read); "resources not closed" SHALL report only
what the analyser reports, at its certainty. Missing indexes, full scans, lock contention and cache stampede are OUT
(they need query plans or runtime data) and listed on the Scope page.
Status: PLANNED (open-in-view and eager fetch from files, phase 4; the rest semantic prototype, phase 5).

#### Scenario: eager fetching
- WHEN an entity declares `@OneToMany(fetch = FetchType.EAGER)`
- THEN "Eager fetching on a collection" is a possible issue citing the line

### Requirement: New controls for Data correctness and messaging
The catalogue SHALL add: consumer acknowledgement or offset commit mode stated; producer acknowledgement and
idempotence; consumer idempotency; write and publish without an outbox; optimistic locking on concurrently updated
entities; transactions spanning remote calls; ordering and concurrency settings on consumers. Code-pattern controls
SHALL be possible issues.
Status: PLANNED.

#### Scenario: database write and Kafka send in one method
- WHEN a `@Transactional` method saves an entity and calls `kafkaTemplate.send`
- THEN "Write and publish without an outbox" is a possible issue citing both lines

### Requirement: Modernisation readiness is relative to a declared target
Modernisation controls (javax where the target needs jakarta; APIs removed in the target Java or framework version;
build tool too old for the target JDK; local filesystem writes; in-memory session state; hard-coded hosts) SHALL raise
gaps only against a target the consultant declares for the run; with no target they SHALL show as AS-IS facts.
Reference data SHALL carry source and review status (R-11).
Status: PLANNED.

#### Scenario: no target declared
- WHEN a Spring Boot 2 application imports `javax.persistence` and no target is declared
- THEN the AS-IS view shows "javax namespace: 214 imports" and no gap is raised

### Requirement: Controls with no detector, and tools not run, are a tool gap
A control with no detector, and a control whose tool (semantic tier, vulnerability scan) was not run, SHALL be listed
once on the Scope page and SHALL NOT appear per application or in any count (R-17).
Status: PARTIAL (pending controls excluded from coverage, commit 4f47cd7; still listed per application; tool-not-run
results per application today).

#### Scenario: no vulnerability scan
- WHEN `scan.py` was not run
- THEN the Scope page says "vulnerability scan not run" once, and no application shows it as not checked

### Requirement: Severity is a signed-off policy
Each control's severity SHALL come from the catalogue; the table SHALL be signed off by a person, versioned, include
`critical` in the sort order, and be shown with its status until signed off.
Status: PARTIAL (severities exist; status DRAFT; `critical` missing from `aspects.py:18`; decision D-6).

#### Scenario: an end-of-support framework
- WHEN a framework's support has ended
- THEN its severity is the signed-off one, the same for every application
