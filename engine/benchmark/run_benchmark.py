#!/usr/bin/env python3
"""Accuracy benchmark for app-discovery. Separate from discovery output; stdlib only; the engine is imported read-only.

  run_benchmark.py [--fixtures DIR] [--out DIR] [--case NAME]...

Each case is `fixtures/<name>/{case.json, repo/}`. `case.json` is HAND-WRITTEN ground truth: what a careful reviewer
who reads the files in `repo/` would conclude. There is deliberately no command that writes or updates expectations
from engine output. An expectation that cannot be met today is marked `"unsupported": "<reason>"`; it is reported as a
documented limitation, never silently changed or dropped.

Four things are measured independently:
  precision   of the positive claims the engine makes about labelled facts
  recall      of the labelled facts that are expected to be found
  integrity   every CONFIRMED fact is backed by verifying citations or a valid derivation chain (bounded NOT_FOUND
              observations count as support), plus schema validity and no false MET
  determinism a second run on a fresh copy of the same repo is identical apart from the timestamp
Exit codes: 0 all gates pass, 1 a gate failed, 2 could not run.
"""
from __future__ import annotations

import argparse
import copy
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
os.environ["DISCOVERY_FIXED_TIME"] = "2026-01-01T00:00:00Z"

import discover  # noqa: E402
import evidence  # noqa: E402
import validate  # noqa: E402

BENCHMARK_VERSION = "1.0.0"
POSITIVE_STATUSES = ("CONFIRMED", "INFERRED")
GIT_ENV = {"GIT_AUTHOR_NAME": "bench", "GIT_AUTHOR_EMAIL": "b@example.com", "GIT_COMMITTER_NAME": "bench",
           "GIT_COMMITTER_EMAIL": "b@example.com", "GIT_AUTHOR_DATE": "2020-01-01T00:00:00Z",
           "GIT_COMMITTER_DATE": "2020-01-01T00:00:00Z"}


# ---------------------------------------------------------------- fixtures
def materialise(case_dir: str, parent: str, setup: dict) -> str:
    """Copy repo/ to <parent>/<case name> (fixed basename so replays are comparable) and apply the declared setup."""
    name = os.path.basename(case_dir.rstrip("/"))
    dst = os.path.join(parent, name)
    shutil.copytree(os.path.join(case_dir, "repo"), dst, symlinks=True)
    env = dict(os.environ, **GIT_ENV)

    def git(*a):
        subprocess.run(["git", *a], cwd=dst, env=env, check=True, capture_output=True)
    git("init", "-q")
    for link, target in (setup.get("symlinks") or {}).items():
        t = os.path.join(parent, "outside_" + os.path.basename(target))
        with open(t, "w") as fh:
            fh.write(setup.get("symlink_content", "OUTSIDE_SECRET_MARKER") + "\n")
        os.makedirs(os.path.dirname(os.path.join(dst, link)) or dst, exist_ok=True)
        os.symlink(t, os.path.join(dst, link))
    if setup.get("remote"):
        git("remote", "add", "origin", setup["remote"])
    if setup.get("commit"):
        git("add", "-A")
        git("commit", "-q", "-m", "fixture")
    for rel in setup.get("old_files") or []:  # make a file older than the commit (stale coverage report)
        os.utime(os.path.join(dst, rel), (1, 1))
    for rel in setup.get("dirty") or []:
        with open(os.path.join(dst, rel), "w") as fh:
            fh.write("uncommitted\n")
    return dst


def run_engine(case_dir: str, setup: dict):
    with tempfile.TemporaryDirectory(prefix="appdisc-bench-") as parent:
        repo = materialise(case_dir, parent, setup)
        doc = discover.build(repo)
        bad = []
        for fid, f in evidence.iter_facts(doc):
            for e in f["evidence"]:
                why = evidence.verify(repo, e)
                if why:
                    bad.append("%s: %s" % (fid, why))
        return doc, bad


def strip_time(doc: dict) -> dict:
    d = copy.deepcopy(doc)
    d["run_meta"].pop("generated_at", None)
    return d


# ---------------------------------------------------------------- comparison
def get_fact(doc, fid):
    sec, key = fid.split(".", 1)
    return (doc.get(sec) or {}).get(key)


def dig(value, path):
    for p in (path.split(".") if path else []):
        if isinstance(value, dict):
            value = value.get(p)
        else:
            return None
    return value


def truthy(v) -> bool:
    return v not in (None, False, 0, "", [], {})


def _sub(item, sub):
    """True when every key of `sub` is in `item` with the same value (a list value: all its members are present)."""
    if not isinstance(item, dict):
        return False
    for k, v in sub.items():
        have = item.get(k)
        if isinstance(v, list):
            if not (isinstance(have, list) and all(x in have for x in v)):
                return False
        elif have != v:
            return False
    return True


def eval_fact(doc, exp):
    f = get_fact(doc, exp["id"])
    if f is None:
        return False, None, "fact missing", False
    val = dig(f["value"], exp.get("path", ""))
    ok = True
    if "value" in exp:
        ok = val == exp["value"]
    if ok and "value_includes" in exp:
        ok = isinstance(val, list) and all(x in val for x in exp["value_includes"])
    if ok and "value_absent" in exp:
        ok = not (isinstance(val, list) and any(x in val for x in exp["value_absent"]))
    if ok and "value_contains" in exp:
        ok = isinstance(val, str) and exp["value_contains"] in val
    if ok and "items_include" in exp:  # a list of objects: each listed subset must match some item
        ok = isinstance(val, list) and all(any(_sub(i, sub) for i in val) for sub in exp["items_include"])
    if ok and "items_absent" in exp:
        ok = not (isinstance(val, list) and any(_sub(i, sub) for i in val for sub in exp["items_absent"]))
    if ok and "status" in exp:
        ok = f["status"] in exp["status"]
    if ok and "note_contains" in exp:
        ok = exp["note_contains"] in (f.get("note") or "")
    if ok and "note_excludes" in exp:
        ok = exp["note_excludes"] not in (f.get("note") or "")
    engine_pos = f["status"] in POSITIVE_STATUSES and truthy(val)
    if "items_absent" in exp:  # asserting that one named item is NOT reported: only that item counts as a positive claim
        engine_pos = engine_pos and isinstance(val, list) and any(_sub(i, sub) for i in val for sub in exp["items_absent"])
    return ok, {"value": val, "status": f["status"]}, None, engine_pos


def expected_positive(exp) -> bool:
    if "value" in exp:
        v = exp["value"]
    elif "value_includes" in exp:
        v = exp["value_includes"]
    elif "value_contains" in exp:
        v = exp["value_contains"]
    elif "items_include" in exp:
        v = exp["items_include"]
    else:
        return False
    st = exp.get("status") or ["CONFIRMED"]
    return truthy(v) and any(s in POSITIVE_STATUSES for s in st)


def evaluate_case(case, doc, invalid_citations, replay_doc):
    res = []
    crit = {c["id"]: c for c in doc["maturity"]["criteria"]}
    tp = fp = fn = tn = 0
    met_claimed = met_correct = met_expected = met_found = false_met = 0
    for exp in case.get("facts", []):
        ok, actual, why, engine_pos = eval_fact(doc, exp)
        exp_pos = expected_positive(exp)
        if exp_pos and engine_pos and ok:
            tp += 1
        elif engine_pos and not ok:
            fp += 1
        elif exp_pos:
            fn += 1
        elif ok:
            tn += 1
        res.append({"kind": "fact", "id": exp["id"], "rule": exp.get("rule", "unspecified"), "detector": exp["id"].split(".")[0],
                    "expected": {k: exp[k] for k in exp if k in ("value", "value_includes", "value_absent", "value_contains", "items_include", "items_absent", "path", "status", "note_contains", "note_excludes")},
                    "actual": actual or {"error": why}, "ok": ok, "unsupported": exp.get("unsupported")})
    for exp in case.get("criteria", []):
        c = crit.get(exp["id"])
        if exp.get("absent"):
            ok, actual = c is None, ({"result": c["result"]} if c else {"result": "not applicable (absent)"})
        else:
            ok = c is not None and c["result"] in exp["result"]
            actual = {"result": c["result"] if c else "absent"}
        exp_met = "MET" in (exp.get("result") or [])
        eng_met = bool(c) and c["result"] == "MET"
        met_expected += exp_met and not exp.get("absent", False)
        met_claimed += eng_met
        met_correct += eng_met and exp_met
        met_found += exp_met and eng_met
        if eng_met and not exp_met:
            false_met += 1
        res.append({"kind": "criterion", "id": exp["id"], "rule": exp.get("rule", "unspecified"), "detector": "maturity",
                    "expected": {"result": exp.get("result"), "absent": exp.get("absent", False)}, "actual": actual,
                    "ok": ok, "unsupported": exp.get("unsupported")})
    for cid in case.get("never_met", []):
        c = crit.get(cid)
        bad = bool(c) and c["result"] == "MET"
        if bad and not any(r["kind"] == "criterion" and r["id"] == cid and not r["ok"] for r in res):
            false_met += 1
        res.append({"kind": "never_met", "id": cid, "rule": "no-false-met", "detector": "maturity",
                    "expected": {"result": "not MET"}, "actual": {"result": c["result"] if c else "absent"}, "ok": not bad, "unsupported": None})
    if case.get("never_met_all"):
        mets = [cid for cid, c in crit.items() if c["result"] == "MET"]
        false_met += len(mets)
        res.append({"kind": "never_met", "id": "*", "rule": "no-false-met", "detector": "maturity", "expected": {"result": "no criterion MET"},
                    "actual": {"met": mets}, "ok": not mets, "unsupported": None})
    text = json.dumps(doc)
    for s in case.get("forbid_in_output", []):
        res.append({"kind": "forbidden", "id": s[:12] + "...", "rule": case.get("forbid_rule", "redaction"), "detector": "evidence",
                    "expected": {"absent_from_output": True}, "actual": {"present": s in text}, "ok": s not in text, "unsupported": None})
    for cm in case.get("citation_modules", []):
        f = get_fact(doc, cm["id"])
        cites = [e for e in (f["evidence"] if f else []) if e.get("path", "").startswith(cm["path_prefix"])]
        ok = bool(cites) and all(e.get("module") == cm["module"] for e in cites)
        res.append({"kind": "citation_module", "id": cm["id"], "rule": "module-attribution", "detector": cm["id"].split(".")[0],
                    "expected": {"module": cm["module"], "prefix": cm["path_prefix"]}, "actual": {"cited": len(cites)}, "ok": ok, "unsupported": None})
    for r in res:
        r["status"] = ("pass" if r["ok"] else "fail") if not r["unsupported"] else ("now_supported" if r["ok"] else "documented_unsupported")
    # integrity over EVERY fact in the document, not only the labelled ones
    schema_errs = validate.validate(doc)
    prov_errs = validate.provenance(doc)
    confirmed = [(fid, f) for fid, f in evidence.iter_facts(doc) if f["status"] == "CONFIRMED"]
    unsupported_confirmed = [fid for fid, f in confirmed if not f["evidence"] and not f.get("derivation")]
    bad_prov = {e.split(":")[0] for e in prov_errs}
    invalid_by_fact = {e.split(":")[0] for e in invalid_citations}
    supported = [fid for fid, f in confirmed if fid not in bad_prov and fid not in invalid_by_fact and (f["evidence"] or f.get("derivation"))]
    integrity = {"confirmed_facts": len(confirmed), "supported_confirmed": len(supported),
                 "unsupported_confirmed": sorted(set(unsupported_confirmed) | (bad_prov & {fid for fid, _ in confirmed})),
                 "citations_checked": sum(len(f["evidence"]) for _, f in evidence.iter_facts(doc)),
                 "invalid_citations": invalid_citations, "schema_errors": schema_errs, "provenance_errors": prov_errs}
    determinism = {"identical": strip_time(doc) == strip_time(replay_doc),
                   "fingerprint_equal": doc["run_meta"]["fingerprint"] == replay_doc["run_meta"]["fingerprint"]}
    counts = {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "met_claimed": met_claimed, "met_correct": met_correct,
              "met_expected": met_expected, "false_met": false_met}
    return res, counts, integrity, determinism


# ---------------------------------------------------------------- report
def ratio(a, b):
    return round(a / b, 4) if b else None


def summarise(cases_out):
    t = {k: 0 for k in ("tp", "fp", "fn", "tn", "met_claimed", "met_correct", "met_expected", "false_met", "confirmed", "supported",
                        "citations", "invalid", "schema", "prov", "nondet")}
    by_det, by_rule, unsupported, now_supported = {}, {}, [], []
    for c in cases_out:
        for k in ("tp", "fp", "fn", "tn", "met_claimed", "met_correct", "met_expected", "false_met"):
            t[k] += c["counts"][k]
        i = c["integrity"]
        t["confirmed"] += i["confirmed_facts"]
        t["supported"] += i["supported_confirmed"]
        t["citations"] += i["citations_checked"]
        t["invalid"] += len(i["invalid_citations"])
        t["schema"] += len(i["schema_errors"])
        t["prov"] += len(i["provenance_errors"])
        t["nondet"] += 0 if (c["determinism"]["identical"] and c["determinism"]["fingerprint_equal"]) else 1
        for r in c["results"]:
            row = {"case": c["name"], "kind": r["kind"], "id": r["id"], "rule": r["rule"], "detector": r["detector"],
                   "expected": r["expected"], "actual": r["actual"]}
            if r["status"] == "fail":
                by_det.setdefault(r["detector"], []).append(row)
                by_rule.setdefault(r["rule"], []).append(row)
            elif r["status"] == "documented_unsupported":
                unsupported.append(dict(row, reason=r["unsupported"]))
            elif r["status"] == "now_supported":
                now_supported.append(dict(row, reason=r["unsupported"]))
    n_exp = sum(len(c["results"]) for c in cases_out)
    n_fail = sum(len(v) for v in by_det.values())
    metrics = {
        "fact_precision": ratio(t["tp"], t["tp"] + t["fp"]), "fact_recall": ratio(t["tp"], t["tp"] + t["fn"]),
        "met_precision": ratio(t["met_correct"], t["met_claimed"]), "met_recall": ratio(t["met_correct"], t["met_expected"]),
        "false_met": t["false_met"],
        "evidence_integrity": ratio(t["supported"], t["confirmed"]), "confirmed_facts": t["confirmed"],
        "unsupported_confirmed": t["confirmed"] - t["supported"], "citations_checked": t["citations"], "invalid_citations": t["invalid"],
        "schema_errors": t["schema"], "provenance_errors": t["prov"],
        "deterministic_replays": "%d/%d" % (len(cases_out) - t["nondet"], len(cases_out)), "nondeterministic_cases": t["nondet"],
        "expectations": n_exp, "expectation_failures": n_fail, "documented_unsupported": len(unsupported)}
    gates = {"no_expectation_failures": n_fail == 0, "no_false_met": t["false_met"] == 0,
             "no_unsupported_confirmed": metrics["unsupported_confirmed"] == 0, "no_invalid_citations": t["invalid"] == 0,
             "schema_and_provenance_valid": t["schema"] == 0 and t["prov"] == 0, "deterministic_replay": t["nondet"] == 0}
    return metrics, gates, by_det, by_rule, unsupported, now_supported


def markdown(report) -> str:
    m, g = report["metrics"], report["gates"]
    pc = lambda v: "n/a" if v is None else "%.1f%%" % (100 * v)
    out = ["# app-discovery accuracy benchmark", "",
           "engine %s, benchmark %s, %d cases, %d expectations" % (report["engine_version"], report["benchmark_version"],
                                                                 len(report["cases"]), m["expectations"]), "",
           "| measure | result |", "|---|---|",
           "| fact precision | %s |" % pc(m["fact_precision"]), "| fact recall | %s |" % pc(m["fact_recall"]),
           "| MET precision / recall | %s / %s |" % (pc(m["met_precision"]), pc(m["met_recall"])),
           "| false MET | %d |" % m["false_met"],
           "| evidence integrity (CONFIRMED facts supported) | %s (%d facts, %d unsupported) |" % (pc(m["evidence_integrity"]), m["confirmed_facts"], m["unsupported_confirmed"]),
           "| citations re-verified | %d checked, %d invalid |" % (m["citations_checked"], m["invalid_citations"]),
           "| schema / provenance errors | %d / %d |" % (m["schema_errors"], m["provenance_errors"]),
           "| deterministic replay | %s |" % m["deterministic_replays"], "",
           "## Gates", ""] + ["- %s %s" % ("PASS" if v else "FAIL", k.replace("_", " ")) for k, v in g.items()]
    out += ["", "## Cases", "", "| case | category | pass | fail | unsupported |", "|---|---|---|---|---|"]
    for c in report["cases"]:
        rs = c["results"]
        out.append("| %s | %s | %d | %d | %d |" % (c["name"], c["category"], sum(r["status"] == "pass" for r in rs),
                                                   sum(r["status"] == "fail" for r in rs), sum(r["status"] == "documented_unsupported" for r in rs)))
    for title, key in (("Failures by detector", "failures_by_detector"), ("Failures by rule", "failures_by_rule")):
        out += ["", "## " + title, ""]
        if not report[key]:
            out.append("none")
        for k, rows in sorted(report[key].items()):
            out.append("- **%s** (%d)" % (k, len(rows)))
            for r in rows:
                out.append("  - `%s` %s %s: expected %s, got %s" % (r["case"], r["kind"], r["id"], json.dumps(r["expected"]), json.dumps(r["actual"])))
    out += ["", "## Documented unsupported scenarios", ""]
    out += ["- `%s` %s %s (rule %s): %s. Engine currently returns %s." % (u["case"], u["kind"], u["id"], u["rule"], u["reason"], json.dumps(u["actual"]))
            for u in report["unsupported"]] or ["none"]
    if report["now_supported"]:
        out += ["", "## Marked unsupported but now passing (review the label)", ""]
        out += ["- `%s` %s %s" % (u["case"], u["kind"], u["id"]) for u in report["now_supported"]]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fixtures", default=os.path.join(HERE, "fixtures"))
    ap.add_argument("--out", help="directory for report.json and report.md (default: print only)")
    ap.add_argument("--case", action="append", help="run only these cases")
    a = ap.parse_args(argv)
    names = sorted(n for n in os.listdir(a.fixtures) if os.path.isfile(os.path.join(a.fixtures, n, "case.json")))
    if a.case:
        names = [n for n in names if n in a.case]
    if not names:
        print("no cases found in %s" % a.fixtures, file=sys.stderr)
        return 2
    cases_out = []
    for n in names:
        d = os.path.join(a.fixtures, n)
        case = json.load(open(os.path.join(d, "case.json"), encoding="utf-8"))
        setup = case.get("setup") or {}
        doc, invalid = run_engine(d, setup)
        replay, _ = run_engine(d, setup)
        results, counts, integrity, det = evaluate_case(case, doc, invalid, replay)
        cases_out.append({"name": n, "category": case["category"], "description": case["description"],
                          "results": results, "counts": counts, "integrity": integrity, "determinism": det})
    metrics, gates, by_det, by_rule, unsupported, now_supported = summarise(cases_out)
    report = {"benchmark_version": BENCHMARK_VERSION, "engine_version": discover.TOOL_VERSION,
              "metrics": metrics, "gates": gates, "failures_by_detector": by_det, "failures_by_rule": by_rule,
              "unsupported": unsupported, "now_supported": now_supported, "cases": cases_out,
              "passed": all(gates.values())}
    text = markdown(report)
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
            fh.write("\n")
        with open(os.path.join(a.out, "report.md"), "w", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
