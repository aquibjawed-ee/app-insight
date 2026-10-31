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
GAP_STATES = ("ISSUE", "ABSENT", "PARTIAL")
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
# criteria whose MET result means the pipeline runs the control, not only that it is configured
ENFORCED = {"automated_build", "tests_run_in_ci", "version_tagging", "automated_deploy", "rollback", "coverage", "secret_scanning", "dependency_scanning", "sast"}
CRITERION_STATE = {"MET": "PRESENT", "PARTIAL": "PARTIAL", "NO_EVIDENCE": "ABSENT", "NOT_MET": "ISSUE", "UNKNOWN": "UNKNOWN"}
HA_STATE = {"present": "PRESENT", "partial": "PARTIAL", "absent": "ABSENT", "unknown": "UNKNOWN", "default": "UNKNOWN", "not_applicable": "NOT_APPLICABLE", "not_assessed": "NOT_ASSESSED"}


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
            "outbound_http": "CALLS_API" in types or bool(_fact(disc, "stack.http_client_libraries").get("value")),
            "messaging": bool({"PUBLISHES_TO", "CONSUMES_FROM"} & types) or "Messaging" in kinds,
            "database": bool({"READS_FROM", "WRITES_TO"} & types) or any(d.get("kind") == "Database" and not d.get("embedded") for d in self.deps),
            "http_endpoints": _endpoints(disc) or any(n["type"] == "ApiEndpoint" and n.get("app") == app for n in portfolio["nodes"]),
        }
        self.criteria = {c["id"]: c for c in (disc.get("maturity") or {}).get("criteria", [])}
        self.ha = {c["id"]: c for c in (res or {}).get("summary", [])}


def _endpoints(disc):
    f = _fact(disc, "api.http_endpoints_present")
    v = f.get("value")
    return f.get("status") == "CONFIRMED" and (v.get("controller_files", 0) > 0 if isinstance(v, dict) else bool(v))


def _a(kind):
    return ("an " if kind[:1] in "aeiou" else "a ") + kind + (" application" if kind == "unknown" else "")


NEED_TEXT = {"spring_boot": "no Spring Boot found", "outbound_http": "no outbound HTTP calls or HTTP client found", "messaging": "no messaging found",
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
    ev, notes = [], []
    for p in facts:
        f = _fact(cx.disc, p)
        ev += _ev(f.get("evidence"), f.get("status"))
        if f.get("note") and not f["note"].startswith("derived from"):
            notes.append(f["note"])
    level = ("enforced" if cid in ENFORCED else "configured") if st in ("PRESENT", "PARTIAL") else None
    head = {"PRESENT": "Found", "PARTIAL": "Partly in place", "ABSENT": "Not found in the files read", "ISSUE": "Switched off or disabled", "UNKNOWN": "Cannot be decided from the files"}[st]
    return _r(st, head + (": " + notes[0] if notes else ""), level, ev, facts)


def eval_ha(hid, cx):
    if not cx.res or cx.res.get("state") != "assessed":
        return _r("NOT_ASSESSED", (cx.res or {}).get("reason") or "no deployment files read")
    c = cx.ha.get(hid)
    if not c:
        return _r("NOT_ASSESSED", "check not run")
    st = HA_STATE.get(c["state"], "UNKNOWN")
    note = (c.get("notes") or [None])[0]
    return _r(st, note or c.get("why") or c["state"], "configured" if st in ("PRESENT", "PARTIAL") else None, _ev(c.get("evidence")), ["resilience." + hid])


def eval_lifecycle(which, cx):
    d = (cx.dims or {}).get("dimensions", {}).get("technology_lifecycle") or {}
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
    if v.get("oss_status") == "ended":
        return _r("ISSUE", "Spring Boot %s: open-source support ended" % v["version"], "configured", ev, ["stack.spring_boot_version"])
    return _r("PRESENT", "Spring Boot %s: open-source support %s" % (v["version"], v.get("oss_status")), "configured", ev, ["stack.spring_boot_version"])


def eval_fact(path, cx):
    f = _fact(cx.disc, path)
    st, val = f.get("status"), f.get("value")
    ev = _ev(f.get("evidence"), st)
    if st in ("CONFIRMED", "INFERRED") and val not in (None, False, [], "", {}):
        shown = val if isinstance(val, str) else ", ".join(map(str, val)) if isinstance(val, list) else "found"
        return _r("PRESENT", str(shown)[:160], "configured" if st == "CONFIRMED" else "declared", ev, [path])
    if st == "UNKNOWN":
        return _r("UNKNOWN", f.get("note") or "cannot be decided from the files", facts=[path])
    return _r("ABSENT", f.get("note") or "not found in the files read", None, ev, [path])


def eval_dependency(spec, cx):
    rx = re.compile(spec["match"], re.I)
    hits = [d for d in cx.deps if d.get("kind") == spec["kind"] and rx.search(d.get("technology") or "")]
    allev = _fact(cx.disc, "stack.external_dependencies").get("evidence") or []
    if not hits:
        return _r("ABSENT", "no %s dependency found" % spec["kind"].lower(), facts=["stack.external_dependencies"])
    at = {a for d in hits for a in d.get("at") or []}
    ev = [dict(e, status="CONFIRMED") for e in allev if "%s:%s" % (e.get("path"), e.get("line_start")) in at]
    strong = any(d.get("evidence_strength") == "configured" for d in hits)
    return _r("PRESENT", ", ".join(sorted({d["technology"] for d in hits})) + ("" if strong else " (dependency declared; no configuration found)"),
              "configured" if strong else "declared", ev, ["stack.external_dependencies"])


def eval_safetynet(cx):
    s = (cx.sn or {}).get("summary") or {}
    tot = sum(v["mapped_with_assertions"] + v["mapped_no_assertion_seen"] + v["unverified"] for v in s.values())
    mapped = sum(v["direct"] if v.get("direct") is not None else v["mapped_with_assertions"] + v["mapped_no_assertion_seen"] for v in s.values())
    if not tot:
        return _r("NOT_APPLICABLE", "no endpoints, consumers, publishers or data paths were discovered")
    st = "PRESENT" if mapped == tot else "PARTIAL" if mapped else "ABSENT"
    return _r(st, "%d of %d discovered components have a test mapped by route, listener or data path (unverified is not untested)" % (mapped, tot), "configured" if mapped else None, facts=["safetynet.summary"])


def eval_security_scan(cx):
    d = (cx.dims or {}).get("dimensions", {}).get("security_exposure") or {}
    if d.get("state") == "assessed":
        st = {"concern": "ISSUE", "attention": "PARTIAL"}.get(d.get("level"), "PRESENT")
        return _r(st, d.get("headline") or "scanned", "verified" if st == "PRESENT" else None, facts=d.get("based_on") or [])
    return _r("ABSENT", d.get("headline") or "no vulnerability scan was run", facts=d.get("based_on") or [])


def eval_graph(which, cx):
    E = cx.edges
    if which == "unmatched_calls":
        if not E:
            return _r("NOT_APPLICABLE", "no outbound calls, messages or data access found")
        bad = [e for e in E if e["resolution"]["state"] in ("unresolved", "ambiguous")]
        ev = [dict(x, status="INFERRED") for e in bad[:6] for x in (e.get("evidence") or [])[:1]]
        return _r("PARTIAL" if bad else "PRESENT", "%d of %d relationships not matched to a known application" % (len(bad), len(E)) if bad else "all %d relationships matched" % len(E),
                  "configured", ev, ["relationships"])
    if which == "shared_database":
        mine = {e["target"] for e in E if e["type"] in ("READS_FROM", "WRITES_TO")}
        shared = []
        for t in mine:
            n = cx.nodes.get(t) or {}
            if n.get("type") == "Database" and (n.get("attrs") or {}).get("identity") == "connection":
                others = sorted({e["source"][4:] for e in cx.portfolio["edges"] if e["target"] == t and e["source"].startswith("app:") and e["source"] != "app:" + cx.app})
                if others:
                    shared.append("%s (also %s)" % (n.get("name"), ", ".join(others[:3])))
        return _r("ISSUE" if shared else "PRESENT", "shares " + "; ".join(shared) if shared else "no database shared with another analysed application", "configured", [], ["relationships"])
    if which == "profile_differences":
        n = sum(1 for e in E if re.search(r"differs between profiles", (e.get("resolution") or {}).get("reason") or ""))
        return _r("PARTIAL" if n else "PRESENT", "%d connection target(s) differ between profiles" % n if n else "no target differs between profiles", "configured", [], ["relationships"])
    if which == "unresolved_placeholders":
        n = sum(1 for e in E if (e.get("attrs") or {}).get("how") == "placeholder" and e["resolution"]["state"] == "unresolved")
        return _r("PARTIAL" if n else "PRESENT", "%d target(s) held in a placeholder that could not be resolved" % n if n else "every placeholder resolved", "configured", [], ["relationships"])
    return _r("NOT_ASSESSED", "unknown graph check " + which)


def evaluate(ctl, cx):
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
        return eval_fact(s["fact"], cx)
    if "dependency" in s:
        return eval_dependency(s["dependency"], cx)
    if "safetynet" in s:
        return eval_safetynet(cx)
    if "security_scan" in s:
        return eval_security_scan(cx)
    if "graph" in s:
        return eval_graph(s["graph"], cx)
    return _r("NOT_ASSESSED", "No detector yet: " + s.get("pending", "not built"))


def remedies_for(ctl, packs):
    for p in packs:
        keys = (p.get("controls") or {}).get(ctl["id"]) or (p.get("aspects") or {}).get(ctl["aspect"])
        if keys:
            return [dict(p["remedies"][k], key=k, pack=p["id"]) for k in keys if k in p["remedies"]]
    return []


def rollup(controls):
    app_ = [c for c in controls if c["state"] != "NOT_APPLICABLE"]
    counts = {}
    for c in controls:
        counts[c["state"]] = counts.get(c["state"], 0) + 1
    assessed = [c for c in app_ if c["state"] not in ("NOT_ASSESSED", "UNKNOWN")]
    if not app_:
        status = "not_applicable"
    elif not assessed:
        status = "not_assessed"
    elif any(c["state"] == "ISSUE" or (c["state"] in ("ABSENT", "PARTIAL") and c["severity"] == "high") for c in assessed):
        status = "issues"
    elif any(c["state"] in ("ABSENT", "PARTIAL") for c in assessed):
        status = "gaps"
    else:
        status = "in_place"
    present = sum(1 for c in assessed if c["state"] == "PRESENT")
    return status, counts, {"applicable": len(app_), "assessed": len(assessed), "present": present}


def build_app(app, disc, rel, res, sn, dims, portfolio, catalogue, packs, generated_at=None):
    cx = Context(app, disc, rel, res, sn, dims, portfolio)
    by_aspect = {a["id"]: [] for a in catalogue["aspects"]}
    findings = []
    for ctl in catalogue["controls"]:
        r = evaluate(ctl, cx)
        sev = r.pop("severity") or ctl.get("severity", "medium")
        c = {"id": ctl["id"], "aspect": ctl["aspect"], "title": ctl["title"], "state": r["state"], "level": r["level"], "summary": r["summary"],
             "severity": sev if r["state"] in GAP_STATES else None, "facts": r["facts"], "evidence": r["evidence"], "fix": ctl.get("fix"),
             "remedies": remedies_for(ctl, packs) if r["state"] in GAP_STATES else [], "finding": None}
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
            json.dump(doc, fh, indent=1, sort_keys=True)
        docs[app] = doc
    summary = {"contract": "aspects-portfolio.v1", "generated_at": man.get("generated_at"), "catalogue": catalogue["version"], "remedy_packs": [p["id"] for p in packs],
               "aspects": [{"id": a["id"], "title": a["title"]} for a in sorted(catalogue["aspects"], key=lambda x: x["order"])],
               "applications": {app: {a["id"]: a["status"] for a in doc["aspects"]} for app, doc in sorted(docs.items())}}
    os.makedirs(os.path.join(out, "portfolio"), exist_ok=True)
    with open(os.path.join(out, "portfolio", "aspects.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1, sort_keys=True)
    return docs
