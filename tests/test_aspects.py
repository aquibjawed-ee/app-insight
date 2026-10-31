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

    def test_pending_detectors_report_not_assessed_with_a_reason(self):
        doc = next(iter(self.docs.values()))
        c = next(c for a in doc["aspects"] for c in a["controls"] if c["id"] == "code.hotspots")
        self.assertEqual(c["state"], "NOT_ASSESSED")
        self.assertIn("No detector yet", c["summary"])

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
