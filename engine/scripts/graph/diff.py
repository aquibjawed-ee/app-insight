"""Graph diff between two analyses (base vs head): what an MR changes in the estate, and what it breaks.

Compares relationships by meaning (type, ends, method, path shape), never by file or line, so moved code is not a change. `breaking`:
an endpoint removed while a call to it remains, an application removed while calls to it remain, a topic that lost its last publisher but still has
consumers, and calls that newly cannot be matched to an application.
"""
from __future__ import annotations

from typing import Dict, List

CONTRACT = "graphdiff.v1"


def _idx(g: dict) -> dict:
    nodes = {n["id"]: n for n in g["nodes"]}

    def tid(nid):  # an unresolved placeholder is identified by what it stands for, not by the hash of where it was found (which includes the line)
        n = nodes.get(nid)
        return "unresolved:%s" % (n["attrs"].get("expression") or n["name"]) if n and n["attrs"].get("unresolved") else nid
    calls, msg, exposes = {}, {}, set()
    for e in g["edges"]:
        t = tid(e["attrs"].get("original_target") or e["target"])
        if e["type"] == "EXPOSES_API":
            exposes.add(e["target"])
        elif e["type"] == "CALLS_API":
            calls[(e["source"], t, e["attrs"].get("method"), e["attrs"].get("path_shape"))] = e
        elif e["type"] in ("PUBLISHES_TO", "CONSUMES_FROM"):
            msg[(e["type"], e["source"], tid(e["target"]))] = e
    apps = {n["id"] for n in g["nodes"] if n["type"] == "Application"}
    return {"tid": tid, "nodes": nodes, "calls": calls, "msg": msg, "exposes": exposes, "apps": apps, "edges": g["edges"]}


def _nm(idx, nid):
    n = idx["nodes"].get(nid)
    return n["name"] if n else (nid.split(":", 1)[1] if nid.startswith("unresolved:") else nid)


def diff(base: dict, head: dict) -> dict:
    b, h = _idx(base), _idx(head)
    out: Dict[str, list] = {"breaking": [], "added_endpoints": [], "removed_endpoints": [], "added_calls": [], "removed_calls": [], "added_messaging": [], "removed_messaging": [],
                            "new_unmatched": [], "applications_added": sorted(h["apps"] - b["apps"]), "applications_removed": sorted(b["apps"] - h["apps"])}
    for nid in sorted(h["exposes"] - b["exposes"]):
        out["added_endpoints"].append(_nm(h, nid))
    for nid in sorted(b["exposes"] - h["exposes"]):
        out["removed_endpoints"].append(_nm(b, nid))
    for k in sorted(set(h["calls"]) - set(b["calls"]), key=str):
        out["added_calls"].append("%s -> %s %s %s" % (_nm(h, k[0]), _nm(h, k[1]), k[2] or "", k[3] or ""))
    for k in sorted(set(b["calls"]) - set(h["calls"]), key=str):
        out["removed_calls"].append("%s -> %s %s %s" % (_nm(b, k[0]), _nm(b, k[1]), k[2] or "", k[3] or ""))
    for k in sorted(set(h["msg"]) - set(b["msg"])):
        out["added_messaging"].append("%s %s %s" % (_nm(h, k[1]), k[0].lower().replace("_", " "), _nm(h, k[2])))
    for k in sorted(set(b["msg"]) - set(h["msg"])):
        out["removed_messaging"].append("%s %s %s" % (_nm(b, k[1]), k[0].lower().replace("_", " "), _nm(b, k[2])))
    # breaking 1: endpoint removed but still called (by a call that resolved to it before, or a call with the same method and path now)
    head_calls = {(k[2], k[3]): e for k, e in h["calls"].items()}
    for e in base["edges"]:
        if e["type"] != "CALLS_API" or not e["target"].startswith("api:") or e["target"] in h["exposes"]:
            continue
        caller = e["source"]
        still = [x for x in head["edges"] if x["type"] == "CALLS_API" and x["source"] == caller and x["attrs"].get("method") == e["attrs"].get("method") and x["attrs"].get("path_shape") == e["attrs"].get("path_shape")]
        if still:
            out["breaking"].append({"kind": "removed endpoint is still called", "subject": _nm(b, e["target"]), "detail": "%s still calls it; no analysed application exposes it any more" % _nm(b, caller),
                                    "evidence": still[0]["evidence"][:1]})
    # breaking 2: application removed but calls to it remain
    for a in sorted(b["apps"] - h["apps"]):
        callers = sorted({x["source"] for x in base["edges"] if x["type"] == "CALLS_API" and (x["target"] == a or (b["nodes"].get(x["target"], {}).get("app") == a[4:] and x["target"].startswith("api:")))
                          and x["source"] in h["apps"]})
        if callers:
            out["breaking"].append({"kind": "application removed but still called", "subject": _nm(b, a), "detail": "still called by: " + ", ".join(_nm(b, c) for c in callers), "evidence": []})
    # breaking 3: topic with consumers but no publisher any more
    pubs_h, cons_h = {}, {}
    for (t, s, tgt) in h["msg"]:
        (pubs_h if t == "PUBLISHES_TO" else cons_h).setdefault(tgt, []).append(s)
    pubs_b = {tgt for (t, s, tgt) in b["msg"] if t == "PUBLISHES_TO"}
    for tid in sorted(cons_h):
        if tid in pubs_b and tid not in pubs_h:
            out["breaking"].append({"kind": "topic lost its last publisher", "subject": _nm(h, tid), "detail": "still consumed by: " + ", ".join(_nm(h, c) for c in sorted(cons_h[tid])), "evidence": []})
    # breaking 4: calls that newly cannot be matched
    for k, e in h["calls"].items():
        if e["resolution"].get("state") in ("unresolved", "ambiguous") and not (k in b["calls"] and b["calls"][k]["resolution"].get("state") in ("unresolved", "ambiguous")):
            out["new_unmatched"].append({"call": "%s -> %s %s %s" % (_nm(h, k[0]), _nm(h, k[1]), k[2] or "", k[3] or ""), "state": e["resolution"]["state"], "evidence": e["evidence"][:1]})
    return {"contract": CONTRACT, **out}


def to_markdown(d: dict) -> str:
    L = ["# Estate change report", ""]
    L.append("**Breaking changes: %d**" % len(d["breaking"]) if d["breaking"] else "**No breaking changes found.**")
    for b in d["breaking"]:
        L.append("- **%s**: %s. %s" % (b["kind"], b["subject"], b["detail"]))
    L.append("")
    for title, key in (("Applications added", "applications_added"), ("Applications removed", "applications_removed"), ("Endpoints added", "added_endpoints"), ("Endpoints removed", "removed_endpoints"),
                       ("Calls added", "added_calls"), ("Calls removed", "removed_calls"), ("Messaging added", "added_messaging"), ("Messaging removed", "removed_messaging")):
        if d[key]:
            L += ["## %s (%d)" % (title, len(d[key]))] + ["- " + x for x in d[key]] + [""]
    if d["new_unmatched"]:
        L += ["## Calls that cannot be matched to an application (new) (%d)" % len(d["new_unmatched"])] + ["- %s (%s)" % (x["call"], x["state"]) for x in d["new_unmatched"]] + [""]
    L.append("_Static analysis of both versions: a relationship that is not seen is not necessarily gone._")
    return "\n".join(L) + "\n"
