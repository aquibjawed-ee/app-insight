"""Safety-net mapping: for each discovered component, what static evidence is there that a test protects it?

Never claims a component is "untested": when no mapping can be established the classification is `unverified` (the scan could
not connect any test to it), which is different from "no test". Execution results are never known offline, so `passes` is
always `unknown`. Seven separate questions are answered per component and kept separate.
"""
from __future__ import annotations

import re
from typing import Dict, List

import evidence
from detectors import Ctx
from graph.adapters.common import ev, mask_comments
from graph.model import norm_path

CONTRACT = "safetynet.v1"
VERSION = "0.2.0"
ASSERT = re.compile(r"\bassert\w*\(|andExpect\(|\bverify\(|\.should\w*|statusCode\(|\.body\(|isEqualTo|expectStatus|expectBody|\bexpect\(|assertThat|shouldBe|\bthen\(|\.isOk\b|\.hasSize|\.contains\w*\(")
ROUTE = [  # (regex capturing verb and path, file must also match)
    (re.compile(r"\b(get|post|put|delete|patch)\(\s*\"([^\"]+)\""), re.compile(r"MockMvc|mockMvc|perform\(|MockMvcRequestBuilders")),
    (re.compile(r"\.(get|post|put|delete|patch)\(\)\s*\.uri\(\s*\"([^\"]+)\""), re.compile(r"WebTestClient|webTestClient|webClient")),
    (re.compile(r"\.(get|post|put|delete|patch)\(\s*\"(/[^\"]*)\""), re.compile(r"RestAssured|given\(\)|restAssured")),
    (re.compile(r"\b(get|post|put|delete|patch)For(?:Entity|Object)\(\s*\"([^\"]+)\"|\b(put|delete)\(\s*\"(/[^\"]*)\""), re.compile(r"TestRestTemplate|testRestTemplate|restTemplate")),
]
STUB = [  # downstream HTTP stubs: WireMock, MockRestServiceServer, Pact, MockWebServer
    (re.compile(r"\b(get|post|put|delete|patch)\(\s*(?:urlEqualTo|urlPathEqualTo|urlMatching|urlPathMatching|anyUrl)?\(?\s*\"([^\"]+)\""), re.compile(r"WireMock|wiremock|stubFor")),
    (re.compile(r"requestTo\(\s*\"[^\"]*?(/[^\"]*)\""), re.compile(r"MockRestServiceServer|requestTo")),
    (re.compile(r"\.path\(\s*\"([^\"]+)\"\s*\)"), re.compile(r"\bPact\b|PactDslWithProvider|@Pact\b|au\.com\.dius")),
]
STATE = ("yes", "no", "unknown", "not_applicable")


def _load_tests(ctx) -> List[dict]:
    files = sorted({f for f in ctx.files if f.endswith((".java", ".kt", ".groovy")) and (f in set(ctx.src_test) or ctx.SRC_TEST.search("/" + f))
                    and not ctx._aux(f.replace("/src/test/", "/src/main/"))})
    out = []
    for f in files:
        lines = evidence.read_lines(ctx.repo, f) or []
        out.append({"path": f, "lines": lines, "masked": mask_comments(lines), "text": "\n".join(mask_comments(lines))})
    return out


def _window_has_assertion(masked, i, span=14):
    """An assertion within the test method body that contains line i (approximated by the next `span` lines up to the next @Test)."""
    end = i + 1
    while end < min(len(masked), i + span) and not re.search(r"@Test\b|@ParameterizedTest\b|\bfun\s+`?\w+`?\s*\(\s*\)\s*\{?\s*$", masked[end]):
        end += 1
    return any(ASSERT.search(x) for x in masked[max(0, i - 2):end])


def _file_assert(tf) -> bool:
    """A reference through a field (repository, listener) is not followed into the test methods; an assertion anywhere in the class is used instead."""
    return any(ASSERT.search(x) for x in tf["masked"])


def _score(tp: str, shape: str, ctx_path: str = ""):
    """None when the concrete/templated test path cannot be the endpoint; else the number of literal segments that matched exactly
    (a concrete `/orders/42` fits `/orders/{}`, but `/orders/export` fits the literal endpoint better)."""
    tp = re.sub(r"%[sd]|\+\s*\w+|\$\w+|\$\{[^}]*\}", "{}", tp).split("?")[0]
    a = [x for x in norm_path(tp).split("/") if x]
    for cand in (shape, norm_path(ctx_path + "/" + shape.lstrip("/"))) if ctx_path else (shape,):
        b = [x for x in cand.split("/") if x]
        if len(a) == len(b) and all(x == y or x == "{}" or y == "{}" for x, y in zip(a, b)):
            return sum(1 for x, y in zip(a, b) if x == y and x != "{}")
    return None


def _best(tp: str, verb: str, endpoints: List[dict], ctx_path: str):
    """Endpoints of this verb that the test path fits best; one winner or none (a tie is not guessed)."""
    scored = [(sc, n) for n in endpoints if n["attrs"]["method"] == verb for sc in [_score(tp, n["attrs"]["path_shape"], ctx_path)] if sc is not None]
    if not scored:
        return []
    top = max(sc for sc, _ in scored)
    return [n for sc, n in scored if sc == top]


def map_application(repo: str, graph: dict, disc: dict) -> dict:
    ctx = Ctx(repo)
    app = graph["meta"]["application"]
    tests = _load_tests(ctx)
    nodes = {n["id"]: n for n in graph["nodes"]}
    t = disc.get("tests", {})

    def fv(key):
        f = t.get(key, {})
        return f.get("status"), f.get("value")
    st_unit, v_unit = fv("unit_tests")
    st_int, v_int = fv("integration_tests")
    st_ctr, _ = fv("contract_tests")
    exists = "yes" if (st_unit == "CONFIRMED" or st_int == "CONFIRMED" or st_ctr == "CONFIRMED") else ("unknown" if "UNKNOWN" in (st_unit, st_int) else "no")
    st_ci, v_ci = fv("ci_test_execution")
    runs = {"enabled": "yes", "disabled": "no", "partial": "unknown"}.get(v_ci if isinstance(v_ci, str) else "", "unknown") if st_ci != "UNKNOWN" else "unknown"
    cov_m = "yes" if t.get("coverage_measured", {}).get("status") == "CONFIRMED" else ("no" if t.get("coverage_measured", {}).get("status") == "NOT_FOUND" else "unknown")
    cov_e = "yes" if t.get("coverage_enforced", {}).get("status") == "CONFIRMED" or t.get("coverage_gate_in_ci", {}).get("value") in ("gate_in_ci", "gate_run_in_ci") else \
        ("unknown" if t.get("coverage_enforced", {}).get("status") == "UNKNOWN" else "no")
    repo_level = {"test_exists": {"state": exists, "evidence": (t.get("unit_tests", {}).get("evidence", []) + t.get("integration_tests", {}).get("evidence", []))[:2]},
                  "runs_automatically": {"state": runs, "note": "from the pipeline definition; no run was observed", "evidence": t.get("ci_test_execution", {}).get("evidence", [])[:1]},
                  "passes": {"state": "unknown", "note": "nothing was executed; pass/fail is not known offline"},
                  "coverage_measured": {"state": cov_m, "note": "repository-wide: a report on disk, not per component"},
                  "coverage_threshold_enforced": {"state": cov_e, "note": "repository-wide"}}
    comps = []

    def comp(cid, kind, label, edge_ids, mapped_refs, how):
        mapped = bool(mapped_refs)
        assertion = any(r["assertion"] for r in mapped_refs)
        strength = ("route" if any(r["how"].startswith("route ") for r in mapped_refs) else "class" if kind == "api_endpoint" and mapped_refs else "reference" if mapped_refs else None)
        comps.append({"component_id": cid, "kind": kind, "label": label, "edges": edge_ids, "strength": strength,
                      "dimensions": {"test_exists": repo_level["test_exists"]["state"],
                                     "mapped_to_component": "yes" if mapped else "unknown",
                                     "runs_automatically": runs if mapped else "unknown",
                                     "passes": "unknown",
                                     "coverage_measured": "unknown",
                                     "coverage_threshold_enforced": "unknown",
                                     "behaviour_verified": ("unknown" if not mapped else "unknown")},
                      "mapping": [{"how": r["how"], "evidence": r["evidence"], "assertion_in_test": r["assertion"]} for r in mapped_refs][:4],
                      "classification": ("mapped_with_assertions" if mapped and assertion else "mapped_no_assertion_seen" if mapped else "unverified"),
                      "explanation": ("a test references this %s (%s)%s" % (kind.replace("_", " "), how, "" if assertion else "; no assertion was seen near the reference")) if mapped else
                                     "no test could be connected to this %s by static analysis; this does not show that none exists" % kind.replace("_", " ")})

    app_node = "app:" + app
    ctx_path = nodes.get(app_node, {}).get("attrs", {}).get("context_path") or ""
    # API endpoints
    endpoints = sorted((x for x in graph["nodes"] if x["type"] == "ApiEndpoint" and x.get("app") == app), key=lambda x: x["id"])
    route_refs: Dict[str, List[dict]] = {n["id"]: [] for n in endpoints}
    for tf in tests:
        for rx, gate in ROUTE:
            if not gate.search(tf["text"]):
                continue
            for i, ln in enumerate(tf["masked"]):
                for m in rx.finditer(ln):
                    g = [x for x in m.groups() if x]
                    if len(g) < 2:
                        continue
                    win = _best(g[1], g[0].upper(), endpoints, ctx_path)
                    if len(win) == 1:  # ties between equally specific endpoints are not guessed
                        route_refs[win[0]["id"]].append({"how": "route %s %s requested in a test" % (g[0].upper(), g[1]), "evidence": ev(tf["path"], i + 1, tf["lines"], app),
                                                         "assertion": _window_has_assertion(tf["masked"], i)})
    for n in endpoints:
        refs = route_refs[n["id"]]
        ctl = n["attrs"].get("controller")
        if ctl and not refs:
            for tf in tests:
                if re.search(r"@WebMvcTest\s*\(\s*(?:\w+\s*=\s*)?\[?\s*%s(?:\.class|::class)" % re.escape(ctl), tf["text"]):
                    i = next(i for i, l in enumerate(tf["masked"]) if "@WebMvcTest" in l)
                    refs.append({"how": "a controller test covers this class of endpoints (class level, route not matched)", "evidence": ev(tf["path"], i + 1, tf["lines"], app), "assertion": False})
                    break
            if not refs:  # a plain unit test that constructs or calls the controller class: mapped at class level, route not matched
                for tf in tests:
                    i = next((i for i, l in enumerate(tf["masked"]) if re.search(r"\b%s\b" % re.escape(ctl), l) and not l.lstrip().startswith("import ")), None)
                    if i is not None:
                        refs.append({"how": "a unit test references this controller class (class level, route not matched)", "evidence": ev(tf["path"], i + 1, tf["lines"], app), "assertion": _file_assert(tf)})
                        break
        comp(n["id"], "api_endpoint", n["name"], [e["id"] for e in graph["edges"] if e["target"] == n["id"] and e["type"] == "EXPOSES_API"], refs[:4],
             "route match" if any(r["how"].startswith("route ") for r in refs) else "class level")
    # messaging, persistence, downstream HTTP
    for e in sorted(graph["edges"], key=lambda x: x["id"]):
        if e["source"] != app_node:
            continue
        refs, kind = [], None
        if e["type"] in ("CONSUMES_FROM", "PUBLISHES_TO") and e["resolution"]["state"] == "resolved":
            tn = nodes[e["target"]]
            kind = "message_consumer" if e["type"] == "CONSUMES_FROM" else "message_publisher"
            tname, cls = tn["name"], e["attrs"].get("listener_class")
            for tf in tests:
                for i, ln in enumerate(tf["masked"]):
                    hit = None
                    if cls and re.search(r"\b%s\b" % re.escape(cls), ln):
                        hit = "the listener is referenced in a test"
                    elif re.search(r"[\"']%s[\"']" % re.escape(tname), ln) and re.search(r"EmbeddedKafka|Testcontainers|KafkaContainer|RabbitMQContainer|send|poll|verify|consume|listen", tf["text"]):
                        hit = "topic %s named in a messaging test" % tname
                    if hit:
                        refs.append({"how": hit, "evidence": ev(tf["path"], i + 1, tf["lines"], app),
                                     "assertion": _window_has_assertion(tf["masked"], i) or (hit.startswith("listener") and _file_assert(tf))})
            comp(e["id"], kind, "%s %s" % ("consumes" if kind == "message_consumer" else "publishes to", tname), [e["id"]], refs[:4], "topic/listener reference")
        elif e["type"] in ("READS_FROM", "WRITES_TO"):
            repo_name = e["attrs"].get("repository")
            kind = "database_path"
            for tf in tests:
                for i, ln in enumerate(tf["masked"]):
                    if repo_name and re.search(r"\b%s\b" % re.escape(repo_name), ln) and re.search(r"@DataJpaTest|@JdbcTest|@DataMongoTest|@SpringBootTest|@Testcontainers", tf["text"]):
                        refs.append({"how": "a Spring Data repository is used in a data/integration test", "evidence": ev(tf["path"], i + 1, tf["lines"], app),
                                     "assertion": _window_has_assertion(tf["masked"], i) or _file_assert(tf)})
                    elif not repo_name and re.search(r"JdbcTemplate|@JdbcTest", ln):
                        refs.append({"how": "JdbcTemplate/JdbcTest used in a test", "evidence": ev(tf["path"], i + 1, tf["lines"], app), "assertion": _window_has_assertion(tf["masked"], i)})
            comp(e["id"], kind, "%s %s" % ("reads" if e["type"] == "READS_FROM" else "writes", "via repository" if repo_name else "via JDBC"), [e["id"]], refs[:4], "repository reference")
        elif e["type"] == "CALLS_API" and e["resolution"]["state"] != "unresolved" or e["type"] == "CALLS_API":
            path = e["attrs"].get("path")
            kind = "downstream_http"
            tname = nodes.get(e["attrs"].get("original_target") or e["target"], nodes.get(e["target"], {})).get("name", e["target"])
            for tf in tests:
                for rx, gate in STUB:
                    if not gate.search(tf["text"]) or not path:
                        continue
                    for i, ln in enumerate(tf["masked"]):
                        for m in rx.finditer(ln):
                            g = [x for x in m.groups() if x]
                            if g and _score(g[-1], norm_path(path)) is not None:
                                refs.append({"how": "downstream %s stubbed in a test (WireMock/MockRestServiceServer/Pact)" % path, "evidence": ev(tf["path"], i + 1, tf["lines"], app),
                                             "assertion": _window_has_assertion(tf["masked"], i)})
            comp(e["id"], kind, "calls %s %s %s" % (tname, e["attrs"].get("method") or "", path or ""), [e["id"]], refs[:4], "stubbed downstream")
    summary: Dict[str, Dict[str, int]] = {}
    for c in comps:
        s = summary.setdefault(c["kind"], {"mapped_with_assertions": 0, "mapped_no_assertion_seen": 0, "unverified": 0, "direct": 0, "class_level": 0})
        s[c["classification"]] += 1
        if c["strength"] == "class":
            s["class_level"] += 1      # a test mentions the controller class; no route was matched
        elif c["strength"]:
            s["direct"] += 1           # a route, listener, repository or stub path was matched
    return {"contract": CONTRACT, "application": app, "version": VERSION, "repository_level": repo_level, "components": comps, "summary": summary,
            "limitations": ["Mapping is by static reference (route literal, class name, topic name, stub path); a test that exercises a component indirectly is not seen.",
                            "`unverified` means no mapping was established. It never means untested.",
                            "No test was run: `passes` is always unknown and coverage is not available per component.",
                            "An assertion near a reference suggests, but does not prove, that behaviour is verified."]}
