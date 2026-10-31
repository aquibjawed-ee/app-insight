"""Phase 3: safety-net mapping. `unverified` is never `untested`; mapping needs a static reference."""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(1, HERE)
os.environ["DISCOVERY_FIXED_TIME"] = "2026-01-01T00:00:00Z"

import discover  # noqa: E402
import graph_fixtures as F  # noqa: E402
from graph import extract, safetynet  # noqa: E402


class SafetyNetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.repos = F.make_portfolio(names=["orders-service", "inventory-service"])
        cls.sn = {}
        for a, r in cls.repos.items():
            d = discover.build(r)
            cls.sn[a] = safetynet.map_application(r, extract.extract(r, d), d)

    def comp(self, app, kind, label):
        return next(c for c in self.sn[app]["components"] if c["kind"] == kind and c["label"] == label)

    def test_route_in_test_with_assertion_is_mapped_with_assertions(self):
        c = self.comp("orders-service", "api_endpoint", "GET /api/orders/{id}")
        self.assertEqual(c["classification"], "mapped_with_assertions")
        self.assertIn("/api/orders/1", c["mapping"][0]["how"])
        self.assertEqual(c["mapping"][0]["evidence"]["path"], "src/test/java/com/shop/orders/OrderControllerTest.java")

    def test_route_without_assertion_is_reported_as_such(self):
        self.assertEqual(self.comp("orders-service", "api_endpoint", "POST /api/orders")["classification"], "mapped_no_assertion_seen")

    def test_class_level_mapping_is_weaker_and_says_so(self):
        c = self.comp("orders-service", "api_endpoint", "DELETE /api/orders/{id}")
        self.assertEqual(c["classification"], "mapped_no_assertion_seen")
        self.assertIn("class level", c["mapping"][0]["how"])
        self.assertIn("class level", c["explanation"])

    def test_concrete_id_does_not_map_to_a_more_specific_literal_endpoint(self):
        endpoints = [{"id": "a", "attrs": {"method": "GET", "path_shape": "/o/{}"}}, {"id": "b", "attrs": {"method": "GET", "path_shape": "/o/export"}}]
        self.assertEqual([n["id"] for n in safetynet._best("/o/export", "GET", endpoints, "")], ["b"])
        self.assertEqual([n["id"] for n in safetynet._best("/o/42", "GET", endpoints, "")], ["a"])
        tie = endpoints + [{"id": "c", "attrs": {"method": "GET", "path_shape": "/{}/{}"}}]
        self.assertEqual(safetynet._best("/o/42", "GET", tie, ""), [tie[0]])  # most literal segments wins

    def test_unmapped_component_is_unverified_never_untested(self):
        c = self.comp("orders-service", "message_publisher", "publishes to orders.created")
        self.assertEqual(c["classification"], "unverified")
        self.assertEqual(c["dimensions"]["mapped_to_component"], "unknown")
        self.assertNotIn("untested", {c["classification"] for s in self.sn.values() for c in s["components"]})
        self.assertIn("does not show that none exists", c["explanation"])

    def test_pass_state_and_component_coverage_are_unknown_because_nothing_ran(self):
        for s in self.sn.values():
            self.assertEqual(s["repository_level"]["passes"]["state"], "unknown")
            for c in s["components"]:
                self.assertEqual(c["dimensions"]["passes"], "unknown")
                self.assertEqual(c["dimensions"]["coverage_measured"], "unknown")

    def test_database_path_mapped_through_repository_in_data_test(self):
        c = self.comp("orders-service", "database_path", "writes via repository")
        self.assertEqual(c["classification"], "mapped_with_assertions")

    def test_downstream_call_without_stub_is_unverified(self):
        c = self.comp("orders-service", "downstream_http", "calls inventory-service POST /api/stock/reserve")
        self.assertEqual(c["classification"], "unverified")

    def test_a_plain_unit_test_of_the_controller_class_maps_at_class_level(self):
        import tempfile
        files = {"pom.xml": F.pom("u", "3.2.4", "17", [F.dep("spring-boot-starter-web")]),
                 "src/main/java/u/PingController.java": "package u;\n@RestController\n@RequestMapping(\"/ping\")\nclass PingController {\n  @GetMapping(\"/a\") String a() { return \"a\"; }\n  @GetMapping(\"/b\") String b() { return \"b\"; }\n}\n",
                 "src/main/java/u/Other.java": "package u;\n@RestController\nclass OtherController {\n  @GetMapping(\"/other\") String o() { return \"o\"; }\n}\n",
                 "src/test/java/u/PingControllerTest.java": "package u;\nimport org.junit.jupiter.api.Test;\nclass PingControllerTest {\n  @Test void a() { assertEquals(\"a\", new PingController().a()); }\n}\n"}
        r = F.make_repo(tempfile.mkdtemp(), "u", files)
        d = discover.build(r)
        sn = safetynet.map_application(r, extract.extract(r, d), d)
        by = {c["label"]: c for c in sn["components"]}
        self.assertEqual(by["GET /ping/a"]["classification"], "mapped_with_assertions")
        self.assertIn("class level", by["GET /ping/a"]["explanation"])
        self.assertEqual(by["GET /other"]["classification"], "unverified")      # no test mentions OtherController
        self.assertNotIn("PingController", by["GET /ping/a"]["explanation"])     # class names are not shown

    def test_repository_level_questions_are_kept_separate(self):
        r = self.sn["orders-service"]["repository_level"]
        self.assertEqual(r["test_exists"]["state"], "yes")
        self.assertEqual(r["runs_automatically"]["state"], "yes")
        self.assertEqual(r["coverage_threshold_enforced"]["state"], "no")


if __name__ == "__main__":
    unittest.main()
