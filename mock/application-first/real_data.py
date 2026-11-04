#!/usr/bin/env python3
"""Turn one app-insight run into data-real.js: the same globals the application-first mock reads
(capDefs, aspectDefs, apps, edges, pendingControls), plus the facts, modules, endpoints and
dependencies the AS-IS and Architecture tabs draw. Read only; run with python3 -I.

    python3 -I real_data.py <run-dir> <out.js>
"""
import json
import os
import re
import sys

ENGINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "engine", "scripts")
sys.path.insert(0, ENGINE)
import evidence as _ev  # noqa: E402  (app-insight's own redaction, applied again before anything is embedded)

RUN, OUT = sys.argv[1], sys.argv[2]
A = os.path.join(RUN, "analysis")
load = lambda *p: json.load(open(os.path.join(A, *p)))

# the mock's four groups; display only, a draft for sign-off
CAPS = {"delivery": "change", "testing": "change", "api": "change", "code": "change",
        "security": "platform", "platform": "platform", "config": "platform",
        "runtime": "runtime", "availability": "runtime",
        "observability": "operate", "data": "operate", "architecture": "operate", "knowledge": "operate"}
CAPDEFS = [{"id": "change", "title": "Change safety", "icon": "code"},
           {"id": "platform", "title": "Platform & protection", "icon": "shield"},
           {"id": "runtime", "title": "Runtime reliability", "icon": "route"},
           {"id": "operate", "title": "Operability & recovery", "icon": "settings"}]
SNIP = 240


def snip(s):
    if not isinstance(s, str):
        return ""
    if "PRIVATE KEY" in s:                       # never more than the header, whatever the input holds
        return s.strip().splitlines()[0][:60] + " [key material not copied]"
    return s[:SNIP]


def evs(lst):
    out = []
    for e in lst or []:
        if isinstance(e, dict) and e.get("path"):
            out.append({"path": e["path"], "line": e.get("line_start"), "snippet": snip(e.get("snippet"))})
    return out[:12]


def cite(e):
    return "%s:%s" % (e["path"], e["line"]) if e.get("line") else e["path"]


def searched(v):
    if not v:
        return []
    if isinstance(v, dict) and "in" in v:          # {"for": what, "in": [{area, count, files[]}]}
        out = ["Looked for " + v["for"]] if v.get("for") else []
        for x in v.get("in") or []:
            fs = x.get("files") or []
            more = (x.get("count") or len(fs)) - len(fs)
            out.append("%s (%s file%s): %s%s" % (x.get("area"), x.get("count"), "" if x.get("count") == 1 else "s", ", ".join(fs), " and %d more" % more if more > 0 else ""))
        return out
    if isinstance(v, dict):
        v = ["%s: %s" % (k, x) for k, x in v.items()]
    return [str(x) for x in (v if isinstance(v, list) else [v])][:12]


def fact(sec, key):
    return (sec or {}).get(key) or {}


def factrow(label, f, value=None):
    """[label, value, evidence[], note]; a fact that was not found says so with the tool's own note"""
    v = f.get("value") if value is None else value
    if v in (None, [], "", {}) or f.get("status") == "NOT_FOUND":
        return [label, "not found", evs(f.get("evidence")), f.get("note") or ""]
    if isinstance(v, list):
        v = ", ".join(str(x) for x in v)
    return [label, str(v), evs(f.get("evidence")), f.get("note") or ""]




LABELS = {"health": "Health endpoint", "http_timeouts": "HTTP client timeouts", "db_timeouts": "Database timeouts", "retries_breakers": "Retries and circuit breakers",
          "graceful_shutdown": "Graceful shutdown", "metrics_export": "Metrics export", "structured_logging": "Structured logging", "messaging_errors": "Messaging error handling",
          "service_urls": "Service addresses in configuration", "deploy_descriptors": "Deployment descriptors", "multiple_instances": "More than one instance",
          "rolling_or_zero_downtime_strategy": "Rolling or zero-downtime deploy", "container_image": "Container image", "health_probes": "Health probes", "rollback": "Rollback",
          "health_endpoint": "Health endpoint", "build_wrapper": "Build wrapper", "modules_with_tests_disabled": "Modules with tests switched off", "build_level_test_skip": "Tests switched off in the build", "unit_tests": "Unit tests", "integration_tests": "Integration tests", "contract_tests": "Contract tests",
          "acceptance_tests": "Acceptance tests", "performance_tests": "Performance tests", "frameworks": "Test frameworks", "coverage_tool_configured": "Coverage tool",
          "coverage_scope": "Coverage configured in", "coverage_state": "Coverage", "coverage_threshold_pct": "Coverage threshold", "coverage_measured": "Coverage measured",
          "ci_test_execution": "Tests run in CI", "ci_skip_flags": "CI commands that skip tests", "build_step": "Build step in CI", "deploy_step": "Deploy step in CI",
          "publish_step": "Publish step in CI", "manual_deploy_documented": "Manual deploy documented", "release_plugin_tags": "Release plugin tags versions",
          "artifact_tag_from_commit": "Artefact tagged with the commit", "version_from_git_tag": "Version from git tag", "stages": "CI stages", "jobs": "CI jobs"}


def fmtv(key, v):
    """one readable sentence for a fact value; facts only, never the state inside a derived value"""
    if isinstance(v, dict) and "summary" in v:
        return v["summary"]
    if isinstance(v, bool):
        return "yes" if v else "no"
    if key == "unit_tests" and isinstance(v, dict):
        bm = v.get("by_module") or {}
        return "%s test classes in %s files%s" % (v.get("test_classes"), v.get("test_files"), (" (" + ", ".join("%s %s" % ("root" if m == "." else m, n) for m, n in bm.items()) + ")") if len(bm) > 1 else "")
    if key == "integration_tests" and isinstance(v, dict):
        return "%s test classes%s%s" % (v.get("test_classes"), ("; " + ", ".join(v["tools"])) if v.get("tools") else "", "; own source set" if v.get("separate_source_set") else "")
    if key in ("contract_tests", "acceptance_tests", "performance_tests") and isinstance(v, dict):
        bits = ["%s %s" % (n, k.replace("_", " ")) for k, n in v.items() if isinstance(n, int) and n]
        tools = [x for k in ("tools", "libraries", "browser_tools", "external") for x in (v.get(k) or [])]
        return "; ".join(bits + ([", ".join(tools)] if tools else [])) or "none counted"
    if key == "coverage_scope" and isinstance(v, dict):
        return "%s of %s modules" % (v.get("configured_modules"), v.get("total_modules"))
    if isinstance(v, str):
        return v.replace("_", " ")
    if isinstance(v, list):
        if v and isinstance(v[0], dict) and "key" in v[0]:
            return "; ".join("%s = %s" % (x.get("key"), x.get("value")) for x in v[:6]) + (" and %d more" % (len(v) - 6) if len(v) > 6 else "")
        return ", ".join(str(x) for x in v[:8]) + (" and %d more" % (len(v) - 8) if len(v) > 8 else "")
    return json.dumps(v)[:160]


def panel(sec, keys):
    """[found rows], [labels not found]; a row is [label, value, evidence[], note]"""
    rows, missing = [], []
    for k in keys:
        f = (sec or {}).get(k)
        if not isinstance(f, dict):
            continue
        v = f.get("value")
        if f.get("status") == "NOT_FOUND" or v in (None, [], "", {}):
            missing.append(LABELS.get(k, k))
            continue
        rows.append([LABELS.get(k, k), fmtv(k, v), evs(f.get("evidence")), f.get("note") or ""])
    return rows, missing



def at_ev(at):
    out = []
    for s in at or []:
        path, _, line = str(s).rpartition(":")
        out.append({"path": path or s, "line": int(line) if line.isdigit() else None, "snippet": ""})
    return out


def nplural(n, w):
    return "%s %s%s" % (n, w, "" if n == 1 else "es" if w.endswith("s") else "s")


def build_asis(app, disc, app_edges, facts):
    """AS-IS grouped for reading: fact sections, tests by type, dependencies by category. Facts only."""
    st, idn, ci, rt, rs, ts = disc["stack"], disc["identity"], disc["build_ci"], disc.get("runtime") or {}, disc.get("resilience") or {}, disc.get("tests") or {}
    F = {f[0]: f for f in facts}
    def rows_of(labels):
        r, miss = [], []
        for l in labels:
            f = F[l]
            (miss.append(l) if f[1] == "not found" else r.append(f))
        return r, miss
    sec = []
    r, m = rows_of(["Purpose (README)", "Owners", "Repository", "Commit"]); sec.append({"id": "identity", "title": "Identity", "rows": r, "missing": m})
    hc = fact(st, "http_client_libraries").get("value") or []
    r, m = rows_of(["CI system", "CI files"]); w = panel(st, ["build_wrapper"]); d = panel(ci, ["build_step", "publish_step", "deploy_step", "manual_deploy_documented", "release_plugin_tags", "version_from_git_tag", "artifact_tag_from_commit"])
    sec.append({"id": "delivery", "title": "Build and delivery", "rows": r + w[0] + d[0], "missing": m + w[1] + d[1]})
    # deployment: which tooling was found, then how it behaves
    resil = json.load(open(os.path.join(A, app, "resilience.json")))
    plats = [p.lower() for p in resil.get("platforms") or []]
    cont = fact(st, "container")
    cv = cont.get("value") if isinstance(cont.get("value"), dict) else {}
    desc = fact(rs, "deploy_descriptors")
    tools = []
    cbits = (["Dockerfile: " + ", ".join(cv["dockerfiles"])] if cv.get("dockerfiles") else []) + (["compose: " + ", ".join(cv["compose_files"])] if cv.get("compose_files") else []) + \
            (["image build plugin: " + ", ".join(str(x) for x in cv["build_plugins"])] if cv.get("build_plugins") else []) + (["base image " + ", ".join(cv["base_images"])] if cv.get("base_images") else [])
    if cbits:
        tools.append(["Containers", "; ".join(cbits), evs(cont.get("evidence")), ""])
    TG = [("Orchestration", ("kubernetes", "helm", "kustomize", "eks", "openshift")), ("Configuration management", ("ansible", "chef", "puppet", "salt")), ("Scheduler", ("nomad",))]
    for title, names in TG:
        hit = [p for p in plats if p in names]
        if hit:
            files = [x for x in (desc.get("value") or [])]
            tools.append([title, ", ".join(h.capitalize() for h in hit) + (" · " + nplural(len(files), "descriptor") if files else ""), evs(desc.get("evidence")), desc.get("note") or ""])
    dstep = panel(ci, ["deploy_step"])[0]
    if dstep:
        tools.append(["CI deploy step", "yes", dstep[0][2], dstep[0][3]])
    ign = [i.get("file") for i in resil.get("ignored") or [] if i.get("file")]
    tmiss = [g for g in ["Containers", "Orchestration", "Configuration management", "Scheduler", "CI deploy step"] if g not in [x[0] for x in tools]]
    r, m = rows_of(["Read elsewhere"]); d = panel(rs, ["multiple_instances", "rolling_or_zero_downtime_strategy", "health_probes", "health_endpoint", "rollback"])
    sec.append({"id": "deploy", "title": "Deployment", "tools": tools, "toolsMissing": tmiss, "ignored": sorted(set(ign)), "rows": d[0] + r, "missing": d[1] + m})
    d = panel(rt, ["health", "graceful_shutdown", "structured_logging"]); sec.append({"id": "runtime", "title": "Runtime", "rows": d[0], "missing": d[1]})

    # tests, one card per type the tool tells apart
    def tv(k):
        f = ts.get(k) or {}
        return f, (f.get("value") or {}), f.get("status") != "NOT_FOUND"
    types = []
    f, v, ok = tv("unit_tests")
    bm = v.get("by_module") or {}
    types.append({"id": "unit", "title": "Unit tests", "found": ok, "headline": nplural(v.get("test_classes") or 0, "test class") if ok else "None found",
                  "details": ([nplural(v["test_files"], "test file") + ("; %s only %s that the application starts, so %s not counted" % (v["context_load_only"], "checks" if v["context_load_only"] == 1 else "check", "it is" if v["context_load_only"] == 1 else "they are") if v.get("context_load_only") else "")] if v.get("test_files") else []) + (["by module: " + ", ".join("%s %s" % ("root" if k == "." else k, n) for k, n in bm.items())] if len(bm) > 1 else []),
                  "tools": [], "note": f.get("note") or "", "ev": evs(f.get("evidence"))})
    f, v, ok = tv("integration_tests")
    types.append({"id": "integration", "title": "Integration tests", "found": ok, "headline": nplural(v.get("test_classes") or 0, "test class") if ok else "None found",
                  "details": ["in their own source set"] if v.get("separate_source_set") else [], "tools": v.get("tools") or [], "note": f.get("note") or "", "ev": evs(f.get("evidence"))})
    f, v, ok = tv("contract_tests")
    types.append({"id": "contract", "title": "Contract tests", "found": ok, "headline": "; ".join(x for x in [nplural(v["test_classes"], "test class") if v.get("test_classes") else "", "%s contract files" % v["contract_files"] if v.get("contract_files") else ""] if x) or ("None found" if not ok else "found"),
                  "details": ["outside the repository: " + ", ".join(v["external"])] if v.get("external") else [], "tools": (v.get("tools") or []) + (v.get("libraries") or []), "note": f.get("note") or "", "ev": evs(f.get("evidence"))})
    f, v, ok = tv("acceptance_tests")
    types.append({"id": "acceptance", "title": "Acceptance tests", "found": ok, "headline": "; ".join(x for x in [nplural(v["test_classes"], "test class") if v.get("test_classes") else "", "%s feature files" % v["feature_files"] if v.get("feature_files") else "", "%s Postman collections" % v["postman_collections"] if v.get("postman_collections") else ""] if x) or "None found",
                  "details": ["outside the repository: " + ", ".join(v["external"])] if v.get("external") else [], "tools": (v.get("browser_tools") or []) + (v.get("libraries") or []), "note": f.get("note") or "", "ev": evs(f.get("evidence"))})
    f, v, ok = tv("performance_tests")
    types.append({"id": "performance", "title": "Performance tests", "found": ok, "headline": "%s scripts or plans" % v.get("artefacts") if ok and v.get("artefacts") else ("found" if ok else "None found"),
                  "details": ["outside the repository: " + ", ".join(v["external"])] if v.get("external") else [], "tools": v.get("tools") or [], "note": f.get("note") or "", "ev": evs(f.get("evidence"))})
    PURPOSE = [("Test framework", ("junit4", "junit5", "junit", "testng", "spock", "kotest")), ("Assertions", ("assertj", "hamcrest", "truth", "awaitility")),
               ("Mocks and stubs", ("mockito", "mockk", "wiremock", "mockwebserver")), ("Containers and emulators", ("testcontainers", "localstack")),
               ("Contract", ("pact", "spring-cloud-contract", "dredd")), ("Performance", ("gatling", "jmeter", "locust", "k6")),
               ("Browser and acceptance", ("selenium", "playwright", "cypress", "cucumber", "rest-assured", "serenity")), ("Spring test support", ("spring-boot-test", "spring-mvc-test"))]
    seen = []
    for tt in types:
        seen += tt["tools"]
    seen += fact(ts, "frameworks").get("value") or []
    seen += [d.get("technology") for d in fact(st, "external_dependencies").get("value") or [] if d.get("where") == "tests only"]
    seen = list(dict.fromkeys(x for x in seen if x))
    seen = [x for x in seen if not (" " in x and x.split(" ")[0].lower() in {y.lower() for y in seen if " " not in y})]   # "LocalStack (AWS emulator)" when "localstack" is already there
    def purpose(x):
        lx = x.lower()
        return next((pp for pp, names in PURPOSE if any(lx == n or lx.startswith(n + " ") or n in lx.split(" ") for n in names)), "Other")
    tool_groups = [[pp, [x for x in seen if purpose(x) == pp]] for pp, _ in PURPOSE + [("Other", ())]]
    tool_groups = [g for g in tool_groups if g[1]]
    cov = panel(ts, ["coverage_tool_configured", "coverage_scope", "coverage_state", "coverage_threshold_pct", "coverage_measured", "ci_test_execution", "ci_skip_flags", "modules_with_tests_disabled", "build_level_test_skip"])
    emu = [d.get("technology") for d in fact(st, "external_dependencies").get("value") or [] if d.get("where") == "tests only"]

    # dependencies by category
    xdeps = [d for d in fact(st, "external_dependencies").get("value") or [] if d.get("where") != "tests only"]
    def edges_to(tech):
        return [e for e in app_edges if e["target"] == tech or e.get("tech") == tech]
    def node_of(tech):
        for e in edges_to(tech):
            n = NODES.get(e["targetId"])
            if n:
                return n.get("attrs") or {}
        return {}
    def item_ev(d):
        ev = [x for e in edges_to(d.get("technology")) for x in e["ev"]]
        return (ev or at_ev(d.get("at")))[:8]
    BASIS = {"dependency": "the build dependencies", "connection setting": "a connection setting", "endpoint in configuration": "an endpoint setting", "client declaration": "a client declaration"}
    def how(d):
        return "Found in " + " and ".join(BASIS.get(b, b) for b in d.get("basis") or [])
    def mods(d):
        m = [x for x in d.get("modules") or [] if x != "."]
        return [["Module", ", ".join(m)]] if m else []
    cats = []
    dbs = []
    for d in xdeps:
        if d.get("kind") in ("Database", "Object storage"):
            a = node_of(d["technology"]); c = a.get("connection") or {}
            rows = [["Address", ("%s:%s / %s" % (c.get("host"), c.get("port"), c.get("database"))) if c else "no literal address in the configuration"]]
            if a.get("tables"):
                rows.append(["Tables used", ", ".join(sorted(a["tables"]))])
            rows += mods(d) + [["How it is known", how(d)]]
            dbs.append({"title": d["technology"], "sub": (a.get("role") or d.get("kind")) + (" · embedded" if d.get("embedded") or a.get("embedded") else ""), "rows": rows, "ev": item_ev(d)})
    if dbs:
        cats.append({"id": "db", "title": "Databases and storage", "icon": "database", "items": dbs, "extra": panel(rt, ["db_timeouts"])[0]})
    caches = [{"title": d["technology"], "sub": d.get("kind"), "rows": mods(d) + [["How it is known", how(d)]], "ev": item_ev(d)} for d in xdeps if d.get("kind") == "Cache and data grid"]
    if caches:
        cats.append({"id": "cache", "title": "Caches", "icon": "layers", "items": caches, "extra": []})
    msgs = [{"title": d["technology"], "sub": "message broker", "rows": mods(d) + [["How it is known", how(d)]], "ev": item_ev(d)} for d in xdeps if d.get("kind") == "Messaging"]
    for verb, lane in (("Consumes", "in"), ("Publishes to", "msg")):
        tops = sorted({e["target"] for e in app_edges if e["lane"] == lane and e["nodeType"] == "Topic"})
        if tops:
            msgs.append({"title": verb, "sub": "%d topic%s" % (len(tops), "" if len(tops) == 1 else "s"), "rows": [["Topics", ", ".join(tops)]], "ev": [x for e in app_edges if e["target"] in tops for x in e["ev"]][:8]})
    me = panel(rt, ["messaging_errors"])[0]
    if msgs:
        cats.append({"id": "msg", "title": "Messaging", "icon": "route", "items": msgs, "extra": me})
    calls = [e for e in app_edges if e["relType"] == "CALLS_API"]
    api = []
    if hc or calls:
        known = sorted({e["target"] for e in calls if e["resolved"]})
        unknown = sorted({e["target"] for e in calls if not e["resolved"]})
        rows = [["Calls", "%d client%s" % (len(calls), "" if len(calls) == 1 else "s")]] if calls else []
        if known:
            rows.append(["Services called", ", ".join(known)])
        if unknown:
            rows.append(["Address not known", "%d (set per profile: %s)" % (len(unknown), ", ".join(unknown))])
        api.append({"title": ", ".join(x.get("technology", "") for x in hc) or "HTTP clients", "sub": "HTTP client", "rows": rows,
                    "hidden": {"label": "client interface", "list": sorted({e["via"] for e in calls if e["via"]})}, "ev": [x for e in calls for x in e["ev"]][:8]})
    hosts = {}
    for d in xdeps:
        if d.get("kind") == "Services it calls":
            for h in d.get("hosts") or []:
                hosts.setdefault(h, []).append(d)
    for h, ds in sorted(hosts.items()):
        if any(h == e["target"] for e in calls):
            continue
        api.append({"title": h, "sub": "service named in the configuration", "rows": [["How it is known", how(ds[0])]], "ev": [x for d in ds for x in at_ev(d.get("at"))][:8]})
    if api:
        cats.append({"id": "api", "title": "API clients and services called", "icon": "external", "items": api, "extra": panel(rt, ["http_timeouts", "retries_breakers"])[0]})
    obs = [{"title": d["technology"], "sub": "monitoring", "rows": [["How it is known", how(d)]], "ev": item_ev(d)} for d in xdeps if d.get("kind") == "Observability"]
    if obs:
        cats.append({"id": "obs", "title": "Monitoring", "icon": "spark", "items": obs, "extra": panel(rt, ["metrics_export"])[0]})
    return {"sections": sec, "tests": {"types": types, "coverage": cov, "toolGroups": tool_groups, "frameworks": fact(ts, "frameworks").get("value") or [], "frameworksEv": evs(fact(ts, "frameworks").get("evidence"))}, "deps": cats}



# ---------------------------------------------------------------- model layer (llm-fill.json), validated before use
VOCAB = {"yes", "no", "found", "not set", "not found", "not recognised", "unknown", "set", "default"}


def model_layer(app, disc, asis, roots, fill):
    """fields: every value must appear in the engine's sentence (or be a VOCAB word); gaps: the cited line is re-read
    from the repository and must contain `expect`; summary: every cite must be a real fact id, 'api' or a kept gap."""
    f = (fill or {}).get(app) or {}
    out = {"fields": {}, "gaps": [], "summary": [], "dropped": []}
    rows = {}
    for s in asis["sections"]:
        for r in s["rows"]:
            rows["%s|%s" % (s["id"], r[0])] = r[1]
    for c in asis["deps"]:
        for r in c["extra"]:
            rows["%s|%s" % (c["id"], r[0])] = r[1]
    for key, fields in (f.get("fields") or {}).items():
        sent = rows.get(key)
        if sent is None:
            out["dropped"].append("field %s: no such row" % key); continue
        bad = [v for v in fields.values() if v.lower() not in sent.lower() and v.lower() not in VOCAB]
        if bad:
            out["dropped"].append("field %s: %s not in the sentence" % (key, bad)); continue
        out["fields"][key] = fields
    root = roots.get(app)
    gmap = {}
    for i, g in enumerate(f.get("gaps") or []):
        line = None
        if root:
            fp = os.path.realpath(os.path.join(root, g["path"]))
            if fp.startswith(os.path.realpath(root) + os.sep) and os.path.isfile(fp):
                with open(fp, errors="replace") as fh:
                    for n, l in enumerate(fh, 1):
                        if n == g["line"]:
                            line = l.rstrip("\n"); break
        if line is None or g["expect"] not in line or any(str(g[k]) not in line for k in g.get("from_line") or []) \
                or any(str(g[k]) not in g["path"] for k in g.get("from_path") or []):
            out["dropped"].append("gap %s: line not confirmed" % g.get("name")); continue
        gmap[i] = len(out["gaps"])
        item = {k: v for k, v in g.items() if k not in ("path", "line", "expect", "from_line", "from_path")}
        item["ev"] = [{"path": g["path"], "line": g["line"], "snippet": snip(line.strip())}]
        out["gaps"].append(item)
    for label, value, cites in f.get("summary") or []:
        ok = True
        for c in cites:
            if c == "api":
                continue
            if c.startswith("gap:"):
                ok &= int(c[4:]) in gmap; continue
            sec, _, key = c.partition(".")
            ok &= isinstance(disc.get(sec), dict) and key in disc[sec]
        if ok:
            out["summary"].append([label, value, cites])
        else:
            out["dropped"].append("summary %s: a cite is not a fact" % label)
    return out
rel = load("portfolio", "relationships.json")
NODES = {n["id"]: n for n in rel["nodes"]}
apps_dirs = sorted(d for d in os.listdir(A) if os.path.isdir(os.path.join(A, d)) and d != "portfolio")

aspect_defs, pending, apps, edges = None, {}, [], []
ROOTS = {os.path.basename(p.rstrip("/")): p for p in json.load(open(os.path.join(RUN, "run.json"))).get("inputs") or []}
FILL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm-fill.json")
FILL = json.load(open(FILL_PATH)) if os.path.exists(FILL_PATH) else {}
for app in apps_dirs:
    asp, disc = load(app, "aspects.json"), load(app, "discovery.json")
    if aspect_defs is None:
        aspect_defs = [{"id": x["id"], "title": x["title"], "question": x.get("question") or "", "cap": CAPS.get(x["id"], "operate")}
                       for x in asp["aspects"]]
    controls = []
    for x in asp["aspects"]:
        for c in x["controls"]:
            if c.get("pending"):
                pending.setdefault(c["id"], {"id": c["id"], "title": c["title"], "aspect": x["id"]})
                continue
            controls.append({"id": c["id"], "title": c["title"], "aspect": x["id"], "state": c["state"],
                             "severity": (c.get("severity") or "").upper() or None, "summary": c.get("summary") or "",
                             "evidence": evs(c.get("evidence")), "searched": searched(c.get("searched")),
                             "remedies": [{"title": r.get("title"), "does": r.get("does")} for r in (c.get("remedies") or [])],
                             "fix": c.get("fix") or "", "reference": bool(c.get("reference"))})
    st, idn, ci = disc["stack"], disc["identity"], disc["build_ci"]
    fw = fact(st, "app_framework").get("value") or {}
    fw_label = (fw.get("label") + (" " + fw["version"] if fw.get("version") else "")) if isinstance(fw, dict) and fw.get("label") else "not found"
    jv, kv = fact(st, "java_version").get("value"), fact(st, "kotlin_version").get("value")
    lang = " + ".join(x for x in [("Java " + str(jv)) if jv else "", ("Kotlin " + str(kv)) if kv else ""] if x) or str(fact(st, "language").get("value") or "not found")
    build = str(fact(st, "build_tool").get("value") or "not found").capitalize()
    mods = fact(st, "module_list").get("value") or []
    me = "app:" + app
    # endpoints, grouped by the controller or resource that declares them
    eps = [n for n in rel["nodes"] if n["type"] == "ApiEndpoint" and n.get("app") == app]
    groups = {}
    for n in eps:
        a = n.get("attrs") or {}
        g = groups.setdefault(a.get("controller") or "Other endpoints", {"name": a.get("controller") or "Other endpoints", "framework": a.get("framework"), "endpoints": []})
        g["endpoints"].append({"method": a.get("method"), "path": a.get("path"), "ev": evs(n.get("evidence"))})
    # modules and the module -> module dependencies
    mod_nodes = [n for n in rel["nodes"] if n["type"] == "Module" and n.get("app") == app]
    mod_links = []
    for e in rel["edges"]:
        if e["type"] == "DEPENDS_ON" and e["source"].startswith("module:" + app + ":") and e["target"].startswith("module:" + app + ":"):
            mod_links.append({"from": e["source"].split(":", 2)[2], "to": e["target"].split(":", 2)[2], "ev": evs(e.get("evidence"))})
    # outgoing app-level edges (not CONTAINS / EXPOSES_API); module of origin from the evidence path
    mpaths = sorted([n["attrs"].get("path") for n in mod_nodes if (n.get("attrs") or {}).get("path") not in (None, ".")], key=len, reverse=True)
    for e in rel["edges"]:
        if e["source"] != me and e["target"] != me:
            continue
        if e["type"] in ("CONTAINS", "EXPOSES_API"):
            continue
        out = e["source"] == me
        other = e["target"] if out else e["source"]
        n = NODES.get(other) or {"type": "ExternalSystem", "name": other, "attrs": {}}
        na, ea = n.get("attrs") or {}, e.get("attrs") or {}
        ev = evs(e.get("evidence"))
        origin = next((p for p in mpaths if ev and ev[0]["path"].startswith(p + "/")), ".")
        unresolved = (e.get("resolution") or {}).get("state") in ("unresolved", "ambiguous") or other.startswith("unresolved:")
        if e["type"] == "CONSUMES_FROM":
            lane, label = "in", n["name"]
        elif unresolved:
            lane, label = "unres", (re.search(r"target=([^)]+)", n.get("name", "")) or [None, n.get("name")])[1]
        elif n["type"] in ("Database", "Cache"):
            lane, label = "data", n["name"]
        elif n["type"] in ("MessageBroker", "Topic"):
            lane, label = "msg", n["name"]
        elif n["type"] == "Application":
            lane, label = "apps", n["name"]
        elif na.get("role") == "Observability":
            lane, label = "obs", n["name"]
        else:
            lane, label = "ext", n["name"]
        verb = {"CALLS_API": "calls", "READS_FROM": "reads", "WRITES_TO": "writes", "PUBLISHES_TO": "publishes",
                "CONSUMES_FROM": "consumes", "DEPENDS_ON": "uses"}.get(e["type"], e["type"].lower())
        edges.append({"id": len(edges), "eid": e["id"], "source": app if out else other, "target": label if out else app,
                      "targetId": other, "out": out, "type": verb, "relType": e["type"], "lane": lane, "nodeType": n["type"],
                      "via": ea.get("client_interface") or "", "reason": na.get("reason") or "",
                      "status": e.get("status"), "resolved": not unresolved, "module": origin,
                      "evidence": cite(ev[0]) if ev else "", "ev": ev,
                      "tech": na.get("technology") or na.get("broker_family") or "", "embedded": bool(na.get("embedded"))})
    consumes = sorted({e["target"] for e in edges if e["source"] == app and e["lane"] == "in"})
    entries = (["HTTP API"] if eps else []) + (["Message consumer"] if consumes else [])
    kind = " + ".join(entries) or "No entry point found"
    rt, rs, ts = disc.get("runtime"), disc.get("resilience"), disc.get("tests")
    panels = {"runtime": panel(rt, ["health", "http_timeouts", "db_timeouts", "retries_breakers", "graceful_shutdown", "metrics_export", "structured_logging", "messaging_errors", "service_urls"]),
              "deploy": panel(rs, ["deploy_descriptors", "container_image", "multiple_instances", "rolling_or_zero_downtime_strategy", "health_probes", "health_endpoint", "rollback"]),
              "tests": panel(ts, ["unit_tests", "integration_tests", "contract_tests", "acceptance_tests", "performance_tests", "frameworks", "coverage_tool_configured", "coverage_scope", "coverage_state", "coverage_threshold_pct", "coverage_measured", "ci_test_execution", "ci_skip_flags"]),
              "delivery": panel(ci, ["build_step", "publish_step", "deploy_step", "manual_deploy_documented", "release_plugin_tags", "version_from_git_tag", "artifact_tag_from_commit", "stages"])}
    sn_path = os.path.join(A, app, "safetynet.json")
    sn = json.load(open(sn_path)) if os.path.exists(sn_path) else {"components": [], "repository_level": {}}
    tested = [{"kind": c.get("kind"), "label": (c.get("label") or "").strip(), "cls": c.get("classification"), "strength": c.get("strength"),
               "how": [m.get("how") for m in c.get("mapping") or [] if m.get("how")][:3], "assert": any(m.get("assertion_in_test") for m in c.get("mapping") or []),
               "ev": evs([m.get("evidence") for m in c.get("mapping") or []]), "explanation": c.get("explanation") or ""} for c in sn["components"]]
    repo_level = {k: {"state": (v or {}).get("state"), "note": (v or {}).get("note") or "", "ev": evs((v or {}).get("evidence"))} for k, v in (sn.get("repository_level") or {}).items()}
    deps = []
    for d in fact(st, "external_dependencies").get("value") or []:
        deps.append({"group": d.get("group"), "kind": d.get("kind"), "technology": d.get("technology"), "modules": d.get("modules") or [],
                     "strength": d.get("evidence_strength"), "basis": d.get("basis") or [], "embedded": bool(d.get("embedded")),
                     "hosts": d.get("hosts") or [], "at": (d.get("at") or [])[:6], "where": d.get("where")})
    nd = fact(st, "notable_dependencies")
    facts = [factrow("Purpose (README)", fact(idn, "about")),
             factrow("Owners", fact(idn, "owners")),
             factrow("Repository", fact(idn, "repository_url")),
             factrow("Commit", fact(idn, "git_head")),
             factrow("Language", fact(st, "java_version"), lang),
             factrow("Framework", fact(st, "app_framework"), fw_label if fw_label != "not found" else None),
             factrow("Build tool", fact(st, "build_tool"), build),
             factrow("Kind", fact(st, "artifact_kind")),
             factrow("Packaging", fact(st, "packaging")),
             factrow("Container image", fact(st, "container")),
             factrow("CI system", fact(ci, "ci_system")),
             factrow("CI files", fact(ci, "ci_files")),
             factrow("Modules", fact(idn, "modules"), ", ".join(m.get("name", "") for m in mods) or None),
             factrow("Read elsewhere", fact(disc["scope"], "blind_spots"))]
    cont = fact(st, "container").get("value")
    if isinstance(cont, dict):
        bits = (["base image " + ", ".join(cont["base_images"])] if cont.get("base_images") else []) + \
               (["Dockerfile " + ", ".join(cont["dockerfiles"])] if cont.get("dockerfiles") else []) + \
               (["compose " + ", ".join(cont["compose_files"])] if cont.get("compose_files") else [])
        facts[9][1] = "; ".join(bits)[:200] if bits else "no image build found"
    asis = build_asis(app, disc, [e for e in edges if e["source"] == app], facts)
    model = model_layer(app, disc, asis, ROOTS, FILL)
    for d_ in model["dropped"]:
        print("model layer, dropped:", app, d_)
    apps.append({"id": app, "name": app, "asis": asis, "model": model, "javaVersion": str(jv) if jv else None, "kotlinVersion": str(kv) if kv else None,
                 "fwFamily": fw.get("label") if isinstance(fw, dict) else None, "fwVersion": fw.get("version") if isinstance(fw, dict) else None,
                 "platforms": [p for p in json.load(open(os.path.join(A, app, "resilience.json"))).get("platforms") or []], "language": lang, "framework": fw_label, "build": build, "kind": kind,
                 "team": None, "criticality": None, "controls": controls, "facts": facts,
                 "factsAt": {"language": facts[4][2][:1], "framework": facts[5][2][:1], "build": facts[6][2][:1]},
                 "modules": [{"name": n["name"], "path": (n.get("attrs") or {}).get("path") or ".", "role": (n.get("attrs") or {}).get("role")} for n in mod_nodes],
                 "moduleLinks": mod_links, "api": list(groups.values()), "apiCount": len(eps),
                 "deps": deps, "libs": nd.get("value") or [], "libsEv": evs(nd.get("evidence"))[:4],
                 "ciSystem": fact(ci, "ci_system").get("value") or [], "entries": entries, "consumes": consumes,
                 "panels": panels, "tested": tested, "testedRepo": repo_level, "testedLimits": sn.get("limitations") or []})

meta = json.load(open(os.path.join(RUN, "run.json")))
data = {"capDefs": CAPDEFS, "aspectDefs": aspect_defs, "apps": apps, "edges": edges,
        "pendingControls": sorted(pending.values(), key=lambda x: x["id"]),
        "runMeta": {"id": os.path.basename(RUN.rstrip("/")), "generated": meta.get("finished_at") or meta.get("started_at") or "",
                    "verify": json.load(open(os.path.join(RUN, "verify.json"))).get("checked"), "verifyOk": json.load(open(os.path.join(RUN, "verify.json"))).get("ok"),
                    "verifyProblems": len(json.load(open(os.path.join(RUN, "verify.json"))).get("problems") or []),
                    "catalogue": load(apps_dirs[0], "aspects.json").get("catalogue") or {}}}
data = _ev.redact_tree(data)
blob = json.dumps(data, sort_keys=True).replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
head = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data-demo.js")).read().split("\n")[1:4]   # ICONS, icon, esc
with open(OUT, "w") as f:
    f.write("// Generated from a real app-insight run by real_data.py. Read only; evidence redacted.\n")
    f.write("\n".join(head) + "\n")
    f.write("const DATA=" + blob + ";\n")
    f.write("const {capDefs,aspectDefs,apps,edges,pendingControls,runMeta}=DATA;\n")
print("wrote", OUT, os.path.getsize(OUT), "bytes;", len(apps), "apps,", len(edges), "edges,", len(pending), "pending")
