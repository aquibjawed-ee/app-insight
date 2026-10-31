"""Deterministic change-impact analysis: versioned compatibility rules + graph traversal + safety-net lookup.

Output (impact.v1) keeps apart: confirmed incompatibilities (a literal match in the repository, rule cited), potential behavioural risks,
affected components, potential downstream impact (graph reachability: potential, not proof of breakage), required verification, and
unknowns. Nothing here runs a build, test or model.
"""
from __future__ import annotations

import json
import os
import re
from collections import deque
from typing import Dict, List, Optional

import evidence
from detectors import Ctx
from detectors import integrations as I
from graph import contracts
from graph.adapters.common import Config, ev, mask_comments
from graph.model import norm_path

CONTRACT = "impact.v1"
ENGINE_VERSION = "0.1.0"
RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "rules", "compat.v1.json")
SCENARIOS = ("java_runtime", "spring_boot", "dependency_major", "db_migration", "messaging_schema", "api_contract", "infrastructure")


def load_rules(path: str = RULES_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _major(v) -> Optional[int]:
    if v is None:
        return None
    m = re.match(r"\s*(?:1\.)?(\d+)", str(v))
    return int(m.group(1)) if m else None


def _spring_major(v) -> Optional[int]:
    m = re.match(r"\s*(\d+)", str(v or ""))
    return int(m.group(1)) if m else None


class AppView:
    """Read-only view of one application repository for rule evaluation."""

    def __init__(self, app: str, repo: str, disc: dict):
        self.app, self.repo, self.disc = app, repo, disc
        self.ctx = Ctx(repo)
        self._src = None
        self._coords = None

    def source_lines(self):
        if self._src is None:
            self._src = []
            for f in self.ctx.src_main_java:
                lines = evidence.read_lines(self.repo, f) or []
                self._src.append((f, lines, mask_comments(lines)))
        return self._src

    def coords(self) -> set:
        if self._coords is None:
            c = set()
            cats = I.catalogs(self.ctx)
            for pom in self.ctx.poms:
                c |= {x[0] for x in I.maven_deps(self.ctx, pom)}
            for g in self.ctx.gradle:
                c |= {x[0] for x in I.gradle_deps(self.ctx, g, cats)}
            self._coords = c
        return self._coords

    def grep_source(self, rx, limit=6):
        out, n = [], 0
        for f, lines, masked in self.source_lines():
            for i, ln in enumerate(masked, 1):
                if rx.search(ln):
                    n += 1
                    if len(out) < limit:
                        out.append(ev(f, i, lines, self.app))
        return out, n

    def grep_files(self, files_rx, rx, limit=6):
        out, n = [], 0
        for f in self.ctx.files:
            if re.search(files_rx, f) and not self.ctx._aux(f):
                lines = evidence.read_lines(self.repo, f) or []
                for i, ln in enumerate(lines, 1):
                    if not ln.strip().startswith(("#", "//")) and rx.search(ln):
                        n += 1
                        if len(out) < limit:
                            out.append(ev(f, i, lines, self.app))
        return out, n

    def config_keys(self, rx, limit=6):
        out, n = [], 0
        cfg = Config(self.ctx, self.app)
        for k in sorted(cfg.values):
            if rx.search(k):
                for v, e in cfg.all_values(k):
                    n += 1
                    if len(out) < limit:
                        out.append(e)
        return out, n, cfg


def _applies(rule: dict, sc: dict) -> bool:
    a = rule.get("applies") or {}
    fr, to = sc.get("from"), sc.get("to")
    if "from_lt" in a and not (fr is not None and fr < a["from_lt"]):
        return False
    if "to_gte" in a and not (to is not None and to >= a["to_gte"]):
        return False
    if "from_major" in a and sc.get("from") != a["from_major"]:
        return False
    if "to_major_gte" in a and not (to is not None and to >= a["to_major_gte"]):
        return False
    return True


def eval_rule(rule: dict, view: AppView, sc: dict, graph: dict) -> Optional[dict]:
    d = rule.get("detect") or {}
    t = d.get("type")
    hits, n = [], 0
    if t is None:
        return {"rule": rule, "evidence": [], "count": 0, "informational": True}
    if t == "source_regex":
        hits, n = view.grep_source(re.compile(d["pattern"]))
    elif t == "file_regex":
        hits, n = view.grep_files(d["files"], re.compile(d["pattern"]))
    elif t == "file_exists":
        for f in view.ctx.files:
            if re.search(d["files"], f) and not view.ctx._aux(f):
                n += 1
                if len(hits) < 6:
                    lines = evidence.read_lines(view.repo, f) or [""]
                    hits.append(ev(f, 1, lines, view.app))
    elif t == "config_key":
        hits, n, _ = view.config_keys(re.compile(d["pattern"]))
    elif t == "config_key_value":
        hits, n, cfg = view.config_keys(re.compile(d["pattern"]))
        if sc.get("from_tech"):  # only dialect settings that name the source database
            want = sc["from_tech"].lower().replace(" ", "")
            hits = [h for h in hits if want in h["snippet"].lower().replace(" ", "") or want[:5] in h["snippet"].lower()]
            n = len(hits)
    elif t == "discovery_java_lt":
        j = view.disc.get("stack", {}).get("java_version", {})
        v = _major(j.get("value"))
        if v is not None and v < d["value"]:
            hits, n = j.get("evidence", [])[:2], 1
            hits = [dict(h, app=view.app) for h in hits]
    elif t == "dependency_present":
        found = [c for c in d["coords"] if c in view.coords()]
        if found:
            n = len(found)
            for pom in view.ctx.poms + view.ctx.gradle:
                lines = evidence.read_lines(view.repo, pom) or []
                for i, ln in enumerate(lines, 1):
                    if any(c.split(":")[1] in ln for c in found) and len(hits) < 4:
                        hits.append(ev(pom, i, lines, view.app))
    elif t == "graph_exposes_api":
        eps = [n_ for n_ in graph["nodes"] if n_["type"] == "ApiEndpoint" and n_.get("app") == view.app]
        n = len(eps)
        hits = [e for n_ in eps[:3] for e in n_["evidence"][:1]]
    if not n:
        return None
    if rule.get("unless_dependency") and any(c in view.coords() for c in rule["unless_dependency"]):
        return None  # a replacement library is declared: the removal does not break this application
    return {"rule": rule, "evidence": hits, "count": n}


# ---- graph traversal ----------------------------------------------------------------------------------------------------

def blast_radius(graph: dict, seeds: List[str], max_hops: int = 3) -> List[dict]:
    """Components that could be affected by a change in the seed nodes, by following who relies on whom:
       caller -> callee (CALLS_API resolved onto the seed's app/endpoints), subscriber <- publisher (CONSUMES_FROM a topic the seed
       PUBLISHES_TO), and applications that read/write the same database. Each hop is an edge that exists in the graph; a path through an
       ambiguous or inferred edge says so. Reachability is potential impact, never proof of breakage."""
    nodes = {n["id"]: n for n in graph["nodes"]}
    edges = graph["edges"]
    app_of = lambda nid: nid if nodes[nid]["type"] == "Application" else ("app:" + nodes[nid]["app"] if nodes[nid].get("app") and nodes[nid]["type"] in ("ApiEndpoint", "Module") else None)
    out_pub = {}
    for e in edges:
        if e["type"] == "PUBLISHES_TO":
            out_pub.setdefault(e["target"], []).append(e)
    consumers = {}
    for e in edges:
        if e["type"] == "CONSUMES_FROM":
            consumers.setdefault(e["target"], []).append(e)
    callers = {}
    for e in edges:
        if e["type"] == "CALLS_API" and e["resolution"].get("state") == "resolved":
            tgt = e["target"]
            callers.setdefault(tgt, []).append(e)
            a = app_of(tgt)
            if a and a != tgt:
                callers.setdefault(a, []).append(e)
    dbs = {}
    for e in edges:
        if e["type"] in ("READS_FROM", "WRITES_TO", "DEPENDS_ON") and e["target"].startswith("db:") and nodes[e["target"]]["attrs"].get("identity") == "connection" and e["resolution"].get("state") == "resolved":
            dbs.setdefault(e["target"], []).append(e)
    mod_deps = {}
    for e in edges:
        if e["type"] == "DEPENDS_ON" and e["source"].startswith("module:") and e["target"].startswith("module:"):
            mod_deps.setdefault(e["target"], []).append(e)
    seen = {s: None for s in seeds}
    q = deque((s, 0, []) for s in seeds)
    found = []
    while q:
        cur, hops, path = q.popleft()
        if hops >= max_hops:
            continue
        nxt = []
        a = cur if nodes[cur]["type"] == "Application" else app_of(cur)
        # everything the application exposes is the thing callers rely on
        scope = [cur] + ([a] if a and a != cur else [])
        if a:
            scope += [e["target"] for e in edges if e["type"] == "EXPOSES_API" and e["source"] == a]
            for t, pubs in out_pub.items():
                for p in pubs:
                    if p["source"] == a:
                        for c in consumers.get(t, []):
                            if c["source"] != a:
                                nxt.append((c["source"], [p, c], "consumes %s published by %s" % (nodes[t]["name"], a[4:])))
            for dbid, es in dbs.items():
                if any(x["source"] == a for x in es):
                    for x in es:
                        if x["source"] != a:
                            nxt.append((x["source"], [[y for y in es if y["source"] == a][0], x], "shares database %s" % nodes[dbid]["name"]))
        for s in scope:
            for c in callers.get(s, []):
                if c["source"] != a:
                    nxt.append((c["source"], [c], "calls %s" % (nodes[c["target"]]["name"] if c["target"] in nodes else c["target"])))
        if nodes[cur]["type"] == "Module":
            for e in mod_deps.get(cur, []):
                nxt.append((e["source"], [e], "module depends on %s" % nodes[cur]["name"]))
        for tgt, es, why in nxt:
            if tgt in seen:
                continue
            seen[tgt] = cur
            reduced = any(x["basis"] in ("inferred", "declared") or x["resolution"].get("strength") == "medium" or x["confidence"] == "low" for x in es)
            step = {"component": tgt, "type": nodes[tgt]["type"], "name": nodes[tgt]["name"], "hops": hops + 1, "via": path + [x["id"] for x in es],
                    "because": why, "path_confidence": "reduced" if reduced else "as_discovered",
                    "note": "potential impact: a relationship exists; whether the change breaks it is not established"}
            found.append(step)
            q.append((tgt, hops + 1, path + [x["id"] for x in es]))
    return sorted(found, key=lambda s: (s["hops"], s["component"]))


def adjacent_unknowns(graph: dict, apps: List[str]) -> List[dict]:
    out = []
    nodes = {n["id"]: n for n in graph["nodes"]}
    for e in graph["edges"]:
        if e["resolution"].get("state") in ("unresolved", "ambiguous") and e["source"] in ["app:" + a for a in apps]:
            out.append({"what": "%s %s %s" % (e["type"], e["source"][4:], nodes[e["target"]]["name"]),
                        "why": "%s: %s" % (e["resolution"]["state"], e["resolution"].get("reasoning") or e["resolution"].get("reason", "")), "edge": e["id"],
                        "evidence": e["evidence"][:1]})
    return out


def _safety(safetynets: Dict[str, dict], edge_or_node_id: str):
    for a, s in safetynets.items():
        for c in s["components"]:
            if c["component_id"] == edge_or_node_id or edge_or_node_id in c.get("edges", []):
                return {"app": a, "component": c["label"], "classification": c["classification"], "explanation": c["explanation"]}
    return None


# ---- scenarios -----------------------------------------------------------------------------------------------------------

def assess(scenario: dict, graph: dict, views: Dict[str, AppView], safetynets: Optional[Dict[str, dict]] = None, rules: Optional[dict] = None) -> dict:
    rules = rules or load_rules()
    safetynets = safetynets or {}
    typ = scenario["type"]
    if typ not in SCENARIOS:
        raise ValueError("unknown scenario %r (known: %s)" % (typ, ", ".join(SCENARIOS)))
    sc = dict(scenario)
    confirmed, potential, info, affected, unknowns, verify, notes = [], [], [], [], [], [], []
    target_apps = sorted(scenario.get("apps") or views.keys())
    nodes = {n["id"]: n for n in graph["nodes"]}
    seeds: List[str] = []

    def add_finding(app, r):
        rule = r["rule"]
        f = {"rule_id": rule["id"], "app": app, "message": rule["message"], "evidence": r["evidence"], "occurrences": r["count"],
             "remediation": rule.get("remediation"), "reference": rule.get("reference")}
        (confirmed if rule["severity"] == "confirmed" else potential if rule["severity"] == "potential" else info).append(f)

    if typ in ("java_runtime", "spring_boot"):
        for app in target_apps:
            v = views[app]
            if typ == "java_runtime":
                fr = sc.get("from") or _major(v.disc["stack"]["java_version"]["value"])
                this = dict(sc, **{"from": fr})
                if fr is None:
                    unknowns.append({"what": "%s: current Java baseline" % app, "why": "no explicit Java version in build files, so version-dependent rules cannot be applied (rules without a lower bound still run)"})
            else:
                fr = _spring_major(v.disc["stack"].get("spring_boot_version", {}).get("value"))
                this = dict(sc, **{"from": fr, "to": _spring_major(sc["to"])})
                if fr is None:
                    unknowns.append({"what": "%s: current Spring Boot version" % app, "why": "no resolvable Spring Boot version in build files"})
                    continue
                # Boot rules need the Java baseline as an input to compare
            for rule in rules["rules"]:
                if rule["scenario"] != typ or not _applies(rule, this):
                    continue
                if typ == "java_runtime" and this.get("from") is None and "from_lt" in (rule.get("applies") or {}):
                    continue
                r = eval_rule(rule, v, this, graph)
                if r:
                    add_finding(app, r)
            if typ == "java_runtime" and v.disc["stack"].get("kotlin_version", {}).get("value"):
                potential.append({"rule_id": "java.kotlin-compat-unchecked", "app": app, "message": "Kotlin %s is declared; compatibility of the Kotlin compiler/runtime with the target JDK is not checked by a rule." %
                                  v.disc["stack"]["kotlin_version"]["value"], "evidence": v.disc["stack"]["kotlin_version"].get("evidence", [])[:1], "occurrences": 1,
                                  "remediation": "Check the Kotlin release notes for the target JDK.", "reference": None})
            seeds.append("app:" + app)
            affected.append({"component": "app:" + app, "type": "Application", "why": "the %s change applies to this application's build/runtime" % typ})
    elif typ == "dependency_major":
        coord, to = scenario["coordinate"], scenario.get("to")
        for app in target_apps:
            v = views[app]
            if coord in v.coords():
                lines = []
                for f in v.ctx.build_files:
                    ls = evidence.read_lines(v.repo, f) or []
                    for i, ln in enumerate(ls, 1):
                        if coord.split(":")[1] in ln and len(lines) < 3:
                            lines.append(ev(f, i, ls, app))
                affected.append({"component": "app:" + app, "type": "Application", "why": "declares %s" % coord, "evidence": lines})
                seeds.append("app:" + app)
                potential.append({"rule_id": "dep.major-version", "app": app, "message": "A major version of %s changes its public API; which of this application's call sites break cannot be determined without the library's release notes or a compile." % coord,
                                  "evidence": lines, "occurrences": 1, "remediation": "Compile against the target version; check for an OpenRewrite recipe for this library.", "reference": None})
        for rel in rules.get("coordinate_relocations", []):
            if rel["from"] == coord:
                confirmed.append({"rule_id": "dep.relocated", "app": ", ".join(a["component"][4:] for a in affected) or "-", "message": "%s is published as %s in newer versions (%s)." % (coord, rel["to"], rel["note"]),
                                  "evidence": affected[0]["evidence"] if affected else [], "occurrences": 1, "remediation": "Change the coordinate and the imports.", "reference": None})
        if not affected:
            unknowns.append({"what": "usage of %s" % coord, "why": "no analysed application declares this coordinate (declarations through unresolved ${property} coordinates are not seen)"})
    elif typ == "db_migration":
        ft = scenario["from_tech"]
        db_nodes = [n for n in graph["nodes"] if n["type"] == "Database" and n["attrs"].get("technology") == ft]
        for n in db_nodes:
            affected.append({"component": n["id"], "type": "Database", "why": "database of the source technology"})
            seeds.append(n["id"])
        apps_using = sorted({e["source"][4:] for e in graph["edges"] if e["target"] in {n["id"] for n in db_nodes} and e["source"].startswith("app:")})
        for app in apps_using:
            sc2 = dict(sc)
            for rule in rules["rules"]:
                if rule["scenario"] == "db_migration":
                    r = eval_rule(rule, views[app], sc2, graph) if app in views else None
                    if r:
                        add_finding(app, r)
            affected.append({"component": "app:" + app, "type": "Application", "why": "reads/writes or depends on a %s database" % ft})
        for n in db_nodes:
            users = sorted({e["source"] for e in graph["edges"] if e["target"] == n["id"] and e["source"].startswith("app:")})
            if len(users) > 1:
                potential.append({"rule_id": "db.shared-database", "app": ", ".join(u[4:] for u in users), "message": "%s is used by %d applications (same host/database in their connection settings): all of them are affected by the migration together." % (n["name"], len(users)),
                                  "evidence": [x for e in graph["edges"] if e["target"] == n["id"] for x in e["evidence"][:1]][:4], "occurrences": len(users), "remediation": "Plan the migration as one change across these applications.", "reference": None})
        seeds = [s for s in seeds]
        unknowns += [{"what": "databases of type %s with application-local identity" % ft, "why": "no literal host/database: sharing with other applications cannot be established", "edge": None}
                     for n in graph["nodes"] if n["type"] == "Database" and n["attrs"].get("technology") == ft and n["attrs"].get("identity") != "connection"]
        if not db_nodes:
            unknowns.append({"what": "%s databases" % ft, "why": "none found in the analysed applications"})
    elif typ == "messaging_schema":
        topic = scenario["topic"]
        tnodes = [n for n in graph["nodes"] if n["type"] == "Topic" and (n["id"] == topic or n["name"] == topic or n["id"].startswith(topic + "@") or n["id"].endswith(":" + topic) or (":" + topic + "@") in n["id"])]
        if len({n["id"] for n in tnodes}) > 1:
            unknowns.append({"what": "which %s" % topic, "why": "the name matches %d distinct topics (different broker clusters: %s); all are analysed - pass the full node id to select one" % (
                len(tnodes), "; ".join(sorted(n["id"] for n in tnodes)))})
        if not tnodes:
            unknowns.append({"what": "topic %s" % topic, "why": "no resolved publisher or consumer of this topic in the graph"})
        for tn in tnodes:
            pubs = [e for e in graph["edges"] if e["target"] == tn["id"] and e["type"] == "PUBLISHES_TO"]
            cons = [e for e in graph["edges"] if e["target"] == tn["id"] and e["type"] == "CONSUMES_FROM"]
            affected.append({"component": tn["id"], "type": "Topic", "why": "topic whose message schema changes", "publishers": sorted(e["source"] for e in pubs), "consumers": sorted(e["source"] for e in cons)})
            for e in pubs + cons:
                affected.append({"component": e["source"], "type": "Application", "why": "%s the topic" % ("publishes to" if e["type"] == "PUBLISHES_TO" else "consumes from"), "via": [e["id"]]})
            seeds += [e["source"] for e in pubs]
            if not cons:
                unknowns.append({"what": "consumers of %s" % tn["name"], "why": "no consumer found in the analysed applications; consumers in other repositories are not visible"})
            hints = tn["attrs"].get("cluster_verified")
            if hints is False and len(pubs + cons) > 1:
                unknowns.append({"what": "whether %s is one topic" % tn["name"], "why": "publishers/consumers matched on name only: broker address not stated for every application"})
            for e in cons:
                s = _safety(safetynets, e["id"])
                verify.append({"what": "consumer %s handles the new schema" % e["source"][4:], "component": e["id"], "safety_net": s})
        unres = [e for e in graph["edges"] if e["type"] in ("PUBLISHES_TO", "CONSUMES_FROM") and e["resolution"]["state"] == "unresolved"]
        for e in unres:
            unknowns.append({"what": "unresolved %s by %s" % (e["type"].lower().replace("_", " "), e["source"][4:]), "why": "destination not known; it could be this topic: " + e["resolution"].get("reason", ""), "edge": e["id"]})
        if scenario.get("old_schema") and scenario.get("new_schema"):
            old, new = contracts.load_spec(scenario["old_schema"]), contracts.load_spec(scenario["new_schema"])
            if old is None or new is None:
                unknowns.append({"what": "schema comparison", "why": "schema file(s) could not be parsed (JSON Avro schemas only)"})
            else:
                for d in contracts.diff_avro(old, new):
                    (confirmed if d["breaking"] else info).append({"rule_id": "schema.avro." + d["change"], "app": "-", "message": d["detail"], "evidence": [], "occurrences": 1,
                                                                    "remediation": "Add a default or version the topic.", "reference": "Avro schema resolution"})
        else:
            unknowns.append({"what": "schema compatibility", "why": "no old/new schema files were supplied: only who is connected to the topic is known"})
    elif typ == "api_contract":
        changes: List[dict] = []
        if scenario.get("old_spec") and scenario.get("new_spec"):
            o, n = contracts.load_spec(scenario["old_spec"]), contracts.load_spec(scenario["new_spec"])
            if o is None or n is None:
                unknowns.append({"what": "OpenAPI comparison", "why": "specification could not be parsed (JSON, or YAML when PyYAML is installed)"})
            else:
                changes = [c for c in contracts.diff_openapi(o, n) if c["breaking"]]
                for c in changes:
                    confirmed.append({"rule_id": "api.contract." + c["change"], "app": scenario.get("app", "-"), "message": "%s: %s" % (c["endpoint"], c["detail"]), "evidence": [], "occurrences": 1,
                                      "remediation": "Version the endpoint or keep the old behaviour until callers move.", "reference": "OpenAPI diff of the supplied specifications"})
        if scenario.get("endpoint"):
            changes.append({"endpoint": scenario["endpoint"], "change": scenario.get("change", "changed")})
        for c in changes:
            ep = c["endpoint"]
            verb, _, path = ep.partition(" ")
            app = scenario.get("app")
            cands = [n for n in graph["nodes"] if n["type"] == "ApiEndpoint" and (app is None or n.get("app") == app)
                     and n["attrs"]["method"] == verb.upper() and n["attrs"]["path_shape"] == norm_path(path)]
            if len(cands) != 1:
                unknowns.append({"what": "endpoint %s" % ep, "why": "%d matching endpoints in the graph (give --app to disambiguate)" % len(cands) if cands else "not found in the graph"})
                continue
            node = cands[0]
            affected.append({"component": node["id"], "type": "ApiEndpoint", "why": "endpoint whose contract changes (%s)" % c.get("change")})
            seeds.append(node["id"])
            callers = [e for e in graph["edges"] if e["type"] == "CALLS_API" and e["target"] == node["id"]]
            for e in callers:
                affected.append({"component": e["source"], "type": "Application", "why": "calls %s (resolved by %s)" % (ep, e["resolution"].get("reasoning", "")), "via": [e["id"]]})
                verify.append({"what": "caller %s still works against the changed contract" % e["source"][4:], "component": e["id"], "safety_net": _safety(safetynets, e["id"])})
            for e in graph["edges"]:  # unresolved calls with the same verb+path could be to this endpoint
                if e["type"] == "CALLS_API" and e["resolution"].get("state") in ("unresolved", "ambiguous") and e["attrs"].get("method") == verb.upper() and e["attrs"].get("path_shape") == node["attrs"]["path_shape"]:
                    unknowns.append({"what": "%s %s %s" % (e["source"][4:], e["attrs"]["method"], e["attrs"]["path"]), "why": "same method and path as the changed endpoint but the target service is %s: it may be this one" % e["resolution"]["state"], "edge": e["id"]})
    elif typ == "infrastructure":
        plat = scenario["platform"]
        infra = [n for n in graph["nodes"] if n["type"] == "InfrastructureResource" and n["attrs"].get("platform") == plat]
        for n in infra:
            affected.append({"component": n["id"], "type": "InfrastructureResource", "why": "runtime platform changing"})
            for e in graph["edges"]:
                if e["type"] == "DEPLOYED_ON" and e["target"] == n["id"]:
                    affected.append({"component": e["source"], "type": "Application", "why": "deployed on %s" % plat, "via": [e["id"]]})
                    seeds.append(e["source"])
        if plat == "Kubernetes" and scenario.get("to"):
            to_v = tuple(int(x) for x in re.findall(r"\d+", str(scenario["to"]))[:2])
            for app, v in sorted(views.items()):
                if "app:" + app not in seeds:
                    continue
                for ra in rules.get("k8s_removed_apis", []):
                    rem = tuple(int(x) for x in ra["removed_in"].split("."))
                    if to_v >= rem:
                        for f in v.ctx.deploy_files:
                            lines = evidence.read_lines(v.repo, f) or []
                            doc_api = None
                            for i, ln in enumerate(lines, 1):
                                m = re.match(r"^apiVersion:\s*(\S+)", ln)
                                if m:
                                    doc_api, line = m.group(1), i
                                k = re.match(r"^kind:\s*(\w+)", ln)
                                if k and doc_api == ra["apiVersion"] and k.group(1) in ra["kinds"]:
                                    confirmed.append({"rule_id": ra["id"], "app": app, "message": "%s %s uses %s, removed in Kubernetes %s." % (k.group(1), f, ra["apiVersion"], ra["removed_in"]),
                                                      "evidence": [ev(f, line, lines, app)], "occurrences": 1, "remediation": "Use %s." % ra["use"], "reference": "Kubernetes deprecated API migration guide"})
        if not infra:
            unknowns.append({"what": "applications on %s" % plat, "why": "no deployment descriptor naming this platform was found"})
        unknowns.append({"what": "workloads defined outside the analysed repositories", "why": "Helm values, GitOps repositories and cluster state are not visible"})
    # downstream impact and unknowns shared by all scenarios
    downstream = blast_radius(graph, sorted(set(seeds)))
    apps_in_play = sorted({a["component"][4:] for a in affected if a["component"].startswith("app:")} | {d["component"][4:] for d in downstream if d["component"].startswith("app:")})
    unknowns += adjacent_unknowns(graph, [a["component"][4:] for a in affected if a["component"].startswith("app:")])
    for d in downstream:
        verify.append({"what": "%s %s (%s)" % (d["type"].lower(), d["name"], d["because"]), "component": d["component"],
                       "safety_net": next((s for s in [_safety(safetynets, e) for e in d["via"][::-1]] if s), None)})
    for a in [x for x in affected if x["component"].startswith("app:") and x["component"][4:] in safetynets]:
        sn = safetynets[a["component"][4:]]
        un = [c["label"] for c in sn["components"] if c["classification"] == "unverified"]
        if un:
            verify.append({"what": "%d component(s) of %s have no mapped test: %s" % (len(un), a["component"][4:], "; ".join(un[:5]) + ("; ..." if len(un) > 5 else "")),
                           "component": a["component"], "safety_net": {"classification": "unverified", "explanation": "mapping could not be established; this is not evidence that no test exists"}})
    for a in affected:
        if a["component"].startswith("app:") and a["component"][4:] not in safetynets:
            unknowns.append({"what": "safety net of %s" % a["component"][4:], "why": "no safety-net analysis was supplied"})
    out = {"contract": CONTRACT, "engine_version": ENGINE_VERSION, "rules_version": rules["version"], "rules_reviewed_as_of": rules["reviewed_as_of"], "rules_review": rules.get("review") or {"status": "unreviewed"},
           "scenario": {k: v for k, v in scenario.items()}, "graph_scope": graph["scope"],
           "confirmed_incompatibilities": confirmed, "potential_risks": potential, "informational": info, "affected_components": _dedupe(affected),
           "downstream_impact": downstream, "required_verification": _dedupe(verify, "what"), "unknowns": _dedupe(unknowns, "what"),
           "statement": ("Confirmed incompatibilities are literal matches of a cited rule in cited files. Downstream impact is graph reachability: a relationship "
                         "means a change may matter there, not that it breaks. Unresolved and ambiguous relationships are listed as unknowns, never assumed."),
           "applications_in_scope": apps_in_play}
    return out


def _dedupe(items, key="component"):
    seen, out = set(), []
    for i in items:
        k = (i.get(key), i.get("why") or i.get("what"))
        if k not in seen:
            seen.add(k)
            out.append(i)
    return out
