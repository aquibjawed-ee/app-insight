"""Cross-repository entity resolution: merge per-application graphs into one portfolio graph.

Rules are exact and explained; nothing is matched on similarity.
  service name -> application   only an exact (case-insensitive) match on a declared identity key; strong keys
                                (spring.application.name, Kubernetes Service name) resolve; medium keys (artifactId, Deployment/chart
                                name) resolve with lower strength; a repository name alone never resolves; two applications sharing
                                a key make the match ambiguous and the edge keeps its candidates.
  call path -> endpoint         the callee's exposed endpoints are searched by method and path shape (callee context path applied);
                                no match is reported as a potential contract mismatch, not hidden.
  topic / queue                 identity is broker family + name; applications whose cluster addresses are all different do NOT share it.
  database                      identity is the literal host/port/database of the connection setting.
Every decision is written to meta.resolution_log with its reasoning and the evidence it used.
"""
from __future__ import annotations

import copy
import re
from collections import defaultdict
from typing import Dict, List

from graph import model
from graph.model import norm_path

RESOLVER_VERSION = "0.2.0"


def merge(docs: List[dict]) -> dict:
    nodes: Dict[str, dict] = {}
    edges: Dict[str, dict] = {}
    skipped, apps, limitations = [], [], []
    for d in sorted(docs, key=lambda d: d["meta"]["application"]):
        apps.append(d["meta"]["application"])
        limitations = d["meta"].get("limitations", limitations)
        for n in d["nodes"]:
            n = copy.deepcopy(n)
            cur = nodes.get(n["id"])
            if cur is None:
                nodes[n["id"]] = n
                continue
            for k, v in n["attrs"].items():
                if k == "cluster_hints":
                    cur["attrs"][k] = sorted(set(cur["attrs"].get(k, [])) | set(v))
                else:
                    cur["attrs"].setdefault(k, v)
            for e in n["evidence"]:
                if e not in cur["evidence"] and len(cur["evidence"]) < 8:
                    cur["evidence"].append(e)
        for e in d["edges"]:
            edges.setdefault(e["id"], copy.deepcopy(e))
        skipped += [dict(s, app=d["meta"]["application"]) for s in d["not_relationships"]]
    return {"contract": model.CONTRACT, "scope": "portfolio", "nodes": nodes, "edges": edges, "skipped": skipped, "apps": apps, "limitations": limitations}


def _app_of_edge(e):
    return e["source"].split(":", 1)[1] if e["source"].startswith("app:") else None


def resolve(docs: List[dict], aliases: Dict[str, str] = None) -> dict:
    m = merge(docs)
    nodes, edges, log = m["nodes"], m["edges"], []
    apps = {nid: n for nid, n in nodes.items() if n["type"] == "Application"}
    index: Dict[str, List[tuple]] = defaultdict(list)  # lowercased identity value -> [(app node id, key)]
    for nid, n in apps.items():
        for k in n["attrs"].get("identity_keys", []):
            index[k["value"].lower()].append((nid, k))

    # 1. service name -> application, then call -> endpoint
    for eid, e in sorted(edges.items()):
        if e["type"] != "CALLS_API" or not e["target"].startswith("svc:") or e["resolution"].get("state") != "unresolved":
            continue
        name = nodes[e["target"]]["name"]
        hits = index.get(name.lower(), [])
        by_app: Dict[str, List[dict]] = defaultdict(list)
        for nid, k in hits:
            if nid != e["source"]:
                by_app[nid].append(k)
        for strength in ("strong", "medium"):
            cand = {nid: [k for k in ks if k["strength"] == strength] for nid, ks in by_app.items()}
            cand = {nid: ks for nid, ks in cand.items() if ks}
            if cand:
                break
        else:
            strength, cand = None, {}
        entry = {"kind": "service-name", "subject": "%s calls %r" % (e["source"], name), "edge": eid}
        if len(cand) == 1:
            tid, ks = next(iter(cand.items()))
            why = "service name %r equals %s of %s (%s identity key)" % (name, " and ".join("%s %r" % (k["kind"], k["value"]) for k in ks), tid, strength)
            e["attrs"]["original_target"] = e["target"]
            e["target"] = tid
            e["resolution"] = {"state": "resolved", "strength": strength, "reasoning": why, "matched_on": [k["kind"] for k in ks],
                               "matched_evidence": [k["evidence"] for k in ks if k["evidence"]][:2]}
            if strength == "medium":
                e["confidence"] = "medium" if e["confidence"] == "high" else e["confidence"]
            entry.update(decision="resolved", reasoning=why)
            _endpoint_match(e, nodes, edges, tid, log)
        elif len(cand) > 1:
            why = "service name %r is an identity key of %d applications (%s): not guessed" % (name, len(cand), ", ".join(sorted(cand)))
            e["resolution"] = {"state": "ambiguous", "reasoning": why, "candidates": sorted(cand), "strength": strength}
            e["basis"] = "unresolved"
            entry.update(decision="ambiguous", reasoning=why, candidates=sorted(cand))
        else:
            weak = sorted(nid for nid, ks in by_app.items() if ks)
            why = ("only the repository name of %s matches %r; a repository name is not an identity, so the call is not attached" % (", ".join(weak), name)
                   if weak else "no analysed application declares an identity (application name, Kubernetes Service, artifactId) equal to %r" % name)
            e["resolution"] = {"state": "unresolved", "reasoning": why, "weak_candidates": weak}
            entry.update(decision="unresolved", reasoning=why, weak_candidates=weak)
        log.append(entry)

    # 1b. hosts that are really an analysed application: an alias supplied by the user, a host the callee declares about itself, or a Kubernetes service DNS name
    hostidx: Dict[str, List[tuple]] = defaultdict(list)
    for nid, n in apps.items():
        for d in n["attrs"].get("declared_hosts", []):
            hostidx[d["host"]].append((nid, d))
    al = {str(k).lower(): str(v) for k, v in (aliases or {}).items()}
    for eid, e in sorted(edges.items()):
        if e["type"] != "CALLS_API" or not e["target"].startswith("ext:") or nodes[e["target"]]["attrs"].get("unresolved"):
            continue
        host = (nodes[e["target"]]["attrs"].get("host") or "").lower()
        target, how = al.get(host), "alias file"
        if target is None and host in hostidx:
            owners = {nid: d for nid, d in hostidx[host] if nid != e["source"]}
            if len(owners) == 1:
                nid, d = next(iter(owners.items()))
                why = "host %s is declared by %s in its own %s" % (host, nid[4:], d["source"])
                e["attrs"]["original_target"] = e["target"]
                e["target"] = nid
                e["resolution"] = {"state": "resolved", "strength": d["strength"], "reasoning": why, "matched_on": [d["source"]], "matched_evidence": [d["evidence"]]}
                log.append({"kind": "host", "subject": "%s calls %s" % (e["source"], host), "edge": eid, "decision": "resolved", "reasoning": why})
                _endpoint_match(e, nodes, edges, nid, log)
                continue
            if len(owners) > 1:
                why = "host %s is declared by %d applications (%s): not guessed" % (host, len(owners), ", ".join(sorted(x[4:] for x in owners)))
                e["resolution"] = {"state": "ambiguous", "reasoning": why, "candidates": sorted(owners)}
                e["basis"] = "unresolved"
                log.append({"kind": "host", "subject": "%s calls %s" % (e["source"], host), "edge": eid, "decision": "ambiguous", "reasoning": why})
                continue
        if target is None:
            dm = re.match(r"^([a-z0-9-]+)\.[a-z0-9-]+\.svc(?:\.cluster\.local)?$", host)
            target, how = (dm.group(1), "Kubernetes service DNS name") if dm else (None, None)
        if target is None:
            continue
        cand = sorted({nid for nid, k in index.get(target.lower(), []) if nid != e["source"] and k["strength"] in ("strong", "medium")})
        if len(cand) == 1:
            why = "host %s is %s for %s (%s)" % (host, "mapped by the alias file to" if how == "alias file" else "the Kubernetes DNS name of", target, how)
            e["attrs"]["original_target"] = e["target"]
            e["target"] = cand[0]
            e["resolution"] = {"state": "resolved", "strength": "alias" if how == "alias file" else "strong", "reasoning": why, "matched_on": [how]}
            log.append({"kind": "host", "subject": "%s calls %s" % (e["source"], host), "edge": eid, "decision": "resolved", "reasoning": why})
            _endpoint_match(e, nodes, edges, cand[0], log)
        elif len(cand) > 1:
            why = "host %s maps to %r, which is an identity of %d applications: not guessed" % (host, target, len(cand))
            e["resolution"] = {"state": "ambiguous", "reasoning": why, "candidates": cand}
            e["basis"] = "unresolved"
            log.append({"kind": "host", "subject": "%s calls %s" % (e["source"], host), "edge": eid, "decision": "ambiguous", "reasoning": why})
        elif how == "alias file":  # an alias to something that is not an analysed application names an external system
            ext = "ext:" + target.lower()
            nodes.setdefault(ext, {"id": ext, "type": "ExternalSystem", "name": target, "app": None, "attrs": {"host": host, "named_by": "alias file"}, "evidence": []})
            e["attrs"]["original_target"] = e["target"]
            e["target"] = ext
            log.append({"kind": "host", "subject": "%s calls %s" % (e["source"], host), "edge": eid, "decision": "named", "reasoning": "host %s is named %r by the alias file; no analysed application has that name" % (host, target)})

    # 2. topics: split by cluster, annotate shared
    users: Dict[str, List[str]] = defaultdict(list)
    for eid, e in edges.items():
        if e["type"] in ("PUBLISHES_TO", "CONSUMES_FROM") and e["target"].startswith("topic:") and e["resolution"].get("state") == "resolved":
            users[e["target"]].append(eid)
    app_hints = {a: set() for a in apps}
    for tid, eids in sorted(users.items()):
        per_app: Dict[str, set] = {}
        for eid in eids:
            a = edges[eid]["source"]
            per_app.setdefault(a, set())
        # cluster hints are node-level in a merged node: recover per-application hints from the per-app source documents
        for d in docs:
            an = "app:" + d["meta"]["application"]
            if an in per_app:
                for n in d["nodes"]:
                    if n["id"] == tid:
                        per_app[an] = set(n["attrs"].get("cluster_hints", []))
        groups: List[tuple] = []  # (hint set, [apps])
        for a, h in sorted(per_app.items()):
            for g in groups:
                if (not h) or (not g[0]) or (h & g[0]):
                    g[0].update(h)
                    g[1].append(a)
                    break
            else:
                groups.append((set(h), [a]))
        if len(groups) > 1:  # clusters differ: these are different topics that happen to share a name
            for hints, members in groups:
                new_id = "%s@%s" % (tid, ",".join(sorted(hints)) or "unspecified")
                nodes[new_id] = copy.deepcopy(nodes[tid])
                nodes[new_id].update(id=new_id)
                nodes[new_id]["attrs"]["cluster_hints"] = sorted(hints)
                for eid in eids:
                    if edges[eid]["source"] in members:
                        edges[eid]["target"] = new_id
                        edges[eid]["attrs"]["original_target"] = tid
                for e2 in edges.values():  # topic -> broker edges belong to the application whose broker they name
                    if e2["source"] == tid and e2["target"].startswith("broker:") and "app:" + e2["target"].split(":")[1] in members:
                        e2["source"] = new_id
            for e2 in edges.values():  # a hosting edge of an application that no longer uses the node (none expected)
                if e2["source"] == tid:
                    e2["source"] = next(iter(n for n in nodes if n.startswith(tid + "@")))
            del nodes[tid]
            log.append({"kind": "topic", "subject": tid, "decision": "not merged",
                        "reasoning": "applications connect to different broker addresses (%s); same name on different clusters is not the same topic" %
                                     "; ".join("%s -> %s" % (", ".join(sorted(m)), ", ".join(sorted(h)) or "none") for h, m in groups)})
            continue
        hints = groups[0][0]
        all_known = all(per_app.values())
        nodes[tid]["attrs"]["cluster_hints"] = sorted(hints)
        nodes[tid]["attrs"]["cluster_verified"] = bool(all_known and len(per_app) > 1 and all(per_app[a] & hints for a in per_app))
        if len(per_app) > 1:
            log.append({"kind": "topic", "subject": tid, "decision": "shared",
                        "reasoning": "same broker family and name used by %s; %s" % (", ".join(sorted(per_app)),
                                     "broker addresses overlap (%s)" % ", ".join(sorted(hints)) if nodes[tid]["attrs"]["cluster_verified"] else
                                     "broker address not stated for every application: matched on name only")})
    # 3. databases shared by literal connection identity
    db_users: Dict[str, set] = defaultdict(set)
    for e in edges.values():
        if e["target"].startswith("db:") and e["source"].startswith("app:") and nodes[e["target"]]["attrs"].get("identity") == "connection":
            db_users[e["target"]].add(e["source"])
    for did, us in sorted(db_users.items()):
        if len(us) > 1:
            c = nodes[did]["attrs"]["connection"]
            log.append({"kind": "database", "subject": did, "decision": "shared",
                        "reasoning": "%s connect to %s at %s:%s database %s (literal connection settings match)" % (
                            ", ".join(sorted(us)), nodes[did]["attrs"]["technology"], c["host"], c["port"], c["database"])})
    # tables per database: who creates a table and who uses it (a table used by several applications couples them)
    for did, n in nodes.items():
        if n["type"] != "Database":
            continue
        tabs: Dict[str, dict] = {}
        for e in edges.values():
            if e["target"] != did or not e["source"].startswith("app:"):
                continue
            who = e["source"][4:]
            for t in e["attrs"].get("tables_owned", []):
                tabs.setdefault(t, {"owned_by": set(), "used_by": set()})["owned_by"].add(who)
            for t in e["attrs"].get("tables", []):
                tabs.setdefault(t, {"owned_by": set(), "used_by": set()})["used_by"].add(who)
        if tabs:
            n["attrs"]["tables"] = {t: {"owned_by": sorted(v["owned_by"]), "used_by": sorted(v["used_by"])} for t, v in sorted(tabs.items())}
            multi = sorted(t for t, v in tabs.items() if len(v["used_by"] | v["owned_by"]) > 1)
            if multi and n["attrs"].get("identity") == "connection":
                log.append({"kind": "tables", "subject": did, "decision": "shared",
                            "reasoning": "tables used by more than one application on %s: %s" % (n["name"], ", ".join(multi[:8]))})
    # drop service placeholders nothing points at any more
    used = {e["target"] for e in edges.values()} | {e["source"] for e in edges.values()}
    for nid in [n for n in nodes if n.startswith("svc:") and n not in used]:
        del nodes[nid]
    doc = {"contract": model.CONTRACT, "scope": "portfolio", "nodes": [nodes[k] for k in sorted(nodes)], "edges": [edges[k] for k in sorted(edges)],
           "not_relationships": sorted(m["skipped"], key=lambda u: (u["app"], u["what"], u["why"])),
           "meta": {"resolver_version": RESOLVER_VERSION, "applications": sorted(m["apps"]), "resolution_log": log, "limitations": m["limitations"],
                    "static_analysis_only": True}}
    return doc


def _endpoint_match(e, nodes, edges, target_app, log):
    """Point a resolved call at the endpoint it names when the callee exposes it; otherwise say what is (not) known."""
    app = target_app.split(":", 1)[1]
    ctx_path = nodes[target_app]["attrs"].get("context_path") or ""
    exposed = [(eid2, nodes[x["target"]]) for eid2, x in edges.items() if x["type"] == "EXPOSES_API" and x["source"] == target_app]
    path, verb = e["attrs"].get("path"), e["attrs"].get("method")
    if path is None:
        e["attrs"]["endpoint_match"] = "not_checked: the call names no path"
        return
    if not exposed:
        e["attrs"]["endpoint_match"] = "unknown: no endpoints were discovered for %s" % app
        return
    if path.endswith(("/**", "/*")):  # a gateway route pattern: a prefix, so check what the callee exposes under it
        pre = norm_path(ctx_path + "/" + re.sub(r"/\*+$", "", path).lstrip("/"))
        under = [n for _, n in exposed if norm_path(ctx_path + "/" + n["attrs"]["path"].lstrip("/")).startswith(pre)]
        e["attrs"]["endpoint_match"] = "found" if under else "not_found"
        e["attrs"]["endpoints_under_route"] = len(under)
        if not under:
            e["attrs"]["endpoint_note"] = "%s exposes no endpoint under the route %s: the route may be stale or the endpoints are not visible to this scan" % (app, path)
            log.append({"kind": "endpoint", "subject": "%s route %s" % (e["source"], path), "decision": "no matching endpoint", "reasoning": e["attrs"]["endpoint_note"]})
        return
    want = norm_path(ctx_path + "/" + path.lstrip("/"))
    hit = [n for _, n in exposed if norm_path(ctx_path + "/" + n["attrs"]["path"].lstrip("/")) == want and (verb in (None, "ANY") or n["attrs"]["method"] in (verb, "ANY"))]
    if len(hit) == 1:
        e["attrs"]["endpoint_match"] = "found"
        e["attrs"]["resolved_endpoint"] = hit[0]["id"]
        e["target"] = hit[0]["id"]
        e["resolution"]["reasoning"] += "; endpoint %s exposed by %s" % (hit[0]["name"], app)
    else:
        e["attrs"]["endpoint_match"] = "not_found"
        e["attrs"]["endpoint_note"] = "%s exposes no endpoint matching %s %s: possible contract mismatch, stale client, or an endpoint this scan cannot see" % (app, verb or "", path)
        log.append({"kind": "endpoint", "subject": "%s %s %s" % (e["source"], verb or "", path), "decision": "no matching endpoint",
                    "reasoning": e["attrs"]["endpoint_note"]})
