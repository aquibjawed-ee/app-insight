#!/usr/bin/env python3
"""Cross-check data-real.js against the run itself: counts per app, edges covered, no secret material.

    python3 -I check.py <run-dir>
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
run = sys.argv[1]
A = os.path.join(run, "analysis")
t = open(os.path.join(HERE, "data-real.js")).read()
D = json.loads(t[t.index("const DATA=") + 11:t.index(";\nconst {")])
BAD, OPEN = {"PARTIAL", "ABSENT", "ISSUE"}, {"UNKNOWN", "NOT_ASSESSED"}
ok = True
rel = json.load(open(os.path.join(A, "portfolio", "relationships.json")))
print("%-28s %8s %5s %10s %6s %6s" % ("app", "findings", "high", "unverified", "edges", "eps"))
for a in D["apps"]:
    cs = [c for x in json.load(open(os.path.join(A, a["id"], "aspects.json")))["aspects"] for c in x["controls"] if not c.get("pending")]
    f = sum(c["state"] in BAD for c in cs)
    h = sum(c["state"] in BAD and (c.get("severity") or "").lower() == "high" for c in cs)
    u = sum(c["state"] in OPEN for c in cs)
    mf = sum(c["state"] in BAD for c in a["controls"])
    mh = sum(c["state"] in BAD and c["severity"] == "HIGH" for c in a["controls"])
    mu = sum(c["state"] in OPEN for c in a["controls"])
    me = "app:" + a["id"]
    want = {e["id"] for e in rel["edges"] if me in (e["source"], e["target"]) and e["type"] not in ("CONTAINS", "EXPOSES_API")}
    got = {e["eid"] for e in D["edges"] if a["id"] in (e["source"], e["target"])}
    eps = sum(1 for n in rel["nodes"] if n["type"] == "ApiEndpoint" and n.get("app") == a["id"])
    good = (f, h, u) == (mf, mh, mu) and want == got and eps == a["apiCount"] and len(cs) == len(a["controls"])
    ok &= good
    print("%-28s %8s %5s %10s %6s %6s %s" % (a["id"], f, h, u, len(got), eps, "ok" if good else "MISMATCH mock=%s" % ((mf, mh, mu),)))
pend = {c["id"] for d in D["apps"] for x in json.load(open(os.path.join(A, d["id"], "aspects.json")))["aspects"] for c in x["controls"] if c.get("pending")}
print("pending listed once:", sorted(pend) == sorted(p["id"] for p in D["pendingControls"]), len(pend))
html = open(os.path.join(HERE, "mock.html")).read()
print("private key header only:", html.count("PRIVATE KEY"), "occurrence(s), each followed by the not-copied note:", html.count("PRIVATE KEY") == html.count("[key material not copied]"))
print("external URLs loaded:", [x for x in ("http://", "https://") if ('src="' + x) in html or ("href=\"" + x) in html])
print("ALL OK" if ok else "SOME MISMATCH")
