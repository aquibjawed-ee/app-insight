"""Meta-tests: the benchmark must pass on the shipped fixtures AND be able to fail. A benchmark that cannot fail proves nothing."""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.join(HERE, "..", "benchmark")
sys.path.insert(0, BENCH)
import run_benchmark as rb  # noqa: E402


def run_cases(fixtures):
    out = tempfile.mkdtemp()
    code = rb.main(["--fixtures", fixtures, "--out", out])
    return code, json.load(open(os.path.join(out, "report.json")))


class ShippedBenchmark(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            cls.code, cls.report = run_cases(os.path.join(BENCH, "fixtures"))

    def test_all_gates_pass(self):
        self.assertEqual(self.report["gates"], {k: True for k in self.report["gates"]}, self.report["failures_by_rule"])
        self.assertEqual(self.code, 0)

    def test_scope_covers_the_required_scenarios(self):
        names = {c["name"] for c in self.report["cases"]}
        cats = {c["category"] for c in self.report["cases"]}
        self.assertEqual(cats, {"positive", "negative", "contradictory", "insufficient"})
        for needle in ("maven", "gradle", "kotlin", "kover", "jacoco", "openapi", "multimodule", "partial_run", "gate"):
            self.assertTrue(any(needle in n for n in names), needle)
        self.assertGreaterEqual(len(names), 50)

    def test_unsupported_scenarios_are_documented_not_hidden(self):
        reasons = {u["rule"]: u["reason"] for u in self.report["unsupported"]}
        # nothing is unsupported right now (jvmToolchain and version catalogs are read); any future gap must carry a reason
        self.assertTrue(all(r for r in reasons.values()))
        self.assertNotIn("version-catalog", reasons)  # catalogs are read now; their fixtures are ordinary expectations

    def test_expectations_are_hand_written_ground_truth(self):
        # every case file carries a human description and a rule label on each expectation; none contains engine-only fields
        for n in os.listdir(os.path.join(BENCH, "fixtures")):
            case = json.load(open(os.path.join(BENCH, "fixtures", n, "case.json")))
            self.assertTrue(case["description"].strip(), n)
            for e in case.get("facts", []) + case.get("criteria", []):
                self.assertIn("rule", e, n)
                self.assertNotIn("actual", e, n)


class BenchmarkCanFail(unittest.TestCase):
    def _copy(self, name):
        root = tempfile.mkdtemp()
        shutil.copytree(os.path.join(BENCH, "fixtures", name), os.path.join(root, name))
        return root, os.path.join(root, name, "case.json")

    def _mutate(self, name, fn):
        root, path = self._copy(name)
        case = json.load(open(path))
        fn(case)
        json.dump(case, open(path, "w"))
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            return run_cases(root)

    def test_a_wrong_fact_expectation_fails_the_gate_and_is_grouped(self):
        def wrong(c):
            c["facts"][0]["value"] = "scala"  # stack.language is java in this fixture
        code, rep = self._mutate("maven_jacoco_gate_reached_by_ci", wrong)
        self.assertEqual(code, 1)
        self.assertIn("stack", rep["failures_by_detector"])
        self.assertIn("language-from-source-files", rep["failures_by_rule"])
        self.assertLess(rep["metrics"]["fact_precision"], 1.0)

    def test_false_met_is_counted_and_fails(self):
        def wrong(c):  # the engine says MET; pretend the truth is PARTIAL
            for e in c["criteria"]:
                if e["id"] == "coverage":
                    e["result"] = ["PARTIAL"]
        code, rep = self._mutate("maven_jacoco_gate_reached_by_ci", wrong)
        self.assertEqual((code, rep["metrics"]["false_met"]), (1, 1))
        self.assertFalse(rep["gates"]["no_false_met"])

    def test_never_met_guard_trips(self):
        def wrong(c):
            c["never_met"] = ["coverage"]
        code, rep = self._mutate("maven_jacoco_gate_reached_by_ci", wrong)
        self.assertEqual(code, 1)
        self.assertIn("no-false-met", rep["failures_by_rule"])

    def test_forbidden_output_is_detected(self):
        def wrong(c):
            c["forbid_in_output"] = ["spring-boot-starter-parent"]  # appears in cited evidence
        code, rep = self._mutate("maven_jacoco_gate_reached_by_ci", wrong)
        self.assertEqual(code, 1)

    def test_unsupported_label_turns_a_failure_into_documentation(self):
        def label(c):
            c["facts"][0]["value"] = "scala"
            c["facts"][0]["unsupported"] = "deliberately wrong, labelled"
        code, rep = self._mutate("maven_jacoco_gate_reached_by_ci", label)
        self.assertEqual(code, 0)
        self.assertTrue(any(u["reason"] == "deliberately wrong, labelled" for u in rep["unsupported"]))

    def test_integrity_check_flags_an_unsupported_confirmed_fact(self):
        case = {"name": "x", "category": "positive", "description": "d", "facts": [], "criteria": []}
        d = tempfile.mkdtemp()
        shutil.copytree(os.path.join(BENCH, "fixtures", "maven_no_tests_no_ci", "repo"), os.path.join(d, "r"))
        doc, bad = rb.run_engine(os.path.join(BENCH, "fixtures", "maven_no_tests_no_ci"), {})
        broken = copy.deepcopy(doc)
        broken["stack"]["java_version"] = {"value": "17", "status": "CONFIRMED", "evidence": []}
        _, _, integrity, _ = rb.evaluate_case(case, broken, [], doc)
        self.assertIn("stack.java_version", integrity["unsupported_confirmed"])
        self.assertTrue(integrity["provenance_errors"])

    def test_determinism_check_flags_a_changed_replay(self):
        case = {"name": "x", "category": "positive", "description": "d", "facts": [], "criteria": []}
        doc, _ = rb.run_engine(os.path.join(BENCH, "fixtures", "maven_no_tests_no_ci"), {})
        other = copy.deepcopy(doc)
        other["stack"]["language"]["value"] = "changed"
        _, _, _, det = rb.evaluate_case(case, doc, [], other)
        self.assertFalse(det["identical"])


class RegressionsFoundByTheBenchmark(unittest.TestCase):
    def _doc(self, files):
        import test_discovery as td
        return td.run(files)[1]

    def test_compact_pom_parent_version_and_long_line_threshold(self):
        import test_discovery as td
        pom = ("<project><parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>3.2.0</version></parent>"
               "<groupId>d</groupId><artifactId>s</artifactId><version>1.0.0</version><build><plugins><plugin><artifactId>jacoco-maven-plugin</artifactId>"
               "<executions><execution><goals><goal>check</goal></goals><configuration><rules><rule><limits><limit><counter>LINE</counter>"
               "<value>COVEREDRATIO</value><minimum>0.80</minimum></limit></limits></rule></rules></configuration></execution></executions></plugin></plugins></build></project>")
        doc = self._doc({"pom.xml": pom})
        self.assertEqual(doc["stack"]["spring_boot_version"]["value"], "3.2.0")
        self.assertEqual(doc["tests"]["coverage_threshold_pct"]["value"], 80.0)

    def test_groovy_dsl_kotlin_plugin_and_qualified_test_annotation(self):
        doc = self._doc({"build.gradle": "plugins {\n  id 'org.jetbrains.kotlin.jvm' version '1.9.0'\n}\n",
                         "src/test/java/a/ATest.java": "class ATest { @org.junit.jupiter.api.Test void t() {} }\n"})
        self.assertEqual(doc["stack"]["kotlin_version"]["value"], "1.9.0")
        self.assertEqual(doc["tests"]["unit_tests"]["value"]["test_classes"], 1)

    def test_absence_of_a_spec_is_not_a_confirmed_fact(self):
        doc = self._doc({"pom.xml": "<project/>", "src/main/java/a/C.java": "@RestController class C {}\n"})
        f = doc["api"]["openapi_exposure"]
        self.assertEqual((f["value"], f["status"]), ("not_exposed", "NOT_FOUND"))


if __name__ == "__main__":
    unittest.main()
