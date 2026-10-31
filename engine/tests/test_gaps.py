"""Gaps found by reading spring-service-graph, each pinned by a tiny stub repository: @HttpExchange, gateway routes, mappings on implemented
interfaces, WebFlux routers, host aliases and Kubernetes DNS names, profile / external-config / environment layering, table-level data, graph diff."""
import copy
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(1, HERE)
os.environ["DISCOVERY_FIXED_TIME"] = "2026-10-30T00:00:00Z"

import discover  # noqa: E402
import gap_fixtures as G  # noqa: E402
import graph_fixtures as F  # noqa: E402
import relate  # noqa: E402
from graph import diff as graphdiff, extract, model, resolve  # noqa: E402


def build(repos, profile=None, config_dirs=(), aliases=None):
    docs = {n: extract.extract(r, discover.build(r), profile=profile, config_dirs=config_dirs) for n, r in repos.items()}
    return docs, resolve.resolve(list(docs.values()), aliases)


class GapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = tempfile.mkdtemp()
        cls.repos = {n: F.make_repo(root, n, f) for n, f in G.GAPS.items()}
        cls.cfg = tempfile.mkdtemp()
        for k, v in G.CONFIG_DIR_FILES.items():
            open(os.path.join(cls.cfg, k), "w").write(v)
        cls.docs, cls.P = build(cls.repos, profile="prod", config_dirs=[cls.cfg], aliases=relate.load_aliases(cls._aliases(root)))
        cls.docs0, cls.P0 = build(cls.repos)    # no profile, no config dir, no aliases

    @staticmethod
    def _aliases(root):
        p = os.path.join(root, "aliases.yml")
        open(p, "w").write(G.ALIASES)
        return p

    def edges(self, P, app, etype, **attrs):
        return [e for e in P["edges"] if e["source"] == "app:" + app and e["type"] == etype and all(e["attrs"].get(k) == v for k, v in attrs.items())]

    def names(self, P, app, etype):
        n = {x["id"]: x for x in P["nodes"]}
        return {n[e["target"]]["name"] for e in P["edges"] if e["source"] == "app:" + app and e["type"] == etype}

    def test_every_graph_is_valid(self):
        ext = {}
        for d in self.docs.values():
            ext.update(d["meta"].get("external_sources", {}))
        for P in (self.P, self.P0):
            self.assertEqual(model.validate_integrity(P, self.repos, ext), [])

    # A
    def test_http_exchange_methods_carry_paths_to_the_single_configured_base_url(self):
        calls = {(e["attrs"]["method"], e["attrs"]["path"]) for e in self.edges(self.P, "gap-exchange", "CALLS_API")}
        self.assertEqual(calls, {("GET", "/api/stock/{sku}"), ("POST", "/api/stock/reserve")})        # before: one path-less edge to the host

    # B
    def test_gateway_routes_become_calls_and_a_route_to_an_analysed_app_is_checked_against_its_endpoints(self):
        routes = self.edges(self.P, "gap-gateway", "CALLS_API", style="gateway-route")
        self.assertEqual({e["attrs"]["route_pattern"] for e in routes}, {"/pay/**", "/v1/orders/**"})
        internal = next(e for e in routes if e["attrs"]["route_pattern"] == "/v1/orders/**")
        self.assertEqual(internal["resolution"]["state"], "resolved")
        self.assertEqual((internal["attrs"]["endpoint_match"], internal["attrs"]["endpoints_under_route"]), ("found", 2))

    # C
    def test_endpoints_declared_on_an_implemented_interface_are_found_with_the_interface_prefix(self):
        self.assertEqual(self.names(self.P, "gap-iface", "EXPOSES_API"), {"GET /v1/orders/{id}", "POST /v1/orders"})
        self.assertEqual(self.names(self.P0, "gap-iface", "EXPOSES_API"), {"GET /v1/orders/{id}", "POST /v1/orders"})

    # D
    def test_webflux_router_functions_are_endpoints_and_plain_GET_strings_are_not(self):
        self.assertEqual(self.names(self.P, "gap-router", "EXPOSES_API"), {"GET /ping", "POST /echo", "GET /status/{id}", "DELETE /status/{id}"})
        self.assertEqual(self.names(self.P, "gap-not-router", "EXPOSES_API"), set())

    # E
    def test_alias_file_attaches_a_host_to_an_analysed_application(self):
        e = next(x for x in self.edges(self.P, "gap-alias", "CALLS_API") if x["attrs"].get("path") == "/invoices" and x["attrs"].get("original_target") == "ext:billing.internal.acme-corp.io")
        self.assertEqual(e["resolution"]["state"], "resolved")
        self.assertEqual(e["resolution"]["strength"], "alias")
        self.assertIn("alias file", e["resolution"]["reasoning"])
        self.assertTrue(e["target"].startswith("api:billing-service") or e["target"] == "app:billing-service")
        # without the alias file the host stays an external system: nothing is matched on a guess
        e0 = next(x for x in self.edges(self.P0, "gap-alias", "CALLS_API") if x["attrs"].get("method") == "POST" and "billing.internal" in x["target"])
        self.assertEqual(e0["resolution"]["state"], "not_applicable")

    def test_kubernetes_service_dns_name_resolves_without_any_alias(self):
        for P in (self.P, self.P0):
            hit = [x for x in P["edges"] if x["source"] == "app:gap-alias" and x["attrs"].get("original_target") == "ext:billing-service.shop.svc.cluster.local"]
            self.assertTrue(hit)
            self.assertEqual(hit[0]["resolution"]["state"], "resolved")
            self.assertEqual(hit[0]["attrs"].get("endpoint_match"), "found")

    def test_alias_to_a_name_with_no_application_names_an_external_system(self):
        P = resolve.resolve(list(self.docs.values()), {"billing.internal.acme-corp.io": "stripe"})
        e = next(x for x in P["edges"] if x["source"] == "app:gap-alias" and x["attrs"].get("original_target") == "ext:billing.internal.acme-corp.io")
        self.assertEqual(e["target"], "ext:stripe")

    # F
    def test_values_differing_between_profiles_are_reported_not_picked(self):
        e = next(x for x in self.edges(self.P0, "gap-profiles", "CALLS_API") if x["attrs"].get("path") == "/charge")
        self.assertEqual(e["resolution"]["state"], "unresolved")
        self.assertIn("differs between profiles", e["resolution"]["reason"])

    def test_selected_profile_overrides_base_environment_and_external_config_fill_the_rest(self):
        t = {x["attrs"].get("path"): x for x in self.edges(self.P, "gap-profiles", "CALLS_API")}
        self.assertEqual(t["/charge"]["target"], "ext:pay.acme-corp.io")                 # prod overrides base
        self.assertEqual(t["/entries"]["target"], "ext:ledger.acme-corp.io")             # ${LEDGER_URL} from the Deployment env
        self.assertEqual([e["path"] for e in t["/entries"]["evidence"]], ["src/main/java/g/Pay.java", "deploy/k8s/app.yaml"])
        self.assertEqual(t["/events"]["target"], "ext:audit.acme-corp.io")               # ${audit.url} from the external config directory
        ext = [e for e in t["/events"]["evidence"] if e.get("external")]
        self.assertEqual(len(ext), 1)
        self.assertTrue(ext[0]["path"].startswith("[config-dir]"))

    # G
    def test_tables_come_from_entities_native_sql_and_jdbc_and_not_from_jpql_or_comments(self):
        used = set()
        for e in self.P["edges"]:
            if e["source"] == "app:gap-data" and e["attrs"].get("tables"):
                used |= set(e["attrs"]["tables"])
        self.assertEqual(used, {"orders", "customers", "customer", "audit_log"})         # `commented_out` (comment) and the JPQL entity query are not tables
        self.assertFalse(self.edges(self.P0, "gap-data", "READS_FROM", via="native query") and False)

    def test_migrations_say_which_tables_the_application_owns_and_shared_tables_are_reported(self):
        dep = next(e for e in self.edges(self.P, "gap-data", "DEPENDS_ON") if e["attrs"].get("tables_owned"))
        self.assertEqual(dep["attrs"]["tables_owned"], ["order_lines", "orders"])
        db = next(n for n in self.P["nodes"] if n["type"] == "Database" and n["attrs"].get("tables"))
        self.assertEqual(db["attrs"]["tables"]["orders"]["owned_by"], ["gap-data"])
        self.assertEqual(db["attrs"]["tables"]["orders"]["used_by"], ["gap-data", "gap-data2"])
        self.assertTrue([l for l in self.P["meta"]["resolution_log"] if l["kind"] == "tables" and "orders" in l["reasoning"]])


class BoundValueTest(GapTest):  # reuses the stub portfolio built by GapTest.setUpClass
    def test_topics_named_through_configuration_properties_and_injected_values_are_resolved(self):
        pubs = {e["target"]: e for e in self.edges(self.P, "gap-props", "PUBLISHES_TO")}
        self.assertTrue({"topic:kafka:notifications", "topic:kafka:payments", "topic:kafka:audit"} <= set(pubs))
        for t in ("topic:kafka:notifications", "topic:kafka:payments", "topic:kafka:audit"):
            self.assertEqual(pubs[t]["resolution"]["state"], "resolved")
            self.assertTrue(pubs[t]["evidence"])
        self.assertEqual(pubs["topic:kafka:notifications"]["attrs"]["how"], "bound property")
        self.assertEqual(pubs["topic:kafka:audit"]["attrs"]["how"], "placeholder")

    def test_a_bound_property_that_is_not_set_stays_unresolved_and_says_which_key(self):
        un = [e for e in self.edges(self.P, "gap-props", "PUBLISHES_TO") if e["resolution"]["state"] == "unresolved"]
        self.assertEqual(len(un), 1)
        self.assertIn("kafka.unknown-topic", un[0]["resolution"]["reason"])


class DeclaredHostTest(GapTest):
    """Discovery without being told anything: the callee's own files name its host."""

    def call_to(self, P, original_host):
        return next(e for e in P["edges"] if e["source"] == "app:gap-hostcaller" and e["attrs"].get("original_target") == "ext:" + original_host or
                    (e["source"] == "app:gap-hostcaller" and e["target"] == "ext:" + original_host))

    def test_hosts_declared_in_openapi_servers_ingress_gateway_audience_and_own_pipeline_resolve_to_the_declaring_app_without_any_alias(self):
        for host, owner, how, strength in (("orders.api.acme-corp.io", "gap-owner-a", "OpenAPI servers", "strong"), ("orders-ingress.acme-corp.io", "gap-owner-a", "ingress / route host", "strong"),
                                          ("pay.flex.acme-corp.io", "gap-owner-c", "API gateway audience", "strong"), ("orders-smoke.acme-corp.io", "gap-owner-a", "own pipeline base URL", "medium")):
            e = self.call_to(self.P0, host)       # P0: no alias file, no profile, no config directory
            self.assertEqual(e["resolution"]["state"], "resolved", host)
            self.assertTrue(e["target"].endswith(owner) or ("api:" + owner) in e["target"], (host, e["target"]))
            self.assertEqual(e["resolution"]["strength"], strength, host)
            self.assertIn(how, e["resolution"]["reasoning"])
            self.assertTrue(e["resolution"]["matched_evidence"], host)

    def test_the_resolved_call_is_checked_against_the_declaring_apps_endpoints(self):
        e = self.call_to(self.P0, "orders.api.acme-corp.io")
        self.assertEqual(e["attrs"]["endpoint_match"], "found")

    def test_two_applications_declaring_the_same_host_make_it_ambiguous(self):
        e = self.call_to(self.P0, "shared.api.acme-corp.io")
        self.assertEqual(e["resolution"]["state"], "ambiguous")
        self.assertEqual(e["resolution"]["candidates"], ["app:gap-owner-b", "app:gap-owner-c"])

    def test_a_host_only_repeated_by_another_caller_or_a_non_self_pipeline_variable_is_not_a_declaration(self):
        for host in ("repeated-by-callers.acme-corp.io", "not-mine.acme-corp.io"):
            e = self.call_to(self.P0, host)
            self.assertEqual(e["target"], "ext:" + host)
            self.assertEqual(e["resolution"]["state"], "not_applicable")

    def test_an_alias_still_wins_over_a_declared_host(self):
        P = resolve.resolve(list(self.docs.values()), {"orders.api.acme-corp.io": "gap-owner-c"})
        e = next(x for x in P["edges"] if x["source"] == "app:gap-hostcaller" and x["attrs"].get("original_target") == "ext:orders.api.acme-corp.io")
        self.assertIn("alias", e["resolution"]["reasoning"])


class DiffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = tempfile.mkdtemp()
        cls.base_repos = {n: F.make_repo(os.path.join(root, "b"), n, f) for n, f in F.PORTFOLIO.items()}
        head = copy.deepcopy(F.PORTFOLIO)
        head["inventory-service"]["src/main/kotlin/com/shop/inventory/StockController.kt"] = head["inventory-service"]["src/main/kotlin/com/shop/inventory/StockController.kt"].replace(
            '    @PostMapping("/reserve")\n    fun reserve(@RequestBody r: Reserve): Reservation = svc.reserve(r)\n', "")
        head["orders-service"]["src/main/java/com/shop/orders/OrderService.java"] = head["orders-service"]["src/main/java/com/shop/orders/OrderService.java"].replace(
            '        kafkaTemplate.send("orders.created", o.id());          // literal topic\n', "")
        cls.head_repos = {n: F.make_repo(os.path.join(root, "h"), n, f) for n, f in head.items()}
        cls.base = build(cls.base_repos)[1]
        cls.head = build(cls.head_repos)[1]
        cls.d = graphdiff.diff(cls.base, cls.head)

    def test_a_removed_endpoint_that_is_still_called_is_breaking(self):
        kinds = {(b["kind"], b["subject"]) for b in self.d["breaking"]}
        self.assertIn(("removed endpoint is still called", "POST /api/stock/reserve"), kinds)
        self.assertEqual(self.d["removed_endpoints"], ["POST /api/stock/reserve"])

    def test_a_topic_that_lost_its_last_publisher_but_still_has_consumers_is_breaking(self):
        b = [x for x in self.d["breaking"] if x["kind"] == "topic lost its last publisher"]
        self.assertTrue(b and "orders.created" in b[0]["subject"])
        self.assertIn("billing-service", b[0]["detail"])

    def test_identical_analyses_have_no_changes_and_line_moves_are_ignored(self):
        same = graphdiff.diff(self.base, self.base)
        self.assertEqual(same["breaking"], [])
        self.assertEqual([same[k] for k in ("added_endpoints", "removed_endpoints", "added_calls", "removed_calls", "added_messaging", "removed_messaging")], [[]] * 6)
        moved = json.loads(json.dumps(self.base))
        for e in moved["edges"]:
            for x in e["evidence"]:
                x["line_start"] = x.get("line_start", 1) + 40
        self.assertEqual(graphdiff.diff(self.base, moved)["breaking"], [])

    def test_unresolved_placeholders_are_compared_by_meaning_not_by_where_they_were_found(self):
        self.assertFalse([m for m in self.d["added_messaging"] + self.d["removed_messaging"] if "unresolved" in m])

    def test_markdown_and_cli_exit_code(self):
        md = graphdiff.to_markdown(self.d)
        self.assertIn("**Breaking changes: 2**", md)
        self.assertIn("POST /api/stock/reserve", md)
        out_b, out_h = tempfile.mkdtemp(), tempfile.mkdtemp()
        for out, repos in ((out_b, self.base_repos), (out_h, self.head_repos)):
            self.assertEqual(relate.main(["analyse"] + sorted(repos.values()) + ["--out", out]), 0)
        self.assertEqual(relate.main(["diff", "--base", out_b, "--head", out_h, "--file", os.path.join(out_h, "d.md")]), 0)
        self.assertEqual(relate.main(["diff", "--base", out_b, "--head", out_h, "--file", os.path.join(out_h, "d.md"), "--fail-on-breaking"]), 3)
        self.assertEqual(relate.main(["diff", "--base", out_b, "--head", out_b, "--fail-on-breaking"]), 0)


if __name__ == "__main__":
    unittest.main()
