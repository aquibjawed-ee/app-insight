"""Phase 4: change-impact. Confirmed = cited rule + literal match; downstream = potential; unknowns kept explicit."""
import copy
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
from graph import contracts, extract, impact, resolve, safetynet  # noqa: E402


class ImpactBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.repos = F.make_portfolio()
        cls.discs = {n: discover.build(r) for n, r in cls.repos.items()}
        docs = [extract.extract(r, cls.discs[n]) for n, r in cls.repos.items()]
        cls.G = resolve.resolve(docs)
        cls.sn = {n: safetynet.map_application(r, d, cls.discs[n]) for (n, r), d in zip(cls.repos.items(), docs)}
        cls.views = {n: impact.AppView(n, r, cls.discs[n]) for n, r in cls.repos.items()}

    def run_s(self, **sc):
        return impact.assess(sc, self.G, self.views, self.sn)

    def ids(self, items):
        return {(i["rule_id"], i["app"]) for i in items}


class JavaRuntimeTest(ImpactBase):
    def test_jaxb_import_without_jaxb_dependency_is_a_confirmed_incompatibility_with_evidence(self):
        r = self.run_s(type="java_runtime", to=17, apps=["billing-service"])
        self.assertIn(("java.jaxb-removed", "billing-service"), self.ids(r["confirmed_incompatibilities"]))
        f = [x for x in r["confirmed_incompatibilities"] if x["rule_id"] == "java.jaxb-removed"][0]
        self.assertEqual(f["evidence"][0]["snippet"], "import javax.xml.bind.JAXBContext;")
        self.assertEqual(f["reference"], "JEP 320 (Remove the Java EE and CORBA Modules)")

    def test_replacement_library_suppresses_the_finding(self):
        v = self.views["billing-service"]
        v._coords = set(v.coords()) | {"jakarta.xml.bind:jakarta.xml.bind-api"}
        try:
            r = self.run_s(type="java_runtime", to=17, apps=["billing-service"])
            self.assertNotIn("java.jaxb-removed", {x["rule_id"] for x in r["confirmed_incompatibilities"]})
        finally:
            v._coords = None

    def test_already_on_java_11_nothing_from_the_11_rules_applies(self):
        r = self.run_s(type="java_runtime", to=17, apps=["orders-service"])
        self.assertEqual([x for x in r["confirmed_incompatibilities"]], [])

    def test_downstream_of_a_changed_application_is_potential_and_has_a_path(self):
        r = self.run_s(type="java_runtime", to=17, apps=["inventory-service"])
        d = {x["component"]: x for x in r["downstream_impact"]}
        self.assertIn("app:orders-service", d)
        self.assertIn("potential impact", d["app:orders-service"]["note"])
        self.assertTrue(d["app:orders-service"]["via"])

    def test_same_topic_name_on_another_cluster_is_not_in_the_blast_radius(self):
        r = self.run_s(type="java_runtime", to=17, apps=["orders-service"])
        comps = {x["component"] for x in r["downstream_impact"]}
        self.assertIn("app:billing-service", comps)      # consumes orders.created on the same cluster
        self.assertIn("app:inventory-service", comps)
        self.assertNotIn("app:reporting", comps)         # same topic name, different cluster

    def test_unresolved_and_ambiguous_relationships_become_unknowns_not_impact(self):
        r = self.run_s(type="java_runtime", to=17, apps=["orders-service"])
        whys = " ".join(u["why"] for u in r["unknowns"])
        self.assertIn("ambiguous", whys)
        self.assertIn("unresolved", whys)
        comps = {x["component"] for x in r["downstream_impact"]}
        self.assertFalse({"app:notifier-a", "app:notifier-b"} & comps)

    def test_verification_lists_unverified_components_without_calling_them_untested(self):
        r = self.run_s(type="java_runtime", to=17, apps=["orders-service"])
        text = json.dumps(r["required_verification"])
        self.assertIn("unverified", text)
        self.assertNotIn("untested", text)

    def test_low_maturity_does_not_produce_a_migration_recommendation(self):
        r = self.run_s(type="java_runtime", to=17, apps=["orders-service"])
        self.assertNotIn("recommend", json.dumps(r).lower().replace("remediation", ""))


class SpringBootTest(ImpactBase):
    def test_boot2_to_3_confirmed_findings(self):
        r = self.run_s(type="spring_boot", to="3.2", apps=["orders-service"])
        ids = {x["rule_id"] for x in r["confirmed_incompatibilities"]}
        self.assertIn("boot3.requires-java17", ids)       # java 11 baseline
        self.assertIn("boot3.javax-to-jakarta", ids)      # javax.persistence imports
        pot = {x["rule_id"] for x in r["potential_risks"]}
        self.assertTrue({"boot3.trailing-slash", "boot3.hibernate6", "boot3.cloud-compat"} <= pot)

    def test_renamed_property_is_found_in_configuration(self):
        r = self.run_s(type="spring_boot", to="3.2", apps=["reporting"])
        f = [x for x in r["confirmed_incompatibilities"] if x["rule_id"] == "boot3.property-spring-redis"]
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["evidence"][0]["snippet"], "host: cache2.internal")  # YAML leaf under spring.redis

    def test_application_already_on_boot3_is_not_flagged(self):
        r = self.run_s(type="spring_boot", to="3.2", apps=["inventory-service"])
        self.assertEqual(r["confirmed_incompatibilities"], [])

    def test_unknown_boot_version_is_an_unknown_not_a_guess(self):
        v = self.views["orders-service"]
        saved = v.disc["stack"]["spring_boot_version"]
        v.disc["stack"]["spring_boot_version"] = {"value": None, "status": "NOT_FOUND", "evidence": []}
        try:
            r = self.run_s(type="spring_boot", to="3.2", apps=["orders-service"])
            self.assertTrue([u for u in r["unknowns"] if "Spring Boot version" in u["what"]])
            self.assertEqual(r["confirmed_incompatibilities"], [])
        finally:
            v.disc["stack"]["spring_boot_version"] = saved


class OtherScenariosTest(ImpactBase):
    def test_api_contract_change_reports_resolved_callers_and_possible_unresolved_ones(self):
        r = self.run_s(type="api_contract", endpoint="POST /api/stock/reserve", app="inventory-service")
        comps = {a["component"] for a in r["affected_components"]}
        self.assertIn("app:orders-service", comps)
        self.assertTrue([v for v in r["required_verification"] if "caller orders-service" in v["what"]])

    def test_removed_endpoint_in_openapi_diff_is_a_confirmed_breaking_change(self):
        old = {"paths": {"/api/stock/reserve": {"post": {"responses": {"200": {}}}}, "/api/stock/{sku}": {"get": {"responses": {"200": {}, "404": {}}}}}}
        new = {"paths": {"/api/stock/{sku}": {"get": {"responses": {"200": {}}}}}}
        changes = {(c["endpoint"], c["change"]) for c in contracts.diff_openapi(old, new)}
        self.assertEqual(changes, {("POST /api/stock/reserve", "removed"), ("GET /api/stock/{}", "response_removed")})

    def test_added_optional_things_are_not_breaking(self):
        old = {"paths": {"/a": {"get": {"parameters": [], "responses": {"200": {}}}}}}
        new = {"paths": {"/a": {"get": {"parameters": [{"in": "query", "name": "q", "required": False}], "responses": {"200": {}}}}, "/b": {"get": {"responses": {"200": {}}}}}}
        self.assertEqual([c for c in contracts.diff_openapi(old, new) if c["breaking"]], [])
        new["paths"]["/a"]["get"]["parameters"][0]["required"] = True
        self.assertEqual([c["change"] for c in contracts.diff_openapi(old, new) if c["breaking"]], ["required_param_added"])

    def test_messaging_change_lists_publishers_consumers_and_the_cluster_ambiguity(self):
        r = self.run_s(type="messaging_schema", topic="orders.created")
        aff = {a["component"]: a for a in r["affected_components"]}
        t = aff["topic:kafka:orders.created@kafka-1.internal:9092"]
        self.assertEqual(t["publishers"], ["app:orders-service"])
        self.assertEqual(t["consumers"], ["app:billing-service", "app:inventory-service"])
        self.assertTrue([u for u in r["unknowns"] if u["what"] == "which orders.created"])
        self.assertTrue([u for u in r["unknowns"] if u["what"] == "schema compatibility"])
        self.assertTrue([u for u in r["unknowns"] if "unresolved publishes to" in u["what"]])  # computed topic could be this one

    def test_avro_compat(self):
        old = {"type": "record", "name": "O", "fields": [{"name": "id", "type": "string"}, {"name": "note", "type": "string", "default": ""}]}
        new = {"type": "record", "name": "O", "fields": [{"name": "id", "type": "long"}, {"name": "qty", "type": "int"}]}
        got = {(d["change"], d["field"], d["breaking"]) for d in contracts.diff_avro(old, new)}
        self.assertEqual(got, {("field_removed", "note", False), ("field_added", "qty", True), ("type_changed", "id", True)})

    def test_database_migration_finds_shared_database_and_source_dialect_signals(self):
        r = self.run_s(type="db_migration", from_tech="PostgreSQL", to_tech="Oracle")
        aff = {a["component"] for a in r["affected_components"]}
        self.assertIn("db:PostgreSQL:orders-db.internal:5432:orders", aff)
        self.assertTrue([p for p in r["potential_risks"] if p["rule_id"] == "db.shared-database"])

    def test_infrastructure_change_finds_deployed_applications_and_removed_kubernetes_apis(self):
        r = self.run_s(type="infrastructure", platform="Kubernetes", to="1.25")
        self.assertTrue({"app:orders-service", "app:inventory-service"} <= {a["component"] for a in r["affected_components"]})
        self.assertEqual(r["confirmed_incompatibilities"], [])  # fixture manifests use apps/v1
        self.assertTrue([u for u in r["unknowns"] if "outside the analysed repositories" in u["what"]])

    def test_removed_kubernetes_api_is_confirmed_when_present(self):
        import tempfile
        files = dict(F.INVENTORY)
        files["deploy/k8s/ingress.yaml"] = "apiVersion: extensions/v1beta1\nkind: Ingress\nmetadata:\n  name: inventory-service\n"
        root = tempfile.mkdtemp()
        repo = F.make_repo(root, "inventory-service", files)
        d = discover.build(repo)
        g = extract.extract(repo, d)
        r = impact.assess({"type": "infrastructure", "platform": "Kubernetes", "to": "1.25"}, resolve.resolve([g]), {"inventory-service": impact.AppView("inventory-service", repo, d)}, {})
        self.assertEqual([x["rule_id"] for x in r["confirmed_incompatibilities"]], ["k8s.extensions-ingress"])

    def test_dependency_major_relocation_is_confirmed_only_when_declared(self):
        r = self.run_s(type="dependency_major", coordinate="org.postgresql:postgresql", to="43")
        self.assertTrue(r["affected_components"])
        self.assertEqual(r["confirmed_incompatibilities"], [])
        r = self.run_s(type="dependency_major", coordinate="com.acme:nothing", to="2")
        self.assertEqual(r["affected_components"], [])
        self.assertTrue(r["unknowns"])

    def test_unknown_scenario_is_rejected(self):
        with self.assertRaises(ValueError):
            impact.assess({"type": "rewrite-everything"}, self.G, self.views)

    def test_impact_is_deterministic(self):
        a = self.run_s(type="java_runtime", to=17)
        b = self.run_s(type="java_runtime", to=17)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
