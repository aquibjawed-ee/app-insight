"""The aspect trace: every control of the catalogue appears once per application, states are from the contract, applicability follows
the application's profile, findings are exactly the controls in a gap state, and remedy packs layer by priority."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(1, os.path.join(HERE, "..", "engine", "tests"))
os.environ["DISCOVERY_FIXED_TIME"] = "2026-10-29T00:00:00Z"

from app_insight import aspects as A  # noqa: E402
from app_insight import engine_path  # noqa: E402,F401
import graph_fixtures as F  # noqa: E402
import relate  # noqa: E402


class AspectsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, repos = F.make_portfolio()
        cls.out = tempfile.mkdtemp(prefix="asp-")
        assert relate.main(["analyse"] + sorted(repos.values()) + ["--out", cls.out]) == 0
        cls.cat = A.load_catalogue()
        cls.docs = A.build(cls.out, cls.cat, A.load_remedy_packs(["modernise-plugin", "generic"]))

    def test_catalogue_is_consistent(self):
        ids = [c["id"] for c in self.cat["controls"]]
        self.assertEqual(len(ids), len(set(ids)))
        aspects = {a["id"] for a in self.cat["aspects"]}
        self.assertTrue(all(c["aspect"] in aspects for c in self.cat["controls"]))
        self.assertEqual(sorted(a["order"] for a in self.cat["aspects"]), list(range(1, len(aspects) + 1)))

    def test_every_control_appears_once_with_a_contract_state(self):
        for app, doc in self.docs.items():
            cs = [c for a in doc["aspects"] for c in a["controls"]]
            self.assertEqual(sorted(c["id"] for c in cs), sorted(c["id"] for c in self.cat["controls"]), app)
            for c in cs:
                self.assertIn(c["state"], self.cat["states"], c["id"])
                self.assertTrue(c["summary"], c["id"])
                if c["level"]:
                    self.assertIn(c["level"], self.cat["levels"])

    def test_findings_are_exactly_the_controls_in_a_gap_state(self):
        for app, doc in self.docs.items():
            gaps = sorted(c["finding"] for a in doc["aspects"] for c in a["controls"] if c["state"] in A.GAP_STATES)
            self.assertEqual(sorted(doc["findings"]), gaps)
            for a in doc["aspects"]:
                for c in a["controls"]:
                    self.assertEqual(bool(c["severity"]), c["state"] in A.GAP_STATES)

    def test_not_assessed_is_never_counted_as_in_place(self):
        for doc in self.docs.values():
            for a in doc["aspects"]:
                live = [c for c in a["controls"] if c["state"] != "NOT_APPLICABLE"]
                if live and all(c["state"] in ("NOT_ASSESSED", "UNKNOWN") for c in live):
                    self.assertEqual(a["status"], "not_assessed", a["id"])
                if a["status"] == "in_place":
                    self.assertTrue(any(c["state"] == "PRESENT" for c in live))

    def test_an_aspect_with_unchecked_controls_is_never_plain_in_place(self):
        for doc in self.docs.values():
            for a in doc["aspects"]:
                live = [c for c in a["controls"] if c["state"] != "NOT_APPLICABLE" and not c.get("pending")]
                if a["status"] == "in_place":
                    self.assertTrue(all(c["state"] == "PRESENT" for c in live), a["id"])
                    self.assertFalse(any(c.get("pending") for c in a["controls"]), a["id"])  # a check never run is not a pass
                self.assertEqual(a["coverage"]["applicable"], len(live))  # a detector we have not built is not the application's gap

    def test_every_control_in_place_cites_a_line(self):
        for doc in self.docs.values():
            neg = {x["id"] for x in self.cat["controls"] if x.get("negative_scan")}  # "none found in N files" has nothing to cite
            for c in (c for a in doc["aspects"] for c in a["controls"] if c["state"] == "PRESENT"):
                if c["id"] not in neg:
                    self.assertTrue(c["evidence"], c["id"])

    def test_no_scan_run_is_not_checked_rather_than_a_gap(self):
        for doc in self.docs.values():
            c = next(c for a in doc["aspects"] for c in a["controls"] if c["id"] == "security.exposure_known")
            self.assertEqual(c["state"], "NOT_ASSESSED")
            self.assertIsNone(c["finding"])

    def test_enforced_is_only_claimed_when_the_pipeline_runs_it(self):
        for doc in self.docs.values():
            for c in (c for a in doc["aspects"] for c in a["controls"]):
                if c["level"] == "enforced":
                    self.assertEqual(c["state"], "PRESENT", c["id"])

    def test_build_and_ci_controls_do_not_cite_test_sources(self):
        for doc in self.docs.values():
            for c in (c for a in doc["aspects"] for c in a["controls"] if c["id"] in ("testing.coverage_gate", "delivery.build", "delivery.version_tagging")):
                for e in c["evidence"]:
                    self.assertNotRegex(e["path"], A.TEST_PATH, c["id"])

    def test_graph_checks_with_nothing_to_check_do_not_apply(self):
        cx = A.Context("x", {}, None, None, None, None, {"nodes": [], "edges": []})
        for which in ("shared_database", "profile_differences", "unresolved_placeholders", "unmatched_calls"):
            self.assertEqual(A.eval_graph(which, cx)["state"], "NOT_APPLICABLE", which)

    def test_a_remedy_is_offered_only_where_it_works(self):
        packs = A.load_remedy_packs(["modernise-plugin", "generic"])
        ctl = next(c for c in self.cat["controls"] if c["id"] == "delivery.version_tagging")
        cx = A.Context("x", {"build_ci": {"ci_system": {"value": ["jenkins"]}}}, None, None, None, None, {"nodes": [], "edges": []})
        self.assertEqual([r["pack"] for r in A.remedies_for(ctl, packs, cx)], ["generic"])  # /modernise-pipeline edits .gitlab-ci.yml
        cx.stack["ci_system"] = ["gitlab"]
        self.assertEqual(A.remedies_for(ctl, packs, cx)[0]["cmd"], "/modernise-pipeline")

    def _cx(self, framework=None, deps=(), sn=None):
        disc = {"stack": {"app_framework": {"value": {"name": framework, "label": framework.title()} if framework else None},
                          "external_dependencies": {"value": list(deps)}}}
        return A.Context("x", disc, None, None, sn, None, {"nodes": [], "edges": []})

    def test_a_spring_only_check_says_not_recognised_for_another_framework(self):
        ctl = next(c for c in self.cat["controls"] if c["id"] == "runtime.http_timeouts")
        r = A.evaluate(ctl, self._cx("dropwizard"))
        self.assertEqual(r["state"], "UNKNOWN")
        self.assertIn("Not recognised for Dropwizard", r["summary"])
        self.assertEqual(A.evaluate(ctl, self._cx("spring_boot"))["state"], "NOT_APPLICABLE")  # Spring Boot with no client: truly does not apply

    def test_relational_checks_do_not_apply_to_document_stores_or_in_memory_databases(self):
        ctl = next(c for c in self.cat["controls"] if c["id"] == "data.migrations")
        for deps in ([{"kind": "Database", "technology": "DynamoDB"}], [{"kind": "Database", "technology": "H2 (embedded)", "embedded": True}]):
            self.assertEqual(A.evaluate(ctl, self._cx("spring_boot", deps))["state"], "NOT_APPLICABLE", deps)
        self.assertEqual(A.evaluate(ctl, self._cx("spring_boot", [{"kind": "Database", "technology": "PostgreSQL"}]))["state"], "ABSENT")

    def test_tests_that_reach_a_component_by_class_are_partial_not_absent(self):
        sn = {"summary": {"api_endpoint": {"class_level": 9, "direct": 0, "mapped_no_assertion_seen": 0, "mapped_with_assertions": 9, "unverified": 0}}, "components": []}
        r = A.eval_safetynet(self._cx("spring_boot", sn=sn))
        self.assertEqual(r["state"], "PARTIAL")
        self.assertIn("9 more are reached only by a test that names their class", r["summary"])

    def test_spring_only_remedies_are_not_offered_to_other_frameworks(self):
        packs = A.load_remedy_packs(["modernise-plugin", "generic"])
        ctl = next(c for c in self.cat["controls"] if c["id"] == "api.openapi")
        self.assertEqual([r["pack"] for r in A.remedies_for(ctl, packs, self._cx("dropwizard"))], ["generic"])

    def test_pipeline_checks_are_unknown_when_the_pipeline_lives_outside_the_repository(self):
        disc = {"build_ci": {"ci_system": {"value": ["external"], "evidence": [{"kind": "file", "path": "README.md", "line_start": 3, "snippet": "jenkins"}]}},
                "maturity": {"criteria": [{"id": "automated_build", "result": "NO_EVIDENCE", "facts": []}]}}
        cx = A.Context("x", disc, None, None, None, None, {"nodes": [], "edges": []})
        r = A.eval_criterion("automated_build", cx)
        self.assertEqual(r["state"], "UNKNOWN")
        self.assertIn("README.md:3", r["summary"])

    def test_services_named_in_configuration_but_not_traced_make_the_map_incomplete(self):
        disc = {"runtime": {"service_urls": {"value": [{"key": "trustedApiBaseUrl", "value": "https://x", "at": "src/main/resources/application.yml:18"}],
                                             "evidence": [{"kind": "file", "path": "src/main/resources/application.yml", "line_start": 18, "snippet": "trustedApiBaseUrl: https://x"}]}}}
        cx = A.Context("x", disc, None, None, None, None, {"nodes": [], "edges": []})
        r = A.eval_graph("unmatched_calls", cx)
        self.assertEqual(r["state"], "UNKNOWN")
        self.assertIn("trustedApiBaseUrl", r["summary"])

    def test_pending_detectors_report_not_assessed_with_a_reason(self):
        doc = next(iter(self.docs.values()))
        c = next(c for a in doc["aspects"] for c in a["controls"] if c["id"] == "code.hotspots")
        self.assertEqual(c["state"], "NOT_ASSESSED")
        self.assertIn("No detector yet", c["summary"])

    def test_runtime_controls_take_the_detector_verdict_and_a_runtime_remedy(self):
        doc = self.docs["orders-service"]
        cs = {c["id"]: c for a in doc["aspects"] for c in a["controls"]}
        for cid in ("runtime.http_timeouts", "runtime.messaging_errors", "runtime.db_timeouts", "runtime.graceful_shutdown", "observability.structured_logging"):
            self.assertNotEqual(cs[cid]["state"], "NOT_ASSESSED", cid)
            self.assertNotIn("No detector yet", cs[cid]["summary"])
        self.assertEqual(cs["runtime.graceful_shutdown"]["state"], "ABSENT")  # Spring Boot 2.7, server.shutdown not set
        self.assertEqual(cs["runtime.graceful_shutdown"]["remedies"][0]["key"], "graceful_shutdown")

    def test_an_analysis_without_the_runtime_section_is_not_assessed(self):
        ctl = next(c for c in self.cat["controls"] if c["id"] == "runtime.db_timeouts")
        cx = type("Cx", (), {"disc": {}})()
        self.assertEqual(A.eval_check(ctl["source"]["check"], cx)["state"], "NOT_ASSESSED")

    def test_remedy_packs_layer_by_priority(self):
        ctl = next(c for c in self.cat["controls"] if c["id"] == "delivery.build")
        both = A.remedies_for(ctl, A.load_remedy_packs(["modernise-plugin", "generic"]))
        generic = A.remedies_for(ctl, A.load_remedy_packs(["generic"]))
        self.assertEqual(both[0]["cmd"], "/modernise-pipeline")
        self.assertEqual(generic[0]["key"], "ci")
        self.assertNotIn("cmd", generic[0])

    def test_written_files_match_the_returned_documents(self):
        for app, doc in self.docs.items():
            with open(os.path.join(self.out, app, "aspects.json")) as fh:
                self.assertEqual(json.load(fh)["findings"], doc["findings"])
        with open(os.path.join(self.out, "portfolio", "aspects.json")) as fh:
            self.assertEqual(sorted(json.load(fh)["applications"]), sorted(self.docs))


if __name__ == "__main__":
    unittest.main()
