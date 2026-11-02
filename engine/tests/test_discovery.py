"""Fixture repos are built on disk per test (no git history needed beyond `git init`)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
os.environ["DISCOVERY_FIXED_TIME"] = "2026-01-01T00:00:00Z"

import discover  # noqa: E402
import validate  # noqa: E402
import build_ui  # noqa: E402
import scan  # noqa: E402

POM = """<project>
  <parent><artifactId>spring-boot-starter-parent</artifactId>
    <version>2.7.5</version></parent>
  <properties><java.version>11</java.version></properties>
  <dependencies>
    <dependency><artifactId>spring-boot-starter-web</artifactId></dependency>
    %(deps)s
  </dependencies>
  <build><plugins>%(plugins)s</plugins></build>
</project>
"""
JACOCO = "<plugin><artifactId>jacoco-maven-plugin</artifactId></plugin>"
JACOCO_ENFORCED = ("<plugin><artifactId>jacoco-maven-plugin</artifactId><executions><execution>"
                   "<goals><goal>check</goal></goals><configuration><minimum>0.80</minimum>"
                   "</configuration></execution></executions></plugin>")
SPRINGDOC = "<dependency><artifactId>springdoc-openapi-ui</artifactId></dependency>"


def make(files):
    d = tempfile.mkdtemp(prefix="appdisc-")
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    for rel, text in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write(text)
    return d


def java(files=None):
    base = {"src/main/java/a/C.java": "package a;\n@RestController\nclass C {}\n",
            "src/test/java/a/CTest.java": "package a;\nclass CTest { @Test void t(){} }\n"}
    base.update(files or {})
    return base


def run(files):
    d = make(files)
    return d, discover.build(d)


class Detection(unittest.TestCase):
    def test_enforced_coverage_and_tests_in_ci(self):
        _, doc = run(java({"pom.xml": POM % {"deps": SPRINGDOC, "plugins": JACOCO_ENFORCED},
                           ".gitlab-ci.yml": "stages:\n  - test\ntest:\n  script:\n    - mvn verify\n"}))
        t = doc["tests"]
        self.assertEqual(t["coverage_state"]["value"], "coverage_enforced")
        self.assertEqual(t["coverage_threshold_pct"]["value"], 80.0)
        self.assertEqual(t["ci_test_execution"]["value"], "enabled")
        self.assertEqual(doc["api"]["openapi_exposure"]["value"], "exposed_via_library")
        self.assertEqual(doc["stack"]["spring_boot_version"]["value"], "2.7.5")
        self.assertEqual(doc["stack"]["java_version"]["value"], "11")
        self.assertEqual(doc["run_meta"]["evidence_invalid"], [])

    def test_no_tests(self):
        _, doc = run({"pom.xml": POM % {"deps": "", "plugins": ""},
                      "src/main/java/a/C.java": "package a;\nclass C {}\n"})
        self.assertEqual(doc["tests"]["coverage_state"]["value"], "no_tests")
        self.assertEqual(doc["tests"]["unit_tests"]["status"], "NOT_FOUND")
        self.assertEqual(doc["tests"]["ci_test_execution"]["value"], "no_ci")

    def test_tests_present_coverage_not_configured(self):
        _, doc = run(java({"pom.xml": POM % {"deps": "", "plugins": ""},
                           ".gitlab-ci.yml": "t:\n  script:\n    - mvn test\n"}))
        self.assertEqual(doc["tests"]["coverage_state"]["value"], "tests_present_coverage_not_configured")

    def test_skip_tests_in_pipeline(self):
        _, doc = run(java({"pom.xml": POM % {"deps": "", "plugins": JACOCO_ENFORCED},
                           ".gitlab-ci.yml": "t:\n  script:\n    - mvn -DskipTests package\n"}))
        self.assertEqual(doc["tests"]["ci_test_execution"]["value"], "disabled_in_pipeline")
        self.assertEqual(doc["tests"]["coverage_state"]["value"], "tests_disabled_in_pipeline")

    def test_skip_in_pom_and_commented_pom_ignored(self):
        pom = POM % {"deps": "<!-- <dependency><artifactId>springdoc-openapi-ui</artifactId></dependency> -->",
                     "plugins": "<plugin><configuration><skipTests>true</skipTests></configuration></plugin>"}
        _, doc = run(java({"pom.xml": pom, ".gitlab-ci.yml": "t:\n  script:\n    - mvn verify\n"}))
        self.assertEqual(doc["tests"]["ci_test_execution"]["value"], "disabled_in_build")
        self.assertEqual(doc["api"]["openapi_library"]["status"], "NOT_FOUND")

    def test_remote_include_gives_unknown_not_not_found(self):
        _, doc = run(java({"pom.xml": POM % {"deps": "", "plugins": ""},
                           ".gitlab-ci.yml": "include:\n  - project: org/templates\n    file: ci.yml\n"}))
        self.assertEqual(doc["tests"]["ci_test_execution"]["status"], "UNKNOWN")
        self.assertEqual(doc["security"]["secret_scanning"]["status"], "UNKNOWN")
        self.assertEqual(doc["build_ci"]["build_step"]["status"], "UNKNOWN")
        self.assertIn("amb-remote-includes", [a["id"] for a in doc["llm_fill"]["ambiguities"]])

    def test_measured_coverage_from_report(self):
        rep = ('<report name="x"><package name="p"><counter type="LINE" missed="1" covered="1"/></package>'
               '<counter type="LINE" missed="20" covered="80"/><counter type="BRANCH" missed="50" covered="50"/></report>')
        _, doc = run(java({"pom.xml": POM % {"deps": "", "plugins": JACOCO},
                           "target/site/jacoco/jacoco.xml": rep}))
        self.assertEqual(doc["tests"]["coverage_measured"]["value"], {"BRANCH": 50.0, "LINE": 80.0})

    def test_broken_pom_does_not_crash(self):
        _, doc = run(java({"pom.xml": "<project><unclosed>"}))
        self.assertEqual(doc["run_meta"]["failures"], [])
        self.assertIn(doc["stack"]["build_tool"]["value"], ("maven",))

    def test_security_and_resilience(self):
        _, doc = run(java({"pom.xml": POM % {"deps": "", "plugins": ""},
                           ".gitlab-ci.yml": "s:\n  script:\n    - ggshield secret scan ci\n    - snyk test\n",
                           "deploy/app.nomad": 'job "a" {\n group "g" {\n count = 3\n update {\n  auto_revert = true\n }\n }\n}\n'}))
        self.assertTrue(doc["security"]["secret_scanning"]["value"])
        self.assertTrue(doc["security"]["dependency_scanning"]["value"])
        self.assertFalse(doc["security"]["cloud_scanning"]["value"])
        self.assertTrue(doc["resilience"]["multiple_instances"]["value"])
        self.assertTrue(doc["resilience"]["rollback"]["value"])


GRADLE_KTS = """plugins {
    id("org.springframework.boot") version "2.3.4.RELEASE"
    id("org.owasp.dependencycheck") version "6.0.2"
    kotlin("jvm") version "1.4.10"
    jacoco
}
java.sourceCompatibility = JavaVersion.VERSION_1_8
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test") {
        exclude(group = "org.mockito", module = "mockito-core")
    }
    testImplementation("com.ninja-squad:springmockk:2.0.0")
}
tasks.withType<Test> { useJUnitPlatform() }
tasks { jacocoTestCoverageVerification { violationRules { rule { limit { minimum = BigDecimal.valueOf(0.80) } } } } }
version = "1.0." + System.getenv("CIRCLE_BUILD_NUM")
"""
CIRCLE = """version: 2
jobs:
  build:
    steps:
      - restore_cache:
          keys:
            - gradle-cache-{{ checksum "build.gradle.kts" }}
      - run:
          name: Compile
          command: ./gradlew clean build
      - run:
          command: ./gradlew bintrayUpload
      - save_cache:
          paths:
            - ~/.gradle/dependency-check-data
workflows:
  version: 2
  build:
    jobs:
      - build
"""


class Provenance(unittest.TestCase):
    def _doc(self):
        return run(java({"build.gradle.kts": "// x\n", "src/main/kotlin/App.kt": "class App\n"}))[1]

    def test_kotlin_only_project_is_not_reported_as_java(self):  # audit P0-2
        f = self._doc()["stack"]
        self.assertEqual((f["language"]["value"], f["java_sources"]["status"]), ("java+kotlin", "CONFIRMED"))  # base fixture has C.java too
        d, doc = run({"build.gradle.kts": 'plugins{kotlin("jvm") version "1.9.0"}\n', "src/main/kotlin/App.kt": "class App\n"})
        s = doc["stack"]
        self.assertEqual((s["language"]["value"], s["java_sources"]["status"], s["kotlin_sources"]["status"]), ("kotlin", "NOT_FOUND", "CONFIRMED"))
        self.assertEqual(s["language"]["derivation"], {"rule": "language-from-source-files", "inputs": ["stack.kotlin_sources"]})
        self.assertTrue(s["kotlin_sources"]["evidence"])
        self.assertEqual(validate.validate(doc), [])

    def test_java_only_mixed_and_empty_projects(self):
        langs = {}
        for name, files in {"java": {"pom.xml": "<project/>", "src/main/java/A.java": "class A{}\n"},
                            "mixed": {"build.gradle": "", "src/main/java/A.java": "class A{}\n", "src/main/kotlin/B.kt": "class B\n"},
                            "empty": {"pom.xml": "<project/>"}}.items():
            langs[name] = run(files)[1]["stack"]["language"]["value"]
        self.assertEqual(langs, {"java": "java", "mixed": "java+kotlin", "empty": None})

    def test_derived_fact_without_inputs_or_with_missing_or_unsupported_inputs_is_rejected(self):
        doc = self._doc()
        doc["stack"]["guess"] = {"value": None, "status": "UNKNOWN", "evidence": []}
        for derivation, expect in (
                ({"rule": "r", "inputs": []}, "names no input facts"),
                ({"rule": "r", "inputs": ["stack.nope"]}, "does not exist"),
                ({"rule": "r", "inputs": ["stack.guess"]}, "not supported by evidence")):  # UNKNOWN input
            d = json.loads(json.dumps(doc))
            d["stack"]["language"]["derivation"] = derivation
            errs = validate.provenance(d)
            self.assertTrue(any(expect in e for e in errs), (derivation, errs))

    def test_derivation_cycles_are_rejected(self):
        doc = self._doc()
        doc["stack"]["java_sources"] = {"value": 1, "status": "CONFIRMED", "evidence": [], "derivation": {"rule": "r", "inputs": ["stack.language"]}}
        doc["stack"]["language"]["derivation"] = {"rule": "r", "inputs": ["stack.java_sources"]}
        self.assertTrue(any("cycle" in e for e in validate.provenance(doc)))

    def test_confirmed_with_nothing_is_rejected_by_validate(self):
        doc = self._doc()
        doc["stack"]["java_version"] = {"value": "17", "status": "CONFIRMED", "evidence": []}
        self.assertTrue(any("java_version" in e for e in validate.validate(doc)))


GATE_GRADLE = """plugins { jacoco }
tasks.test { finalizedBy("jacocoTestCoverageVerification") }
tasks.jacocoTestCoverageVerification { violationRules { rule { limit { minimum = "0.80".toBigDecimal() } } } }
"""
GATE_GRADLE_UNWIRED = """plugins { jacoco }
tasks.jacocoTestCoverageVerification { violationRules { rule { limit { minimum = "0.80".toBigDecimal() } } } }
"""
CIRCLE_RUN = "version: 2\njobs:\n  build:\n    steps:\n      - run:\n          command: %s\nworkflows:\n  w:\n    jobs: [build]\n"


class CoverageGateWiring(unittest.TestCase):
    def _res(self, files):
        d, doc = run(java(files))
        return {c["id"]: c["result"] for c in doc["maturity"]["criteria"]}, doc["tests"]

    def test_config_only_gate_with_no_pipeline_is_not_met(self):  # audit P0-1 reproduction
        res, t = self._res({"build.gradle.kts": GATE_GRADLE_UNWIRED})
        self.assertEqual((res["coverage"], t["coverage_gate_in_ci"]["value"]), ("PARTIAL", "not_shown"))
        self.assertEqual(t["coverage_measured"]["status"], "UNKNOWN")

    def test_ci_runs_tests_but_gate_is_not_wired_is_not_met(self):  # reviewer's counter-example
        res, t = self._res({"build.gradle.kts": GATE_GRADLE_UNWIRED, ".circleci/config.yml": CIRCLE_RUN % "./gradlew test"})
        self.assertEqual((res["tests_run_in_ci"], res["coverage"], t["coverage_gate_in_ci"]["value"]), ("MET", "PARTIAL", "not_shown"))

    def test_wired_gate_and_a_pipeline_that_runs_that_task_is_met(self):
        res, t = self._res({"build.gradle.kts": GATE_GRADLE, ".circleci/config.yml": CIRCLE_RUN % "./gradlew clean build"})
        self.assertEqual((res["coverage"], t["coverage_gate_in_ci"]["value"], t["coverage_gate_in_ci"]["status"]), ("MET", "wired_into_build", "INFERRED"))

    def test_pipeline_naming_the_verification_task_is_confirmed(self):
        res, t = self._res({"build.gradle.kts": GATE_GRADLE_UNWIRED, ".circleci/config.yml": CIRCLE_RUN % "./gradlew test jacocoTestCoverageVerification"})
        self.assertEqual((res["coverage"], t["coverage_gate_in_ci"]["status"]), ("MET", "CONFIRMED"))

    def test_maven_check_goal_needs_a_verify_phase_command(self):
        pom = POM % {"deps": "", "plugins": JACOCO_ENFORCED}
        res, t = self._res({"pom.xml": pom, ".gitlab-ci.yml": "build:\n  script:\n    - mvn test\n"})
        self.assertEqual((res["coverage"], t["coverage_gate_in_ci"]["value"]), ("PARTIAL", "not_shown"))
        res, t = self._res({"pom.xml": pom, ".gitlab-ci.yml": "build:\n  script:\n    - mvn verify\n"})
        self.assertEqual((res["coverage"], t["coverage_gate_in_ci"]["value"]), ("MET", "maven_lifecycle"))

    def test_remote_templates_make_the_gate_unknown_not_missing(self):
        ci = "include:\n  - project: grp/templates\n    file: ci.yml\nbuild:\n  script:\n    - echo hi\n"
        res, t = self._res({"build.gradle.kts": GATE_GRADLE_UNWIRED, ".gitlab-ci.yml": ci})
        self.assertEqual((res["coverage"], t["coverage_gate_in_ci"]["value"]), ("UNKNOWN", "unknown_remote_includes"))


class ApiAndCompleteness(unittest.TestCase):
    def test_static_spec_file_is_provided_not_exposed(self):  # audit P1-2 reproduction
        d, doc = run(java({"pom.xml": POM % {"deps": "", "plugins": ""}, "src/main/resources/openapi.yaml": "openapi: 3.0.0\n"}))
        c = {x["id"]: x for x in doc["maturity"]["criteria"]}["openapi_exposed"]
        self.assertEqual((doc["api"]["openapi_exposure"]["value"], c["result"]), ("static_spec_only", "PARTIAL"))
        self.assertIn("provided", c["label"])

    def test_generator_dependency_is_met(self):
        d, doc = run(java({"pom.xml": POM % {"deps": SPRINGDOC, "plugins": ""}}))
        self.assertEqual({x["id"]: x["result"] for x in doc["maturity"]["criteria"]}["openapi_exposed"], "MET")

    def test_completeness_counts_determined_checks_separately_from_the_score(self):
        ci = "include:\n  - project: grp/t\n    file: ci.yml\nbuild:\n  script:\n    - ./gradlew build\n"
        d, doc = run(java({".gitlab-ci.yml": ci, "build.gradle.kts": "// x\n"}))
        m = doc["maturity"]
        cp = m["completeness"]
        self.assertEqual(cp["applicable"], len(m["criteria"]))
        self.assertEqual(cp["unknown"], m["unknown"])
        self.assertEqual(cp["determined"] + cp["unknown"], cp["applicable"])
        self.assertEqual(cp["with_evidence"] + cp["no_evidence"], cp["determined"])
        self.assertGreater(cp["unknown"], 0)
        self.assertEqual(validate.validate(doc), [])


class ModuleScope(unittest.TestCase):
    FILES = {"settings.gradle.kts": 'include("api")\ninclude("worker")\n', "build.gradle.kts": "// root\n",
             "api/build.gradle.kts": "// api\n", "worker/build.gradle.kts": "// worker\n",
             "api/src/test/kotlin/a/ATest.kt": "class ATest { @Test fun t(){} }\n",
             "api/src/test/kotlin/a/BTest.kt": "class BTest { @Test fun t(){} }\n",
             "worker/src/test/kotlin/w/WTest.kt": "class WTest { @Test fun t(){} }\n"}

    def test_citations_carry_their_module_and_unit_counts_split_by_module(self):
        d, doc = run(self.FILES)
        u = doc["tests"]["unit_tests"]
        self.assertEqual(u["value"]["by_module"], {"api": 2, "worker": 1})
        self.assertEqual({e["path"].split("/")[0]: e["module"] for e in u["evidence"] if e["path"].startswith(("api/", "worker/"))},
                         {"api": "api", "worker": "worker"})
        self.assertEqual(validate.validate(doc), [])
        self.assertEqual(doc["run_meta"]["evidence_invalid"], [])  # the extra field does not disturb re-verification

    def test_single_module_repos_get_no_module_noise(self):
        d, doc = run(java())
        self.assertFalse(any("module" in e for _, f in __import__("evidence").iter_facts(doc) for e in f["evidence"]))


class VulnerabilityReports(unittest.TestCase):
    def test_reports_parsed_with_severity_counts(self):
        rep = {"dependencies": [{"vulnerabilities": [{"severity": "HIGH"}, {"severity": "MODERATE"}]},
                                {"vulnerabilities": [{"severity": "CRITICAL"}]}]}
        d, doc = run(java({"pom.xml": POM % {"deps": "", "plugins": ""},
                           "build/reports/dependency-check-report.json": json.dumps(rep)}))
        f = doc["security"]["vulnerability_reports"]
        self.assertEqual(f["status"], "INFERRED" if f["value"][0]["stale"] else "CONFIRMED")
        v = f["value"][0]
        self.assertEqual((v["critical"], v["high"], v["medium"], v["total"]), (1, 1, 1, 3))
        self.assertEqual(validate.validate(doc), [])

    def test_no_report_is_not_found_and_garbage_is_ignored(self):
        d, doc = run(java({"pom.xml": POM % {"deps": "", "plugins": ""}, "snyk-x.json": "not json"}))
        self.assertEqual(doc["security"]["vulnerability_reports"]["status"], "NOT_FOUND")


FAKE_TRIVY = """#!/bin/sh
if [ "$1" = "--version" ]; then echo "Version: 9.9.9"; exit 0; fi
if [ "$1" = "version" ]; then echo '{"Version":"9.9.9","VulnerabilityDB":{"UpdatedAt":"2026-01-01T00:00:00Z"}}'; exit 0; fi
while [ $# -gt 0 ]; do [ "$1" = "--output" ] && out="$2"; shift; done
cat "$FAKE_TRIVY_REPORT" > "$out"
"""


KOVER_KTS = """plugins { id("org.jetbrains.kotlinx.kover") version "0.9.0" }
kover { reports { verify { rule { minBound(80) } } } }
"""
GITLAB_TRIGGERS = """stages: [build, e2e]
build:
  stage: build
  script:
    - ./gradlew build
acceptance-tests:
  stage: e2e
  trigger:
    project: grp/svc/app-acceptance-tests
    strategy: depend
performance-tests:
  stage: e2e
  trigger:
    project: grp/svc/app-performance-tests
deploy-prod:
  stage: e2e
  script:
    - ./deploy.sh
"""


JACOCO_HTML = ("<html><body><table><tfoot><tr><td>Total</td><td class=\"bar\">250 of 1,000</td><td class=\"ctr2\">75%</td>"
               "<td class=\"bar\">20 of 40</td><td class=\"ctr2\">50%</td><td class=\"ctr1\">30</td><td class=\"ctr2\">100</td>"
               "<td class=\"ctr1\">60</td><td class=\"ctr2\">240</td><td class=\"ctr1\">5</td><td class=\"ctr2\">50</td>"
               "<td class=\"ctr1\">1</td><td class=\"ctr2\">10</td></tr></tfoot></table></body></html>")
JACOCO_CSV = ("GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,"
              "COMPLEXITY_MISSED,COMPLEXITY_COVERED,METHOD_MISSED,METHOD_COVERED\n"
              "g,p,A,10,90,2,8,1,9,1,4,0,3\ng,p,B,40,60,0,0,4,6,2,2,1,1\n")
KOVER_HTML = ('<html><body><h2>Overall Coverage Summary</h2>\n<table class="coverageStats">\n<tr><th class="name">Package</th>'
              '<th class="coverageStat "> Class, % </th><th class="coverageStat "> Method, % </th><th class="coverageStat "> Branch, % </th>'
              '<th class="coverageStat "> Line, % </th><th class="coverageStat "> Instruction, % </th></tr>\n'
              '<tr><td class="name">all classes</td>'
              '<td class="coverageStat"><span class="percent"> 50% </span><span class="absValue"> (5/10) </span></td>'
              '<td class="coverageStat"><span class="percent"> 40% </span><span class="absValue"> (40/100) </span></td>'
              '<td class="coverageStat"><span class="percent"> 25% </span><span class="absValue"> (10/40) </span></td>'
              '<td class="coverageStat"><span class="percent"> 80% </span><span class="absValue"> (80/100) </span></td>'
              '<td class="coverageStat"><span class="percent"> 70% </span><span class="absValue"> (700/1000) </span></td></tr></table></body></html>')
COBERTURA = '<?xml version="1.0"?>\n<coverage line-rate="0.85" branch-rate="0.6" lines-valid="200" version="1"><packages/></coverage>\n'
CLOVER = ('<?xml version="1.0"?>\n<coverage generated="1"><project name="p"><metrics statements="200" coveredstatements="150" '
          'conditionals="40" coveredconditionals="10" methods="50" coveredmethods="45"/></project></coverage>\n')


def _result(cls, n):
    return '<?xml version="1.0"?>\n<testsuite name="%s" tests="%d" skipped="0" failures="0" errors="0">\n</testsuite>\n' % (cls, n)


class PartialRunReports(unittest.TestCase):
    def _files(self, executed):
        f = {"build.gradle.kts": 'plugins { id("org.jetbrains.kotlinx.kover") }\n', "build/reports/kover/html/index.html": KOVER_HTML}
        for i in range(10):
            f["src/test/java/a/T%dTest.java" % i] = "class T%dTest { @Test void t(){} }\n" % i
        for i in range(executed):
            f["build/test-results/test/TEST-a.T%dTest.xml" % i] = _result("a.T%dTest" % i, 3)
        if executed:
            f["build/test-results/test/TEST-a.T0Test$Inner.xml"] = _result("a.T0Test$Inner", 2)
        return f

    def test_report_from_a_run_of_few_classes_is_not_representative(self):
        d, doc = run(self._files(2))
        run_ = doc["tests"]["coverage_run"]["value"]
        self.assertEqual((run_["executed_test_classes"], run_["executed_test_cases"], run_["representative"]), (2, 8, False))
        m = doc["tests"]["coverage_measured"]
        self.assertEqual(m["status"], "INFERRED")
        self.assertIn("PARTIAL RUN", m["note"])
        self.assertEqual(validate.validate(doc), [])

    def test_report_from_a_full_run_is_representative(self):
        d, doc = run(self._files(9))
        self.assertTrue(doc["tests"]["coverage_run"]["value"]["representative"])
        self.assertNotIn("PARTIAL RUN", doc["tests"]["coverage_measured"]["note"])

    def test_no_results_on_disk_means_unchecked_not_partial(self):
        d, doc = run(self._files(0))
        self.assertEqual(doc["tests"]["coverage_run"]["status"], "NOT_FOUND")
        self.assertNotIn("PARTIAL RUN", doc["tests"]["coverage_measured"]["note"])

    def test_partial_report_never_satisfies_the_75_percent_rule(self):
        f = self._files(2)
        f["build.gradle.kts"] = 'plugins { id("org.jetbrains.kotlinx.kover") }\nkover { reports { verify { rule { minBound(10) } } } }\n'
        f["build/reports/kover/html/index.html"] = KOVER_HTML.replace("(80/100)", "(99/100)")
        d, doc = run(f)
        res = {c["id"]: c["result"] for c in doc["maturity"]["criteria"]}
        self.assertEqual(res["coverage"], "PARTIAL")  # threshold 10 < 75, and the figure from a 2-class run is ignored


class CoverageReports(unittest.TestCase):
    def _measured(self, files):
        d, doc = run(java(files))
        return doc["tests"]["coverage_measured"], d

    def test_jacoco_html(self):
        f, d = self._measured({"build/reports/jacoco/test/html/index.html": JACOCO_HTML})
        self.assertEqual((f["value"]["INSTRUCTION"], f["value"]["BRANCH"], f["value"]["LINE"], f["value"]["METHOD"]), (75.0, 50.0, 75.0, 90.0))
        self.assertEqual(f["evidence"][0]["line_start"], 1)

    def test_jacoco_csv_sums_all_rows(self):
        f, d = self._measured({"target/site/jacoco/jacoco.csv": JACOCO_CSV})
        self.assertEqual((f["value"]["INSTRUCTION"], f["value"]["LINE"], f["value"]["BRANCH"]), (75.0, 75.0, 80.0))

    def test_kover_html_uses_the_all_classes_row(self):
        f, d = self._measured({"build/reports/kover/html/index.html": KOVER_HTML})
        self.assertEqual((f["value"]["LINE"], f["value"]["BRANCH"], f["value"]["INSTRUCTION"]), (80.0, 25.0, 70.0))
        self.assertEqual(f["evidence"][0]["line_start"], 4)  # cites the line holding the totals
        self.assertEqual(validate.validate(discover.build(d)), [])

    def test_cobertura_and_clover(self):
        f, d = self._measured({"target/site/cobertura/coverage.xml": COBERTURA})
        self.assertEqual((f["value"]["LINE"], f["value"]["BRANCH"]), (85.0, 60.0))
        f, d = self._measured({"target/clover/clover.xml": CLOVER})
        self.assertEqual((f["value"]["LINE"], f["value"]["BRANCH"], f["value"]["METHOD"]), (75.0, 25.0, 90.0))

    def test_exact_formats_win_and_a_configured_tool_ranks_first(self):
        f, d = self._measured({"build/reports/jacoco/test/html/index.html": JACOCO_HTML, "target/jacoco.csv": JACOCO_CSV})
        self.assertEqual(f["value"]["LINE"], 75.0)
        self.assertIn("csv", f["note"])
        f, d = self._measured({"build.gradle.kts": 'plugins { id("org.jetbrains.kotlinx.kover") }\n',
                               "target/jacoco.csv": JACOCO_CSV, "build/reports/kover/html/index.html": KOVER_HTML})
        self.assertIn("kover html", f["note"])

    def test_unparseable_reports_are_ignored(self):
        f, d = self._measured({"target/site/jacoco/jacoco.xml": "<report><oops", "build/reports/kover/html/index.html": "<html></html>"})
        self.assertEqual(f["status"], "UNKNOWN")

    def test_tools_are_detected_together_and_gate_is_per_tool_file(self):
        d, doc = run(java({"build.gradle.kts": 'plugins { id("jacoco"); id("org.jetbrains.kotlinx.kover") }\n',
                           "pom.xml": POM % {"deps": "", "plugins": "<plugin><artifactId>maven-checkstyle-plugin</artifactId><executions><execution>"
                                                "<goals><goal>check</goal></goals></execution></executions></plugin>"}}))
        t = doc["tests"]
        self.assertEqual(t["coverage_tool_configured"]["value"], "jacoco+kover")
        self.assertFalse(t["coverage_enforced"]["value"])  # a checkstyle `check` goal is not a coverage gate

    def test_cobertura_threshold(self):
        d, doc = run(java({"pom.xml": POM % {"deps": "", "plugins": "<plugin><artifactId>cobertura-maven-plugin</artifactId>"
                                             "<configuration><check><totalLineRate>80</totalLineRate></check></configuration></plugin>"}}))
        t = doc["tests"]
        self.assertEqual((t["coverage_tool_configured"]["value"], t["coverage_threshold_pct"]["value"], t["coverage_enforced"]["value"]),
                         ("cobertura", 80.0, True))


class FixesFromCheckout(unittest.TestCase):
    def test_kover_tool_threshold_and_enforcement(self):
        d, doc = run(java({"build.gradle.kts": KOVER_KTS}))
        t = doc["tests"]
        self.assertEqual((t["coverage_tool_configured"]["value"], t["coverage_threshold_pct"]["value"],
                          t["coverage_state"]["value"]), ("kover", 80.0, "coverage_enforced"))

    def test_kover_without_a_rule_is_not_enforced(self):
        d, doc = run(java({"build.gradle.kts": 'plugins { id("org.jetbrains.kotlinx.kover") version "0.9.0" }\n'}))
        self.assertEqual(doc["tests"]["coverage_state"]["value"], "coverage_configured_not_enforced")

    def test_triggered_suites_are_partial_and_stage_alone_proves_nothing(self):
        d, doc = run(java({".gitlab-ci.yml": GITLAB_TRIGGERS}))
        res = {c["id"]: c["result"] for c in doc["maturity"]["criteria"]}
        self.assertEqual((res["acceptance_tests"], res["performance_tests"]), ("PARTIAL", "PARTIAL"))
        self.assertEqual(doc["tests"]["acceptance_tests"]["status"], "INFERRED")
        jobs = [e["job"] for k in ("acceptance_tests", "performance_tests") for e in doc["tests"][k]["value"]["external"]]
        self.assertEqual(sorted(jobs), ["acceptance-tests", "performance-tests"])  # deploy-prod sits in e2e but is not a test
        self.assertEqual(validate.validate(doc), [])

    def test_in_repo_evidence_beats_external(self):
        d, doc = run(java({".gitlab-ci.yml": GITLAB_TRIGGERS, "src/test/java/a/acceptance/FlowTest.java": "class FlowTest { @Test void t(){} }\n"}))
        self.assertEqual(doc["tests"]["acceptance_tests"]["status"], "CONFIRMED")

    def test_settings_gradle_modules_and_custom_build_file_names(self):
        d, doc = run(java({"settings.gradle.kts": 'rootProject.name = "x"\ninclude("contract")\n'
                           'project(":contract").projectDir = file("contract")\n'
                           'project(":contract").buildFileName = "contract.gradle.kts"\n',
                           "build.gradle.kts": "// root\n", "contract/contract.gradle.kts": 'dependencies { testImplementation("au.com.dius.pact") }\n',
                           "gradle/libs.gradle.kts": "// helper script\n"}))
        self.assertEqual(doc["identity"]["modules"]["value"], [".", "contract"])

    def test_functional_and_contract_dirs_are_not_unit_tests(self):
        d, doc = run(java({"functional/src/test/kotlin/a/FTest.kt": "class FTest { @Test fun t(){} }\n",
                           "contract/src/test/kotlin/a/CTest.kt": "class CTest { @Test fun t(){} }\n"}))
        self.assertEqual(doc["tests"]["unit_tests"]["value"]["test_classes"], 1)  # only CTest.java from java() base
        self.assertEqual(doc["tests"]["acceptance_tests"]["value"]["test_classes"], 1)
        self.assertEqual(doc["tests"]["contract_tests"]["value"]["test_classes"], 1)

    def test_alias_subdomain_and_host_seen_in_readme(self):
        d = make(java({"README.md": "# T\nSee [docs](https://gitlab.com/Org/other/-/blob/x).\n"}))
        subprocess.run(["git", "remote", "add", "origin", "git@work.gitlab.com:Org/team/app.git"], cwd=d, check=True)
        i = discover.build(d)["identity"]
        self.assertEqual(i["repository_url"]["value"], "https://gitlab.com/Org/team/app")
        self.assertIn("link in the repository", i["repository_url"]["note"])
        d2 = make(java())
        subprocess.run(["git", "remote", "add", "origin", "git@work.gitlab.com:Org/team/app.git"], cwd=d2, check=True)
        self.assertEqual(discover.build(d2)["identity"]["repository_url"]["value"], "https://gitlab.com/Org/team/app")

    def test_readme_prerequisites_list_is_not_a_description(self):
        md = "# Checkout\n\n### Prerequisites\n* JDK 21\n  * install via\n    `/Users/x/Library/Java`\n\nRun things.\n"
        self.assertEqual(run(java({"README.md": md}))[1]["identity"]["about"]["status"], "NOT_FOUND")

    def test_readme_overview_section_is_accepted(self):
        md = "# Checkout\n\n## Overview\nA BFF for the checkout journey.\n\n## Setup\nrun\n"
        self.assertEqual(run(java({"README.md": md}))[1]["identity"]["about"]["value"], ["A BFF for the checkout journey."])

    def test_working_tree_flag_ignores_the_tool_output_dir(self):
        d = make(java())
        subprocess.run(["git", "add", "-A"], cwd=d, check=True)
        subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "x"], cwd=d, check=True)
        os.makedirs(os.path.join(d, ".modernise"))
        open(os.path.join(d, ".modernise", "x"), "w").write("y")
        self.assertTrue(discover.build(d)["identity"]["working_tree_clean"]["value"]["clean"])
        open(os.path.join(d, "new.txt"), "w").write("z")
        v = discover.build(d)["identity"]["working_tree_clean"]["value"]
        self.assertEqual((v["clean"], v["changed_files"]), (False, 1))


class NewColumns(unittest.TestCase):
    POMX = POM % {"deps": "", "plugins": ""}

    def test_dependabot_is_updates_not_scanning(self):
        d, doc = run(java({"pom.xml": self.POMX, ".github/dependabot.yml": "version: 2\n"}))
        self.assertTrue(doc["security"]["dependency_updates"]["value"])
        self.assertFalse(doc["security"]["dependency_scanning"]["value"])
        ids = {c["id"]: c["result"] for c in doc["maturity"]["criteria"]}
        self.assertEqual(ids["dependency_updates"], "MET")
        self.assertEqual(ids["dependency_scanning"], "NO_EVIDENCE")

    def test_no_update_config_is_no_evidence_and_new_criteria_exist(self):
        d, doc = run(java({"pom.xml": self.POMX}))
        ids = {c["id"]: c["result"] for c in doc["maturity"]["criteria"]}
        self.assertEqual((ids["dependency_updates"], ids["sast"], ids["integration_tests"]), ("NO_EVIDENCE",) * 3)

    def test_sast_and_integration_count_when_present(self):
        d, doc = run(java({"pom.xml": self.POMX + "\n<!-- sonar -->", "sonar-project.properties": "sonar.projectKey=x\n",
                           "src/test/java/a/XIT.java": "@SpringBootTest\nclass XIT { @Test void t(){} }\n"}))
        ids = {c["id"]: c["result"] for c in doc["maturity"]["criteria"]}
        # configured (sonar-project.properties) but no CI file invokes it: PARTIAL, not MET
        self.assertEqual((ids["sast"], ids["integration_tests"]), ("PARTIAL", "MET"))

    def test_scanner_invoked_by_ci_is_met(self):
        d, doc = run(java({"pom.xml": self.POMX, "sonar-project.properties": "sonar.projectKey=x\n",
                           ".github/workflows/ci.yml": "jobs:\n  s:\n    steps:\n      - run: mvn sonar:sonar\n"}))
        ids = {c["id"]: c["result"] for c in doc["maturity"]["criteria"]}
        self.assertEqual(ids["sast"], "MET")
        self.assertTrue(doc["security"]["sast_in_pipeline"]["value"])

    def test_owners_from_catch_all_rule(self):
        d, doc = run(java({".github/CODEOWNERS": "# who\n/docs/ @docs\n* @org/platform @bob\n"}))
        f = doc["identity"]["owners"]
        self.assertEqual((f["value"], f["evidence"][0]["line_start"]), (["@org/platform", "@bob"], 3))

    def test_no_codeowners(self):
        self.assertEqual(run(java())[1]["identity"]["owners"]["status"], "NOT_FOUND")


class IntegrationDetail(unittest.TestCase):
    def test_tools_and_source_set_are_captured(self):
        d, doc = run(java({"src/test/java/a/FlowIT.java": "@SpringBootTest\n@EmbeddedKafka\nclass FlowIT { @Test void t(){} }\n",
                           "src/integrationTest/java/a/DbIT.java": "@Testcontainers\nclass DbIT { @Test void t(){} }\n"}))
        v = doc["tests"]["integration_tests"]["value"]
        self.assertEqual(v["tools"], ["embedded-kafka", "spring-boot-test", "testcontainers"])
        self.assertTrue(v["separate_source_set"])

    def test_same_source_set_is_flagged_false(self):
        d, doc = run(java({"src/test/java/a/FlowIT.java": "@SpringBootTest\nclass FlowIT { @Test void t(){} }\n"}))
        self.assertFalse(doc["tests"]["integration_tests"]["value"]["separate_source_set"])


class About(unittest.TestCase):
    def test_first_paragraph_without_badges_headings_or_markup(self):
        md = ("# My Service\n\n[![Build](https://x/y.svg)](https://x)\n\n"
              "Handles **loan** account [reads](http://a) for the portal.\nIt serves cached data.\n\n## Usage\nRun it.\n")
        d, doc = run(java({"README.md": md}))
        f = doc["identity"]["about"]
        self.assertEqual(f["value"], ["Handles loan account reads for the portal.", "It serves cached data."])
        self.assertEqual(f["evidence"][0]["line_start"], 5)
        self.assertEqual(validate.validate(doc), [])

    def test_cap_and_secret_redaction(self):
        md = "\n".join(["line %d password=hunter2hunter2" % i for i in range(9)])
        d, doc = run(java({"README.md": md}))
        v = doc["identity"]["about"]["value"]
        self.assertEqual(len(v), 5)
        self.assertNotIn("hunter2hunter2", " ".join(v))

    def test_missing_or_empty_readme_is_not_found(self):
        self.assertEqual(run(java())[1]["identity"]["about"]["status"], "NOT_FOUND")
        self.assertEqual(run(java({"README.md": "# Title\n\n[![b](x)](y)\n"}))[1]["identity"]["about"]["status"], "NOT_FOUND")


class Links(unittest.TestCase):
    def _doc(self, remote, ci_file, ci_text="version: 2\n"):
        files = java({ci_file: ci_text})
        d = make(files)
        subprocess.run(["git", "remote", "add", "origin", remote], cwd=d, check=True)
        return discover.build(d)["identity"]

    def test_ssh_alias_with_github_in_name_is_inferred_github(self):
        i = self._doc("git@xinja.github.com:Org/app.git", ".circleci/config.yml")
        self.assertEqual(i["repository_url"]["value"], "https://github.com/Org/app")
        self.assertEqual(i["pipeline_url"]["value"], "https://app.circleci.com/pipelines/github/Org/app")
        self.assertEqual(i["repository_url"]["status"], "INFERRED")
        self.assertIn("assumed", i["repository_url"]["note"])

    def test_gitlab_pipeline_and_credentials_stripped(self):
        i = self._doc("https://user:s3cretpw@gitlab.example.com/grp/app.git", ".gitlab-ci.yml", "stages: [build]\n")
        self.assertEqual(i["git_remote"]["value"], "https://gitlab.example.com/grp/app.git")
        self.assertEqual(i["pipeline_url"]["value"], "https://gitlab.example.com/grp/app/-/pipelines")

    def test_unknown_ci_gives_no_pipeline_link(self):
        i = self._doc("git@github.com:Org/app.git", "Jenkinsfile", "pipeline {}\n")
        self.assertEqual(i["pipeline_url"]["status"], "NOT_FOUND")


class VulnerabilityScan(unittest.TestCase):
    def _scan(self, report):
        bindir = tempfile.mkdtemp()
        p = os.path.join(bindir, "trivy")
        open(p, "w").write(FAKE_TRIVY)
        os.chmod(p, 0o755)
        rp = os.path.join(bindir, "r.json")
        json.dump(report, open(rp, "w"))
        old = (os.environ.get("PATH"), os.environ.get("FAKE_TRIVY_REPORT"))
        os.environ["PATH"] = bindir + os.pathsep + os.environ["PATH"]
        os.environ["FAKE_TRIVY_REPORT"] = rp
        try:
            d, doc = run(java({"pom.xml": POM % {"deps": "", "plugins": ""}}))
            out = os.path.join(d, "out")
            os.makedirs(out)
            json.dump(doc, open(os.path.join(out, "discovery.json"), "w"))
            rc = scan.main(["--repo", d, "--discovery", out, "--skip-db-update"])
            return rc, json.load(open(os.path.join(out, "discovery.json")))
        finally:
            os.environ["PATH"] = old[0]
            os.environ.pop("FAKE_TRIVY_REPORT", None)

    def test_findings_are_counted_and_doc_stays_valid(self):
        rc, doc = self._scan({"Results": [{"Target": "pom.xml", "Vulnerabilities": [
            {"VulnerabilityID": "CVE-1", "Severity": "CRITICAL"}, {"VulnerabilityID": "CVE-2", "Severity": "LOW"}]}]})
        v = doc["security"]["vulnerability_scan"]
        self.assertEqual((rc, v["status"], v["value"]["critical"], v["value"]["total"]), (0, "CONFIRMED", 1, 2))
        self.assertEqual(validate.validate(doc), [])
        self.assertEqual(doc["run_meta"]["fingerprint"], validate.fingerprint(doc))

    def test_nothing_analysed_is_never_reported_as_zero(self):
        rc, doc = self._scan({"Results": []})
        v = doc["security"]["vulnerability_scan"]
        self.assertEqual((rc, v["status"], v["value"]["state"]), (1, "UNKNOWN", "could_not_scan"))
        self.assertNotIn("total", v["value"])

    def test_clean_manifest_is_a_real_zero(self):
        rc, doc = self._scan({"Results": [{"Target": "pom.xml"}]})
        self.assertEqual((rc, doc["security"]["vulnerability_scan"]["value"]["total"]), (0, 0))


class GradleKotlinCircleCI(unittest.TestCase):
    """Regressions found by the first real-repo trial run."""

    def setUp(self):
        _, self.doc = run({"build.gradle.kts": GRADLE_KTS, ".circleci/config.yml": CIRCLE,
                           "src/main/kotlin/a/A.kt": "package a\nclass A\n",
                           "src/test/kotlin/a/ATest.kt": "package a\n@TestInstance(PER_CLASS)\nclass ATest {\n @Test fun t() {}\n}\n"})

    def test_java_version_keeps_minor(self):
        self.assertEqual(self.doc["stack"]["java_version"]["value"], "1.8")
        self.assertEqual(self.doc["stack"]["kotlin_version"]["value"], "1.4.10")

    def test_threshold_from_bigdecimal(self):
        self.assertEqual(self.doc["tests"]["coverage_threshold_pct"]["value"], 80.0)

    def test_cache_key_is_not_a_test_command(self):
        ev = self.doc["tests"]["ci_test_execution"]["evidence"][0]
        self.assertIn("gradlew clean build", ev["snippet"])

    def test_excluded_mockito_not_reported(self):
        fw = self.doc["tests"]["frameworks"]["value"]
        self.assertIn("junit5", fw)
        self.assertIn("mockk", fw)
        self.assertNotIn("mockito", fw)

    def test_circleci_jobs_and_unit_evidence_line(self):
        self.assertEqual(self.doc["build_ci"]["jobs"]["value"], ["build"])
        self.assertEqual(self.doc["tests"]["unit_tests"]["evidence"][0]["snippet"], "@Test fun t() {}")

    def test_security_cites_plugin_not_cache_path(self):
        ev = self.doc["security"]["dependency_scanning"]["evidence"]
        self.assertEqual(ev[0]["path"], "build.gradle.kts")

    def test_library_makes_deploy_criteria_not_applicable(self):
        self.assertEqual(self.doc["stack"]["artifact_kind"]["value"], "library")
        ids = [c["id"] for c in self.doc["maturity"]["criteria"]]
        for na in ("automated_deploy", "zero_downtime", "rollback", "openapi_exposed"):
            self.assertNotIn(na, ids)
        self.assertTrue(self.doc["build_ci"]["artifact_version_from_ci"]["value"])

    def test_stale_report_is_flagged(self):
        d, _ = None, None
        files = {"build.gradle.kts": GRADLE_KTS, "src/test/kotlin/a/ATest.kt": "class T { @Test fun t(){} }\n",
                 "build/reports/jacoco/test/jacocoTestReport.xml":
                 '<report name="x"><counter type="LINE" missed="1" covered="3"/></report>'}
        repo = make(files)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"], cwd=repo, check=True)
        os.utime(os.path.join(repo, "build/reports/jacoco/test/jacocoTestReport.xml"), (1_000_000_000, 1_000_000_000))
        f = discover.build(repo)["tests"]["coverage_measured"]
        self.assertEqual(f["status"], "INFERRED")
        self.assertIn("STALE", f["note"])


class Hardening(unittest.TestCase):
    """Adopted from the ADE comparison: untrusted-repo safety, input identity, bounded absence claims."""

    def test_symlinks_are_never_read(self):
        d = make({"src/test/x.txt": "x"})
        os.symlink("/etc/hosts", os.path.join(d, "pom.xml"))
        os.symlink("/etc/hosts", os.path.join(d, ".gitlab-ci.yml"))
        os.symlink("/etc", os.path.join(d, "linked-dir"))
        doc = discover.build(d)
        self.assertEqual(doc["build_ci"]["ci_files"]["value"], [])
        self.assertEqual(doc["identity"]["modules"]["value"], [])
        self.assertNotIn("localhost", json.dumps(doc))

    def test_secret_literals_redacted_but_variables_kept(self):
        import evidence
        ci = ("deploy:\n  script:\n    - ./gradlew -Ppassword=hunter2hunter2 build\n"
              "    - curl -H 'Authorization: Bearer abcdefghijklmnop' x\n    - export TOKEN=ghp_abcdefghijklmnop1234\n"
              "    - docker login -p $REGISTRY_PASSWORD\n")
        d, doc = run({"pom.xml": POM % {"deps": "", "plugins": ""}, ".gitlab-ci.yml": ci})
        text = json.dumps(doc)
        for leak in ("hunter2hunter2", "abcdefghijklmnop", "ghp_abcdefghijklmnop1234"):
            self.assertNotIn(leak, text)
        self.assertEqual(doc["run_meta"]["evidence_invalid"], [])  # redacted snippet still re-verifies
        self.assertIn("$REGISTRY_PASSWORD", evidence.redact("docker login -p $REGISTRY_PASSWORD"))

    def test_dtd_in_coverage_report_is_rejected(self):
        evil = '<!DOCTYPE r [<!ENTITY a "aaaa">]><report><counter type="LINE" missed="1" covered="1"/></report>'
        _, doc = run(java({"pom.xml": POM % {"deps": "", "plugins": JACOCO}, "target/site/jacoco/jacoco.xml": evil}))
        self.assertEqual(doc["tests"]["coverage_measured"]["status"], "UNKNOWN")

    def test_real_jacoco_doctype_is_accepted(self):
        rep = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><!DOCTYPE report PUBLIC "-//JACOCO//DTD Report 1.1//EN" '
               '"report.dtd"><report name="x"><counter type="LINE" missed="1" covered="3"/></report>')
        _, doc = run(java({"pom.xml": POM % {"deps": "", "plugins": JACOCO}, "target/site/jacoco/jacoco.xml": rep}))
        self.assertEqual(doc["tests"]["coverage_measured"]["value"], {"LINE": 75.0})

    def test_internal_subset_is_rejected(self):
        evil = '<!DOCTYPE report [<!ELEMENT report ANY>]><report><counter type="LINE" missed="1" covered="1"/></report>'
        _, doc = run(java({"pom.xml": POM % {"deps": "", "plugins": JACOCO}, "target/site/jacoco/jacoco.xml": evil}))
        self.assertEqual(doc["tests"]["coverage_measured"]["status"], "UNKNOWN")

    def test_inventory_fingerprint_detects_changed_input(self):
        d, doc = run(java({"pom.xml": POM % {"deps": "", "plugins": ""}}))
        out = tempfile.mkdtemp()
        discover.main(["--repo", d, "--out", out])
        path = os.path.join(out, "discovery.json")
        self.assertEqual(validate.main(["check", path, "--repo", d]), 0)
        with open(os.path.join(d, "src/main/java/a/C.java"), "a") as fh:
            fh.write("// edit\n")
        self.assertEqual(validate.main(["check", path, "--repo", d]), 1)

    def test_tampered_fact_fails_check(self):
        d, _ = run(java({"pom.xml": POM % {"deps": "", "plugins": ""}}))
        out = tempfile.mkdtemp()
        discover.main(["--repo", d, "--out", out])
        path = os.path.join(out, "discovery.json")
        doc = json.load(open(path))
        doc["tests"]["unit_tests"]["value"]["test_classes"] = 999
        json.dump(doc, open(path, "w"))
        self.assertEqual(validate.main(["check", path]), 1)

    def test_no_temp_file_left_after_write(self):
        d, _ = run(java({"pom.xml": POM % {"deps": "", "plugins": ""}}))
        out = tempfile.mkdtemp()
        discover.main(["--repo", d, "--out", out])
        self.assertEqual(sorted(os.listdir(out)), ["discovery.json"])

    def test_absence_vs_disabled_vs_unknown(self):
        _, none = run(java({"pom.xml": POM % {"deps": "", "plugins": ""}, ".gitlab-ci.yml": "t:\n  script:\n    - mvn test\n"}))
        res = {c["id"]: c["result"] for c in none["maturity"]["criteria"]}
        self.assertEqual(res["secret_scanning"], "NO_EVIDENCE")  # nothing matched: not claimed as failing
        self.assertEqual(res["tests_run_in_ci"], "MET")
        _, off = run(java({"pom.xml": POM % {"deps": "", "plugins": ""},
                           ".gitlab-ci.yml": "t:\n  script:\n    - mvn -DskipTests package\n"}))
        res = {c["id"]: c["result"] for c in off["maturity"]["criteria"]}
        self.assertEqual(res["tests_run_in_ci"], "NOT_MET")  # positive evidence tests are off
        self.assertEqual(res["coverage"], "NOT_MET")
        _, unk = run(java({"pom.xml": POM % {"deps": "", "plugins": ""},
                           ".gitlab-ci.yml": "include:\n  - project: o/t\n    file: c.yml\n"}))
        res = {c["id"]: c["result"] for c in unk["maturity"]["criteria"]}
        self.assertEqual(res["secret_scanning"], "UNKNOWN")
        gaps = {g["criterion"]: g["title"] for g in none["gaps_and_risks"]}
        self.assertTrue(gaps["secret_scanning"].startswith("No evidence of"))

    def test_scope_limitations_and_detector_versions_recorded(self):
        _, doc = run(java({"pom.xml": POM % {"deps": "", "plugins": ""}}))
        rm = doc["run_meta"]
        self.assertEqual(rm["completeness"]["build_execution"], "not_run")
        self.assertTrue(rm["limitations"])
        self.assertEqual([d["id"] for d in rm["detectors"]][:2], ["identity", "stack"])
        self.assertTrue(all(d["version"] for d in rm["detectors"]))
        self.assertEqual(len(rm["inventory_fingerprint"]), 64)


class Contract(unittest.TestCase):
    def setUp(self):
        self.repo, self.doc = run(java({"pom.xml": POM % {"deps": SPRINGDOC, "plugins": JACOCO},
                                        ".gitlab-ci.yml": "t:\n  script:\n    - mvn verify\n"}))

    def test_schema_valid(self):
        self.assertEqual(validate.validate(self.doc), [])

    def test_schema_rejects_unknown_key(self):
        self.doc["tests"]["x"] = {"value": 1, "status": "GUESSED", "evidence": []}
        self.assertTrue(validate.validate(self.doc))

    def test_determinism(self):
        again = discover.build(self.repo)
        self.assertEqual(json.dumps(self.doc, sort_keys=True), json.dumps(again, sort_keys=True))

    def test_evidence_verifier_catches_drift(self):
        import evidence
        ev = self.doc["tests"]["coverage_tool_configured"]["evidence"][0]
        self.assertIsNone(evidence.verify(self.repo, ev))
        with open(os.path.join(self.repo, ev["path"]), "a") as fh:
            fh.write("\n")
        os.system("sed -i.bak '1s/.*/<changed>/' %s" % os.path.join(self.repo, "pom.xml"))
        ev2 = dict(ev, line_start=1, snippet="<project>")
        self.assertIsNotNone(evidence.verify(self.repo, ev2))

    def test_every_confirmed_fact_cites_evidence_or_derives_from_supported_facts(self):
        import evidence
        self.assertEqual(validate.provenance(self.doc), [])  # no allowlist: derived facts are checked through their inputs
        for fid, f in evidence.iter_facts(self.doc):
            if f["status"] == "CONFIRMED":
                self.assertTrue(f["evidence"] or f.get("derivation"), "%s is CONFIRMED with neither evidence nor derivation" % fid)

    def test_llm_cannot_touch_facts(self):
        bad = {"narrative": {"text": "x", "cites": ["tests.coverage_state"]}, "status": "CONFIRMED"}
        self.assertTrue(validate.merge_llm(json.loads(json.dumps(self.doc)), bad))
        bad2 = {"narrative": {"text": "x", "cites": ["made.up_fact"]}}
        self.assertTrue(validate.merge_llm(json.loads(json.dumps(self.doc)), bad2))
        ok = {"narrative": {"text": "Looks fine.", "cites": ["tests.coverage_state"]}}
        d = json.loads(json.dumps(self.doc))
        self.assertEqual(validate.merge_llm(d, ok), [])
        self.assertEqual(d["llm_fill"]["narrative"]["source"], "llm")
        self.assertEqual(validate.fingerprint(d), self.doc["run_meta"]["fingerprint"])

    def test_cli_exit_codes_and_ui(self):
        out = tempfile.mkdtemp()
        self.assertEqual(discover.main(["--repo", self.repo, "--out", out]), 0)
        self.assertEqual(discover.main(["--repo", "/no/such/dir"]), 2)
        html = os.path.join(out, "p.html")
        self.assertEqual(build_ui.main([out, "--out", html]), 0)
        text = open(html).read()
        self.assertIn('"contract": "discovery.v1"', text)
        self.assertNotIn("/*__DATA__*/", text)
        self.assertEqual(validate.main(["check", os.path.join(out, "discovery.json"), "--repo", self.repo]), 0)


if __name__ == "__main__":
    unittest.main()


class CommitTagging(unittest.TestCase):
    def test_an_image_tagged_with_the_commit_is_partial_tagging_not_absent(self):
        jf = "pipeline {\n  environment {\n    COMMIT_TAG = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()\n  }\n}\n"
        d, doc = run(java({"Jenkinsfile": jf}))
        res = {c["id"]: c for c in doc["maturity"]["criteria"]}["version_tagging"]
        self.assertEqual(res["result"], "PARTIAL")
        self.assertIn("build_ci.artifact_tag_from_commit", res["facts"])
        self.assertEqual(doc["build_ci"]["artifact_tag_from_commit"]["evidence"][0]["path"], "Jenkinsfile")
