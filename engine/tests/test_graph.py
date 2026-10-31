"""Phase 1: relationship extraction, identity resolution, negative / ambiguous / missing-evidence cases, determinism, read-only."""
import copy
import hashlib
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(1, HERE)
os.environ["DISCOVERY_FIXED_TIME"] = "2026-01-01T00:00:00Z"

import graph_fixtures as F  # noqa: E402
import validate  # noqa: E402
from graph import extract, model, resolve  # noqa: E402

SCHEMA = json.load(open(os.path.join(HERE, "..", "schemas", "relationships.v1.schema.json")))


def tree_hash(root):
    h = hashlib.sha256()
    for r, dirs, names in os.walk(root):
        dirs.sort()
        for n in sorted(names):
            p = os.path.join(r, n)
            if ".git" in p.split(os.sep):
                continue
            h.update(p.encode() + open(p, "rb").read())
    return h.hexdigest()


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.repos = F.make_portfolio()
        cls.before = {n: tree_hash(r) for n, r in cls.repos.items()}
        cls.docs = {n: extract.extract(r) for n, r in cls.repos.items()}
        cls.P = resolve.resolve(list(cls.docs.values()))

    def edges(self, doc, **kw):
        return [e for e in doc["edges"] if all((e.get(k) if k != "attr" else None) == v for k, v in kw.items() if k != "attr")]

    def find(self, doc, etype, src=None, tgt=None, **attrs):
        out = []
        for e in doc["edges"]:
            if e["type"] != etype or (src and e["source"] != src) or (tgt and not e["target"].startswith(tgt)):
                continue
            if all(e["attrs"].get(k) == v for k, v in attrs.items()):
                out.append(e)
        return out


class ExtractionTest(Base):
    def test_schema_and_integrity_hold_for_every_application_and_the_portfolio(self):
        for n, d in list(self.docs.items()) + [("portfolio", self.P)]:
            errs = []
            validate._mini(SCHEMA, d, SCHEMA, "$", errs)
            self.assertEqual(errs, [], n)
            self.assertEqual(model.validate_integrity(d, self.repos), [], n)

    def test_rest_endpoints_are_exposed_with_class_prefix_and_path_shape(self):
        d = self.docs["orders-service"]
        names = {n["name"] for n in d["nodes"] if n["type"] == "ApiEndpoint"}
        self.assertEqual(names, {"GET /api/orders/{id}", "POST /api/orders", "DELETE /api/orders/{id}"})
        self.assertEqual(len(self.find(d, "EXPOSES_API", "app:orders-service")), 3)

    def test_kotlin_controller_is_read(self):
        names = {n["name"] for n in self.docs["inventory-service"]["nodes"] if n["type"] == "ApiEndpoint"}
        self.assertEqual(names, {"GET /api/stock/{sku}", "POST /api/stock/reserve"})

    def test_commented_out_and_non_literal_endpoints_are_not_relationships(self):
        d = self.docs["orders-service"]
        self.assertFalse([n for n in d["nodes"] if "secret" in n["name"] or "export" in n["name"].lower()])
        self.assertTrue([u for u in d["not_relationships"] if "EXPORT" in u["why"]])

    def test_feign_client_calls_carry_method_and_path(self):
        d = self.docs["orders-service"]
        calls = {(e["attrs"]["method"], e["attrs"]["path"], e["target"]) for e in d["edges"] if e["type"] == "CALLS_API" and e["target"] == "svc:inventory-service"}
        self.assertEqual(calls, {("GET", "/api/stock/{sku}", "svc:inventory-service"), ("POST", "/api/stock/reserve", "svc:inventory-service"),
                                 ("GET", "/api/stock/legacy", "svc:inventory-service")})

    def test_declared_but_unreferenced_client_is_low_confidence(self):
        d = self.docs["orders-service"]
        ghost = self.find(d, "CALLS_API", tgt="svc:ghost")[0]
        self.assertEqual(ghost["confidence"], "low")
        self.assertFalse(ghost["attrs"]["referenced_elsewhere"])
        self.assertEqual(self.find(d, "CALLS_API", tgt="svc:loyalty-service")[0]["confidence"], "high")

    def test_property_placeholder_url_is_resolved_from_configuration_with_both_citations(self):
        e = self.find(self.docs["orders-service"], "CALLS_API", tgt="ext:api.acme-pay.io")[0]
        self.assertEqual(e["attrs"]["path"], "/v2/charges")

    def test_urls_in_logs_comments_tests_and_local_addresses_are_not_calls(self):
        d = self.docs["orders-service"]
        targets = {e["target"] for e in d["edges"]}
        self.assertNotIn("ext:wiki.internal", targets)
        self.assertNotIn("ext:localhost", targets)
        self.assertNotIn("ext:audit.internal", targets)  # log text that mentions a client is not a call
        self.assertTrue([u for u in d["not_relationships"] if "localhost" in u["why"]])

    def test_kafka_publishers_literal_constant_and_computed(self):
        d = self.docs["orders-service"]
        pub = {e["target"]: e for e in d["edges"] if e["type"] == "PUBLISHES_TO"}
        self.assertEqual(pub["topic:kafka:orders.created"]["attrs"]["how"], "literal")
        self.assertEqual(pub["topic:kafka:orders.audit"]["attrs"]["how"], "constant")
        unresolved = [e for t, e in pub.items() if t.startswith("unresolved:")]
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["resolution"]["state"], "unresolved")
        self.assertEqual(unresolved[0]["basis"], "unresolved")

    def test_send_on_a_non_messaging_variable_is_not_a_publication(self):
        pubs = {e["target"] for e in self.docs["orders-service"]["edges"] if e["type"] == "PUBLISHES_TO"}
        self.assertFalse([t for t in pubs if "welcome" in t])
        self.assertEqual(len(pubs), 3)  # orders.created, orders.audit and the computed one

    def test_javadoc_listener_is_not_a_consumer(self):
        self.assertFalse([e for e in self.docs["orders-service"]["edges"] if e["type"] == "CONSUMES_FROM"])
        self.assertNotIn("topic:kafka:ghost.topic", {n["id"] for d in self.docs.values() for n in d["nodes"]})

    def test_consumer_destination_from_property_placeholder_and_kotlin_array(self):
        self.assertTrue(self.find(self.docs["billing-service"], "CONSUMES_FROM", tgt="topic:kafka:orders.created"))
        self.assertTrue(self.find(self.docs["inventory-service"], "CONSUMES_FROM", tgt="topic:kafka:orders.created"))

    def test_dependency_declaration_alone_is_not_a_publisher_or_consumer(self):
        d = self.docs["billing-service"]  # kafka-clients declared, no template calls
        self.assertEqual([e for e in d["edges"] if e["type"] == "PUBLISHES_TO"], [])
        self.assertTrue([e for e in d["edges"] if e["type"] == "DEPENDS_ON" and e["target"].startswith("broker:")])

    def test_test_only_database_is_not_a_dependency(self):
        d = self.docs["orders-service"]
        self.assertFalse([n for n in d["nodes"] if "H2" in n["name"]])
        self.assertTrue([u for u in d["not_relationships"] if "H2" in u["what"] and "tests only" in u["why"]])

    def test_database_identity_comes_from_literal_connection_settings(self):
        d = self.docs["orders-service"]
        db = [n for n in d["nodes"] if n["type"] == "Database"][0]
        self.assertEqual(db["id"], "db:PostgreSQL:orders-db.internal:5432:orders")
        self.assertEqual(db["attrs"]["connection"]["database"], "orders")

    def test_repository_edges_are_inferred_and_point_at_the_one_database(self):
        d = self.docs["orders-service"]
        r, w = self.find(d, "READS_FROM", "app:orders-service")[0], self.find(d, "WRITES_TO", "app:orders-service")[0]
        for e in (r, w):
            self.assertEqual((e["basis"], e["resolution"]["state"]), ("inferred", "resolved"))
            self.assertTrue(e["target"].startswith("db:PostgreSQL"))

    def test_jdbc_template_on_a_kotlin_variable(self):
        d = self.docs["inventory-service"]
        self.assertTrue(self.find(d, "WRITES_TO", "app:inventory-service"))
        self.assertTrue(self.find(d, "READS_FROM", "app:inventory-service"))

    def test_kubernetes_workloads_give_deployment_and_identity(self):
        d = self.docs["orders-service"]
        infra = [n for n in d["nodes"] if n["type"] == "InfrastructureResource"][0]
        self.assertEqual(infra["attrs"]["platform"], "Kubernetes")
        self.assertIn("orders-service", {w["name"] for w in infra["attrs"]["workloads"]})
        kinds = {k["kind"] for k in d["nodes"][0]["attrs"].get("identity_keys", [])} | {k["kind"] for n in d["nodes"] if n["type"] == "Application" for k in n["attrs"]["identity_keys"]}
        self.assertIn("kubernetes Service name", kinds)
        self.assertTrue(self.find(d, "DEPLOYED_ON"))

    def test_every_edge_has_evidence_and_a_stable_id(self):
        again = extract.extract(self.repos["orders-service"])
        self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(self.docs["orders-service"], sort_keys=True))  # identical input -> identical output
        for d in self.docs.values():
            for e in d["edges"]:
                self.assertTrue(e["evidence"], e["id"])

    def test_scanned_repositories_are_not_modified(self):
        self.assertEqual({n: tree_hash(r) for n, r in self.repos.items()}, self.before)


class KotlinClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.repo = F.make_repo(tempfile.mkdtemp(), "kclient", F.KOTLIN_CLIENT)
        cls.doc = extract.extract(cls.repo)

    def calls(self):
        return {(e["target"], e["attrs"]["path"]) for e in self.doc["edges"] if e["type"] == "CALLS_API"}

    def test_escaped_kotlin_placeholder_resolves_from_configuration(self):
        self.assertIn(("ext:loyalty.partner.io", "/points/{id}"), self.calls())

    def test_host_taken_from_configuration_cites_the_configuration_line(self):
        e = next(e for e in self.doc["edges"] if e["type"] == "CALLS_API" and e["target"] == "ext:loyalty.partner.io")
        self.assertEqual([x["path"] for x in e["evidence"]], ["src/main/kotlin/k/Loyalty.kt", "src/main/resources/application.yml"])
        self.assertEqual(e["attrs"]["host_from_configuration"], "src/main/resources/application.yml")

    def test_a_clients_methods_are_not_attributed_to_the_previous_client(self):
        self.assertNotIn(("ext:loyalty.partner.io", "/x"), self.calls())
        other = [e for e in self.doc["edges"] if e["type"] == "CALLS_API" and e["attrs"].get("path") == "/x"]
        self.assertEqual(len(other), 1)
        self.assertEqual(other[0]["resolution"]["state"], "unresolved")
        self.assertIn("missing.api.url", other[0]["resolution"]["reason"])


class ResolutionTest(Base):
    def test_service_name_resolves_on_strong_identity_and_cites_it(self):
        e = [x for x in self.P["edges"] if x["type"] == "CALLS_API" and x["attrs"].get("original_target") == "svc:inventory-service"]
        self.assertEqual(len(e), 3)
        for x in e:
            self.assertEqual(x["resolution"]["state"], "resolved")
            self.assertEqual(x["resolution"]["strength"], "strong")
            self.assertTrue(x["resolution"]["matched_evidence"])
            self.assertIn("inventory-service", x["resolution"]["reasoning"])

    def test_call_is_attached_to_the_exposed_endpoint_when_it_exists(self):
        t = {x["attrs"]["path"]: x for x in self.P["edges"] if x["type"] == "CALLS_API" and x["attrs"].get("original_target") == "svc:inventory-service"}
        self.assertEqual(t["/api/stock/reserve"]["target"], "api:inventory-service:POST /api/stock/reserve")
        self.assertEqual(t["/api/stock/{sku}"]["target"], "api:inventory-service:GET /api/stock/{}")

    def test_missing_callee_endpoint_is_reported_not_hidden(self):
        x = [x for x in self.P["edges"] if x["type"] == "CALLS_API" and x["attrs"].get("path") == "/api/stock/legacy"][0]
        self.assertEqual(x["target"], "app:inventory-service")
        self.assertEqual(x["attrs"]["endpoint_match"], "not_found")
        self.assertTrue([l for l in self.P["meta"]["resolution_log"] if l["kind"] == "endpoint"])

    def test_unknown_service_stays_unresolved(self):
        x = [x for x in self.P["edges"] if x["target"] == "svc:loyalty-service"][0]
        self.assertEqual(x["resolution"]["state"], "unresolved")
        self.assertIn("no analysed application", x["resolution"]["reasoning"])

    def test_two_applications_with_the_same_name_make_the_match_ambiguous(self):
        x = [x for x in self.P["edges"] if x["target"] == "svc:notifier"][0]
        self.assertEqual(x["resolution"]["state"], "ambiguous")
        self.assertEqual(x["resolution"]["candidates"], ["app:notifier-a", "app:notifier-b"])
        self.assertEqual(x["basis"], "unresolved")

    def test_repository_name_alone_does_not_resolve(self):
        x = [x for x in self.P["edges"] if x["target"] == "svc:reporting"][0]
        self.assertEqual(x["resolution"]["state"], "unresolved")
        self.assertEqual(x["resolution"]["weak_candidates"], ["app:reporting"])

    def test_topics_merge_on_family_name_and_cluster(self):
        t = "topic:kafka:orders.created@kafka-1.internal:9092"
        users = {(e["type"], e["source"]) for e in self.P["edges"] if e["target"] == t}
        self.assertEqual(users, {("PUBLISHES_TO", "app:orders-service"), ("CONSUMES_FROM", "app:billing-service"), ("CONSUMES_FROM", "app:inventory-service")})

    def test_same_topic_name_on_a_different_cluster_is_not_merged(self):
        other = "topic:kafka:orders.created@kafka-legacy.internal:9092"
        self.assertEqual({e["source"] for e in self.P["edges"] if e["target"] == other}, {"app:reporting"})
        self.assertTrue([l for l in self.P["meta"]["resolution_log"] if l["kind"] == "topic" and l["decision"] == "not merged"])

    def test_databases_with_identical_connection_settings_are_shared(self):
        db = "db:PostgreSQL:orders-db.internal:5432:orders"
        self.assertEqual({e["source"] for e in self.P["edges"] if e["target"] == db and e["type"] == "DEPENDS_ON"}, {"app:orders-service", "app:billing-service"})
        self.assertTrue([l for l in self.P["meta"]["resolution_log"] if l["kind"] == "database"])

    def test_resolution_is_deterministic_and_input_order_independent(self):
        a = resolve.resolve(list(self.docs.values()))
        b = resolve.resolve(list(reversed(list(self.docs.values()))))
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_resolution_does_not_mutate_its_inputs(self):
        snap = json.dumps(self.docs, sort_keys=True)
        resolve.resolve(list(self.docs.values()))
        self.assertEqual(json.dumps(self.docs, sort_keys=True), snap)


if __name__ == "__main__":
    unittest.main()
