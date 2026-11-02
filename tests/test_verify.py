"""The accuracy and consistency gate: a clean run passes, and each kind of wrong claim is caught by its rule."""
import copy
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
from app_insight import report as R  # noqa: E402
from app_insight import verify as V  # noqa: E402
import graph_fixtures as F  # noqa: E402
import relate  # noqa: E402


class VerifyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, repos = F.make_portfolio()
        cls.run_dir = tempfile.mkdtemp(prefix="ver-")
        out = os.path.join(cls.run_dir, "analysis")
        assert relate.main(["analyse"] + sorted(repos.values()) + ["--out", out]) == 0
        packs = A.load_remedy_packs(["modernise-plugin", "generic"])
        cls.docs = A.build(out, A.load_catalogue(), packs)
        R.build(out, os.path.join(cls.run_dir, "report.html"), A.load_catalogue(), packs, [], "test")
        cls.app = sorted(cls.docs)[0]
        cls.path = os.path.join(out, cls.app, "aspects.json")
        with open(cls.path) as fh:
            cls.clean = json.load(fh)

    def tearDown(self):
        with open(self.path, "w") as fh:
            json.dump(self.clean, fh)

    def tamper(self, fn):
        doc = copy.deepcopy(self.clean)
        fn(doc)
        with open(self.path, "w") as fh:
            json.dump(doc, fh)
        return {p["rule"] for p in V.check(self.run_dir)["problems"] if p["app"] == self.app}

    def cited(self, doc):
        return next(c for a in doc["aspects"] for c in a["controls"] if c["evidence"] and c["evidence"][0].get("kind") == "file")

    def test_a_clean_run_passes(self):
        res = V.check(self.run_dir)
        self.assertTrue(res["ok"], res["problems"][:5])
        self.assertGreater(res["checked"]["lines_reread"], 0)

    def test_a_cited_line_that_does_not_say_it_is_caught(self):
        self.assertIn("ACC-1", self.tamper(lambda d: self.cited(d)["evidence"][0].update(snippet="not what the file says")))

    def test_in_place_without_a_citation_is_caught(self):
        def f(d):
            c = self.cited(d)
            c.update(state="PRESENT", evidence=[])
        self.assertIn("ACC-2", self.tamper(f))

    def test_enforced_without_a_ci_file_is_caught(self):
        def f(d):
            c = self.cited(d)
            c["level"] = "enforced"
            c["evidence"] = [e for e in c["evidence"] if not V.CI_FILE.search(e.get("path") or "")] or [{"kind": "other"}]
        self.assertIn("ACC-3", self.tamper(f))

    def test_a_status_that_does_not_follow_from_its_controls_is_caught(self):
        def f(d):
            d["aspects"][0]["status"] = "in_place" if d["aspects"][0]["status"] != "in_place" else "issues"
        self.assertTrue({"CON-2", "CON-4", "CON-6"} <= self.tamper(f))

    def test_in_place_built_on_an_unknown_is_caught(self):
        def f(d):
            c = self.cited(d)
            c.update(state="PRESENT", summary="Spring Boot 3.5.3: open-source support line-specific (unknown)")
        self.assertIn("ACC-7", self.tamper(f))

    def test_controls_that_contradict_each_other_are_caught(self):
        def f(d):
            cs = {c["id"]: c for a in d["aspects"] for c in a["controls"]}
            cs["data.migrations"].update(state="NOT_APPLICABLE", summary=A.NEED_TEXT["database"], severity=None, finding=None)
            cs["runtime.db_timeouts"].update(state="PRESENT")
        self.assertIn("CON-7", self.tamper(f))

    def test_a_secret_in_any_written_file_fails_the_run(self):
        leak = os.path.join(self.run_dir, "analysis", "portfolio", "planted.json")
        with open(leak, "w") as fh:
            fh.write('{"target": "https://hooks.slack.com/services/T0000AAAA/B0000BBBB/' + "x" * 24 + '"}\n')
        try:
            self.assertIn("ACC-9", {p["rule"] for p in V.check(self.run_dir)["problems"]})
        finally:
            os.remove(leak)

    def test_readme_without_a_description_is_partial_with_a_fitting_remedy(self):
        ctl = next(c for c in A.load_catalogue()["controls"] if c["id"] == "knowledge.readme")
        disc = {"identity": {"about": {"status": "NOT_FOUND", "value": None, "note": "README has no descriptive text",
                                       "evidence": [{"kind": "file", "path": "README.md", "line_start": 1, "snippet": "Office Integration"}]}}}
        r = A.evaluate(ctl, A.Context("x", disc, None, None, None, None, {"nodes": [], "edges": []}))
        self.assertEqual(r["state"], "PARTIAL")

    def test_graceful_shutdown_on_an_old_spring_boot_is_an_upgrade(self):
        ctl = next(c for c in A.load_catalogue()["controls"] if c["id"] == "runtime.graceful_shutdown")
        cx = A.Context("x", {"stack": {"spring_boot_version": {"value": "1.5.10.RELEASE"}}}, None, None, None, None, {"nodes": [], "edges": []})
        self.assertEqual([r["key"] for r in A.remedies_for(ctl, A.load_remedy_packs(["generic"]), cx)], ["graceful_shutdown_upgrade"])

    def absent(self, d):
        hide = {c["id"] for c in A.load_catalogue()["controls"] if c.get("search", {}).get("blind_to", c.get("search", {}).get("in"))}
        return next(c for a in d["aspects"] for c in a["controls"] if c["state"] == "ABSENT" and c.get("searched") and c["id"] in hide)

    def test_every_not_found_says_where_it_looked(self):
        cs = [c for a in self.clean["aspects"] for c in a["controls"] if c["state"] == "ABSENT"]
        self.assertTrue(cs)
        self.assertTrue(all(c["searched"]["for"] and c["searched"]["in"] for c in cs), [c["id"] for c in cs if not c.get("searched")])

    def test_a_not_found_without_a_search_record_is_caught(self):
        self.assertIn("ACC-10", self.tamper(lambda d: self.absent(d).update(searched=None)))

    def test_a_not_found_in_an_area_outside_the_scan_is_caught(self):
        def f(d):
            area = next(a for c in A.load_catalogue()["controls"] if c["id"] == self.absent(d)["id"] for a in c["search"].get("blind_to", c["search"]["in"]))
            d["scope"]["blind_spots"] = [{"id": "x", "area": area, "what": "something held elsewhere", "at": ["pom.xml:3"]}]
        self.assertIn("CON-8", self.tamper(f))

    def test_a_blind_spot_turns_not_found_into_undecided(self):
        ctl = next(c for c in A.load_catalogue()["controls"] if c["id"] == "security.sast")
        spot = {"id": "build.parent_pom", "area": "build", "what": "a parent POM from outside this repository (com.acme:parent)", "at": ["pom.xml:5"]}
        disc = {"maturity": {"criteria": [{"id": "sast", "result": "NO_EVIDENCE", "facts": ["security.sast"]}]},
                "scope": {"blind_spots": {"value": [spot], "status": "CONFIRMED", "evidence": [{"kind": "file", "path": "pom.xml", "line_start": 5, "snippet": "<groupId>com.acme</groupId>"}]},
                          "files_read": {"value": {"build": {"count": 1, "files": ["pom.xml"]}, "ci": {"count": 0, "files": []}}}}}
        r = A.evaluate(ctl, A.Context("x", disc, None, None, None, None, {"nodes": [], "edges": []}))
        self.assertEqual(r["state"], "UNKNOWN")
        self.assertIn("pom.xml:5", r["summary"])
        disc["scope"]["blind_spots"]["value"] = []
        r = A.evaluate(ctl, A.Context("x", disc, None, None, None, None, {"nodes": [], "edges": []}))
        self.assertEqual((r["state"], [x["count"] for x in r["searched"]["in"]]), ("ABSENT", [0, 1]))

    def test_a_blind_spot_only_hides_what_it_could_hold(self):
        ctl = next(c for c in A.load_catalogue()["controls"] if c["id"] == "testing.integration")  # a parent POM cannot add test classes
        spot = {"id": "build.parent_pom", "area": "build", "what": "a parent POM from outside this repository (com.acme:parent)", "at": ["pom.xml:5"]}
        disc = {"maturity": {"criteria": [{"id": "integration_tests", "result": "NO_EVIDENCE", "facts": ["tests.integration_tests"]}]},
                "scope": {"blind_spots": {"value": [spot], "evidence": []}, "files_read": {"value": {"build": {"count": 1, "files": ["pom.xml"]}, "test_source": {"count": 2, "files": []}}}}}
        self.assertEqual(A.evaluate(ctl, A.Context("x", disc, None, None, None, None, {"nodes": [], "edges": []}))["state"], "ABSENT")

    def test_findings_that_drift_from_the_gap_controls_are_caught(self):
        self.assertIn("CON-3", self.tamper(lambda d: d["findings"].append("made.up@" + self.app)))


if __name__ == "__main__":
    unittest.main()
