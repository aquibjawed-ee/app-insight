# Detectors

Sections map 1:1 to `scripts/detectors/<name>.py` and to UI tabs. Source of truth is the code; this lists
what each fact means. Fact ids are `section.key`.

| Section | Key facts | Decided by |
|---|---|---|
| identity | `app_id`, `git_head`, `git_remote`, `git_branch`, `modules` | `git` command capture; pom/gradle files |
| stack | `build_tool`, `java_version`, `spring_boot_version`, `packaging`, `notable_dependencies`, `build_wrapper`, `language` | regex over pom.xml / build.gradle(.kts) (XML comments ignored) |
| build_ci | `ci_system`, `jobs`, `stages`, `includes`, `unresolved_includes`, `build_step`, `deploy_step`, `version_tagging` | CI files (`.gitlab-ci.yml` plus resolved `include: local:`, Jenkinsfile, GitHub workflows, ...) |
| tests | `unit_tests`, `integration_tests`, `acceptance_tests`, `contract_tests`, `performance_tests`, `ci_test_execution`, `build_level_test_skip`, `coverage_*` | files under `src/test`, build files, CI command lines, JaCoCo xml on disk |
| api | `http_endpoints_present`, `openapi_library`, `openapi_spec_files`, `openapi_exposure` | build files, `@RestController`/`@OpenAPIDefinition`, `application*.properties` |
| resilience | `multiple_instances`, `health_probes`, `rolling_or_zero_downtime_strategy`, `rollback`, `health_endpoint` | nomad/k8s/helm/compose descriptors, CI files |
| identity | `owners` | owners on the catch-all (or first) rule of CODEOWNERS |
| identity | `about` | first lines of the root README with headings, badges, HTML, tables, lists and code skipped and markup removed; at most 5 lines; secrets redacted |
| identity | `repository_url`, `pipeline_url` | derived from the git remote (credentials stripped) and the CI file; SSH aliases containing `github` are assumed to be github.com and labelled INFERRED |
| security | `secret_scanning`, `dependency_scanning`, `cloud_scanning`, `sast`, `dependency_updates`, `vulnerability_reports` | tool names in CI, build files and tool config files |

## States worth knowing

- `tests.ci_test_execution`: `enabled`, `partially_disabled`, `disabled_in_pipeline` (a CI mvn/gradle line carries `-DskipTests`,
  `-Dmaven.test.skip`, `-x test`), `disabled_in_build` (`<skipTests>true`, `test.enabled = false` in the build file),
  `unknown_remote_includes`, `no_test_command_found`, `no_ci`.
- `tests.coverage_state`: `no_tests`, `tests_disabled_in_pipeline`, `tests_present_coverage_not_configured`,
  `coverage_configured_not_enforced`, `coverage_enforced`.
- `tests.coverage_measured` is parsed from an existing `jacoco*.xml` under `target/` or `build/`; absent report = `UNKNOWN`.
- `api.openapi_exposure`: `exposed_via_library` is `INFERRED` (dependency present and not disabled; no running app queried).

## Known limits (v1)

Line-granular XML comment handling; a pom `<skip>` flag is only recognised in the forms in `tests.py`;
profiles/properties indirection (`${skip.tests}`) is not resolved; multi-module repos are aggregated, not
scored per module; Gradle version catalogs are read only for the Kotlin and Spring Boot versions (an entry must resolve through `version.ref`, and all matching entries must agree). Each limit fails toward `NOT_FOUND`/`UNKNOWN`
with the searched files visible in evidence, not toward a guess.

## Adding a stack

Add `detectors/<name>.py` exposing `detect(ctx) -> {key: fact}`, register it in `discover.ORDER`, add the
section to `schemas/discovery.v1.schema.json`, `evidence.iter_facts`, the UI `TABS`, and a test fixture.

`scan.py` (opt-in) adds `security.vulnerability_scan` from a local Trivy run: counts by severity, scanner and database version, scan time. `could_not_scan` when Trivy analysed no manifest.

Scored criteria added: integration tests, code scanning (SAST), automated dependency updates (Dependabot/Renovate config). Dependabot config counts as updates, not as dependency scanning.

Notes from running on a second real repo:
- Coverage tools: JaCoCo and Kover (plugin, `minBound`/`minValue` rule, XML report if on disk).
- Acceptance, performance and contract suites that live in another project but are triggered by a CI job are INFERRED and score PARTIAL; tests found in the repo are CONFIRMED and score MET. A CI stage name alone is never evidence.
- Test classes under a `functional`/`e2e`/`acceptance` path count as acceptance, under `contract` as contract, not as unit.
- Gradle modules come from `settings.gradle(.kts)` `include()`/`projectDir`; any `*.gradle(.kts)` file is read for build facts.
- `identity.working_tree_clean` records uncommitted changes (ignoring `.modernise/`); the other facts describe the working tree.

Coverage (`scripts/coverage_tools.py`, one registry for Java and Kotlin projects):

| Tool | Configured by | Enforced by | Reports read |
|---|---|---|---|
| JaCoCo | `jacoco` in a build file | `jacoco:check`, `jacocoTestCoverageVerification`, `violationRules` | XML, CSV, HTML summary |
| Kover | `org.jetbrains.kotlinx.kover`, `kover-maven-plugin` | `minBound(..)`, `koverVerify`, `minValue =` | XML, HTML summary |
| Cobertura | `cobertura` | `<check>`, `<totalLineRate>` | XML |
| Clover / OpenClover | `clover` | `targetPercentage` | XML |

Enforcement and threshold are only read from build files that mention the tool (a Checkstyle `check` goal is not a coverage gate). Several tools can be configured together (`jacoco+kover`). Reports are only parsed, never produced; JaCoCo `.exec` and Kover `.ic` binaries cannot be read. When several reports exist the choice is deterministic: configured tool first, then XML/CSV before HTML, then the largest (aggregate) report. A report older than the HEAD commit is INFERRED and marked stale. Adding a tool is one entry in `TOOLS` and, for reports, one in `REPORTS` plus a parser.

Provenance and honesty rules added after the independent audit:
- Every CONFIRMED fact cites evidence, or carries `derivation: {rule, inputs}`. `validate.py` checks each input exists and is itself supported (cites evidence, is a bounded NOT_FOUND search, or has a valid derivation) and rejects cycles. A derivation is not an exemption.
- `stack.language` is derived from `stack.java_sources` and `stack.kotlin_sources`, each citing a file.
- Coverage is judged on separate facts: `coverage_tool_configured`, `coverage_threshold_pct` / `coverage_enforced` (a minimum is configured), `coverage_gate_in_ci` (invoked_in_ci, wired_into_build, maven_lifecycle, not_shown, unknown_remote_includes, no_gate), `coverage_measured` and `coverage_run`. The coverage check is MET only when a minimum of 75% or more is configured and the pipeline runs or wires the gate. It is never a verified pass.
- OpenAPI: a generator dependency is MET (a spec is produced); a spec file alone is PARTIAL; serving the spec cannot be verified offline.
- `maturity.completeness` reports how many applicable checks could be determined (found or searched-and-absent) versus UNKNOWN, separately from the score.
- File citations carry the `module` they came from when the repository has more than one build module; `unit_tests.by_module` splits the unit-class count. Assessment itself stays repository-wide.

## Detail tabs
About, Stack, Tests (unit, integration, acceptance, contract, performance, coverage), Build & release, Operations, Security, Scan info. Every section is a table of Check / Result / What we found. Acceptance looks for Gherkin `.feature` files with Cucumber, Karate or Serenity; test classes in e2e, acceptance, journey or functional modules or `acceptanceTest` source sets; Postman collections; Cypress, Playwright or Selenium suites (config file, spec or test code); and pipeline jobs that trigger a suite kept in another project.

## Hosting, dependencies, modules and container (Stack tab)
- `stack.hosting`: `[{target, role, via[], basis[], at[]}]`; status UNKNOWN (not NOT_FOUND) when no descriptor or deploy command is found but a remote pipeline include or a Jenkins/TeamCity job may deploy it. Helm, Kustomize, Kubernetes manifests (`Deployment`, `StatefulSet`, `DaemonSet`, `CronJob`, `Job`, `Pod`) and `kubectl`/`helm` pipeline commands are one target, `Kubernetes`, with `via` naming what said so. A pipeline command counts only when it is the command a line runs (after `&&`, `;`, `|`, `sudo`), not text inside `echo`/`printf`/a string; `kubectl get` is not a deployment. `role` is `deployment target` (a descriptor such as a Kubernetes `Deployment`, Helm `Chart.yaml`, Nomad job, `serverless.yml` with provider aws, `app.yaml`, ECS task definition, or a pipeline command such as `kubectl apply`, `helm upgrade`, `gcloud run deploy`, `aws ecs update-service`) or `image registry` (ECR, GCR/Artifact Registry, ACR: where images are stored, not where they run). A cloud SDK dependency means the application uses that cloud's service and is never a deployment target; a compose file alone is not reported.
- `stack.external_dependencies`: `[{group, kind, technology, where, evidence_strength, embedded, basis[], modules[], hosts[], at[]}]`; `at[0]` is the citation that supports the claim shown, `modules` the build modules it was found in, `hosts` the literal hosts of an `Endpoint:` item. Groups: Data stores (database, cache, search, object storage, schema migrations), Messaging, Services it calls (named by a declared client), Identity and access, Configuration/secrets/discovery, Observability, Notifications, Stubs and emulators. `where` is `application`, `tests only`, `docker-compose only`, `tests and docker-compose only` or `a build profile only`; the UI lists test-only items in their own section. `evidence_strength` is `configured` (a connection setting, deployment value or declared client names it), `declared` (a dependency exists, no connection setting found), `named in source` (only a string literal in main source) or `compose`. Scope and basis are tracked as pairs, so a test-scope driver never strengthens a claim about the application.
- `stack.http_client_libraries`: Feign, REST client, Micronaut client, Ktor client, OkHttp, Retrofit, Apache HttpClient. A library says how calls are made, not which services are called, so it is never an item of `external_dependencies`.
- `Endpoint: <key>` items (Services it calls): a literal http(s) URL under a `…url / uri / endpoint / host` key in configuration, with hosts. It names an address the application is configured with, not what runs there; localhost, placeholders, documentation, callback/redirect/issuer keys and keys already typed as a database/broker/identity setting are skipped. Auth0, Okta, PingFederate, Cognito and Azure AD are recognised by key namespace or host.
- A database type is stated only when a driver, JDBC/R2DBC/Mongo scheme, driver class, dialect or `db-kind` says so. ORM or JDBC starters with no type anywhere are reported as `SQL database (type not stated)`; a JNDI data source likewise. The name of a `${placeholder}` is never read as evidence.
- Not counted: commented dependencies, a plugin's own dependencies, `dependencyManagement`/`pluginManagement` entries, exclusions, IDE output copies (`bin/main`), test modules (tests only), docs/samples paths. In-process caches (Caffeine, Ehcache) and pools (HikariCP) are not external services.
- Hosts are not resolved, and a service reached only at run time, through a client built in code, or through a URL held in a property is not named; a `@RegisterRestClient` with no name or `baseUri` is reported as `HTTP client interface: X`, which makes no claim about the service.
- `stack.module_list`: each build module's `name`, `path`, `build` and `role` (read from the build file; `null` when it cannot be told).
- `stack.container`: `image_build` (a Dockerfile; Jib; a Spring Boot `build-image` goal, `<image>` block, `bootBuildImage` block or pipeline command; or a Quarkus container-image extension that is switched on), `dockerfiles`, `base_images` (stage aliases and `$`-parameterised images are skipped), `compose_files`.
- `stack.container.jib` (when Jib is configured): `base_image`, `target_image`, `ports`, `main_class`, `run_by` (`the pipeline`, `a script the pipeline calls` or none), read from Maven `<configuration><from><image>` / `<to><image>` / `<container>` and Gradle `jib { from { image } to { image } container { ports mainClass } }` (Groovy and Kotlin DSL), plus `jib.from.image` / `jib.to.image` properties. A value held in a variable, a Maven `${property}` or `System.getenv(...)` is never reported as a string: `base_image_set_by_variable` / `target_image_set_by_variable` are true and the environment variable's name is given in `base_image_env` / `target_image_env`. When no `from` is configured the base image is reported as not set in the build; Jib's own default is never stated. The base image is also listed in `base_images`, and a registry named in `to` is reported by `stack.hosting` as an image registry. Commented-out Jib configuration is not an image build.
- Guards are proven, not assumed: `python3 benchmark/guard_check.py` removes each protection in a temporary copy of the skill and requires at least one fixture to fail (it reports UNPROVEN or STALE otherwise). XML (comments, `plugin`, `dependency`) is scanned in one linear pass, so a hostile pom with thousands of unclosed tags costs no more than a clean one.
- `stack.container.spring_boot` (when Spring Boot's image build is configured or run): `image_name`, `builder`, `run_image`, `publish`, `registry` (publishRegistry url), `bound_to_build` (a `build-image` goal in an execution) and `run_by`, from Maven `<image>` / Gradle `bootBuildImage {}` (Groovy and Kotlin DSL) and the pipeline command (`--imageName` too). `spring-boot-maven-plugin` alone (repackage) is a jar build, not an image build. Names held in variables, Maven properties or `System.getenv` are reported as set by a variable / environment variable, never as strings; defaults are never stated.
- `stack.container.quarkus` (when a `quarkus-container-image-*` extension is declared): `builder` (jib, docker, buildpack, openshift, s2i), `enabled` (true / false / null), `enabled_by` (`configuration` or `pipeline flag`), `push`, `image`, `registry`, `group`, `name`, `tag`, `base_image` (`quarkus.jib.base-jvm-image`), `ports`, `dockerfile`, `set_by_variable` and `run_by`. The extension alone builds nothing (`quarkus.container-image.build` defaults to false), so `enabled` stays null and `image_build` false. Only unprefixed and `%prod.` keys count (a `%dev.` or `%test.` value never builds the production image), a `%prod.` value wins over an unprefixed one, `-Dquarkus.container-image.build=true` in a pipeline file enables it, and a `${expression}` value is listed in `set_by_variable`, never as a string. Configuration is read repository-wide: in a repository of many Quarkus applications the values of different modules are merged.
