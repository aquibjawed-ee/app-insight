# AS-IS coverage matrix

What an application's AS-IS consists of, and what app-insight knows about each item today. This is the answer to
"did we miss anything": every item is listed here with a status. An item that is not covered is shown once in the
report's Scope page, never silently absent (R-17).

**How it is known**

| Code | Method | Strongest certainty it can reach |
|---|---|---|
| F | Reading files: build files, configuration, CI files, deployment files, source as text | text |
| S | Analysis of the code through a JVM tool | parsed (no classpath) or semantic (types resolved) |
| G | Git history of the repository (local clone) | text (fact about history) |
| T | An optional tool run on the repository (vulnerability scanner, licence scanner, static analyser) | as good as the tool |
| X | Only outside the repository (platform settings, CI server jobs, monitoring, runbooks elsewhere, the client) | not decidable here: asked, never assumed |

**Status**: BUILT (fact or control exists; facts named are keys in `discovery.json` or files under `analysis/<app>/`),
PARTIAL (some of it), PLANNED, NOT_ASSESSED (a control is in the catalogue but has no detector yet), OUT (out of
scope for this baseline, said so in the report).

**BUILT means implemented, never validated.** Accuracy is measured internally (`design.md` section 7); a result is
shown to a client only after the consultant confirms it (decision D-4, 2026-11-02).

Statuses below were checked against the code on 2026-11-02 (commit 9479a59), and corrected after red-team reviews 1 to 3. "Checked on six repos" means covered by
audits 1-6, all Gradle; nothing here is yet measured on a labelled corpus (see accuracy-assurance).

---

## A0. What was read (file roles)

| Item | How | Status | Where today / note |
|---|---|---|---|
| Files read per area, and why each counts | F | BUILT | `scope.files_read` (commit 9479a59) |
| File role: application, build, CI, deployment, configuration, test, fixture or mock, example, generated, build output | F | PARTIAL | deployment-file roles (`graph/resilience.py:47-49`) and build output folders `target`, `build`, `out`; IDE output such as `bin/` is read as configuration today |
| Places named but not in the repository (blind spots) | F | BUILT | `scope.blind_spots` (commit 9479a59) |

## A1. Identity and ownership

| Item | How | Status | Where today / note |
|---|---|---|---|
| Name, repository URL, branch, commit | F, G | BUILT | `identity.app_id`, `repository_url`, `git_branch`, `git_head` |
| What the application does | F | BUILT | `identity.about` (README description) |
| Owners (CODEOWNERS, README, build) | F | PARTIAL | `identity.owners` reads CODEOWNERS only (`detectors/identity.py:14-18`); README and build owners not read, and the search record must say so |
| Team, business criticality | input list | PARTIAL | `team` shown; the list file's `criticality` column is carried but not shown, and the criticality dimension reads only `--criticality`; never inferred |
| Lifecycle status (active, legacy, retiring) | G, X | PLANNED | from last-commit age (G); stated status only from the client (X) |
| Application boundary: deployable units in a repository; one application spread over several repositories | F, X | PLANNED | today one repository = one application |
| Users and business capability served | X | OUT | the client supplies it; never inferred |

## A2. Language, runtime and framework

| Item | How | Status | Where today / note |
|---|---|---|---|
| Languages and their share | F | PARTIAL | `stack.language`, `java_sources`, `kotlin_sources`; Groovy/Scala counted as source but not reported |
| Java version (source/target, toolchain) | F | BUILT | `stack.java_version` (lowest when several; INFERRED) |
| Kotlin version | F | BUILT | `stack.kotlin_version` |
| JDK vendor and distribution (base image, toolchain vendor) | F | PLANNED | licensing differs by vendor |
| Framework and version (Spring Boot, Spring, Quarkus, Micronaut, Dropwizard, Jakarta EE) | F | PARTIAL | `stack.app_framework`, `spring_boot_version`; Jakarta EE / plain servlet apps and app servers not recognised as a framework |
| Application server (Tomcat, WildFly/JBoss, WebLogic, WebSphere, Liberty) | F | PLANNED | packaging is read (`stack.packaging`); the target server is not |
| Packaging (jar, war, ear) | F | BUILT | `stack.packaging`, `artifact_kind` |
| Support status of Java and framework | F + reference data | BUILT | `dimensions.technology_lifecycle`; Spring Boot per line (spring.io) and Dropwizard dates UNREVIEWED (R-11) |
| javax vs jakarta namespace | F | PLANNED | read in places for other checks; not reported |

## A3. Build system and modules

| Item | How | Status | Where today / note |
|---|---|---|---|
| Build tool and wrapper version | F | BUILT | `stack.build_tool`, `build_wrapper`; Ant, sbt, Bazel, Mill, Leiningen are blind spots (`scope.blind_spots`) |
| Build tool version compatible with the JDK (for example Gradle 2.x cannot run on Java 9+) | F + reference data | PLANNED | |
| Modules and their layout | F | BUILT | `stack.module_list`, `identity.modules` |
| Parent POM / convention plugins from outside the repo | F | BUILT | `scope.blind_spots` (`build.parent_pom`, `build.org_plugin`, `build.remote_script`) |
| Build plugins (quality, coverage, release, packaging) | F | PARTIAL | read per check (coverage, SAST, release); no single list |
| Reproducibility (wrapper, pinned plugin versions, lock files) | F | PLANNED | |

## A4. Libraries and dependencies

| Item | How | Status | Where today / note |
|---|---|---|---|
| Declared dependencies by kind (DB, messaging, HTTP client, observability, ...) | F | BUILT | `stack.external_dependencies` (60+ technologies), `notable_dependencies` |
| Full declared dependency list with versions | F | PARTIAL | read, not reported as a list; versions not resolved through BOMs (limitation stated) |
| Internal shared libraries (the organisation's own artifacts) and their versions across the portfolio | F | PLANNED | needed for upgrade waves; matched by group id prefix |
| Resolved dependency tree | T (build tool) | OUT | needs the build to run; contradicts R-08 unless run in a sandbox the client approves |
| Outdated and end-of-life libraries | F + reference data | PLANNED | control `platform.libraries_current` is NOT_ASSESSED |
| Known vulnerabilities in dependencies | T | PARTIAL | opt-in `scan.py`; without it `security.exposure_known` is NOT_ASSESSED |
| Removed or deprecated APIs blocking an upgrade | S, F | PLANNED | see A24 |

## A5. Application structure and components

| Item | How | Status | Where today / note |
|---|---|---|---|
| Components: controllers, services, repositories, listeners, clients | F | BUILT | relationship graph nodes (`relationships.json`), C4 view |
| Scheduled jobs (`@Scheduled`, Quartz, cron) | F | PLANNED | not read at all today |
| Batch jobs (Spring Batch) | F | PLANNED | |
| Runtime model: servlet or reactive; native image (GraalVM) | F | PLANNED | |
| Web tier technology (JSP, JSF, Struts, GWT, Thymeleaf, an embedded single-page app) | F | PLANNED | |
| Entry points (main classes, servlet init, CLI) | F | PARTIAL | HTTP and messaging entry points read; main/batch/CLI not |
| Layering and dependency rules between packages | S | PLANNED | |
| Size: lines of code, classes, modules | F | PLANNED | |

## A6. Interfaces exposed (inbound)

| Item | How | Status | Where today / note |
|---|---|---|---|
| REST endpoints (method, path) | F | BUILT | `api.http_endpoints_present`, graph `ApiEndpoint` nodes (Spring MVC, WebFlux, JAX-RS, Ktor, Micronaut, Quarkus) |
| OpenAPI spec and generator | F | BUILT | `api.openapi_*` |
| Message consumers (topic/queue) | F | BUILT | graph `CONSUMES_FROM` |
| SOAP / WSDL services | F | PLANNED | not read |
| gRPC, GraphQL, WebSocket | F | PARTIAL | dependency recognised; services/endpoints not listed |
| API versioning and compatibility checks (path or header versions, contract diffs) | F | PLANNED | upstream F-048, F-050 |
| Who calls this application | F (portfolio) | BUILT | portfolio graph, only among analysed applications |
| Role in the estate: API gateway, edge service, BFF | F | PLANNED | gateway routes (Spring Cloud Gateway, Zuul) read as relationships today; the role is not stated |

## A7. Interfaces consumed (outbound) and integrations

| Item | How | Status | Where today / note |
|---|---|---|---|
| Outbound HTTP calls and targets | F | BUILT | graph `CALLS_API` (RestTemplate, WebClient, Feign incl. `Feign.builder()`, Retrofit, OkHttp, ...); targets from literals, resolvable placeholders, constants |
| Service URLs named in configuration but not traced in code | F | BUILT | `runtime.service_urls`, `architecture.calls_matched` |
| Third-party SaaS (mail, SMS, payment, identity providers) | F | BUILT | `stack.external_dependencies` (SendGrid, Twilio, OAuth2/OIDC, LDAP, ...) |
| Service discovery and registry (Eureka, Consul discovery, Kubernetes services) | F | PARTIAL | dependency recognised (`stack.external_dependencies`); registered name not used to match calls |
| Object and file storage (S3, Blob, GCS, SFTP, shared folders) | F | PARTIAL | S3, Blob, GCS, MinIO recognised; SFTP and file-share integrations not |
| Calls through in-house wrappers or generated clients | S | PLANNED | limitation stated; becomes UNKNOWN via `calls_matched` |

## A8. Data stores and data access

| Item | How | Status | Where today / note |
|---|---|---|---|
| Databases, caches, search engines used | F | BUILT | `stack.external_dependencies`, graph `READS_FROM` / `WRITES_TO` |
| Database shared with another analysed application | F | BUILT | `architecture.no_shared_database` |
| Entities and repositories | F | PARTIAL | repository base types read; entity model not reported |
| Schema migrations (Flyway, Liquibase) | F | BUILT | `data.migrations` |
| Transaction boundaries (`@Transactional` placement, propagation) | S | PLANNED | see A19 |
| Native SQL, stored procedures | F | PLANNED | |
| Database vendor, version and SQL dialect lock-in | F | PARTIAL | vendor from driver; version and dialect-specific SQL not read |
| Personal or sensitive data held (data classification) | F, X | PLANNED | field-name signals only (F); classification from the client (X) |
| Backups and restore | X | NOT_ASSESSED | `data.backups` pending; usually outside the repo |

## A9. Messaging

| Item | How | Status | Where today / note |
|---|---|---|---|
| Brokers, topics and queues, producers and consumers | F | BUILT | graph messaging adapter (Kafka, RabbitMQ, JMS, SQS/SNS, Pub/Sub, ...) |
| Consumer error handling (DLT/DLQ, error handler, retry) | F | BUILT | `runtime.messaging_errors` (Spring only; others UNKNOWN) |
| Acknowledgement / offset commit mode, transactions | F | PLANNED | upstream F-057, F-058 |
| Producer settings (acks, idempotent producer, retries) | F | PLANNED | upstream F-057 |
| Ordering, concurrency, prefetch, rebalance handling | F, S | PLANNED | |
| Idempotent consumers, duplicate handling | S | PLANNED | potential issue only (R-13) |
| Message schemas and registry (Avro, JSON schema) | F | PARTIAL | `contract` facts for schemas in repo; registry not |

## A10. Configuration and environments

| Item | How | Status | Where today / note |
|---|---|---|---|
| Configuration files and profiles | F | BUILT | `scope.files_read.config`, profile handling in relationships |
| Values that differ between profiles | F | BUILT | graph `profile_differences` |
| Configuration from outside the repo (config server, Consul, Parameter Store, config tree) | F | BUILT | `scope.blind_spots` (`config.external`) |
| Environment variables required at start | F | PLANNED | placeholders with no default |
| Feature flags | F | PLANNED | |
| Effective value of a setting after precedence | F | PLANNED | upstream F-096; today a setting is read where written |

## A11. Secrets

| Item | How | Status | Where today / note |
|---|---|---|---|
| Secrets committed in code, build, CI and key files | F | BUILT | `security.secrets_committed` (redacted) |
| Secrets as literals in configuration | F | BUILT | `security.secrets_in_config` |
| Secret store in use (Vault, Secrets Manager) | F | BUILT | `stack.external_dependencies` |
| Secrets in git history (removed later) | G | PLANNED | |

## A12. Build and delivery pipeline

| Item | How | Status | Where today / note |
|---|---|---|---|
| CI system and pipeline files | F | BUILT | `build_ci.ci_system`, `ci_files`; GitLab, GitHub Actions, Jenkins, CircleCI, Azure, Bitbucket parsed; others blind spots |
| Build, test, publish, tag, deploy, rollback steps | F | BUILT | `build_ci.*`, maturity criteria |
| Pipeline outside the repository (named in README) | F | PARTIAL | UNKNOWN with the citation; defect: a bare mention of a CI product counts (`build_ci.py:37-38`, T-1.11) |
| Manual deploy documented | F | BUILT | `build_ci.manual_deploy_documented` |
| Shared templates, libraries, reusable workflows | F | BUILT | `scope.blind_spots` |
| Branch protection and required reviews | X | PLANNED | usually outside: "not seen here, confirm" (design 6.6) |
| Environments and promotion path | F | PARTIAL | inventories (Ansible) and deploy jobs read; no environment model |
| DORA measures (deploy frequency, lead time) | X | OUT | needs CI server history |

## A13. Deployment and hosting

| Item | How | Status | Where today / note |
|---|---|---|---|
| Platform (Kubernetes, Nomad, Compose, Ansible/VM) | F | BUILT | `resilience.json`, `stack.hosting` |
| Container image, base image, pinning | F | BUILT | `stack.container`, `availability.image_pinned` |
| Container and deployment security posture (non-root user, read-only filesystem, securityContext, network policy) | F | PLANNED | |
| Replicas, probes, rollout, resources, autoscaling, disruption budget, spread | F | BUILT | 13 `availability.*` controls (Kubernetes, Nomad, Compose, Ansible) |
| Helm charts rendered | T | OUT | templates not rendered (limitation stated) |
| Terraform, ECS, CloudFormation, Cloud Foundry, OpenShift, Serverless, App Engine, Beanstalk | F | PARTIAL | named as blind spots; availability then NOT_ASSESSED with the tool named; not read |
| Deployment held in another repository, GitOps (Argo CD, Flux, image updater) | F, X | PLANNED | today the high-severity deploy control is ABSENT when no CI step deploys; becomes UNKNOWN only with a positive GitOps or outside-pipeline marker (design 6.6), otherwise stays "Not found" |

## A14. Testing

| Item | How | Status | Where today / note |
|---|---|---|---|
| Unit, integration, acceptance, contract, performance tests (counts, tools) | F | BUILT | `tests.*` |
| Context-load-only tests | F | PARTIAL | recognised (`CONTEXT_ONLY`) and excluded; the exclusion is not stated in the summary |
| Tests run in CI, skipped or disabled | F | BUILT | `tests.ci_test_execution`, `build_level_test_skip`, `ci_skip_flags` |
| Coverage tool, threshold, gate in CI | F | BUILT | `tests.coverage_*` |
| Which entry points a test reaches | F | BUILT | `safetynet.json` |
| Tests with no assertion | F | PARTIAL | `safetynet.json` reports `mapped_no_assertion_seen`; not a control |
| Mutation score | T | OUT | needs a build (R-08) |

## A15. Security in the code

| Item | How | Status | Where today / note |
|---|---|---|---|
| Scanners configured and run (secret, dependency, SAST) | F | BUILT | `security.*`, `delivery` criteria |
| Authentication mechanism (Spring Security, OAuth2 resource server, JWT, basic, LDAP) | F | PLANNED | not read today |
| Endpoints left unauthenticated; method security | F, S | PLANNED | |
| CORS, CSRF, security headers | F | PLANNED | |
| Weak crypto, insecure random, TLS verification turned off | F, S | PLANNED | |
| SQL built by string concatenation, deserialisation of untrusted data | S, T | PLANNED | potential issue unless the tool confirms (R-13) |
| Actuator / management endpoints exposed | F | PARTIAL | health exposure checked against security config only |

## A16. Runtime resilience

| Item | How | Status | Where today / note |
|---|---|---|---|
| HTTP client timeouts | F | BUILT | `runtime.http_timeouts` |
| Retries and circuit breakers | F | BUILT | `runtime.retries_breakers` (Spring only) |
| Bulkheads, rate limits, overall call deadlines | F | PLANNED | |
| Database timeouts and pools | F | BUILT | `runtime.db_timeouts` |
| Graceful shutdown | F | BUILT | `runtime.graceful_shutdown` |
| Thread pools and executors bounded | S | PLANNED | see A17 |
| Startup dependencies (fails fast vs waits) | F | PLANNED | |

## A17. Performance and resource use

| Item | How | Status | Where today / note |
|---|---|---|---|
| Open session in view (Spring JPA default) | F | PLANNED | a single setting; decidable |
| Eager fetching on collections | F | PLANNED | annotation; a warning, not an issue |
| N+1 query candidates (repository or lazy collection inside a loop) | S | PLANNED | potential issue only; confirmed needs a query-count test (out of scope) |
| Unbounded queries, missing pagination on list endpoints | S | PLANNED | potential |
| Resources not closed (streams, connections, statements) | T (PMD `CloseResource`), S | PLANNED | as reported by the tool |
| Caching in use, cache expiry and size set | F | PLANNED | |
| Missing indexes, full scans, lock contention, cache stampede | S, runtime | OUT | need query plans or runtime data; upstream G lists them; candidates only via semantic tier later |
| Unbounded thread pools, queues, in-memory collections | S | PLANNED | potential |
| JVM memory and GC settings | F | PARTIAL | container memory read; JVM flags not |

## A18. Data correctness and consistency

| Item | How | Status | Where today / note |
|---|---|---|---|
| Write to database and publish a message in one operation without an outbox | S | PLANNED | potential issue (upstream: high-severity family) |
| Optimistic locking (`@Version`) on entities updated concurrently | S | PLANNED | potential |
| Idempotency keys on inbound requests and consumers | S | PLANNED | potential |
| Transactions spanning remote calls | S | PLANNED | potential |
| Concurrency: deadlock-prone lock ordering, shared mutable state | S | PLANNED | potential only |

## A19. Observability and operations

| Item | How | Status | Where today / note |
|---|---|---|---|
| Health endpoint and its exposure | F | BUILT | `observability.health` |
| Metrics export | F | BUILT | `observability.metrics` |
| Tracing | F | BUILT | `observability.tracing` |
| Structured logging | F | BUILT | `observability.structured_logging` |
| Log shipping (agent, appender to a log service) | F | PARTIAL | log service dependencies recognised (Sentry, Datadog); appenders and agents not reported |
| Correlation IDs propagated | F, S | PLANNED | |
| Alerts, dashboards, SLOs in the repo | F, X | NOT_ASSESSED | control pending; usually outside the repository (consultant-confirmed) |
| Runbooks | F | PARTIAL | read for manual deploys only |

## A20. Code health

| Item | How | Status | Where today / note |
|---|---|---|---|
| Complexity and duplication | T, S | NOT_ASSESSED | control pending |
| Static analysis findings (existing reports in the repo) | F | PARTIAL | vulnerability reports read; quality reports not |
| Dead code, unused dependencies | S | PLANNED | |
| Deprecated API use | S | PLANNED | |

## A21. Change activity (git history)

| Item | How | Status | Where today / note |
|---|---|---|---|
| Last change, commit frequency, age | G | PLANNED | |
| Contributors and knowledge concentration (bus factor) | G | NOT_ASSESSED | control pending |
| Hotspots (churn x complexity) | G, S | NOT_ASSESSED | control pending |

## A22. Knowledge and documentation

| Item | How | Status | Where today / note |
|---|---|---|---|
| README with a description | F | BUILT | `knowledge.readme` |
| How to build and run locally (README instructions, compose for local) | F | PLANNED | onboarding signal |
| Architecture decision records | F | NOT_ASSESSED | control pending |
| API documentation | F | BUILT | via OpenAPI |
| Diagrams in the repo | F | PLANNED | |
| Documentation drift (docs naming endpoints, modules or settings that no longer exist) | F | PLANNED | upstream F-052, F-083 |

## A23. Supply chain and licences

| Item | How | Status | Where today / note |
|---|---|---|---|
| Dependency update automation | F | BUILT | `security.dependency_updates` |
| SBOM produced | F | PLANNED | plugin presence (CycloneDX, SPDX) |
| Artifact signing, provenance | F | PLANNED | |
| Licences of dependencies | T | PLANNED | needs a resolved tree or a licence scanner |

## A24. Modernisation readiness

| Item | How | Status | Where today / note |
|---|---|---|---|
| Upgrade path for Java and framework (what the next version removes) | F + reference data | PARTIAL | `engine/rules/compat.v1.json` and change-impact run for Java runtime |
| javax to jakarta migration needed | F | PLANNED | |
| Containerisation readiness (filesystem writes, local state, config from env) | F, S | PLANNED | twelve-factor signals |
| Cloud readiness (sticky sessions, local files, hard-coded hosts) | F, S | PLANNED | |

---

## Languages and stacks beyond the JVM

The product is described as also covering Node.js, React, C++ and Terraform. Today the engine reads JVM repositories
only; a repository in another language is listed with what could be read (CI, deployment, secrets, documentation) and
every language-specific control NOT_ASSESSED with the reason. Other language adapters are a later change.

## Counts

| Status | Items |
|---|---|
| BUILT (implemented, not validated) | 54 |
| PARTIAL | 26 |
| PLANNED | 67 |
| NOT_ASSESSED (a control exists, no detector yet) | 6 |
| OUT | 6 |
| **Total** | **159 items in 25 areas (A0-A24)** |

(Counted from the tables above; recounted by `tasks.md` T-1.2 when this file changes.)
