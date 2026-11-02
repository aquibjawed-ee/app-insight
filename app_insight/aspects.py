"""The trace: aspects -> controls -> evidence -> finding -> remedy, one document per application (aspects.v1).

Built only from what the engine already wrote for the analysis (discovery, relationships, resilience, safety net,
dimensions). Nothing is re-discovered and no model is involved. The catalogue (packs/aspects.v1.json) decides which
controls exist, where each reads its answer and when it applies; remedy packs say what to do about a gap, so an
organisation can swap the remedies without touching the catalogue.
"""
from __future__ import annotations

import json
import os
import re

PACKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "packs")
CONTRACT = "aspects.v1"
STATES = ("PRESENT", "PARTIAL", "ABSENT", "ISSUE", "UNKNOWN", "NOT_APPLICABLE", "NOT_ASSESSED")
GAP_STATES = ("ISSUE", "ABSENT", "PARTIAL")
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
# criteria whose MET result means the pipeline runs the control, not only that it is configured
ENFORCED = {"automated_build", "tests_run_in_ci", "version_tagging", "automated_deploy", "rollback", "coverage", "secret_scanning", "dependency_scanning", "sast"}
CRITERION_STATE = {"MET": "PRESENT", "PARTIAL": "PARTIAL", "NO_EVIDENCE": "ABSENT", "NOT_MET": "ISSUE", "UNKNOWN": "UNKNOWN"}
# criteria a pipeline decides: with the pipeline defined outside the repository they cannot be read, so they are unknown, not absent
PIPELINE_CRITERIA = {"automated_build", "tests_run_in_ci", "version_tagging", "automated_deploy", "rollback", "secret_scanning", "dependency_scanning", "sast"}
# criteria about tests themselves: a test file is their evidence. For every other criterion a test file proves nothing.
TEST_CRITERIA = {"unit_tests_exist", "integration_tests", "acceptance_tests", "performance_tests", "contract_tests"}
TEST_PATH = re.compile(r"(^|/)src/(?:test|it|integrationTest|intTest)/|(^|/)tests?/|Tests?\.(?:java|kt|groovy|scala)$")
CI_PATH = re.compile(r"(^|/)(Jenkinsfile[^/]*|\.gitlab-ci[^/]*\.ya?ml|\.github/workflows/[^/]+|azure-pipelines[^/]*\.ya?ml|bitbucket-pipelines\.ya?ml|\.circleci/[^/]+|buildspec[^/]*\.ya?ml|\.travis\.ya?ml)$")
# a platform default (Docker's 10 s stop, Kubernetes' rolling update) is there without being configured: partial, not unknown
HA_STATE = {"present": "PRESENT", "partial": "PARTIAL", "absent": "ABSENT", "unknown": "UNKNOWN", "default": "PARTIAL", "not_applicable": "NOT_APPLICABLE", "not_assessed": "NOT_ASSESSED"}


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_catalogue(path=None):
    return _read(path or os.path.join(PACKS, "aspects.v1.json"))


def load_remedy_packs(names):
    """names: pack ids under packs/remedies or paths to an organisation's own pack file, highest priority first."""
    out = []
    for n in names:
        p = n if os.path.isfile(n) else os.path.join(PACKS, "remedies", n + ".v1.json")
        if not os.path.isfile(p):
            raise FileNotFoundError("remedy pack not found: %s" % n)
        out.append(_read(p))
    return out


def _fact(disc, path):
    sec, key = path.split(".", 1)
    return (disc.get(sec) or {}).get(key) or {}


def _ev(evs, status=None, note=None):
    return [dict(e, status=status) if status else dict(e) for e in (evs or [])][:12]


class Context:
    """What one application is and touches: decides applicability, and gives the graph-based controls their input."""

    def __init__(self, app, disc, rel, res, sn, dims, portfolio):
        self.app, self.disc, self.res, self.sn, self.dims = app, disc, res, sn, dims
        me = "app:" + app
        self.edges = [e for e in portfolio["edges"] if e["source"] == me and e["type"] != "CONTAINS"]
        self.nodes = {n["id"]: n for n in portfolio["nodes"]}
        self.portfolio = portfolio
        self.kind = (_fact(disc, "stack.artifact_kind").get("value") or "unknown")
        deps = _fact(disc, "stack.external_dependencies").get("value") or []
        self.deps = [d for d in deps if isinstance(d, dict) and d.get("where") != "tests only"]
        kinds = {d.get("kind") for d in self.deps}
        types = {e["type"] for e in self.edges}
        self.needs = {
            "spring_boot": bool(_fact(disc, "stack.spring_boot_version").get("value")),
            "framework": bool(_fact(disc, "stack.app_framework").get("value")) or bool(_fact(disc, "stack.spring_boot_version").get("value")),
            "outbound_http": "CALLS_API" in types or bool(_fact(disc, "stack.http_client_libraries").get("value"))
            or ((_fact(disc, "runtime.http_timeouts").get("value") or {}).get("state") in GAP_STATES + ("PRESENT",)),  # a client built in code
            "messaging": bool({"PUBLISHES_TO", "CONSUMES_FROM"} & types) or "Messaging" in kinds,
            "database": bool({"READS_FROM", "WRITES_TO"} & types) or any(d.get("kind") == "Database" and not d.get("embedded") for d in self.deps),
            # JDBC timeouts and schema migrations are relational concerns: a document or key-value store, or an in-memory database, is not covered
            "sql_database": any(d.get("kind") == "Database" and not d.get("embedded") and not NOSQL.search(d.get("technology") or "") for d in self.deps),
            "http_endpoints": _endpoints(disc) or any(n["type"] == "ApiEndpoint" and n.get("app") == app for n in portfolio["nodes"]),
        }
        self.criteria = {c["id"]: c for c in (disc.get("maturity") or {}).get("criteria", [])}
        ci = _fact(disc, "build_ci.ci_system").get("value") or []
        self.stack = {"ci_system": [c.lower() for c in (ci if isinstance(ci, list) else [ci])] or ["none"],
                      "build_tool": [str(_fact(disc, "stack.build_tool").get("value") or "unknown").lower()],
                      "platform": (res or {}).get("platforms") or ["none"],
                      "boot_graceful": ["no" if _boot_before(_fact(disc, "stack.spring_boot_version").get("value"), (2, 3)) else "yes"],
                      "framework": [(_fact(disc, "stack.app_framework").get("value") or {}).get("name") or ("spring_boot" if self.needs["spring_boot"] else "none")]}
        fw = _fact(disc, "stack.app_framework").get("value") or {}
        self.framework = fw.get("name") or ("spring_boot" if self.needs["spring_boot"] else None)
        self.framework_label = fw.get("label") or ("Spring Boot" if self.needs["spring_boot"] else None)
        self.ha = {c["id"]: c for c in (res or {}).get("summary", [])}


def _boot_before(v, ver):
    m = re.match(r"\s*(\d+)\.(\d+)", str(v or ""))
    return bool(m) and (int(m.group(1)), int(m.group(2))) < ver


def _endpoints(disc):
    f = _fact(disc, "api.http_endpoints_present")
    v = f.get("value")
    return f.get("status") == "CONFIRMED" and (v.get("controller_files", 0) > 0 if isinstance(v, dict) else bool(v))


def _a(kind):
    return ("an " if kind[:1] in "aeiou" else "a ") + kind + (" application" if kind == "unknown" else "")


NOSQL = re.compile(r"(?i)dynamo|mongo|cassandra|redis|elastic|opensearch|couch|neo4j|cosmos|firestore|bigtable|hbase|s3\b|hazelcast")
NEED_TEXT = {"sql_database": "no relational database found (an in-memory database, or a document or key-value store, is not covered by this check)", "spring_boot": "no Spring Boot found", "framework": "no application framework found", "outbound_http": "no outbound HTTP calls or HTTP client found", "messaging": "no messaging found",
             "database": "no database found", "http_endpoints": "no HTTP endpoints found"}


def applies(ctl, cx):
    a = ctl.get("applies") or {}
    if a.get("kind") and cx.kind not in a["kind"]:
        return False, "does not apply to " + _a(cx.kind)
    if a.get("needs") and not cx.needs.get(a["needs"]):
        return False, NEED_TEXT.get(a["needs"], "not applicable")
    return True, None


def _r(state, summary, level=None, evidence=None, facts=None, severity=None):
    return {"state": state, "summary": summary, "level": level, "evidence": evidence or [], "facts": facts or [], "severity": severity}


def eval_criterion(cid, cx):
    c = cx.criteria.get(cid)
    if not c:
        return _r("NOT_APPLICABLE", "not scored for " + _a(cx.kind))
    st = CRITERION_STATE.get(c["result"], "UNKNOWN")
    facts = c.get("facts") or []
    # a scanner configured but "not run by a CI file" is unknown, not partial, when the pipeline is outside the repository
    manual = _fact(cx.disc, "build_ci.manual_deploy_documented")
    if cid in ("automated_deploy", "rollback") and manual.get("value") and st == "ABSENT":  # a runbook shows a person doing it
        e0 = (manual.get("evidence") or [{}])[0]
        return _r("ABSENT", "Done by hand: the documentation has a person run the deploy (%s:%s)" % (e0.get("path"), e0.get("line_start")),
                  None, _ev(manual.get("evidence"), "CONFIRMED"), ["build_ci.manual_deploy_documented"] + facts)
    if cx.stack["ci_system"] == ["external"] and cid in PIPELINE_CRITERIA and st in ("ABSENT", "UNKNOWN"):
        ext = _fact(cx.disc, "build_ci.ci_system")
        return _r("UNKNOWN", "The pipeline runs outside this repository (named in %s); what it does is not visible here" %
                  ", ".join("%s:%s" % (e["path"], e["line_start"]) for e in (ext.get("evidence") or [])[:1]) or "the README",
                  None, _ev(ext.get("evidence"), "INFERRED"), ["build_ci.ci_system"])
    ev, notes = [], []
    for p in facts:
        f = _fact(cx.disc, p)
        ev += _ev([e for e in f.get("evidence") or [] if cid in TEST_CRITERIA or not TEST_PATH.search(e.get("path") or "")], f.get("status"))
        if f.get("note") and not f["note"].startswith("derived from"):
            notes.append(f["note"])
    # enforced is earned only by a MET result: those rules require the pipeline to run the control. PARTIAL means configured, not run.
    level = ("enforced" if cid in ENFORCED and st == "PRESENT" else "configured") if st in ("PRESENT", "PARTIAL") else None
    if st == "PRESENT" and cid in TEST_CRITERIA:  # tests the pipeline runs are enforced: cite the line that runs them
        run = []
        if cid in ("unit_tests_exist", "integration_tests") and (cx.criteria.get("tests_run_in_ci") or {}).get("result") == "MET":
            run = [e for p in cx.criteria["tests_run_in_ci"].get("facts") or [] for e in _ev(_fact(cx.disc, p).get("evidence"), "CONFIRMED") if CI_PATH.search(e.get("path") or "")][:1]
        ev = run + ev
        if any(CI_PATH.search(e.get("path") or "") for e in ev):
            level = "enforced"
    head = {"PRESENT": "Found", "PARTIAL": "Partly in place", "ABSENT": "Not found in the files read", "ISSUE": "Switched off or disabled", "UNKNOWN": "Cannot be decided from the files"}[st]
    if cid == "coverage" and st in ("PARTIAL", "ABSENT"):
        notes = [coverage_gap(cx)] + notes
    if st == "PRESENT" and not notes:
        notes = [found_what(cid, cx, facts, ev)]
    return _r(st, head + (": " + notes[0] if notes else ""), level, ev, facts)


COUNTS = (("test_classes", "test class", "test classes"), ("feature_files", "feature file", "feature files"), ("contract_files", "contract file", "contract files"),
          ("postman_collections", "Postman collection", "Postman collections"))


def found_what(cid, cx, facts, ev):
    """Say what was found, not just that something was: counts for test suites, otherwise the first cited place."""
    v = _fact(cx.disc, facts[0]).get("value") if facts else None
    if isinstance(v, dict):
        bits = ["%d %s" % (v[k], one if v[k] == 1 else many) for k, one, many in COUNTS if isinstance(v.get(k), int) and v[k]]
        tools = v.get("tools") or v.get("libraries")
        if bits:
            return ", ".join(bits) + (" (%s)" % ", ".join(tools[:3]) if tools else "")
    return "%s:%s" % (ev[0]["path"], ev[0]["line_start"]) if ev else "found"


def coverage_gap(cx):
    """What exactly is missing for a coverage gate, from the coverage facts: no tool, a tool with no minimum, or a minimum the pipeline does not run."""
    tool = _fact(cx.disc, "tests.coverage_tool_configured").get("value")
    if not tool:
        return "no coverage tool (JaCoCo, Kover, ...) is configured"
    if not _fact(cx.disc, "tests.coverage_enforced").get("value"):
        return "%s is configured but sets no minimum (no verification rule fails the build)" % tool
    thr = _fact(cx.disc, "tests.coverage_threshold_pct").get("value")
    if thr is not None and thr < 75:
        return "%s enforces a minimum of %s%%, below 75%%" % (tool, thr)
    return "%s enforces a minimum, but no pipeline step is shown to run it" % tool


def eval_ha(hid, cx):
    if not cx.res or cx.res.get("state") != "assessed":
        return _r("NOT_ASSESSED", (cx.res or {}).get("reason") or "no deployment files read")
    c = cx.ha.get(hid)
    if not c:
        return _r("NOT_ASSESSED", "check not run")
    st = HA_STATE.get(c["state"], "UNKNOWN")
    note = (c.get("notes") or [None])[0]
    n = c.get("workloads") or 0
    said = {"PRESENT": "Set for %d workload%s" % (n, "" if n == 1 else "s"), "PARTIAL": "Set for some workloads, not all", "ABSENT": "Not in the deployment files read",
            "UNKNOWN": "Cannot be decided from the deployment files", "NOT_APPLICABLE": "Does not apply to this platform"}.get(st, c["state"])
    return _r(st, note or said, "configured" if st in ("PRESENT", "PARTIAL") else None, _ev(c.get("evidence")), ["resilience." + hid])


def eval_lifecycle(which, cx):
    d = (cx.dims or {}).get("dimensions", {}).get("technology_lifecycle") or {}
    if which == "framework":  # the application's framework: Spring Boot by release line, others by their published end-of-life table
        fv = (d.get("values") or {}).get("framework")
        if not fv:
            which = "spring_boot"
        else:
            ev = _ev(fv.get("evidence"), "CONFIRMED")
            if fv["status"] == "ended":
                return _r("ISSUE", fv["headline"], "configured", ev, ["stack.app_framework"])
            if fv["status"] == "supported":
                return _r("PRESENT", fv["headline"], "configured", ev, ["stack.app_framework"])
            return _r("UNKNOWN", fv["headline"], None, ev, ["stack.app_framework"])
    v = (d.get("values") or {}).get(which)
    if not v or not v.get("version"):
        return _r("UNKNOWN", "no %s version could be read from the build files" % ("Java" if which == "java" else "Spring Boot"), facts=["stack.%s_version" % which])
    ev = _ev(v.get("evidence"), "CONFIRMED")
    if which == "java":
        st = v.get("status")
        if st == "out_of_support":
            return _r("ISSUE", "Java %s: vendor support ended (extended until %s)" % (v["version"], v.get("extended_until")), "configured", ev, ["stack.java_version"])
        if st == "extended_support_only":
            return _r("PARTIAL", "Java %s: only extended (paid) support remains, until %s" % (v["version"], v.get("extended_until")), "configured", ev, ["stack.java_version"], "medium")
        if st == "premier_support":
            return _r("PRESENT", "Java %s: in premier support until %s" % (v["version"], v.get("premier_until")), "configured", ev, ["stack.java_version"])
        return _r("UNKNOWN", "Java %s: %s" % (v["version"], v.get("note") or "not in the reference data"), None, ev, ["stack.java_version"])
    st, f = v.get("oss_status"), ["stack.spring_boot_version"]
    if st == "ended":
        return _r("ISSUE", "Spring Boot %s: all support ended%s" % (v["version"], " (" + v["commercial_end"] + ")" if v.get("commercial_end") else ""), "configured", ev, f)
    if st == "commercial_only":
        return _r("PARTIAL", "Spring Boot %s: open-source support ended %s; only paid support remains, until %s" % (v["version"], v["oss_end"], v["commercial_end"]), "configured", ev, f, "high")
    if st == "supported":
        return _r("PRESENT", "Spring Boot %s: open-source support until %s" % (v["version"], v["oss_end"]), "configured", ev, f)
    return _r("UNKNOWN", "Spring Boot %s: %s" % (v["version"], v.get("note") or "support window unknown"), None, ev, f)  # no answer is never a pass


def eval_fact(path, cx, partial_if_file=False):
    f = _fact(cx.disc, path)
    st, val = f.get("status"), f.get("value")
    ev = _ev(f.get("evidence"), st)
    if st in ("CONFIRMED", "INFERRED") and val not in (None, False, [], "", {}):
        shown = val if isinstance(val, str) else ", ".join(map(str, val)) if isinstance(val, list) else \
            ("Found at %s:%s" % (ev[0]["path"], ev[0]["line_start"]) if ev else "Found")
        return _r("PRESENT", str(shown)[:160], "configured" if st == "CONFIRMED" else "declared", ev, [path])
    if st == "UNKNOWN":
        return _r("UNKNOWN", f.get("note") or "cannot be decided from the files", facts=[path])
    if partial_if_file and ev:  # the file is there but does not hold what the control asks for (a README with no description)
        return _r("PARTIAL", "%s exists, but %s" % (ev[0]["path"], f.get("note") or "it does not hold what is needed"), "declared", ev, [path])
    return _r("ABSENT", f.get("note") or "not found in the files read", None, ev, [path])


def eval_check(path, cx):
    """A detector that decides the state itself: its fact value is {state, summary, level}."""
    f = _fact(cx.disc, path)
    v = f.get("value")
    if not isinstance(v, dict) or v.get("state") not in STATES:
        return _r("NOT_ASSESSED", "Not in this analysis: it predates the %s detector; scan again" % path.split(".")[0], facts=[path])
    return _r(v["state"], v["summary"], v.get("level"), _ev(f.get("evidence"), f.get("status")), [path])


def eval_dependency(spec, cx):
    rx = re.compile(spec["match"], re.I)
    hits = [d for d in cx.deps if d.get("kind") == spec["kind"] and rx.search(d.get("technology") or "")]
    allev = _fact(cx.disc, "stack.external_dependencies").get("evidence") or []
    if not hits:
        said = "no %s library found" % spec["kind"].lower() if spec["match"] in (".", ".*") else "no library matching %s found" % spec["match"].replace("|", ", ")
        if spec.get("configured_by") and _fact(cx.disc, "resilience.health_endpoint").get("value"):  # the metrics control only
            said += " (a management or health module is present: metrics may be available locally, but nothing exports them)"
        return _r("ABSENT", said, facts=["stack.external_dependencies"])
    at = {a for d in hits for a in d.get("at") or []}
    ev = [dict(e, status="CONFIRMED") for e in allev if "%s:%s" % (e.get("path"), e.get("line_start")) in at]
    strong = any(d.get("evidence_strength") == "configured" for d in hits)
    conf = _fact(cx.disc, spec["configured_by"]) if spec.get("configured_by") else {}
    if conf.get("value"):  # configured in settings or wired in code, not only declared
        strong, ev = True, ev + _ev(conf.get("evidence"), "CONFIRMED")
    return _r("PRESENT", ", ".join(sorted({d["technology"] for d in hits})) + ("" if strong else " (dependency declared; no configuration found)"),
              "configured" if strong else "declared", ev, ["stack.external_dependencies"])


def eval_safetynet(cx):
    s = (cx.sn or {}).get("summary") or {}
    tot = sum(v["mapped_with_assertions"] + v["mapped_no_assertion_seen"] + v["unverified"] for v in s.values())
    mapped = sum(v["direct"] if v.get("direct") is not None else v["mapped_with_assertions"] + v["mapped_no_assertion_seen"] for v in s.values())
    cls = sum(v.get("class_level") or 0 for v in s.values() if v.get("direct") is not None)  # a test names the class, the route is not matched
    if not tot:
        return _r("NOT_APPLICABLE", "no endpoints, consumers, publishers or data paths were discovered")
    st = "PRESENT" if mapped == tot else "PARTIAL" if mapped or cls else "ABSENT"
    # cite only mappings that support the claim: a test file line, not an import of the class under test
    ev = [dict(m["evidence"], status="CONFIRMED") for c in (cx.sn or {}).get("components") or [] for m in (c.get("mapping") or [])[:1]
          if m.get("evidence") and not re.match(r"\s*import\s", m["evidence"].get("snippet") or "")][:6]
    said = "%d of %d discovered components have a test mapped by route, listener or data path" % (mapped, tot)
    if cls:
        said += "; %d more are reached only by a test that names their class (route not matched)" % cls
    if mapped < tot:
        said += "; a route held in a constant or built at run time is not followed, so this can undercount"
    return _r(st, said + " (unverified is not untested)", "configured" if mapped or cls else None, ev, ["safetynet.summary"])


def eval_security_scan(cx):
    d = (cx.dims or {}).get("dimensions", {}).get("security_exposure") or {}
    if d.get("state") == "assessed":
        st = {"concern": "ISSUE", "attention": "PARTIAL"}.get(d.get("level"), "PRESENT")
        return _r(st, d.get("headline") or "scanned", "verified" if st == "PRESENT" else None, facts=d.get("based_on") or [])
    return _r("NOT_ASSESSED", "No vulnerability scan was run, so exposure is not known (run scan.py to check)", facts=d.get("based_on") or [])


def eval_graph(which, cx):
    E = cx.edges
    if which == "unmatched_calls":
        # services named in configuration that no relationship cites: their calls were not traced, so "all matched" would be hollow
        cited = {"%s:%s" % (x.get("path"), x.get("line_start")) for e in E for x in e.get("evidence") or []}
        urls = _fact(cx.disc, "runtime.service_urls")
        untraced = [u for u in urls.get("value") or [] if u["at"] not in cited]
        if untraced:
            ev = [dict(x, status="CONFIRMED") for x in urls.get("evidence") or [] if "%s:%s" % (x["path"], x["line_start"]) in {u["at"] for u in untraced}]
            return _r("UNKNOWN", "Configuration names %d other service%s (%s) whose calls were not traced in code, so the dependency map is incomplete" %
                      (len(untraced), "" if len(untraced) == 1 else "s", ", ".join(u["key"] for u in untraced[:4])), None, ev[:4], ["runtime.service_urls"])
        libs = _fact(cx.disc, "stack.http_client_libraries").get("value") or []
        if libs and not any(e["type"] == "CALLS_API" for e in E):  # a client is there but no call it makes was traced
            return _r("UNKNOWN", "An HTTP client is used (%s) but no call target was traced in the code, so the dependency map is incomplete" %
                      ", ".join(sorted({l.get("technology", "") if isinstance(l, dict) else str(l) for l in libs})[:3]), None, [], ["stack.http_client_libraries"])
        if not E:
            return _r("NOT_APPLICABLE", "no outbound calls, messages or data access found")
        bad = [e for e in E if e["resolution"]["state"] in ("unresolved", "ambiguous")]
        ev = [dict(x, status="INFERRED" if bad else "CONFIRMED") for e in (bad or E)[:6] for x in (e.get("evidence") or [])[:1]]
        return _r("PARTIAL" if bad else "PRESENT", "%d of %d relationships not matched to a known application" % (len(bad), len(E)) if bad else "all %d relationships found in the code were matched (calls whose target is built by hand in code may not be found)" % len(E),
                  "configured", ev, ["relationships"])
    if which == "shared_database":
        mine = {e["target"] for e in E if e["type"] in ("READS_FROM", "WRITES_TO")
                or (e["type"] == "DEPENDS_ON" and (cx.nodes.get(e["target"]) or {}).get("type") == "Database")}
        shared = []
        for t in mine:
            n = cx.nodes.get(t) or {}
            if n.get("type") == "Database" and (n.get("attrs") or {}).get("identity") == "connection":
                others = sorted({e["source"][4:] for e in cx.portfolio["edges"] if e["target"] == t and e["source"].startswith("app:") and e["source"] != "app:" + cx.app})
                if others:
                    shared.append("%s (also %s)" % (n.get("name"), ", ".join(others[:3])))
        if not mine:
            return _r("NOT_APPLICABLE", "no database access found")
        dbe = [dict(x, status="CONFIRMED") for e in E if e["target"] in mine for x in (e.get("evidence") or [])[:1]][:3]
        return _r("ISSUE" if shared else "PRESENT", "shares " + "; ".join(shared) if shared else "no database shared with another analysed application", "configured", dbe, ["relationships"])
    if which == "profile_differences":
        cfg = [e for e in E if (e.get("attrs") or {}).get("host_from_configuration") or (e.get("attrs") or {}).get("how") == "placeholder"]
        if not cfg:
            return _r("NOT_APPLICABLE", "no connection target is read from configuration")
        diff = [e for e in cfg if re.search(r"differs between profiles", (e.get("resolution") or {}).get("reason") or "")]
        ev = [dict(x, status="CONFIRMED") for e in (diff or cfg)[:3] for x in (e.get("evidence") or [])[:1]]
        return _r("PARTIAL" if diff else "PRESENT", "%d of %d configured target(s) differ between profiles" % (len(diff), len(cfg)) if diff else "none of %d configured target(s) differ between profiles" % len(cfg), "configured", ev, ["relationships"])
    if which == "unresolved_placeholders":
        ph = [e for e in E if (e.get("attrs") or {}).get("how") == "placeholder" or (e.get("attrs") or {}).get("host_from_configuration")]
        if not ph:
            return _r("NOT_APPLICABLE", "no target is held in a placeholder")
        bad = [e for e in ph if e["resolution"]["state"] == "unresolved"]
        ev = [dict(x, status="CONFIRMED") for e in (bad or ph)[:3] for x in (e.get("evidence") or [])[:1]]
        return _r("PARTIAL" if bad else "PRESENT", "%d of %d placeholder target(s) could not be resolved" % (len(bad), len(ph)) if bad else "all %d placeholder target(s) resolved" % len(ph), "configured", ev, ["relationships"])
    return _r("NOT_ASSESSED", "unknown graph check " + which)


def evaluate(ctl, cx):
    r = _evaluate(ctl, cx)
    # a detector that reads one framework's conventions cannot say "missing" for another: that is "not recognised", not a gap
    knows = ctl.get("understands")
    # (applicability from outbound HTTP or a database is read the same framework-bound way, so it is not trusted either)
    if knows and cx.framework and cx.framework not in knows and not r.get("pending") and (
            r["state"] == "ABSENT" or (r["state"] == "NOT_APPLICABLE" and (ctl.get("applies") or {}).get("needs") in ("outbound_http", "database"))):
        return _r("UNKNOWN", "Not recognised for %s: this check reads %s conventions, so absence here proves nothing" % (cx.framework_label, " / ".join(LABEL.get(k, k) for k in knows)),
                  facts=r["facts"])
    return r


LABEL = {"spring_boot": "Spring Boot", "spring": "Spring", "quarkus": "Quarkus", "micronaut": "Micronaut", "dropwizard": "Dropwizard"}


def _evaluate(ctl, cx):
    ok, why = applies(ctl, cx)
    if not ok:
        return _r("NOT_APPLICABLE", why)
    s = ctl["source"]
    if "criterion" in s:
        return eval_criterion(s["criterion"], cx)
    if "ha" in s:
        return eval_ha(s["ha"], cx)
    if "lifecycle" in s:
        return eval_lifecycle(s["lifecycle"], cx)
    if "fact" in s:
        return eval_fact(s["fact"], cx, bool(ctl.get("partial_if_file")))
    if "check" in s:
        return eval_check(s["check"], cx)
    if "dependency" in s:
        return eval_dependency(s["dependency"], cx)
    if "safetynet" in s:
        return eval_safetynet(cx)
    if "security_scan" in s:
        return eval_security_scan(cx)
    if "graph" in s:
        return eval_graph(s["graph"], cx)
    return dict(_r("NOT_ASSESSED", "No detector yet: " + s.get("pending", "not built")), pending=True)


def fits(rem, cx):
    """A remedy that names what it works on (GitLab CI, Maven, Kubernetes) is offered only to applications that have it."""
    return all(set(v) & set((cx.stack if cx else {}).get(k, [])) for k, v in (rem.get("requires") or {}).items()) if cx else True


def remedies_for(ctl, packs, cx=None):
    for p in packs:
        keys = (p.get("controls") or {}).get(ctl["id"]) or (p.get("aspects") or {}).get(ctl["aspect"])
        got = [dict(p["remedies"][k], key=k, pack=p["id"]) for k in keys or [] if k in p["remedies"] and fits(p["remedies"][k], cx)]
        if got:
            return got
    return []


def rollup(controls):
    """Status and coverage over the controls that apply. A control with no detector yet is a gap in this tool, not a fact about
    the application, so it is kept out of the coverage; an aspect whose checked controls are all in place while others could
    not be decided is "in place where checked", never plain "in place"."""
    app_ = [c for c in controls if c["state"] != "NOT_APPLICABLE" and not c.get("pending")]
    counts = {}
    for c in controls:
        counts[c["state"]] = counts.get(c["state"], 0) + 1
    assessed = [c for c in app_ if c["state"] not in ("NOT_ASSESSED", "UNKNOWN")]
    if not app_:
        status = "not_assessed" if any(c.get("pending") for c in controls) else "not_applicable"
    elif not assessed:
        status = "not_assessed"
    elif any(c["state"] == "ISSUE" or (c["state"] in ("ABSENT", "PARTIAL") and c["severity"] == "high") for c in assessed):
        status = "issues"
    elif any(c["state"] in ("ABSENT", "PARTIAL") for c in assessed):
        status = "gaps"
    elif len(assessed) < len(app_) or any(c.get("pending") for c in controls):
        status = "in_place_partly_checked"
    else:
        status = "in_place"
    present = sum(1 for c in assessed if c["state"] == "PRESENT")
    return status, counts, {"applicable": len(app_), "assessed": len(assessed), "present": present, "pending": sum(1 for c in controls if c.get("pending"))}


def build_app(app, disc, rel, res, sn, dims, portfolio, catalogue, packs, generated_at=None):
    cx = Context(app, disc, rel, res, sn, dims, portfolio)
    by_aspect = {a["id"]: [] for a in catalogue["aspects"]}
    findings = []
    for ctl in catalogue["controls"]:
        r = evaluate(ctl, cx)
        pending = r.pop("pending", False)
        sev = r.pop("severity") or ctl.get("severity", "medium")
        c = {"id": ctl["id"], "aspect": ctl["aspect"], "title": ctl["title"], "state": r["state"], "level": r["level"], "summary": r["summary"],
             "severity": sev if r["state"] in GAP_STATES else None, "facts": r["facts"], "evidence": r["evidence"], "fix": ctl.get("fix"),
             "remedies": remedies_for(ctl, packs, cx) if r["state"] in GAP_STATES else [], "finding": None, "pending": pending}
        if r["state"] in GAP_STATES:
            c["finding"] = "%s@%s" % (ctl["id"], app)
            findings.append(c["finding"])
        by_aspect[ctl["aspect"]].append(c)
    aspects = []
    for a in sorted(catalogue["aspects"], key=lambda x: x["order"]):
        cs = by_aspect[a["id"]]
        status, counts, cov = rollup(cs)
        aspects.append({"id": a["id"], "title": a["title"], "question": a["question"], "status": status, "counts": counts, "coverage": cov, "controls": cs})
    dd = (dims or {}).get("dimensions", {})
    ctx = {k: {"title": dd[k]["title"], "state": dd[k]["state"], "headline": dd[k]["headline"]} for k in ("business_criticality", "change_complexity", "evidence_completeness", "architecture_coupling") if k in dd}
    return {"contract": CONTRACT, "app": app, "generated_at": generated_at, "catalogue": {"version": catalogue["version"], "status": catalogue.get("status")},
            "remedy_packs": [{"id": p["id"], "version": p["version"]} for p in packs], "profile": {"kind": cx.kind, "has": cx.needs},
            "context": ctx, "aspects": aspects, "findings": findings}


def _redact(doc):
    from . import engine_path  # noqa: F401
    import evidence  # engine
    return evidence.redact_tree(doc)


def build(out, catalogue=None, packs=None):
    """Write <out>/<app>/aspects.json for every application of an analysis, and <out>/portfolio/aspects.json. Returns the per-app docs."""
    catalogue = catalogue or load_catalogue()
    packs = packs if packs is not None else load_remedy_packs(["generic"])
    man = _read(os.path.join(out, "manifest.json"))
    P = _read(os.path.join(out, "portfolio", "relationships.json"))
    docs = {}
    for x in man["applications"]:
        app, d = x["app"], os.path.join(out, x["app"])
        rd = lambda n: _read(os.path.join(d, n)) if os.path.isfile(os.path.join(d, n)) else None  # noqa: E731
        doc = build_app(app, rd("discovery.json"), rd("relationships.json"), rd("resilience.json"), rd("safetynet.json"), rd("dimensions.json"), P, catalogue, packs, man.get("generated_at"))
        with open(os.path.join(d, "aspects.json"), "w", encoding="utf-8") as fh:
            json.dump(_redact(doc), fh, indent=1, sort_keys=True)
        docs[app] = doc
    summary = {"contract": "aspects-portfolio.v1", "generated_at": man.get("generated_at"), "catalogue": catalogue["version"], "remedy_packs": [p["id"] for p in packs],
               "aspects": [{"id": a["id"], "title": a["title"]} for a in sorted(catalogue["aspects"], key=lambda x: x["order"])],
               "applications": {app: {a["id"]: a["status"] for a in doc["aspects"]} for app, doc in sorted(docs.items())}}
    os.makedirs(os.path.join(out, "portfolio"), exist_ok=True)
    with open(os.path.join(out, "portfolio", "aspects.json"), "w", encoding="utf-8") as fh:
        json.dump(_redact(summary), fh, indent=1, sort_keys=True)
    return docs
