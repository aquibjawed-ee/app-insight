"""Regressions from the independent accuracy audit of six real repositories: each test pins one finding that was wrong.
No answer is never a verdict; a framework or tool the detectors do not read is not proof of absence; evidence and wording
follow from what was found."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(1, HERE)
os.environ["DISCOVERY_FIXED_TIME"] = "2026-11-01T00:00:00Z"

import graph_fixtures as F  # noqa: E402
import discover  # noqa: E402
from detectors import Ctx, identity, runtime  # noqa: E402
from graph import dimensions  # noqa: E402

J = "src/main/java/com/acme/"
T = "src/test/java/com/acme/"
GRADLE_DW = """plugins { id 'java' }
apply plugin: 'findbugs'
dependencies {
    compile group: 'io.dropwizard', name: 'dropwizard-core', version: "$dropWizardVersion"
    findbugsPlugins 'com.h3xstream.findsecbugs:findsecbugs-plugin:1.4.4'
    compile group: 'com.custardsource.parfait', name: 'parfait-pcp', version: '0.5.4'
}
apply plugin: "net.researchgate.release"
"""


def repo(files):
    return F.make_repo(tempfile.mkdtemp(), "svc", files)


def lifecycle(boot=None, fw=None):
    disc = {"stack": {"java_version": {"value": "17", "evidence": []}, "spring_boot_version": {"value": boot, "evidence": [], "status": "CONFIRMED" if boot else "NOT_FOUND"},
                      "app_framework": {"value": fw, "evidence": []}}}
    return dimensions.lifecycle(disc, dimensions.load_lifecycle(), "2026-11-01")["values"]


class AccuracyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dw_repo = repo({
            "build.gradle": GRADLE_DW, "gradle.properties": "dropWizardVersion = 0.8.2\n",
            "Jenkinsfile": "pipeline { stages { stage('b') { steps { sh './gradlew clean build -x test' } } } }\n",
            "README.md": "\n# Micro service for uploading files into storage\n\n## Running\n\nrun it\n",
            J + "App.java": "package com.acme;\nclass App {\n  void run(Environment environment) {\n    environment.healthChecks().register(\"db\", new DbCheck());\n  }\n}\n",
            T + "UploadAcceptanceTest.java": "package com.acme;\nclass UploadAcceptanceTest {\n  @ClassRule public static DropwizardAppRule<C> RULE;\n  @Test public void uploads() { assertThat(1).isEqualTo(1); }\n}\n",
            "contracts/upload.md": "FORMAT: 1A\n# Upload API\n",
            "contracts/package-lock.json": "{\n}\n",
        })
        cls.dw = discover.build(cls.dw_repo)

    # --- no answer is never a verdict -------------------------------------------------------------------------------
    def test_spring_boot_support_is_judged_per_release_line(self):
        self.assertEqual(lifecycle("3.2.0")["spring_boot"]["oss_status"], "ended")  # OSS 2024-12-31, paid 2025-12-31
        self.assertEqual(lifecycle("3.5.3")["spring_boot"]["oss_status"], "commercial_only")  # OSS ended 2026-06-30
        self.assertEqual(lifecycle("4.1.0")["spring_boot"]["oss_status"], "supported")
        self.assertEqual(lifecycle("9.9.0")["spring_boot"]["oss_status"], "unknown")  # a line not in the reference data is never "supported"

    def test_dropwizard_is_found_with_its_version_and_its_end_of_life(self):
        fw = self.dw["stack"]["app_framework"]
        self.assertEqual((fw["value"]["name"], fw["value"]["version"]), ("dropwizard", "0.8.2"))
        self.assertEqual([e["path"] for e in fw["evidence"]], ["build.gradle", "gradle.properties"])
        self.assertEqual(lifecycle(fw={"name": "dropwizard", "label": "Dropwizard", "version": "0.8.2"})["framework"]["status"], "ended")

    # --- what the detectors now recognise ---------------------------------------------------------------------------
    def test_aws_sdk_clients_are_outbound_calls_with_library_default_timeouts(self):
        r = repo({"build.gradle.kts": 'dependencies { implementation("software.amazon.awssdk:s3:2.25.0") }\n',
                  "src/main/kotlin/com/acme/S3.kt": "package com.acme\nclass S3 {\n  fun c() = S3Client.builder().build()\n}\n"})
        ctx = Ctx(r)
        t = runtime.http_timeouts(ctx, runtime.settings(ctx))["value"]
        self.assertEqual(t["state"], "PARTIAL")
        self.assertIn("AWS SDK v2", t["summary"])
        self.assertEqual(runtime.retries_breakers(ctx, runtime.settings(ctx))["value"]["state"], "PARTIAL")

    def test_code_registered_health_checks_and_pcp_metrics_are_recognised(self):
        self.assertTrue(self.dw["resilience"]["health_endpoint"]["value"])
        self.assertIn("PCP metrics (Parfait)", [d["technology"] for d in self.dw["stack"]["external_dependencies"]["value"]])

    def test_acceptance_tests_are_found_by_intent_and_a_context_load_is_not_a_test(self):
        self.assertEqual(self.dw["tests"]["acceptance_tests"]["value"]["test_classes"], 1)
        self.assertEqual(self.dw["tests"]["unit_tests"]["value"]["test_classes"], 0)  # the acceptance test is not counted as a unit test
        d = discover.build(repo({"build.gradle": "plugins { id 'java' }\n",
                                 T + "AppTests.java": "package com.acme;\n@SpringBootTest\nclass AppTests {\n  @Test\n  void contextLoads() {\n  }\n}\n"}))
        self.assertEqual((d["tests"]["unit_tests"]["value"]["test_classes"], d["tests"]["integration_tests"]["value"]["test_classes"]), (0, 0))

    def test_a_separate_integration_test_source_set_is_read(self):
        d = discover.build(repo({"build.gradle": "plugins { id 'java' }\n",
                                 "src/integration-test/java/com/acme/FlowTest.java": "package com.acme;\nclass FlowTest {\n  @Test void flows() {}\n}\n"}))
        self.assertEqual(d["tests"]["integration_tests"]["value"]["test_classes"], 1)
        self.assertTrue(d["tests"]["integration_tests"]["value"]["separate_source_set"])

    def test_analysers_wired_into_the_build_lifecycle_count_as_run_by_the_pipeline(self):
        f = self.dw["security"]["sast_in_pipeline"]
        self.assertTrue(f["value"])
        self.assertEqual([e["path"] for e in f["evidence"]], ["Jenkinsfile", "build.gradle"])

    def test_a_release_plugin_is_partial_version_tagging(self):
        res = {c["id"]: c for c in self.dw["maturity"]["criteria"]}["version_tagging"]
        self.assertEqual(res["result"], "PARTIAL")
        self.assertIn("build_ci.release_plugin_tags", res["facts"])

    def test_api_specs_are_recognised_by_content_and_contract_tooling_is_not_evidence(self):
        self.assertEqual(self.dw["api"]["openapi_spec_files"]["value"], ["contracts/upload.md"])
        paths = [e["path"] for e in self.dw["tests"]["contract_tests"]["evidence"]]
        self.assertIn("contracts/upload.md", paths)
        self.assertNotIn("contracts/package-lock.json", paths)

    def test_readme_headings_are_read_as_the_reader_sees_them(self):
        self.assertEqual(self.dw["identity"]["about"]["value"], ["Micro service for uploading files into storage"])
        r = repo({"README.md": "Office Integration\n==================\n\nPre-requisites\n--------------\n- Java 8\n"})
        self.assertEqual(identity._about(Ctx(r))["status"], "NOT_FOUND")  # an underlined title is a heading, not a description

    def test_a_ci_server_named_outside_the_repository_is_not_no_ci(self):
        r = repo({"build.gradle": "plugins { id 'java' }\n", "README.md": "# Svc\n\nBuilt by the jenkins job svc-build.\n"})
        self.assertEqual(discover.build(r)["build_ci"]["ci_system"]["value"], ["external"])


if __name__ == "__main__":
    unittest.main()


class SecondAuditTest(unittest.TestCase):
    """Regressions from the acceptance re-audit: Ansible deployments, committed secrets, health behind security, untraced services."""

    def test_literal_secrets_are_found_and_never_printed(self):
        from detectors import security
        r = repo({"build.gradle": 'publishing { repositories { maven { credentials { password "fixture-pw-1" } } } }\n',
                  "src/main/resources/application.yml": "hz:\n  password:  hzpw\njwt:\n  secret: ${JWT_SECRET:dev_default_secret_value}\ndb:\n  password: ${DB_PASSWORD}\n",
                  "contracts/server.key": "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----\n",
                  "Jenkinsfile": "environment { PASS = credentials('reg_pass') }\n"})
        out = security.secrets(Ctx(r))
        cfg, code = out["secrets_in_config"], out["secrets_committed"]
        self.assertEqual((cfg["value"]["state"], code["value"]["state"]), ("ISSUE", "ISSUE"))
        self.assertEqual(sorted(e["line_start"] for e in cfg["evidence"]), [2, 4])  # the ${DB_PASSWORD} reference is not a secret
        self.assertEqual(sorted(e["path"] for e in code["evidence"]), ["build.gradle", "contracts/server.key"])  # credentials('id') is a store reference
        for e in cfg["evidence"] + code["evidence"]:
            self.assertTrue("[REDACTED]" in e["snippet"] or "PRIVATE KEY" in e["snippet"], e["snippet"])
            self.assertNotIn("hzpw", e["snippet"])
            self.assertNotIn("fixture-pw-1", e["snippet"])

    def test_settings_that_only_mention_a_secret_are_not_secrets(self):
        from detectors import security
        r = repo({"gradle.properties": "sharedSecretsVersion=1.2.3\n", "src/main/resources/application.yml": "sharedSecretLocation: /etc/app/secret\ntoken-ttl: 3600\n",
                  "package.json": '{"dependencies": {"jsonwebtoken": "^8.2.0"}}\n'})
        out = security.secrets(Ctx(r))
        self.assertEqual((out["secrets_in_config"]["value"]["state"], out["secrets_committed"]["value"]["state"]), ("PRESENT", "PRESENT"))

    def test_an_ansible_deployment_is_read_not_reported_unread(self):
        from graph import resilience
        r = repo({"pom.xml": F.pom("svc", "3.2.4", "17", []),
                  "deploy/inventory/prod/prod.ini": "[nodes]\napp-[1:2].prod.example\n\n[app:children]\nnodes\n",
                  "deploy/inventory/local/local.ini": "[nodes]\nlocalhost\n",
                  "deploy/playbook.yml": "- hosts: app\n  serial: 1\n  roles:\n    - app\n",
                  "deploy/roles/app/tasks/main.yml": "- name: run\n  docker_container:\n    image: \"acme/svc:{{ tag }}\"\n    restart_policy: on-failure\n    memory: 2g\n",
                  "deploy/common/tasks/health.yml": "- uri:\n    url: \"http://localhost:8081/health\"\n"})
        d = resilience.assess(r)
        st = {x["id"]: x["state"] for x in d["summary"]}
        self.assertEqual(d["platforms"], ["ansible"])
        self.assertEqual((st["replicas"], st["rollout"], st["restart_recovery"], st["resources"]), ("present", "present", "present", "partial"))  # memory, no CPU
        self.assertEqual((st["readiness"], st["graceful_stop"], st["image_pinned"]), ("partial", "default", "unknown"))
        self.assertEqual(st["pdb"], "not_applicable")  # a Kubernetes-only check does not apply to VMs

    def test_a_health_endpoint_behind_authentication_is_partial(self):
        d = discover.build(repo({"build.gradle": "dependencies { implementation 'org.springframework.boot:spring-boot-starter-actuator' }\n",
                                 J + "Sec.java": "package com.acme;\nclass Sec {\n  void c(HttpSecurity h) {\n    h.authorizeRequests().antMatchers(\"/register\").permitAll().anyRequest().authenticated();\n  }\n}\n"}))
        self.assertEqual(d["runtime"]["health"]["value"]["state"], "PARTIAL")

    def test_a_client_inside_a_health_check_is_not_an_outbound_dependency(self):
        r = repo({"build.gradle": "plugins { id 'java' }\n",
                  J + "health/SelfHealthCheck.java": "package com.acme;\nclass SelfHealthCheck {\n  Object c = HttpClients.custom().setConnectTimeout(1).build();\n}\n"})
        ctx = Ctx(r)
        self.assertEqual(runtime.http_timeouts(ctx, runtime.settings(ctx))["value"]["state"], "UNKNOWN")

    def test_service_urls_in_configuration_are_listed_once(self):
        r = repo({"src/main/resources/application.yml": "trustedApiBaseUrl: https://api:8443/trusted\nserver:\n  port: 8080\n",
                  "src/main/resources/application-qa.yml": "trustedApiBaseUrl: https://api-qa:8443/trusted\n"})
        ctx = Ctx(r)
        self.assertEqual([u["key"] for u in runtime.service_urls(ctx, runtime.settings(ctx))["value"]], ["trustedApiBaseUrl"])

    def test_an_end_of_life_inherited_from_an_older_range_says_before(self):
        fw = lifecycle(fw={"name": "dropwizard", "label": "Dropwizard", "version": "0.8.2"})["framework"]
        self.assertIn("end of life before 2023-01-31", fw["headline"])


class ThirdAuditTest(unittest.TestCase):
    """Regressions from the second acceptance audit: nothing written may carry a secret; partial is partial; dimensions agree with aspects."""
    HOOK = "https://hooks.slack.com/services/T0000AAAA/B0000BBBB/" + "x" * 24

    def test_every_written_string_is_redacted_not_only_evidence(self):
        import evidence
        doc = {"edges": [{"target": "ext:" + self.HOOK, "attrs": {"url": self.HOOK + "?token=abcdef123456"}}], self.HOOK: 1}
        text = repr(evidence.redact_tree(doc))
        self.assertNotIn("x" * 24, text)
        self.assertNotIn("abcdef123456", text)
        for line in ('property "sonar.jdbc.password", "zz9zz"', "key.current=" + "0a" * 32, "- GF_SECURITY_ADMIN_PASSWORD=adminpw"):
            self.assertIn("[REDACTED]", evidence.redact(line))

    def test_webhooks_compose_env_gradle_properties_and_real_db_passwords_are_secrets(self):
        from detectors import security
        r = repo({"deploy/group_vars/all": "slack_webhook_url: %s\n" % self.HOOK,
                  "docker-compose.yaml": "services:\n  grafana:\n    environment:\n      - GF_SECURITY_ADMIN_PASSWORD=adminpw\n",
                  "qa.gradle": 'sonarqube { properties { property "sonar.jdbc.password", "zz9zz" } }\n',
                  "src/main/resources/application.yml": "spring:\n  datasource:\n    url: jdbc:postgresql://db/app\n    password: password\n"})
        out = security.secrets(Ctx(r))
        cfg = sorted(e["path"] for e in out["secrets_in_config"]["evidence"])
        self.assertEqual(cfg, ["deploy/group_vars/all", "docker-compose.yaml", "src/main/resources/application.yml"])
        self.assertEqual([e["path"] for e in out["secrets_committed"]["evidence"]], ["qa.gradle"])
        mem = repo({"src/main/resources/application.yml": "spring:\n  datasource:\n    url: jdbc:h2:mem:t\n    password: password\n"})
        self.assertEqual(security.secrets(Ctx(mem))["secrets_in_config"]["value"]["state"], "PRESENT")  # an in-memory database's default is not a credential

    def test_a_breaker_around_one_client_does_not_cover_the_others(self):
        r = repo({"build.gradle": "plugins { id 'java' }\n",
                  J + "Cmd.java": "package com.acme;\nclass Cmd extends HystrixCommand<String> {\n}\n",
                  J + "ApiConfig.java": "package com.acme;\nclass ApiConfig {\n  Object api() { return Feign.builder().target(Api.class, url); }\n}\n"})
        ctx = Ctx(r)
        self.assertEqual(runtime.retries_breakers(ctx, runtime.settings(ctx))["value"]["state"], "PARTIAL")

    def test_ansible_limits_pins_and_probes_are_judged_precisely(self):
        from graph import resilience
        r = repo({"pom.xml": F.pom("svc", "3.2.4", "17", []), "deploy/inventory/prod/prod.ini": "[nodes]\napp-[1:2].prod\n",
                  "deploy/playbook.yml": "- hosts: nodes\n  serial: 1\n  tasks:\n    - shell: curl -I {{ inventory_hostname }}:8080/app\n",
                  "deploy/roles/app/tasks/main.yml": "- docker_container:\n    image: \"acme/svc:{{ tag }}\"\n    memory: 2g\n",
                  "Jenkinsfile": "sh \"ansible-playbook -i inventory/prod deploy/playbook.yml --extra-vars 'tag=${COMMIT_TAG}'\"\n"})
        st = {x["id"]: x["state"] for x in resilience.assess(r)["summary"]}
        self.assertEqual((st["resources"], st["image_pinned"], st["readiness"]), ("partial", "present", "partial"))

    def test_the_safety_net_headline_counts_each_component_once(self):
        sn = {"summary": {"api_endpoint": {"class_level": 8, "direct": 1, "mapped_no_assertion_seen": 0, "mapped_with_assertions": 9, "unverified": 0}},
              "repository_level": {k: {"state": "unknown"} for k in ("test_exists", "runs_automatically", "passes", "coverage_measured", "coverage_threshold_enforced")},
              "components": []}
        d = dimensions.assess({"identity": {"app_id": {"value": "x"}}, "stack": {}, "maturity": {}}, safetynet=sn)
        self.assertIn("1 of 9 discovered components", d["dimensions"]["safety_net_strength"]["headline"])


class FourthAuditTest(unittest.TestCase):
    """Regressions from the third acceptance audit: configuration and environment, not presence alone."""

    def test_an_include_filter_without_security_rules_neutralises_find_sec_bugs(self):
        from detectors import security
        base = {"build.gradle": "apply plugin: 'findbugs'\nfindbugs { includeFilter = file(\"config/findbugs.xml\") }\n"}
        keep = repo(dict(base, **{"config/findbugs.xml": '<FindBugsFilter>\n  <Match><Bug category="SECURITY"/></Match>\n</FindBugsFilter>\n'}))
        drop = repo(dict(base, **{"config/findbugs.xml": '<FindBugsFilter>\n  <Match><Bug pattern="BC_IMPOSSIBLE_DOWNCAST"/></Match>\n</FindBugsFilter>\n'}))
        self.assertEqual(security.rules_filtered(Ctx(keep)), [])  # the SECURITY category includes find-sec-bugs' rules
        self.assertEqual([e["path"] for e in security.rules_filtered(Ctx(drop))], ["build.gradle", "config/findbugs.xml"])

    def test_qa_inventories_do_not_show_production_redundancy(self):
        from graph import resilience
        files = {"pom.xml": F.pom("svc", "3.2.4", "17", []), "deploy/playbook.yml": "- hosts: app\n  serial: 1\n",
                 "deploy/inventory/qa1/qa1.ini": "[nodes]\napp-[1:2].qa1\n", "deploy/inventory/local/local.ini": "[nodes]\nlocalhost\n"}
        st = {x["id"]: x for x in resilience.assess(repo(files))["summary"]}
        self.assertEqual(st["replicas"]["state"], "unknown")
        files["deploy/inventory/hosts_eu1"] = "[eu1]\napp-1.eu1\napp-2.eu1\n\n[production:children]\neu1\n"
        st = {x["id"]: x for x in resilience.assess(repo(files))["summary"]}
        self.assertEqual(st["replicas"]["state"], "present")  # [production:children] marks it; qa1 and local are named as not counted
        self.assertIn("not counted, non-production", st["replicas"]["notes"][0])

    def test_timeouts_cover_only_the_clients_that_read_them(self):
        r = repo({"src/main/resources/application.yml": "apiReadTimeout: 5000\n",
                  J + "ApiConfig.java": "package com.acme;\nclass ApiConfig {\n  @Value(\"${apiReadTimeout}\") int t;\n  Object a() { return Feign.builder().target(A.class, u); }\n}\n",
                  J + "DiscoveryConfig.java": "package com.acme;\nclass DiscoveryConfig {\n  Object d() { return Feign.builder().target(D.class, u); }\n}\n"})
        ctx = Ctx(r)
        v = runtime.http_timeouts(ctx, runtime.settings(ctx))["value"]
        self.assertEqual(v["state"], "PARTIAL")
        self.assertIn("DiscoveryConfig.java", v["summary"])

    def test_a_library_client_given_timeout_arguments_has_timeouts(self):
        r = repo({J + "AuthModule.java": "package com.acme;\nclass AuthModule {\n  Object c() { return new HttpClient(enc, CONNECTION_TIMEOUT_IN_MILLIS, READ_TIMEOUT_IN_MILLIS); }\n}\n"})
        ctx = Ctx(r)
        self.assertEqual(runtime.http_timeouts(ctx, runtime.settings(ctx))["value"]["state"], "PRESENT")

    def test_a_breaker_named_after_a_client_configuration_covers_it(self):
        r = repo({J + "DiscoveryCommand.java": "package com.acme;\nclass DiscoveryCommand extends HystrixCommand<String> {\n}\n",
                  J + "DiscoveryConfiguration.java": "package com.acme;\nclass DiscoveryConfiguration {\n  Object d() { return Feign.builder().target(D.class, u); }\n}\n"})
        ctx = Ctx(r)
        self.assertEqual(runtime.retries_breakers(ctx, runtime.settings(ctx))["value"]["state"], "PRESENT")


class FifthAuditTest(unittest.TestCase):
    """Regressions from the fifth acceptance audit: scope, shared deadlines, one external-pipeline rule, production inventories."""

    def test_an_analyser_applied_only_to_the_root_project_leaves_modules_out(self):
        d = discover.build(repo({
            "settings.gradle": "include ':orders', ':billing'\n",
            "build.gradle": "apply from: \"${rootDir}/support/quality.gradle\"\nallprojects {\n  repositories { mavenCentral() }\n}\n",
            "support/quality.gradle": "apply plugin: 'findbugs'\ndependencies { findbugsPlugins 'com.h3xstream.findsecbugs:findsecbugs-plugin:1.4.4' }\n",
            "Jenkinsfile": "pipeline { stages { stage('b') { steps { sh './gradlew clean build' } } } }\n",
            "orders/src/main/java/A.java": "class A {}\n", "billing/src/main/java/B.java": "class B {}\n"}))
        self.assertEqual({c["id"]: c["result"] for c in d["maturity"]["criteria"]}["sast"], "PARTIAL")
        self.assertIn("orders, billing", d["security"]["sast_root_only"]["note"])

    def test_a_pipeline_outside_the_repository_makes_found_nothing_unknown_and_configured_partial(self):
        d = discover.build(repo({"build.gradle": "plugins { id 'java' }\napply plugin: 'findbugs'\ndependencies { findbugsPlugins 'com.h3xstream.findsecbugs:findsecbugs-plugin:1' }\n",
                                 "README.md": "# Svc\n\nThe jenkins job svc-build builds it.\n"}))
        res = {c["id"]: c["result"] for c in d["maturity"]["criteria"]}
        self.assertEqual((res["automated_build"], res["sast"]), ("UNKNOWN", "PARTIAL"))

    def test_only_inventories_marked_production_are_counted_when_any_is(self):
        from graph import resilience
        files = {"pom.xml": F.pom("svc", "3.2.4", "17", []), "deploy/playbook.yml": "- hosts: all\n  serial: 1\n",
                 "deploy/inventory/hosts_eu1": "[eu1]\na.eu1\nb.eu1\n\n[production:children]\neu1\n",
                 "deploy/inventory/hosts_load": "[load]\nl1\nl2\n", "deploy/inventory/hosts_dr": "[dr]\nd1\n\n[production:children]\ndr\n"}
        st = {x["id"]: x for x in resilience.assess(repo(files))["summary"]}
        self.assertIn("1 of 2 production inventories", st["replicas"]["notes"][0])
        self.assertIn("hosts_load", st["replicas"]["notes"][0])

    def test_a_class_named_like_an_annotation_is_not_a_consumer(self):
        r = repo({J + "SQSListener.kt": "package com.acme\n@Component\nclass SQSListener {\n  fun on() {}\n}\n"})
        ctx = Ctx(r)
        self.assertEqual(runtime.messaging_errors(ctx, runtime.settings(ctx))["value"]["state"], "NOT_APPLICABLE")


class SixthAuditTest(unittest.TestCase):
    """Regressions from the sixth acceptance audit: one resilience model, programmatic Feign clients, documented manual deploys."""

    def test_feign_clients_built_in_code_are_relationships(self):
        import relate
        r = repo({"src/main/resources/application.yml": "apiBaseUrl: https://api.example.com/v1\n",
                  J + "ApiConfiguration.java": "package com.acme;\nclass ApiConfiguration {\n  Api api(@Value(\"${apiBaseUrl}\") String apiBaseUrl) {\n"
                                               "    return Feign.builder().target(Api.class, apiBaseUrl);\n  }\n}\n"})
        out = tempfile.mkdtemp()
        relate.main(["analyse", r, "--out", out])
        import json
        edges = [e for e in json.load(open(os.path.join(out, "portfolio", "relationships.json")))["edges"] if e["type"] == "CALLS_API"]
        self.assertEqual([e["target"] for e in edges], ["ext:api.example.com"])
        self.assertEqual([x["path"] for x in edges[0]["evidence"]], [J + "ApiConfiguration.java", "src/main/resources/application.yml"])

    def test_an_ansible_deploy_feeds_the_maturity_view_too(self):
        d = discover.build(repo({"pom.xml": F.pom("svc", "3.2.4", "17", []), "deploy/inventory/prod/prod.ini": "[nodes]\na.prod\nb.prod\n\n[production:children]\nnodes\n",
                                 "deploy/playbook.yml": "- hosts: nodes\n  serial: 1\n"}))
        self.assertEqual({c["id"]: c["result"] for c in d["maturity"]["criteria"]}["zero_downtime"], "PARTIAL")  # replicas and rolling, no probe
        self.assertTrue(d["resilience"]["rolling_or_zero_downtime_strategy"]["value"])

    def test_a_documented_manual_deploy_is_a_gap_not_unknown(self):
        d = discover.build(repo({"build.gradle": "plugins { id 'java' }\n",
                                 "README.md": "# Svc\n\nBuilt by the jenkins job svc-build.\n\n## Deploy\n\n    ansible-playbook -i inventory/prod site.yml\n"}))
        res = {c["id"]: c["result"] for c in d["maturity"]["criteria"]}
        self.assertEqual((res["automated_build"], res["automated_deploy"]), ("UNKNOWN", "NO_EVIDENCE"))
