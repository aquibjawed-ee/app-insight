# Proposal: app-insight AS-IS baseline (revision 3)

Status: DECIDED 2026-11-02 (user sign-off: "approve all" after red-team round 3 approved with conditions), and
decision D-7 (consultant review, design section 8) DECIDED the same day after a focused round-4 review and two condition
checks. Phase 1 was started
before sign-off by user decision.

## Why

app-insight grew by fixing what each review found. Independent audits of six Gradle repositories reduced the errors
they found (the last, audit 6 on run 20261102-061233, found 47 of 48 "in place" claims correct and no high-severity
false negatives; model-audited, not a validated rate). Three questions on 2026-11-02 showed the product has no
agreed definition of what it must cover or how accuracy is proven:

1. "Can I run it on any JVM application and get accurate AS-IS results?" No. Nothing is measured beyond those six
   repositories; Maven, Quarkus, Micronaut, Jakarta EE, large multi-module builds, Kubernetes, ECS and Terraform
   deployments are unmeasured.
2. "How are we assessing resources not closed and N+1 queries?" We are not. Performance and data access, data
   correctness, application security in the code, scheduled jobs, git history, licences and more are not read, and
   the report does not say so. The upstream design decided several of these as assessment families.
3. "How are actions mapped?" Through remedy packs, and one mapping never fires (`gitlab` vs `gitlab-ci`).

The review then showed the product is not safe for client use today: the report is written before verification, a
failed run is not marked anywhere an agent or consultant reads, a crashed detector produces false gaps, and the leak
check cannot catch a pattern redaction misses.

## What changes

- **A client-use gate** (design section 2): internal use only until a verified run has been reviewed by the
  consultant, the client file is generated from that review (an unreviewed tool verdict is never shown), and the
  severity table is signed off.
- **The AS-IS scope made explicit** (`coverage-matrix.md`): 159 items in 25 areas, each with its status and how it
  can be known. Anything not covered is listed once on the report's Scope page.
- **Three perspectives** (AS-IS facts, assessment, portfolio) and **one assessment model**: code-level risk rules are
  assessment controls with a `confirmed` flag; the maturity score leaves the report; dimensions become derived views.
- **17 aspects** instead of 13 (adds Application security, Performance and data access, Data correctness and
  messaging, Modernisation readiness relative to a declared target).
- **The absence guard applies to every verdict derived from not finding something** (not found, not applicable by
  need, issue by default), and controls that usually live outside the repository are "not seen here, confirm".
- **Consultant review is the client-facing safeguard** (decided): confirm by result, aspect or application;
  must-review items first; a stop rule; marks bound to what was reviewed; disputed results become synthetic fixtures,
  never copies of client code.
- **Accuracy is measured internally, with honest statistics**: false-pass, false-gap and wrong-kind rates per control
  and stack value with exact bounds on a held-out set, a person's labels as the reference. Statistical validation that
  could be quoted to a client is deferred; its true size (100-200 repositories for one stack) is recorded.
- **A semantic-analysis prototype**, not a commitment, for N+1 candidates and resource handling.
- **Correctness and safety fixes first** (phase 1), then measurement (phase 2), then the report rebuild (phase 3),
  then wider coverage (phases 4, 5).

## Capabilities

| Capability | Spec |
|---|---|
| AS-IS scope and coverage | `specs/asis-coverage/spec.md` |
| Evidence and verdicts | `specs/evidence-and-verdicts/spec.md` |
| Assessment catalogue | `specs/assessment-catalogue/spec.md` |
| Accuracy assurance | `specs/accuracy-assurance/spec.md` |
| Remedies and roadmap | `specs/remedies/spec.md` |
| Report experience | `specs/report-experience/spec.md` |
| Ingestion, operation and safety | `specs/operation-and-safety/spec.md` |
| Relationships and portfolio | `specs/relationships-and-portfolio/spec.md` |

## Impact

Engine, catalogue and packs, product, report and tests. A JDK only if the semantic prototype is adopted (D-3).
Target repositories are never changed (R-08).

## Out of scope

Runtime observation, querying cloud or CI servers, effort and cost estimates, TO-BE design (beyond the declared
modernisation target), non-JVM language adapters.

## Decisions needed for sign-off

D-0 to D-11 in `design.md` section 12, each with a recommendation.
