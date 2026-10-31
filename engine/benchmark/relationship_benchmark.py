#!/usr/bin/env python3
"""Ground-truth benchmark for the relationship platform (relationships.v1). Separate from the engine; stdlib only.

  relationship_benchmark.py [--fixtures DIR] [--case NAME]... [--out DIR]

Each case is `rel_fixtures/<name>/{case.json, repos/<app>/...}`. `case.json` is HAND-WRITTEN: what a careful reviewer reading
the files would conclude. No command writes or refreshes labels from engine output; a failing label is never edited to match the
engine. An expectation the engine cannot meet today carries `"unsupported": "<reason>"` and is reported as a documented limit.

Label kinds (matched on edge type, source application, target node name, optional method/path, optional resolution state):
  expect_edges   an edge that must exist
  forbid_edges   an edge that must NOT exist (a false positive if it does)
  exhaustive     edge types for which every edge leaving the case's applications must be labelled; an unlabelled one is a false positive
Gates (exit 1 on failure): no forbidden edge present, no unlabelled edge for an exhaustive type, every supported expected edge found,
graph integrity valid (every edge cites re-readable evidence), deterministic replay. Precision and recall are reported.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
os.environ["DISCOVERY_FIXED_TIME"] = "2026-01-01T00:00:00Z"

import discover  # noqa: E402
import relate  # noqa: E402
from graph import extract, model, resolve  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "bench", "GIT_AUTHOR_EMAIL": "b@example.com", "GIT_COMMITTER_NAME": "bench", "GIT_COMMITTER_EMAIL": "b@example.com",
           "GIT_AUTHOR_DATE": "2020-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2020-01-01T00:00:00Z"}


def materialise(case_dir, parent):
    import shutil
    out = {}
    for app in sorted(os.listdir(os.path.join(case_dir, "repos"))):
        dst = os.path.join(parent, app)
        shutil.copytree(os.path.join(case_dir, "repos", app), dst)
        env = dict(os.environ, **GIT_ENV)
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", "x"]):
            subprocess.run(cmd, cwd=dst, env=env, check=True, capture_output=True)
        out[app] = dst
    return out


def analyse(repos, aliases):
    docs = [extract.extract(r, discover.build(r)) for r in repos.values()]
    return resolve.resolve(docs, aliases), docs


def describe(P):
    names = {n["id"]: n["name"] for n in P["nodes"]}
    out = []
    for e in P["edges"]:
        if not e["source"].startswith("app:"):
            continue
        out.append({"type": e["type"], "source": e["source"][4:], "target": names.get(e["target"], e["target"]), "method": e["attrs"].get("method"),
                    "path": e["attrs"].get("path"), "state": (e.get("resolution") or {}).get("state")})
    return out


def matches(edge, label):
    return all(edge.get(k) == v for k, v in label.items() if k not in ("unsupported", "note"))


def run_case(case_dir, case):
    with tempfile.TemporaryDirectory() as t:
        repos = materialise(case_dir, t)
        aliases = case.get("aliases")
        if aliases:
            p = os.path.join(t, "aliases.yml")
            open(p, "w").write("".join("%s: %s\n" % kv for kv in aliases.items()))
            aliases = relate.load_aliases(p)
        P, docs = analyse(repos, aliases)
        P2, _ = analyse(repos, aliases)
        integrity = model.validate_integrity(P, repos)
        edges = describe(P)
    res = {"integrity": integrity, "deterministic": json.dumps(P, sort_keys=True) == json.dumps(P2, sort_keys=True), "failures": [], "unsupported": [], "tp": 0, "fn": 0, "fp": 0}
    labelled = []
    for lab in case.get("expect_edges", []):
        found = [e for e in edges if matches(e, lab)]
        labelled.extend(found)
        if found:
            res["tp"] += 1
            if lab.get("unsupported"):
                res["failures"].append("unsupported expectation now passes, review the label: %s" % lab)
        elif lab.get("unsupported"):
            res["unsupported"].append((lab, lab["unsupported"]))
            res["fn"] += 1
        else:
            res["failures"].append("missing expected edge: %s" % lab)
            res["fn"] += 1
    for lab in case.get("forbid_edges", []):
        for e in edges:
            if matches(e, lab):
                res["failures"].append("forbidden edge present: %s" % e)
                res["fp"] += 1
    for typ in case.get("exhaustive", []):
        for e in edges:
            if e["type"] == typ and not any(matches(e, l) for l in case.get("expect_edges", [])):
                res["failures"].append("unlabelled %s edge (false positive under exhaustive labelling): %s" % (typ, e))
                res["fp"] += 1
    if integrity:
        res["failures"].append("graph integrity: %s" % integrity[:3])
    if not res["deterministic"]:
        res["failures"].append("two runs on the same input differ")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", default=os.path.join(HERE, "rel_fixtures"))
    ap.add_argument("--case", action="append")
    ap.add_argument("--out")
    a = ap.parse_args()
    names = sorted(d for d in os.listdir(a.fixtures) if os.path.isfile(os.path.join(a.fixtures, d, "case.json")))
    if a.case:
        names = [n for n in names if n in a.case]
    if not names:
        print("no cases", file=sys.stderr)
        return 2
    tot = {"tp": 0, "fn": 0, "fp": 0}
    rows, failed = [], False
    for n in names:
        d = os.path.join(a.fixtures, n)
        case = json.load(open(os.path.join(d, "case.json")))
        r = run_case(d, case)
        for k in tot:
            tot[k] += r[k]
        rows.append((n, case.get("category", ""), r))
        failed = failed or bool(r["failures"])
    print("| case | category | tp | fn | fp | result |\n|---|---|---|---|---|---|")
    for n, c, r in rows:
        print("| %s | %s | %d | %d | %d | %s |" % (n, c, r["tp"], r["fn"], r["fp"], "FAIL" if r["failures"] else "ok"))
    for n, c, r in rows:
        for f in r["failures"]:
            print("FAIL %s: %s" % (n, f))
        for lab, why in r["unsupported"]:
            print("UNSUPPORTED %s: %s (%s)" % (n, {k: v for k, v in lab.items() if k != "unsupported"}, why))
    p = tot["tp"] / (tot["tp"] + tot["fp"]) if tot["tp"] + tot["fp"] else 1.0
    rc = tot["tp"] / (tot["tp"] + tot["fn"]) if tot["tp"] + tot["fn"] else 1.0
    print("\ncases %d · edge precision %.2f · edge recall %.2f · false positives %d" % (len(rows), p, rc, tot["fp"]))
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        json.dump({"cases": len(rows), "precision": p, "recall": rc, **tot}, open(os.path.join(a.out, "relationship_report.json"), "w"), indent=1)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
