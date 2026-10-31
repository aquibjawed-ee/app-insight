"""Assessment dimensions, kept separate on purpose: no combined score. Each dimension says what it is based on, and a state that
distinguishes `assessed`, `partial`, `not_assessed` (nothing looked), `unknown` (looked, cannot tell) and `not_applicable`."""
from __future__ import annotations

import json
import os
import re
from typing import Dict, Optional

LIFECYCLE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "rules", "lifecycle.v1.json")
CONTRACT = "dimensions.v1"
ORDER = ["engineering_maturity", "security_exposure", "technology_lifecycle", "operational_resilience", "safety_net_strength", "architecture_coupling",
         "change_complexity", "business_criticality", "evidence_completeness"]
TITLES = {"engineering_maturity": "Engineering maturity", "security_exposure": "Security exposure", "technology_lifecycle": "Technology lifecycle",
          "operational_resilience": "Operational resilience", "safety_net_strength": "Safety net", "architecture_coupling": "Architecture coupling",
          "change_complexity": "Change complexity", "business_criticality": "Business criticality", "evidence_completeness": "Evidence completeness"}


def load_lifecycle(path: str = LIFECYCLE_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _d(state, headline, level="info", rule=None, based_on=None, values=None, note=None):
    out = {"state": state, "headline": headline, "level": level, "rule": rule, "based_on": based_on or [], "values": values or {}}
    if note:
        out["note"] = note
    return out


def _fv(disc, path):
    sec, _, key = path.partition(".")
    return (disc.get(sec) or {}).get(key) or {}


def _ym(s):
    y, m = s.split("-")
    return int(y) * 12 + int(m)


def lifecycle(disc, ref, as_of):
    j = _fv(disc, "stack.java_version")
    b = _fv(disc, "stack.spring_boot_version")
    vals, level, heads = {}, "info", []
    now = _ym(as_of[:7])
    jv = re.match(r"\s*(?:1\.)?(\d+)", str(j.get("value"))) if j.get("value") else None
    if jv:
        v = jv.group(1)
        row = ref["java"]["lts"].get(v)
        if row:
            st = "premier_support" if now <= _ym(row["premier_until"]) else "extended_support_only" if now <= _ym(row["extended_until"]) else "out_of_support"
            vals["java"] = {"version": v, "status": st, "premier_until": row["premier_until"], "extended_until": row["extended_until"], "source": ref["java"]["source"],
                            "note": "Oracle roadmap; other distributions publish their own windows", "evidence": j.get("evidence", [])[:1]}
            heads.append("Java %s: %s" % (v, st.replace("_", " ")))
            level = {"out_of_support": "concern", "extended_support_only": "attention"}.get(st, level)
        else:
            vals["java"] = {"version": v, "status": "non_lts_or_unlisted", "note": ref["java"]["non_lts_note"], "evidence": j.get("evidence", [])[:1]}
            heads.append("Java %s: not an LTS release listed in the reference data" % v)
    else:
        vals["java"] = {"version": None, "status": "unknown", "note": "no explicit Java version in build files"}
    sm = re.match(r"\s*(\d+)", str(b.get("value"))) if b.get("value") else None
    if sm:
        row = ref["spring_boot"]["majors"].get(sm.group(1))
        if row:
            vals["spring_boot"] = {"version": b["value"], "oss_status": row["oss_status"], "note": row["note"], "source": ref["spring_boot"]["source"], "evidence": b.get("evidence", [])[:1]}
            heads.append("Spring Boot %s: open-source support %s" % (b["value"], row["oss_status"]))
            if row["oss_status"] == "ended":
                level = "concern"
    elif b.get("status") == "NOT_FOUND":
        vals["spring_boot"] = {"version": None, "status": "not_applicable_or_not_found"}
    known = [k for k in ("java", "spring_boot") if vals.get(k, {}).get("version")]
    vals = {k: v for k, v in vals.items() if v.get("status") != "not_applicable_or_not_found"}  # no Spring Boot is not a gap in the assessment
    if not known:
        return _d("unknown", "No runtime or framework version could be read", "info", "versions are read from build files only", ["stack.java_version", "stack.spring_boot_version"], vals)
    rv = ref.get("review") or {}
    unrev = rv.get("status") != "reviewed"
    return _d("assessed" if len(known) == len(vals) else "partial", "; ".join(heads), level,
              ("REFERENCE DATA NOT REVIEWED by a maintainer. " if unrev else "") + "level: concern = vendor support ended; attention = only paid/extended support remains. Dates come from rules/lifecycle.v1.json (as of %s)" % ref["as_of"],
              ["stack.java_version", "stack.spring_boot_version"], vals)


def assess(disc: dict, graph: Optional[dict] = None, safetynet: Optional[dict] = None, criticality: Optional[dict] = None, lifecycle_ref: Optional[dict] = None,
           portfolio_graph: Optional[dict] = None, as_of: Optional[str] = None, resilience: Optional[dict] = None) -> dict:
    app = disc["identity"]["app_id"]["value"]
    as_of = (as_of or os.environ.get("DISCOVERY_FIXED_TIME") or "2026-10-29")[:10]
    ref = lifecycle_ref or load_lifecycle()
    out: Dict[str, dict] = {}
    m = disc.get("maturity", {})
    out["engineering_maturity"] = _d("assessed", "%s (%s%%): %d criteria met, %d with no evidence, %d unknown" % (
        m.get("band"), m.get("score"), sum(1 for c in m.get("criteria", []) if c["result"] == "MET"), m.get("no_evidence", 0), m.get("unknown", 0)), "info",
        "computed by maturity.py from engineering-practice facts; says nothing about risk or business value", ["maturity"], {"band": m.get("band"), "score": m.get("score")})
    vs = _fv(disc, "security.vulnerability_scan")
    sec = {k: _fv(disc, "security." + k).get("value") for k in ("sast", "dependency_scanning", "secret_scanning", "dependency_updates")}
    if vs.get("value", {}).get("state") == "scanned":
        v = vs["value"]
        out["security_exposure"] = _d("assessed", "%d known vulnerabilities in scanned dependency manifests (critical %d, high %d)" % (v["total"], v.get("critical", 0), v.get("high", 0)),
                                     "concern" if v.get("critical", 0) else "attention" if v.get("high", 0) else "info", "level: concern = any critical, attention = any high",
                                     ["security.vulnerability_scan"], dict(sec, scan=v), "the vulnerability database changes over time; this is a point-in-time scan")
    elif vs:
        out["security_exposure"] = _d("unknown", "A vulnerability scan was attempted but could not analyse the dependencies", "info", None, ["security.vulnerability_scan"], dict(sec, scan=vs.get("value")))
    else:
        out["security_exposure"] = _d("not_assessed", "No vulnerability scan was run, so exposure is not known. Scanning tools configured: %s" % (
            ", ".join(k.replace("_", " ") for k, v in sec.items() if v) or "none found"), "info", "exposure needs scan.py (opt-in); configured scanners only say what is monitored",
            ["security"], sec)
    out["technology_lifecycle"] = lifecycle(disc, ref, as_of)
    if resilience and resilience.get("state") == "assessed":
        rs = [c for c in resilience["summary"] if c["state"] not in ("not_applicable", "not_assessed")]
        pres = [c["id"] for c in rs if c["state"] == "present"]
        absn = [c["id"] for c in rs if c["state"] == "absent"]
        unk = [c["id"] for c in rs if c["state"] in ("unknown", "default", "partial")]
        core = [c for c in ("replicas", "anti_affinity", "pdb") if c in absn]
        out["operational_resilience"] = _d("partial" if unk else "assessed", "%d of %d HA checks in place; %d absent%s" % (len(pres), len(rs), len(absn), (" (" + ", ".join(x.replace("_", " ") for x in core) + ")") if core else ""),
                                           "attention" if core else "info", "attention = replicas, anti-affinity or a disruption budget is absent from the deployment files read (%s)" % ", ".join(resilience["platforms"]),
                                           ["resilience.v1"], {"present": pres, "absent": absn, "unknown": unk, "platforms": resilience["platforms"], "eks": resilience["eks"]["detected"]},
                                           "absent means not in these files; a platform or GitOps repository may add it")
    elif resilience:
        out["operational_resilience"] = _d("not_assessed", "No Kubernetes, Nomad or Compose workload definition in this repository: HA configuration may live elsewhere", "info", "HA settings are read from deployment descriptors", ["resilience.v1"], {"present": [], "absent": [], "unknown": []})
    else:
        res = {k: _fv(disc, "resilience." + k) for k in ("health_endpoint", "health_probes", "multiple_instances", "rolling_or_zero_downtime_strategy", "rollback", "container_image")}
        present = [k for k, f in res.items() if f.get("status") == "CONFIRMED" and f.get("value")]
        absent = [k for k, f in res.items() if f.get("status") == "NOT_FOUND"]
        unknown = [k for k, f in res.items() if f.get("status") == "UNKNOWN"]
        deploy = _fv(disc, "resilience.deploy_descriptors")
        if deploy.get("status") == "NOT_FOUND" and not present:
            out["operational_resilience"] = _d("not_assessed", "No deployment descriptor in this repository: runtime resilience cannot be read", "info",
                                               "resilience practices are read from deployment files", ["resilience"], {"present": [], "absent": absent, "unknown": unknown})
        else:
            out["operational_resilience"] = _d("partial" if unknown else "assessed", "%d of %d practices found (%s)" % (len(present), len(res), ", ".join(p.replace("_", " ") for p in present) or "none"),
                                               "attention" if not present else "info", "attention = none of the listed practices found in deployment files",
                                               ["resilience"], {"present": present, "absent": absent, "unknown": unknown}, "absent means not found in the files read; it may be configured elsewhere")
    if safetynet:
        s = safetynet["summary"]
        tot = sum(sum(v.values()) for v in s.values())
        direct = sum(v.get("direct", v["mapped_with_assertions"] + v["mapped_no_assertion_seen"]) for v in s.values())
        cls = sum(v.get("class_level", 0) for v in s.values())
        mapped = direct + cls
        asrt = sum(v["mapped_with_assertions"] for v in s.values())
        r = safetynet["repository_level"]
        out["safety_net_strength"] = _d("partial" if tot else "not_applicable",
                                       "%d of %d discovered components are mapped to a test by route or reference (%d with an assertion nearby), %d more only by a test that mentions the controller class; %d are unverified (no mapping found, not 'untested')" % (direct, tot, asrt, cls, tot - mapped)
                                       if tot else "No endpoints, consumers, publishers, database paths or downstream calls were discovered", "attention" if tot and mapped == 0 else "info",
                                       "attention = components exist and none could be mapped to a test", ["tests", "relationships"],
                                       {"by_kind": s, "tests_exist": r["test_exists"]["state"], "runs_in_ci": r["runs_automatically"]["state"], "passes": r["passes"]["state"],
                                        "coverage_measured": r["coverage_measured"]["state"], "coverage_threshold_enforced": r["coverage_threshold_enforced"]["state"]},
                                       "mapping is by static reference; no test was executed")
    else:
        out["safety_net_strength"] = _d("not_assessed", "Safety-net mapping was not run", "info", None, ["tests"])
    g = portfolio_graph or graph
    if g:
        me = "app:" + app
        nodes = {n["id"]: n for n in g["nodes"]}
        out_apps, out_ext, in_apps, unresolved, dbs_shared, topics = set(), set(), set(), 0, 0, set()
        for e in g["edges"]:
            if e["source"] == me:
                t = e["target"]
                tn = nodes[t]
                if e["resolution"].get("state") in ("unresolved", "ambiguous"):
                    unresolved += 1
                if e["type"] == "CALLS_API":
                    owner = ("app:" + tn["app"]) if tn.get("app") and tn["type"] == "ApiEndpoint" else t if tn["type"] == "Application" else None
                    (out_apps.add(owner) if owner else out_ext.add(t) if tn["type"] == "ExternalSystem" and not tn["attrs"].get("unresolved") else None)
                elif e["type"] in ("PUBLISHES_TO", "CONSUMES_FROM") and e["resolution"].get("state") == "resolved":
                    topics.add(t)
            if e["type"] == "CALLS_API" and e["source"] != me and ((nodes[e["target"]].get("app") == app) or e["target"] == me):
                in_apps.add(e["source"])
        for t in topics:
            in_apps |= {x["source"] for x in g["edges"] if x["target"] == t and x["type"] == "CONSUMES_FROM" and x["source"] != me}
        for d in {e["target"] for e in g["edges"] if e["source"] == me and e["target"].startswith("db:")}:
            if len({x["source"] for x in g["edges"] if x["target"] == d and x["source"].startswith("app:")}) > 1:
                dbs_shared += 1
        portfolio = g["scope"] == "portfolio"
        vals = {"depends_on_applications": len(out_apps), "depends_on_external_systems": len(out_ext), "topics_used": len(topics), "shared_databases": dbs_shared,
                "unresolved_or_ambiguous_relationships": unresolved, "relied_on_by": (len(in_apps) if portfolio else None)}
        out["architecture_coupling"] = _d("assessed" if portfolio else "partial",
                                          "Depends on %d application(s), %d external system(s); %d topic(s) used, %d shared database(s)%s; %d relationship(s) unresolved" % (
                                              len(out_apps), len(out_ext), len(topics), dbs_shared, ("; relied on by %d" % len(in_apps)) if portfolio else "", unresolved),
                                          "info", "counts of relationships in the graph; not a score", ["relationships"], vals,
                                          None if portfolio else "single-application graph: who depends on this application is unknown until it is analysed with the others")
        integ = len({e["target"] for e in g["edges"] if e["source"] == me and e["type"] in ("CALLS_API", "PUBLISHES_TO", "CONSUMES_FROM", "READS_FROM", "WRITES_TO", "DEPENDS_ON") and not e["target"].startswith("module:")})
        mods = len([n for n in g["nodes"] if n["type"] == "Module" and n.get("app") == app])
        out["change_complexity"] = _d("partial", "%d module(s), %d distinct integration target(s), %d Java and %d Kotlin source file(s)" % (
                                          mods, integ, _fv(disc, "stack.java_sources").get("value") or 0, _fv(disc, "stack.kotlin_sources").get("value") or 0),
                                      "info", "descriptive indicators only; effort for a specific change comes from the impact analysis, not from a general score", ["relationships", "stack"],
                                      {"modules": mods, "integration_targets": integ})
        edges = [e for e in g["edges"] if e["source"] == me]
        by = {"CONFIRMED": 0, "INFERRED": 0, "UNKNOWN": 0}
        for e in edges:
            by[e["status"]] = by.get(e["status"], 0) + 1
    else:
        out["architecture_coupling"] = _d("not_assessed", "Relationships were not extracted", "info")
        out["change_complexity"] = _d("not_assessed", "Relationships were not extracted", "info")
        by = {}
    c = (criticality or {}).get(app)
    out["business_criticality"] = _d("assessed", "%s (source: %s)" % (c["tier"], c["source"]), "info", "taken from the supplied input file as given", ["criticality input"], c) if c else \
        _d("unknown", "Unknown: no verified business-criticality input was supplied. Technical findings are not used to infer it.", "info", "never inferred from technology", [])
    facts = [f for sec in ("stack", "build_ci", "tests", "api", "resilience", "security") for f in (disc.get(sec) or {}).values() if isinstance(f, dict) and "status" in f]
    fs = {k: sum(1 for f in facts if f["status"] == k) for k in ("CONFIRMED", "INFERRED", "NOT_FOUND", "UNKNOWN")}
    out["evidence_completeness"] = _d("assessed", "%d facts confirmed, %d inferred, %d not found, %d unknown; relationships: %s" % (
        fs["CONFIRMED"], fs["INFERRED"], fs["NOT_FOUND"], fs["UNKNOWN"], ", ".join("%d %s" % (v, k.lower()) for k, v in by.items()) or "not extracted"), "info",
        "counts only; the static scan executed nothing", ["run_meta"], {"facts": fs, "relationships": by, "static_analysis_only": True,
                                                                         "not_run": [k for k, v in disc.get("run_meta", {}).get("completeness", {}).items() if v == "not_run"]})
    return {"contract": CONTRACT, "application": app, "as_of": as_of, "dimensions": {k: dict(out[k], title=TITLES[k]) for k in ORDER},
            "statement": "These dimensions are reported separately on purpose. There is no overall score: a weak dimension is a reason to investigate, not a recommendation to migrate."}
