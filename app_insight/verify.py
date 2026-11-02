"""Accuracy and consistency gate for a run: every claim the report makes is re-checked against the repositories and
against every other place the same number appears. Runs at the end of every scan and on demand (`app-insight verify`).

Accuracy: a cited line still reads what was cited; "in place" cites at least one line; "enforced" cites a CI file;
a control about the build or pipeline does not cite test code; a result is a verdict, not the control's description;
"not found" says where it searched, and is never claimed where the repository points outside the scan.
Consistency: coverage and status recompute from the controls; findings are exactly the gap controls; the portfolio
summary and the report carry the same states as the per-application files.
"""
from __future__ import annotations

import json
import os
import re

from . import engine_path  # noqa: F401
from . import aspects as A

import evidence  # engine
from graph import resilience as RES  # engine

CI_FILE = A.CI_PATH
RULES = {
    "ACC-1": "a cited line no longer reads what was cited",
    "ACC-2": "an in-place result cites no line",
    "ACC-3": "'enforced' is claimed without citing a CI file",
    "ACC-4": "a build or pipeline control cites test code",
    "ACC-5": "the result shows the control's description instead of a verdict",
    "ACC-6": "a gap has no severity, or a not-checked result gives no reason",
    "ACC-7": "an in-place result rests on an unknown (version or reference data not known)",
    "ACC-8": "a cited line about a secret shows the secret instead of [REDACTED]",
    "ACC-9": "a file written by the run holds a secret-looking value that is not redacted",
    "ACC-10": "a 'not found' result does not say where it searched and what for",
    "CON-1": "coverage does not recompute from the controls",
    "CON-2": "aspect status does not recompute from the controls",
    "CON-3": "findings are not exactly the controls in a gap state",
    "CON-4": "the portfolio summary disagrees with the application",
    "CON-5": "a state or level outside the catalogue vocabulary",
    "CON-6": "the report shows different data from the analysis",
    "CON-7": "two controls of one application contradict each other",
    "CON-8": "a 'not found' result in an area the scan recorded as partly outside its reach",
}
UNKNOWN_WORDS = re.compile(r"(?i)\bunknown\b|line-specific|not in the reference data|cannot be decided|not recognised")
# (what one control says is not there, the controls whose result shows it is there)
CONTRADICTIONS = [
    (A.NEED_TEXT["database"], {"runtime.db_timeouts": ("PRESENT", "PARTIAL", "ABSENT", "ISSUE"), "architecture.no_shared_database": ("PRESENT", "ISSUE")}),
    (A.NEED_TEXT["outbound_http"], {"runtime.http_timeouts": ("PRESENT", "PARTIAL", "ABSENT", "ISSUE")}),
]


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _report_data(path):
    if not os.path.isfile(path):
        return None
    html = open(path, encoding="utf-8").read()
    i = html.find("const D = ")
    if i < 0:
        return None
    j = html.find(";\n", i)
    try:
        return json.loads(html[i + len("const D = "):j])
    except ValueError:
        return None


def check(run_dir, catalogue=None):
    """Returns {"ok", "checked": {...}, "problems": [{rule, app, control, detail}]}."""
    cat = catalogue or A.load_catalogue()
    out = os.path.join(run_dir, "analysis")
    man = _read(os.path.join(out, "manifest.json"))
    repos = {x["app"]: x.get("repo") for x in man["applications"]}
    by_id = {c["id"]: c for c in cat["controls"]}
    descriptions = {c[3] for c in RES.CHECKS} | {c.get("fix") for c in cat["controls"] if c.get("fix")}
    port = _read(os.path.join(out, "portfolio", "aspects.json")) if os.path.isfile(os.path.join(out, "portfolio", "aspects.json")) else {"applications": {}}
    rep = _report_data(os.path.join(run_dir, "report.html"))
    rep_apps = {a["name"]: a for a in (rep or {}).get("apps", [])}
    probs, n = [], {"applications": 0, "controls": 0, "lines_reread": 0}

    def bad(rule, app, ctl, detail):
        probs.append({"rule": rule, "app": app, "control": ctl, "detail": detail})

    for app, repo in sorted(repos.items()):
        p = os.path.join(out, app, "aspects.json")
        if not os.path.isfile(p):
            continue
        doc = _read(p)
        n["applications"] += 1
        gaps = []
        for asp in doc["aspects"]:
            for c in asp["controls"]:
                n["controls"] += 1
                cid, st, src = c["id"], c["state"], (by_id.get(c["id"]) or {}).get("source") or {}
                if st not in cat["states"] or (c["level"] and c["level"] not in cat["levels"]):
                    bad("CON-5", app, cid, "%s / %s" % (st, c["level"]))
                for e in c["evidence"]:
                    if e.get("kind") == "file" and repo:
                        n["lines_reread"] += 1
                        why = evidence.verify(repo, e)
                        if why:
                            bad("ACC-1", app, cid, why)
                if (by_id.get(cid) or {}).get("source", {}).get("check", "").startswith("security.secrets"):
                    for e in c["evidence"]:
                        if "[REDACTED]" not in (e.get("snippet") or "") and "PRIVATE KEY" not in (e.get("snippet") or ""):
                            bad("ACC-8", app, cid, "%s:%s" % (e.get("path"), e.get("line_start")))
                if st == "PRESENT" and not c["evidence"] and not (by_id.get(cid) or {}).get("negative_scan"):
                    bad("ACC-2", app, cid, c["summary"][:90])
                if c["level"] == "enforced" and not any(CI_FILE.search(e.get("path") or "") for e in c["evidence"]):
                    bad("ACC-3", app, cid, ", ".join("%s:%s" % (e.get("path"), e.get("line_start")) for e in c["evidence"][:3]) or "no evidence")
                test_ok = src.get("criterion") in A.TEST_CRITERIA or "safetynet" in src
                for e in c["evidence"]:
                    if not test_ok and A.TEST_PATH.search(e.get("path") or ""):
                        bad("ACC-4", app, cid, "%s:%s" % (e["path"], e.get("line_start")))
                        break
                if st == "PRESENT" and UNKNOWN_WORDS.search(c["summary"]):
                    bad("ACC-7", app, cid, c["summary"][:90])
                if c["summary"] in descriptions:
                    bad("ACC-5", app, cid, c["summary"][:90])
                if (st in A.GAP_STATES and not c["severity"]) or (st in ("NOT_ASSESSED", "UNKNOWN") and not c["summary"]):
                    bad("ACC-6", app, cid, st)
                if st == "ABSENT" and (by_id.get(cid) or {}).get("search"):
                    s = c.get("searched") or {}
                    if not s.get("for") or not s.get("in"):
                        bad("ACC-10", app, cid, "no search record")
                    srch = (by_id.get(cid) or {}).get("search") or {}
                    areas = set(srch["blind_to"] if "blind_to" in srch else srch.get("in") or [])
                    blind = [b for b in (doc.get("scope") or {}).get("blind_spots") or [] if b["area"] in areas]
                    if blind and not (by_id.get(cid) or {}).get("negative_scan"):
                        bad("CON-8", app, cid, "%s, but %s" % (c["summary"][:60], blind[0]["what"][:60]))
                if st in A.GAP_STATES:
                    gaps.append(c["finding"])
            status, _, cov = A.rollup(asp["controls"])
            if cov != asp["coverage"]:
                bad("CON-1", app, asp["id"], "stored %s, recomputed %s" % (asp["coverage"], cov))
            if status != asp["status"]:
                bad("CON-2", app, asp["id"], "stored %s, recomputed %s" % (asp["status"], status))
            if port["applications"].get(app, {}).get(asp["id"]) != asp["status"]:
                bad("CON-4", app, asp["id"], "portfolio says %s" % port["applications"].get(app, {}).get(asp["id"]))
        by = {c["id"]: c for a in doc["aspects"] for c in a["controls"]}
        for absent_text, shows in CONTRADICTIONS:
            says_none = [c["id"] for c in by.values() if c["summary"] == absent_text]
            says_some = [k for k, sts in shows.items() if k in by and by[k]["state"] in sts]
            if says_none and says_some:
                bad("CON-7", app, says_none[0], "says '%s' but %s found it" % (absent_text, says_some[0]))
        if sorted(gaps) != sorted(doc["findings"]) or None in gaps:
            bad("CON-3", app, "-", "%d gap controls, %d findings" % (len(gaps), len(doc["findings"])))
        if rep is not None and (app not in rep_apps or rep_apps[app].get("aspects") != doc):
            bad("CON-6", app, "-", "report.html does not carry this application's aspects.json")
    if rep is None:
        bad("CON-6", "-", "-", "report.html missing or its data could not be read")
    for root, _, names in os.walk(run_dir):  # every file the run wrote: analysis JSON, the report, the run record
        for name in names:
            if not name.endswith((".json", ".html", ".md", ".txt")) or name == "verify.json":
                continue
            path, rel = os.path.join(root, name), os.path.relpath(os.path.join(root, name), run_dir)
            text = open(path, encoding="utf-8", errors="replace").read()
            # compare decoded values (a JSON escape is not a secret); the page is its data blob plus the markup around it
            if name.endswith(".json"):
                try:
                    leaked = evidence.redact_tree(json.loads(text)) != json.loads(text)
                except ValueError:
                    leaked = evidence.redact(text) != text
            elif name.endswith(".html") and rep is not None and "const D = " in text:
                i = text.find("const D = ")
                j = text.find(";\n", i)
                blob = json.loads(text[i + len("const D = "):j])
                leaked = evidence.redact_tree(blob) != blob or evidence.redact(text[:i] + text[j:]) != text[:i] + text[j:]
            else:
                leaked = evidence.redact(text) != text
            if leaked:  # the location only: the value itself is never repeated
                bad("ACC-9", rel, "-", "holds a value that redaction would mask")
    return {"ok": not probs, "checked": n, "problems": probs, "rules": RULES}


def write(run_dir, catalogue=None):
    res = check(run_dir, catalogue)
    with open(os.path.join(run_dir, "verify.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, sort_keys=True)
    return res


def print_result(res, limit=20):
    n = res["checked"]
    head = "%d applications, %d controls, %d cited lines re-read" % (n["applications"], n["controls"], n["lines_reread"])
    if res["ok"]:
        print("verification:  PASS (%s)" % head)
        return
    by = {}
    for p in res["problems"]:
        by.setdefault(p["rule"], []).append(p)
    print("verification:  FAIL, %d problem(s) (%s)" % (len(res["problems"]), head))
    for rule in sorted(by):
        print("  %s %s: %d" % (rule, RULES[rule], len(by[rule])))
        for p in by[rule][:limit]:
            print("      %s  %s  %s" % (p["app"], p["control"], p["detail"]))
