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
| Files read per area, and why each counts | F | BUILT | `scope.files_read` (commit 9479a59); test `engine/tests/test_accuracy.py::ScopeTest.test_an_ordinary_repository_has_none_and_records_what_was_read` |
| File role: application, build, CI, deployment, configuration, test, fixture or mock, example, generated, build output | F | PARTIAL | deployment-file roles (`graph/resilience.py:47-49`) and build output folders `target`, `build`, `out`; IDE output such as `bin/` is read as configuration today |
| Places named but not in the repository (blind spots) | F | BUILT | `scope.blind_spots` (commit 9479a59); test `engine/tests/test_accuracy.py::ScopeTest.test_a_ci_system_or_build_tool_not_parsed_is_a_blind_spot`, `engine/tests/test_accuracy.py::ScopeTest.test_deployment_in_terraform_is_named` |

## A1. Identity and ownership

| Item | How | Status | Where today / note |
|---|---|---|---|
| Name, repository URL, branch, commit | F, G | PARTIAL | `identity.app_id`, `repository_url`, `git_branch`, `git_head`; tests: `repository_url` `engine/tests/test_discovery.py::FixesFromCheckout.test_alias_subdomain_and_host_seen_in_readme`; `app_id`, `git_head` `engine/tests/test_benchmark.py::ShippedBenchmark.test_all_gates_pass` (benchmark fixtures `ssh_alias_host_corroborated`, `working_tree_clean`); `git_branch` built, no test |
| What the application does | F | BUILT | `identity.about` (README description); test `engine/tests/test_discovery.py::About.test_first_paragraph_without_badges_headings_or_markup` |
| Owners (CODEOWNERS, README, build) | F | PARTIAL | `identity.owners` reads CODEOWNERS only (`detectors/identity.py:14-18`); README and build owners not read, and the search record must say so |
| Team, business criticality | input list | PARTIAL | `team` shown; the list file's `criticality` column is carried but not shown, and the criticality dimension reads only `--criticality`; never inferred |
| Lifecycle status (active, legacy, retiring) | G, X | PLANNED | from last-commit age (G); stated status only from the client (X) |
| Application boundary: deployable units in a repository; one application spread over several repositories | F, X | PLANNED | today one repository = one application |
| Users and business capability served | X | OUT | the client supplies it; never inferred |

## A2. Language, runtime and framework

| Item | How | Status | Where today / note |
|---|---|---|---|
| Languages and their share | F | PARTIAL | `stack.language`, `java_sources`, `kotlin_sources`; Groovy/Scala counted as source but not reported |
| Java version (source/target, toolchain) | F | BUILT | `stack.java_version` (lowest when several; INFERRED); test `engine/tests/test_discovery.py::GradleKotlinCircleCI.test_java_version_keeps_minor`; test `engine/tests/test_benchmark.py::ShippedBenchmark.test_all_gates_pass` (benchmark fixtures `java_version_lowest_declared_is_baseline`, `java_version_toolchain_and_jvm_target`) |
| Kotlin version | F | BUILT | `stack.kotlin_version`; test `engine/tests/test_discovery.py::GradleKotlinCircleCI.test_java_version_keeps_minor` |
| JDK vendor and distribution (base image, toolchain vendor) | F | PLANNED | licensing differs by vendor |
| Framework and version (Spring Boot, Spring, Quarkus, Micronaut, Dropwizard, Jakarta EE) | F | PARTIAL | `stack.app_framework`, `spring_boot_version`; Jakarta EE / plain servlet apps and app servers not recognised as a framework |
| Application server (Tomcat, WildFly/JBoss, WebLogic, WebSphere, Liberty) | F | PLANNED | packaging is read (`stack.packaging`); the target server is not |
| Packaging (jar, war, ear) | F | PARTIAL | `stack.packaging`, `artifact_kind`; `artifact_kind` test `engine/tests/test_discovery.py::GradleKotlinCircleCI.test_library_makes_deploy_criteria_not_applicable`; `stack.packaging` built, no test |
| Support status of Java and framework | F + reference data | BUILT | `dimensions.technology_lifecycle`; Spring Boot per line (spring.io) and Dropwizard dates UNREVIEWED (R-11); test `engine/tests/test_accuracy.py::AccuracyTest.test_spring_boot_support_is_judged_per_release_line`, `engine/tests/test_accuracy.py::AccuracyTest.test_dropwizard_is_found_with_its_version_and_its_end_of_life` |
| javax vs jakarta namespace | F | PLANNED | read in places for other checks; not reported |

## A3. Build system and modules

| Item | How | Status | Where today / note |
|---|---|---|---|
| Build tool and wrapper version | F | BUILT | `stack.build_tool`, `build_wrapper`; Ant, sbt, Bazel, Mill, Leiningen are blind spots (`scope.blind_spots`); test `engine/tests/test_discovery.py::Detection.test_broken_pom_does_not_crash`; test `engine/tests/test_benchmark.py::ShippedBenchmark.test_all_gates_pass` (benchmark fixtures `gradle_kotlin_kover_gate_wired`, `ant_build_not_mistaken_for_maven`) |
| Build tool version compatible with the JDK (for example Gradle 2.x cannot run on Java 9+) | F + reference data | PLANNED | |
| Modules and their layout | F | BUILT | `stack.module_list`, `identity.modules`; test `engine/tests/test_discovery.py::FixesFromCheckout.test_settings_gradle_modules_and_custom_build_file_names`; test `engine/tests/test_benchmark.py::ShippedBenchmark.test_all_gates_pass` (benchmark fixture `modules_maven_named_with_roles`) |
| Parent POM / convention plugins from outside the repo | F | BUILT | `scope.blind_spots` (`build.parent_pom`, `build.org_plugin`, `build.remote_script`); test `engine/tests/test_accuracy.py::ScopeTest.test_an_organisation_parent_pom_outside_the_repository_is_a_blind_spot`, `engine/tests/test_accuracy.py::ScopeTest.test_the_spring_boot_parent_and_a_parent_in_the_repository_are_not` |
| Build plugins (quality, coverage, release, packaging) | F | PARTIAL | read per check (coverage, SAST, release); no single list |
| Reproducibility (wrapper, pinned plugin versions, lock files) | F | PLANNED | |

## A4. Libraries and dependencies

| Item | How | Status | Where today / note |
|---|---|---|---|
| Declared dependencies by kind (DB, messaging, HTTP client, observability, ...) | F | BUILT | `stack.external_dependencies` (60+ technologies), `notable_dependencies`; test `engine/tests/test_integrations.py::CatalogTest.test_real_coordinates_map_to_their_technology`; test `engine/tests/test_benchmark.py::ShippedBenchmark.test_all_gates_pass` (benchmark fixtures `deps_spring_boot_postgres_redis_kafka`, `dependency_oracle_declared`) |
| Full declared dependency list with versions | F | PARTIAL | read, not reported as a list; versions not resolved through BOMs (limitation stated) |
| Internal shared libraries (the organisation's own artifacts) and their versions across the portfolio | F | PLANNED | needed for upgrade waves; matched by group id prefix |
| Resolved dependency tree | T (build tool) | OUT | needs the build to run; contradicts R-08 unless run in a sandbox the client approves |
| Outdated and end-of-life libraries | F + reference data | PLANNED | control `platform.libraries_current` is NOT_ASSESSED |
| Known vulnerabilities in dependencies | T | PARTIAL | opt-in `scan.py`; without it `security.exposure_known` is NOT_ASSESSED |
| Removed or deprecated APIs blocking an upgrade | S, F | PLANNED | see A24 |

## A5. Application structure and components

| Item | How | Status | Where today / note |
|---|---|---|---|
| Components: controllers, services, repositories, listeners, clients | F | BUILT | relationship graph nodes (`relationships.json`), C4 view; test `engine/tests/test_graph.py::ExtractionTest.test_rest_endpoints_are_exposed_with_class_prefix_and_path_shape`, `engine/tests/test_graph.py::ExtractionTest.test_repository_edges_are_inferred_and_point_at_the_one_database`, `engine/tests/test_platform.py::PlatformTest.test_container_view_shows_callers_deployment_and_data` |
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
| REST endpoints (method, path) | F | BUILT | `api.http_endpoints_present`, graph `ApiEndpoint` nodes (Spring MVC, WebFlux, JAX-RS, Ktor, Micronaut, Quarkus); test `engine/tests/test_graph.py::ExtractionTest.test_rest_endpoints_are_exposed_with_class_prefix_and_path_shape`, `engine/tests/test_graph.py::ExtractionTest.test_kotlin_controller_is_read`, `engine/tests/test_gaps.py::GapTest.test_webflux_router_functions_are_endpoints_and_plain_GET_strings_are_not` |
| OpenAPI spec and generator | F | BUILT | `api.openapi_*`; test `engine/tests/test_discovery.py::ApiAndCompleteness.test_static_spec_file_is_provided_not_exposed`, `engine/tests/test_discovery.py::ApiAndCompleteness.test_generator_dependency_is_met` |
| Message consumers (topic/queue) | F | BUILT | graph `CONSUMES_FROM`; test `engine/tests/test_graph.py::ExtractionTest.test_consumer_destination_from_property_placeholder_and_kotlin_array` |
| SOAP / WSDL services | F | PLANNED | not read |
| gRPC, GraphQL, WebSocket | F | PARTIAL | dependency recognised; services/endpoints not listed |
| API versioning and compatibility checks (path or header versions, contract diffs) | F | PLANNED | upstream F-048, F-050 |
| Who calls this application | F (portfolio) | BUILT | portfolio graph, only among analysed applications; test `engine/tests/test_graph.py::ResolutionTest.test_service_name_resolves_on_strong_identity_and_cites_it`, `engine/tests/test_graph.py::ResolutionTest.test_call_is_attached_to_the_exposed_endpoint_when_it_exists` |
| Role in the estate: API gateway, edge service, BFF | F | PLANNED | gateway routes (Spring Cloud Gateway, Zuul) read as relationships today; the role is not stated |

## A7. Interfaces consumed (outbound) and integrations

| Item | How | Status | Where today / note |
|---|---|---|---|
| Outbound HTTP calls and targets | F | BUILT | graph `CALLS_API` (RestTemplate, WebClient, Feign incl. `Feign.builder()`, Retrofit, OkHttp, ...); targets from literals, resolvable placeholders, constants; test `engine/tests/test_graph.py::ExtractionTest.test_feign_client_calls_carry_method_and_path`, `engine/tests/test_graph.py::ExtractionTest.test_property_placeholder_url_is_resolved_from_configuration_with_both_citations`, `engine/tests/test_accuracy.py::SixthAuditTest.test_feign_clients_built_in_code_are_relationships` |
| Service URLs named in configuration but not traced in code | F | BUILT | `runtime.service_urls`, `architecture.calls_matched`; test `engine/tests/test_accuracy.py::SecondAuditTest.test_service_urls_in_configuration_are_listed_once`, `tests/test_aspects.py::AspectsTest.test_services_named_in_configuration_but_not_traced_make_the_map_incomplete` |
| Third-party SaaS (mail, SMS, payment, identity providers) | F | BUILT | `stack.external_dependencies` (SendGrid, Twilio, OAuth2/OIDC, LDAP, ...); test `engine/tests/test_integrations.py::CatalogTest.test_real_coordinates_map_to_their_technology`; test `engine/tests/test_benchmark.py::ShippedBenchmark.test_all_gates_pass` (benchmark fixture `deps_identity_provider_named_by_its_host`) (SendGrid and Twilio entries have no test) |
| Service discovery and registry (Eureka, Consul discovery, Kubernetes services) | F | PARTIAL | dependency recognised (`stack.external_dependencies`); registered name not used to match calls |
| Object and file storage (S3, Blob, GCS, SFTP, shared folders) | F | PARTIAL | S3, Blob, GCS, MinIO recognised; SFTP and file-share integrations not |
| Calls through in-house wrappers or generated clients | S | PLANNED | limitation stated; becomes UNKNOWN via `calls_matched` |

## A8. Data stores and data access

| Item | How | Status | Where today / note |
|---|---|---|---|
| Databases, caches, search engines used | F | BUILT | `stack.external_dependencies`, graph `READS_FROM` / `WRITES_TO`; test `engine/tests/test_graph.py::ExtractionTest.test_repository_edges_are_inferred_and_point_at_the_one_database`, `engine/tests/test_accuracy.py::Phase1Test.test_hazelcast_is_typed_as_a_cache_not_a_database`; test `engine/tests/test_benchmark.py::ShippedBenchmark.test_all_gates_pass` (benchmark fixture `deps_spring_boot_postgres_redis_kafka`) |
| Database shared with another analysed application | F | BUILT | `architecture.no_shared_database`; test `engine/tests/test_graph.py::ResolutionTest.test_databases_with_identical_connection_settings_are_shared`, `engine/tests/test_gaps.py::GapTest.test_migrations_say_which_tables_the_application_owns_and_shared_tables_are_reported` |
| Entities and repositories | F | PARTIAL | repository base types read; entity model not reported |
| Schema migrations (Flyway, Liquibase) | F | BUILT | `data.migrations`; test `tests/test_aspects.py::AspectsTest.test_relational_checks_do_not_apply_to_document_stores_or_in_memory_databases`, `engine/tests/test_integrations.py::CatalogTest.test_real_coordinates_map_to_their_technology` |
| Transaction boundaries (`@Transactional` placement, propagation) | S | PLANNED | see A19 |
| Native SQL, stored procedures | F | PLANNED | |
| Database vendor, version and SQL dialect lock-in | F | PARTIAL | vendor from driver; version and dialect-specific SQL not read |
| Personal or sensitive data held (data classification) | F, X | PLANNED | field-name signals only (F); classification from the client (X) |
| Backups and restore | X | NOT_ASSESSED | `data.backups` pending; usually outside the repo |

## A9. Messaging

| Item | How | Status | Where today / note |
|---|---|---|---|
| Brokers, topics and queues, producers and consumers | F | BUILT | graph messaging adapter (Kafka, RabbitMQ, JMS, SQS/SNS, Pub/Sub, ...); test `engine/tests/test_graph.py::ExtractionTest.test_kafka_publishers_literal_constant_and_computed`, `engine/tests/test_graph.py::ResolutionTest.test_topics_merge_on_family_name_and_cluster` |
| Consumer error handling (DLT/DLQ, error handler, retry) | F | BUILT | `runtime.messaging_errors` (Spring only; others UNKNOWN); test `engine/tests/test_runtime.py::RuntimeTest.test_well_configured_service_is_present_on_every_check`, `engine/tests/test_runtime.py::RuntimeTest.test_hystrix_subclass_in_memory_database_and_sqs_redrive` |
| Acknowledgement / offset commit mode, transactions | F | PLANNED | upstream F-057, F-058 |
| Producer settings (acks, idempotent producer, retries) | F | PLANNED | upstream F-057 |
| Ordering, concurrency, prefetch, rebalance handling | F, S | PLANNED | |
| Idempotent consumers, duplicate handling | S | PLANNED | potential issue only (R-13) |
| Message schemas and registry (Avro, JSON schema) | F | PARTIAL | `contract` facts for schemas in repo; registry not |

## A10. Configuration and environments

| Item | How | Status | Where today / note |
|---|---|---|---|
| Configuration files and profiles | F | BUILT | `scope.files_read.config`, profile handling in relationships; test `engine/tests/test_accuracy.py::ScopeTest.test_an_ordinary_repository_has_none_and_records_what_was_read`, `engine/tests/test_gaps.py::GapTest.test_selected_profile_overrides_base_environment_and_external_config_fill_the_rest` |
| Values that differ between profiles | F | BUILT | graph `profile_differences`; test `engine/tests/test_gaps.py::GapTest.test_values_differing_between_profiles_are_reported_not_picked` |
| Configuration from outside the repo (config server, Consul, Parameter Store, config tree) | F | BUILT | `scope.blind_spots` (`config.external`); test `engine/tests/test_accuracy.py::ScopeTest.test_a_config_server_is_a_blind_spot_for_configuration`, `engine/tests/test_accuracy.py::ScopeTest.test_classpath_config_location_is_not_a_blind_spot` |
| Environment variables required at start | F | PLANNED | placeholders with no default |
| Feature flags | F | PLANNED | |
| Effective value of a setting after precedence | F | PLANNED | upstream F-096; today a setting is read where written |

## A11. Secrets

| Item | How | Status | Where today / note |
|---|---|---|---|
| Secrets committed in code, build, CI and key files | F | BUILT | `security.secrets_committed` (redacted); test `engine/tests/test_accuracy.py::SecondAuditTest.test_literal_secrets_are_found_and_never_printed`, `engine/tests/test_accuracy.py::ThirdAuditTest.test_webhooks_compose_env_gradle_properties_and_real_db_passwords_are_secrets` |
| Secrets as literals in configuration | F | BUILT | `security.secrets_in_config`; test `engine/tests/test_accuracy.py::SecondAuditTest.test_literal_secrets_are_found_and_never_printed`, `engine/tests/test_accuracy.py::SecondAuditTest.test_settings_that_only_mention_a_secret_are_not_secrets` |
| Secret store in use (Vault, Secrets Manager) | F | BUILT | `stack.external_dependencies`; test `engine/tests/test_benchmark.py::ShippedBenchmark.test_all_gates_pass` (benchmark fixture `deps_spring_config_import_names_the_service`) (Google Secret Manager; Vault has no test) |
| Secrets in git history (removed later) | G | PLANNED | |

## A12. Build and delivery pipeline

| Item | How | Status | Where today / note |
|---|---|---|---|
| CI system and pipeline files | F | BUILT | `build_ci.ci_system`, `ci_files`; GitLab, GitHub Actions, Jenkins, CircleCI, Azure, Bitbucket parsed; others blind spots; test `engine/tests/test_discovery.py::GradleKotlinCircleCI.test_circleci_jobs_and_unit_evidence_line`, `engine/tests/test_accuracy.py::ScopeTest.test_a_ci_system_or_build_tool_not_parsed_is_a_blind_spot`; test `engine/tests/test_benchmark.py::ShippedBenchmark.test_all_gates_pass` (benchmark fixtures `ci_jenkins_pipeline_files`, `maven_jacoco_gate_reached_by_ci`) |
| Build, test, publish, tag, deploy, rollback steps | F | BUILT | `build_ci.*`, maturity criteria; test `engine/tests/test_discovery.py::Detection.test_security_and_resilience`, `engine/tests/test_discovery.py::CommitTagging.test_an_image_tagged_with_the_commit_is_partial_tagging_not_absent`; test `engine/tests/test_benchmark.py::ShippedBenchmark.test_all_gates_pass` (benchmark fixtures `ci_jenkins_pipeline_files`, `ci_maven_deploy_is_publish_not_deploy`) |
| Pipeline outside the repository (named in README) | F | PARTIAL | UNKNOWN with the citation; defect: a bare mention of a CI product counts (`build_ci.py:37-38`, T-1.11) |
| Manual deploy documented | F | BUILT | `build_ci.manual_deploy_documented`; test `engine/tests/test_accuracy.py::SixthAuditTest.test_a_documented_manual_deploy_is_a_gap_not_unknown`, `tests/test_phase1.py::OutsideTest.test_a_documented_manual_deploy_stays_a_gap_even_with_a_marker` |
| Shared templates, libraries, reusable workflows | F | BUILT | `scope.blind_spots`; test `engine/tests/test_accuracy.py::ScopeTest.test_remote_ci_shared_libraries_and_reusable_workflows_are_blind_spots` |
| Branch protection and required reviews | X | PLANNED | usually outside: "not seen here, confirm" (design 6.6) |
| Environments and promotion path | F | PARTIAL | inventories (Ansible) and deploy jobs read; no environment model |
| DORA measures (deploy frequency, lead time) | X | OUT | needs CI server history |

## A13. Deployment and hosting

| Item | How | Status | Where today / note |
|---|---|---|---|
| Platform (Kubernetes, Nomad, Compose, Ansible/VM) | F | BUILT | `resilience.json`, `stack.hosting`; test `engine/tests/test_resilience.py::ResilienceTest.test_fully_configured_kubernetes_workload_is_present_everywhere_and_eks_is_detected`, `engine/tests/test_resilience.py::ResilienceTest.test_nomad_job`, `engine/tests/test_resilience.py::ResilienceTest.test_test_harness_and_third_party_compose_files_are_not_the_deployment`, `engine/tests/test_accuracy.py::SecondAuditTest.test_an_ansible_deployment_is_read_not_reported_unread`; test `engine/tests/test_benchmark.py::ShippedBenchmark.test_all_gates_pass` (benchmark fixtures `hosting_kubernetes_manifest`, `hosting_nomad_job`) |
| Container image, base image, pinning | F | BUILT | `stack.container`, `availability.image_pinned`; test `engine/tests/test_resilience.py::ResilienceTest.test_codename_and_moving_tags_are_not_pinned`; test `engine/tests/test_benchmark.py::ShippedBenchmark.test_all_gates_pass` (benchmark fixtures `container_dockerfile_base_images`, `dockerfile_variants_and_dev_images`) |
| Container and deployment security posture (non-root user, read-only filesystem, securityContext, network policy) | F | PLANNED | |
| Replicas, probes, rollout, resources, autoscaling, disruption budget, spread | F | BUILT | 13 `availability.*` controls (Kubernetes, Nomad, Compose, Ansible); test `engine/tests/test_resilience.py::ResilienceTest.test_fully_configured_kubernetes_workload_is_present_everywhere_and_eks_is_detected`, `engine/tests/test_resilience.py::ResilienceTest.test_weak_workload_is_flagged_with_reasons`, `engine/tests/test_resilience.py::ResilienceTest.test_nomad_job`, `engine/tests/test_accuracy.py::SecondAuditTest.test_an_ansible_deployment_is_read_not_reported_unread` |
| Helm charts rendered | T | OUT | templates not rendered (limitation stated) |
| Terraform, ECS, CloudFormation, Cloud Foundry, OpenShift, Serverless, App Engine, Beanstalk | F | PARTIAL | named as blind spots; availability then NOT_ASSESSED with the tool named; not read |
| Deployment held in another repository, GitOps (Argo CD, Flux, image updater) | F, X | PLANNED | today the high-severity deploy control is ABSENT when no CI step deploys; becomes UNKNOWN only with a positive GitOps or outside-pipeline marker (design 6.6), otherwise stays "Not found" |

## A14. Testing

| Item | How | Status | Where today / note |
|---|---|---|---|
| Unit, integration, acceptance, contract, performance tests (counts, tools) | F | BUILT | `tests.*`; test `engine/tests/test_discovery.py::FixesFromCheckout.test_functional_and_contract_dirs_are_not_unit_tests`, `engine/tests/test_discovery.py::IntegrationDetail.test_tools_and_source_set_are_captured`; test `engine/tests/test_benchmark.py::ShippedBenchmark.test_all_gates_pass` (benchmark fixture `performance_tools_jmeter_and_jmh`) |
| Context-load-only tests | F | BUILT | recognised (`CONTEXT_ONLY`), excluded from counts and stated in the summary (phase 1); test `tests/test_phase1.py::Audit6Test.test_context_load_only_classes_are_said_in_the_summary` |
| Tests run in CI, skipped or disabled | F | BUILT | `tests.ci_test_execution`, `build_level_test_skip`, `ci_skip_flags`; test `engine/tests/test_discovery.py::Detection.test_skip_tests_in_pipeline`, `engine/tests/test_discovery.py::Detection.test_skip_in_pom_and_commented_pom_ignored` |
| Coverage tool, threshold, gate in CI | F | BUILT | `tests.coverage_*`; test `engine/tests/test_discovery.py::Detection.test_enforced_coverage_and_tests_in_ci`, `engine/tests/test_discovery.py::CoverageGateWiring.test_wired_gate_and_a_pipeline_that_runs_that_task_is_met` |
| Which entry points a test reaches | F | BUILT | `safetynet.json`; test `engine/tests/test_safetynet.py::SafetyNetTest.test_route_in_test_with_assertion_is_mapped_with_assertions`, `engine/tests/test_safetynet.py::SafetyNetTest.test_unmapped_component_is_unverified_never_untested` |
| Tests with no assertion | F | PARTIAL | `safetynet.json` reports `mapped_no_assertion_seen`; not a control |
| Mutation score | T | OUT | needs a build (R-08) |

## A15. Security in the code

| Item | How | Status | Where today / note |
|---|---|---|---|
| Scanners configured and run (secret, dependency, SAST) | F | BUILT | `security.*`, `delivery` criteria; test `engine/tests/test_discovery.py::Detection.test_security_and_resilience`, `engine/tests/test_discovery.py::NewColumns.test_scanner_invoked_by_ci_is_met` |
| Authentication mechanism (Spring Security, OAuth2 resource server, JWT, basic, LDAP) | F | PLANNED | not read today |
| Endpoints left unauthenticated; method security | F, S | PLANNED | |
| CORS, CSRF, security headers | F | PLANNED | |
| Weak crypto, insecure random, TLS verification turned off | F, S | PLANNED | |
| SQL built by string concatenation, deserialisation of untrusted data | S, T | PLANNED | potential issue unless the tool confirms (R-13) |
| Actuator / management endpoints exposed | F | PARTIAL | health exposure checked against security config only |

## A16. Runtime resilience

| Item | How | Status | Where today / note |
|---|---|---|---|
| HTTP client timeouts | F | BUILT | `runtime.http_timeouts`; test `engine/tests/test_runtime.py::RuntimeTest.test_weak_service_shows_the_gap_and_why`, `engine/tests/test_runtime.py::RuntimeTest.test_disabled_timeouts_and_immediate_shutdown_are_issues` |
| Retries and circuit breakers | F | BUILT | `runtime.retries_breakers` (Spring only); test `engine/tests/test_runtime.py::RuntimeTest.test_weak_service_shows_the_gap_and_why`, `engine/tests/test_accuracy.py::ThirdAuditTest.test_a_breaker_around_one_client_does_not_cover_the_others` |
| Bulkheads, rate limits, overall call deadlines | F | PLANNED | |
| Database timeouts and pools | F | BUILT | `runtime.db_timeouts`; test `engine/tests/test_runtime.py::RuntimeTest.test_weak_service_shows_the_gap_and_why`, `engine/tests/test_runtime.py::RuntimeTest.test_disabled_timeouts_and_immediate_shutdown_are_issues` |
| Graceful shutdown | F | BUILT | `runtime.graceful_shutdown`; test `engine/tests/test_runtime.py::RuntimeTest.test_defaults_are_declared_not_configured`, `engine/tests/test_runtime.py::RuntimeTest.test_disabled_timeouts_and_immediate_shutdown_are_issues`, `tests/test_phase1.py::DeclaredOnlyTest.test_graceful_shutdown_by_default_on_boot_34_stays_present` |
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
| Health endpoint and its exposure | F | BUILT | `observability.health`; test `engine/tests/test_accuracy.py::SecondAuditTest.test_a_health_endpoint_behind_authentication_is_partial`, `engine/tests/test_accuracy.py::AccuracyTest.test_code_registered_health_checks_and_pcp_metrics_are_recognised` |
| Metrics export | F | BUILT | `observability.metrics`; test `engine/tests/test_accuracy.py::AccuracyTest.test_code_registered_health_checks_and_pcp_metrics_are_recognised` (detection of a metrics library; the control's PRESENT path has no test of its own) |
| Tracing | F | BUILT | `observability.tracing`; test `tests/test_phase1.py::DeclaredOnlyTest.test_a_declared_dependency_with_no_configuration_is_partial` |
| Structured logging | F | BUILT | `observability.structured_logging`; test `engine/tests/test_runtime.py::RuntimeTest.test_well_configured_service_is_present_on_every_check`, `engine/tests/test_runtime.py::RuntimeTest.test_defaults_are_declared_not_configured` |
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
| README with a description | F | BUILT | `knowledge.readme`; test `tests/test_verify.py::VerifyTest.test_readme_without_a_description_is_partial_with_a_fitting_remedy`, `engine/tests/test_discovery.py::About.test_missing_or_empty_readme_is_not_found` |
| How to build and run locally (README instructions, compose for local) | F | PLANNED | onboarding signal |
| Architecture decision records | F | NOT_ASSESSED | control pending |
| API documentation | F | BUILT | via OpenAPI; test `engine/tests/test_discovery.py::ApiAndCompleteness.test_generator_dependency_is_met` |
| Diagrams in the repo | F | PLANNED | |
| Documentation drift (docs naming endpoints, modules or settings that no longer exist) | F | PLANNED | upstream F-052, F-083 |

## A23. Supply chain and licences

| Item | How | Status | Where today / note |
|---|---|---|---|
| Dependency update automation | F | BUILT | `security.dependency_updates`; test `engine/tests/test_discovery.py::NewColumns.test_dependabot_is_updates_not_scanning` |
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
| BUILT (implemented, not validated) | 53 |
| PARTIAL | 27 |
| PLANNED | 67 |
| NOT_ASSESSED (a control exists, no detector yet) | 6 |
| OUT | 6 |
| **Total** | **159 items in 25 areas (A0-A24)** |

(Counted from the tables above by `python3 openspec/scripts/matrix.py --write` (T-1.2); `--check` fails when the counts drift or a BUILT
row names no test (R-20, T-1.3).)
