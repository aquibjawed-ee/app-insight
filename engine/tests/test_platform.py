"""End-to-end: CLI analyse -> schemas -> C4 -> dimensions -> report; determinism; read-only; HTML rendered in a real browser when available."""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(1, HERE)
os.environ["DISCOVERY_FIXED_TIME"] = "2026-10-29T00:00:00Z"

import graph_fixtures as F  # noqa: E402
import relate  # noqa: E402
import validate  # noqa: E402
from graph import c4, dimensions, model  # noqa: E402
from test_graph import tree_hash  # noqa: E402

SD = os.path.join(HERE, "..", "schemas")
CHROME = next((p for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", shutil.which("google-chrome") or "", shutil.which("chromium") or "") if p and os.path.exists(p)), None)


def schema_check(doc, name):
    s = json.load(open(os.path.join(SD, name)))
    errs = []
    validate._mini(s, doc, s, "$", errs)
    return errs


def tree_bytes(root):
    out = {}
    for r, _, names in os.walk(root):
        for n in names:
            p = os.path.join(r, n)
            out[os.path.relpath(p, root)] = open(p, "rb").read()
    return out


class PlatformTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.repos = F.make_portfolio()
        cls.before = {n: tree_hash(r) for n, r in cls.repos.items()}
        cls.out = tempfile.mkdtemp(prefix="out-")
        cls.rc = relate.main(["analyse"] + sorted(cls.repos.values()) + ["--out", cls.out])
        for sc in (["--scenario", "java_runtime", "--to", "17"], ["--scenario", "spring_boot", "--to", "3.2", "--app", "orders-service"],
                   ["--scenario", "messaging_schema", "--topic", "orders.created"], ["--scenario", "api_contract", "--endpoint", "POST /api/stock/reserve", "--app", "inventory-service"],
                   ["--scenario", "db_migration", "--from-tech", "PostgreSQL", "--to-tech", "Oracle"], ["--scenario", "infrastructure", "--platform", "Kubernetes", "--to", "1.25"]):
            assert relate.main(["impact", "--out", cls.out] + sc) == 0
        cls.P = json.load(open(os.path.join(cls.out, "portfolio", "relationships.json")))

    def test_analyse_succeeds_and_target_repositories_are_untouched(self):
        self.assertEqual(self.rc, 0)
        self.assertEqual({n: tree_hash(r) for n, r in self.repos.items()}, self.before)
        self.assertEqual(relate.main(["validate", "--out", self.out]), 0)

    def test_every_contract_validates_against_its_schema(self):
        self.assertEqual(schema_check(self.P, "relationships.v1.schema.json"), [])
        for app in self.repos:
            d = os.path.join(self.out, app)
            self.assertEqual(schema_check(json.load(open(os.path.join(d, "relationships.json"))), "relationships.v1.schema.json"), [], app)
            self.assertEqual(schema_check(json.load(open(os.path.join(d, "safetynet.json"))), "safetynet.v1.schema.json"), [], app)
            self.assertEqual(schema_check(json.load(open(os.path.join(d, "dimensions.json"))), "dimensions.v1.schema.json"), [], app)
            self.assertEqual(schema_check(json.load(open(os.path.join(d, "resilience.json"))), "resilience.v1.schema.json"), [], app)
            self.assertEqual(validate.validate(json.load(open(os.path.join(d, "discovery.json")))), [], app)  # the existing contract is untouched
        for f in glob.glob(os.path.join(self.out, "impact", "*.json")):
            self.assertEqual(schema_check(json.load(open(f)), "impact.v1.schema.json"), [], f)

    def test_schema_rejects_malformed_graphs(self):
        bad = json.loads(json.dumps(self.P))
        bad["edges"][0]["basis"] = "guessed"
        self.assertTrue(schema_check(bad, "relationships.v1.schema.json"))
        bad = json.loads(json.dumps(self.P))
        bad["edges"][0]["target"] = "nope"
        self.assertTrue([e for e in model.validate_integrity(bad) if "is not a node" in e])
        bad = json.loads(json.dumps(self.P))
        bad["edges"][0]["evidence"] = []
        self.assertTrue([e for e in model.validate_integrity(bad) if "no evidence" in e])

    def test_tampered_evidence_is_detected(self):
        bad = json.loads(json.dumps(self.P))
        e = next(e for e in bad["edges"] if e["evidence"] and e["evidence"][0].get("kind") == "file")
        e["evidence"][0]["snippet"] = "something the file does not say"
        errs = model.validate_integrity(bad, self.repos)
        self.assertTrue([x for x in errs if "snippet mismatch" in x])

    def test_whole_analysis_is_byte_identical_on_rerun(self):
        out2 = tempfile.mkdtemp(prefix="out2-")
        self.assertEqual(relate.main(["analyse"] + sorted(self.repos.values()) + ["--out", out2]), 0)
        a, b = tree_bytes(self.out), tree_bytes(out2)
        a.pop("manifest.json"); b.pop("manifest.json")  # same content; excluded because it records absolute repository paths
        a = {k: v for k, v in a.items() if not k.startswith("impact") and not k.endswith(".html")}
        b = {k: v for k, v in b.items() if not k.endswith(".html")}
        self.assertEqual(sorted(a), sorted(b))
        for k in a:
            self.assertEqual(a[k], b[k], k)

    def test_unchanged_repository_is_not_stale_and_a_changed_one_is(self):
        p = os.path.join(self.repos["notifier-a"], "NEW.txt")
        open(p, "w").write("x")
        try:
            self.assertEqual(relate.main(["validate", "--out", self.out]), 1)
        finally:
            os.remove(p)
        self.assertEqual(relate.main(["validate", "--out", self.out]), 0)

    def test_duplicate_application_ids_are_disambiguated_not_refused(self):
        # review F14: one duplicate name (api, service) among 300 repositories must not abort the portfolio
        d = tempfile.mkdtemp()
        a = F.make_repo(os.path.join(d, "x"), "same", F.NOTIFIER_A)
        b = F.make_repo(os.path.join(d, "y"), "same", F.NOTIFIER_B)
        self.assertEqual(relate.main(["analyse", a, b, "--out", os.path.join(d, "o")]), 0)
        with open(os.path.join(d, "o", "manifest.json")) as fh:
            man = json.load(fh)
        self.assertEqual(sorted(x["app"] for x in man["applications"]), ["same", "same-y"])
        self.assertEqual(man["renamed"][0]["from"], "same")

    def test_c4_views_are_drawn_from_the_graph_and_keep_unresolved_visible(self):
        v = c4.context(self.P)
        kinds = {n["kind"] for n in v["nodes"]}
        self.assertTrue({"app", "topic", "db", "ext", "unresolved"} <= kinds)
        labels = {n["label"] for n in v["nodes"]}
        self.assertIn("ambiguous: notifier", labels)
        self.assertIn("unresolved: loyalty-service", labels)
        self.assertEqual(len([n for n in v["nodes"] if n["kind"] == "topic" and n["label"] == "orders.created"]), 2)  # two clusters, two topics
        for e in v["edges"]:
            for i in e["edge_ids"]:
                self.assertIn(i, {x["id"] for x in self.P["edges"]})  # every drawn line traces to graph edges
        svg = c4.render_svg(v)
        self.assertEqual(svg, c4.render_svg(c4.context(self.P)))  # deterministic
        self.assertIn("edge unresolved", svg)
        self.assertIn("ambiguous candidate", svg)

    def test_container_view_shows_callers_deployment_and_data(self):
        v = c4.container(self.P, "inventory-service")
        self.assertIn("orders-service", {n["label"] for n in v["nodes"]})
        self.assertIn("deployed on Kubernetes", v["boundaries"][0]["sub"])
        self.assertTrue([n for n in v["nodes"] if n["kind"] == "db"])
        self.assertIn("flowchart LR", c4.render_mermaid(v))

    def test_svg_escapes_hostile_names(self):
        g = json.loads(json.dumps(self.P))
        g["nodes"][0]["name"] = '<script>alert(1)</script>"&'
        svg = c4.render_svg(c4.context(g))
        self.assertNotIn("<script>", svg)

    def test_dimensions_are_separate_and_unknown_is_not_invented(self):
        d = json.load(open(os.path.join(self.out, "orders-service", "dimensions.json")))["dimensions"]
        self.assertEqual(len(d), 9)
        self.assertEqual(d["business_criticality"]["state"], "unknown")
        self.assertEqual(d["security_exposure"]["state"], "not_assessed")
        self.assertEqual(d["technology_lifecycle"]["level"], "attention")  # Boot 2.7: open-source support ended, paid support until 2029 (spring.io)
        self.assertEqual(d["technology_lifecycle"]["values"]["spring_boot"]["oss_status"], "commercial_only")
        def keys(o):
            return {k for x in (o.values() if isinstance(o, dict) else o if isinstance(o, list) else []) for k in keys(x)} | (set(o) if isinstance(o, dict) else set())
        self.assertNotIn("score", keys({k: v for k, v in d.items() if k != "engineering_maturity"}))  # only the maturity dimension carries a score, and it is not combined
        d2 = dimensions.assess(json.load(open(os.path.join(self.out, "orders-service", "discovery.json"))), criticality={"orders-service": {"tier": "tier-1", "source": "CMDB export 2026-09"}})
        self.assertEqual(d2["dimensions"]["business_criticality"]["state"], "assessed")
        self.assertIn("not_assessed", {v["state"] for v in d2["dimensions"].values()})  # nothing extracted -> coupling not assessed, not guessed

    # the HTML report moved to the app-insight product: tests/test_report.py


if __name__ == "__main__":
    unittest.main()
