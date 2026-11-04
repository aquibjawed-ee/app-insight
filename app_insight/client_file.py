"""The client file (design 8.6): exactly what a consultant's review allows to be shown, nothing else from the internal report.

Built from the review's outcomes, never from an unreviewed tool verdict; every count and derived view is recomputed from the
outcomes (a result without one contributes nothing). Written under a temporary name and verified with the rule classification
of 8.8 before it takes its name. Static HTML with no script and no data blob: the page is what it shows.
"""
from __future__ import annotations

import html
import json
import os

from . import aspects as A
from . import report as R
from . import review as RV
from . import verify as V

NAME, PENDING = "report-client.html", "report-client.pending.html"
MARKER = "This client file differs from the internal report only as design section 8.6 defines: it shows review outcomes, never an unreviewed tool verdict."
FACT_LABEL = "read by the tool, not reviewed"
ASIS = (("stack.java_version", "Java"), ("stack.app_framework", "Framework"), ("stack.spring_boot_version", "Spring Boot"), ("stack.build_tool", "Build tool"),
        ("build_ci.ci_system", "CI system"), ("stack.artifact_kind", "Kind"))


def effective(r, o):
    """What a resolved outcome counts as (8.4): cls pass | na | gap | neutral | possible, whether it is a problem found, its
    severity, and whether a person stated it."""
    out = o["outcome"]
    st = {"confirmed": r["state"], "corrected": o.get("state"), "team_stated": o.get("state"), "gap_stated": "GAP"}.get(out)
    sev = r["sev"] if out == "confirmed" else r["ctl"].get("severity", "medium")
    if out == "confirmed" and r["possible"]:
        cls = "possible"
    else:
        cls = {"PRESENT": "pass", "NOT_APPLICABLE": "na", "ABSENT": "gap", "PARTIAL": "gap", "ISSUE": "gap", "GAP": "gap"}.get(st, "neutral")
    return {"cls": cls, "state": st, "issue": cls == "gap" and st == "ISSUE", "high": cls == "gap" and (st == "ISSUE" or sev in RV.HIGH),
            "stated": out in ("corrected", "team_stated", "gap_stated"), "sev": sev}


def cell(rows):
    """The aspect cell, first rule that applies (8.6). rows: [(result, outcome or None)] of results that count (y)."""
    y = len(rows)
    done = [(r, o, effective(r, o)) for r, o in rows if o]
    if y == 0:
        return "Not checked"
    if any(e["high"] for _, _, e in done):
        return "High gaps"
    if any(e["cls"] == "gap" for _, _, e in done):
        return "Gaps"
    if len(done) < y:
        return "Reviewed %d of %d" % (len(done), y)
    if all(e["cls"] == "na" for _, _, e in done):
        return "Not applicable"
    if not any(e["cls"] == "pass" for _, _, e in done):
        return "Reviewed, nothing confirmed"
    if any(e["cls"] in ("neutral", "possible") for _, _, e in done):
        return "Partly confirmed"
    if any(e["cls"] == "pass" and e["stated"] for _, _, e in done):
        return "In place (stated)"
    return "In place"


def _shown(r, o, rv):
    """One result in the client file: its outcome in the 8.4 words; the tool's own result only when a person confirmed it."""
    d = {"key": r["key"], "title": r["title"], "outcome": o["outcome"] if o else "none", "evidence": [], "searched": None, "remedies": [], "remedy_label": None, "detail": None,
         "reference": None, "note": None, "reason": None, "who": None}
    if not o:
        d["text"] = "Not reviewed"
        return d
    e = effective(r, o)
    out = o["outcome"]
    if out == "confirmed":
        d["text"] = "Possible issue" if r["possible"] else "Not seen here" if r["not_seen"] else RV.STATE_LABEL.get(r["state"], r["state"])
        d["mode"], d["detail"] = RV.mark_text(o), r["summary"]
        d["evidence"] = [{"at": "%s:%s" % (x.get("path"), x.get("line_start")) if x.get("kind") == "file" else (x.get("cmd") or ""), "line": x.get("snippet") or ""} for x in r.get("evidence") or []]
        d["searched"] = r.get("searched")
    elif out == "corrected":
        d["text"] = "Corrected by the consultant: %s" % RV.STATE_LABEL.get(o["state"], o["state"])
    elif out == "gap_stated":
        d["text"] = "Gap stated by the consultant"
    elif out == "disputed":
        d["text"] = "Disputed by the consultant"
    elif out == "cannot_confirm":
        d["text"] = "Not reviewed: could not be confirmed"
    elif out == "team_stated":
        d["text"] = "Stated by the team: %s" % o["answer"]
        d["who"] = "%s, %s" % (o.get("who"), o["at"][:10])
        if e["cls"] == "pass":
            d["mode"] = "In place (stated)"
    if out != "cannot_confirm":
        d["reason"] = RV.REASONS.get(o.get("reason"), ("",))[0] or None
        d["note"] = o.get("note")
        d["person_evidence"] = o.get("evidence")
    if r.get("reference") and out == "confirmed":
        ref = r["reference"]
        d["reference"] = "support dates: reference data %s, as of %s" % (ref.get("status"), ref.get("as_of"))
    if e["cls"] == "gap" and out in ("confirmed", "corrected", "gap_stated", "team_stated"):
        rem = r.get("remedies") or [] if out == "confirmed" else A.remedies_for(r["ctl"], rv.packs, rv._context(r["app"])[0])
        d["remedies"] = [{"id": "%s:%s" % (x["pack"], x["key"]), "title": x["title"], "cmd": x.get("cmd"), "does": x.get("does")} for x in rem]
        d["remedy_label"] = None if out == "confirmed" and o.get("remedy_confirmed") else "suggested, not reviewed"
    return d


def model(rv, unavailable=(), at=None):
    at = at or RV.now()
    must = set(rv.must())
    apps, shown = [], []
    for app in rv.scope:
        doc = rv.docs[app]
        fails = sorted({f.split(":")[0].strip() for f in doc.get("failures") or []})
        keys = [k for k in rv.results if rv.results[k]["app"] == app]
        if app in unavailable:
            apps.append({"app": app, "status": "na_verify", "label": "Not available: verification failed"})
            continue
        if fails:
            apps.append({"app": app, "status": "na_analysis", "label": "Not available: analysis incomplete (%s failed)" % ", ".join(fails)})
            continue
        if any(k in must and not rv.resolved(k) for k in keys):
            apps.append({"app": app, "status": "not_yet", "label": "Not yet reviewed"})
            continue
        res = lambda k: rv.doc["outcomes"][k] if rv.doc["outcomes"].get(k) and not rv.expired(rv.doc["outcomes"][k], at) else None  # noqa: E731
        aspects, counts = [], {"issues": 0, "high": 0, "gaps": 0, "disputes": 0, "cannot": 0, "high_aspects": 0}
        for asp in doc["aspects"]:
            rows = []
            for c in asp["controls"]:
                k = "%s::%s" % (app, c["id"])
                r = rv.results.get(k)
                if not r or r["state"] == "NOT_ASSESSED" or (r["possible"] and not res(k)):
                    continue  # not checked by this run, or a possible issue nobody reviewed: absent and not counted (D9)
                rows.append((r, res(k)))
            c_ = cell(rows)
            for r, o in rows:
                if o:
                    e = effective(r, o)
                    counts["issues"] += e["issue"]
                    counts["high"] += e["high"]
                    counts["gaps"] += e["cls"] == "gap"
                    counts["disputes"] += o["outcome"] == "disputed"
                    counts["cannot"] += o["outcome"] == "cannot_confirm"
            counts["high_aspects"] += c_ == "High gaps"
            aspects.append({"id": asp["id"], "title": asp["title"], "cell": c_, "results": [_shown(r, o, rv) for r, o in rows]})
        disc = rv._context(app)[1]
        facts = []
        for path, label in ASIS:
            v = A._fact(disc, path).get("value")
            if isinstance(v, dict):
                v = " ".join(str(x) for x in (v.get("label") or v.get("name"), v.get("version")) if x)
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v)
            if v not in (None, "", [], {}):
                facts.append({"label": label, "value": str(v)})
        a = {"app": app, "status": "shown", "label": "Reviewed", "counts": counts, "aspects": aspects, "facts": facts}
        apps.append(a)
        shown.append(a)
    # ranking (8.6): only reviewed applications; those whose gaps are all disputed or not confirmable come after those with results
    order = sorted(shown, key=lambda a: (0 if a["counts"]["gaps"] else 1, -a["counts"]["issues"], -a["counts"]["high"], -a["counts"]["high_aspects"], a["app"]))
    rank = {a["app"]: i for i, a in enumerate(order)}
    apps.sort(key=lambda a: (0, rank[a["app"]]) if a["app"] in rank else (1, a["app"]))
    findings, remedies = {}, {}
    for a in shown:
        for asp in a["aspects"]:
            for r, d in ((rv.results[d["key"]], d) for d in asp["results"]):
                o = rv.doc["outcomes"].get(r["key"]) if d["outcome"] != "none" else None
                if o and effective(r, o)["cls"] == "gap":
                    f = findings.setdefault(r["id"], {"control": r["id"], "title": r["title"], "aspect": asp["title"], "apps": 0})
                    f["apps"] += 1
                    for x in d["remedies"]:
                        m = remedies.setdefault(x["id"], {"id": x["id"], "title": x["title"], "cmd": x["cmd"], "gaps": 0, "apps": set()})
                        m["gaps"] += 1
                        m["apps"].add(a["app"])
    st = {"n": len(shown), "m": len(rv.scope), "k": sum(1 for a in apps if a["status"] == "not_yet"), "j": sum(1 for a in apps if a["status"].startswith("na_"))}
    reviewers = sorted(set(rv.doc["reviewers"]) | {o["reviewer"] for o in rv.doc["outcomes"].values()} | ({rv.doc["auditor"]} if rv.audited() else set()))
    out_of_scope = sorted(set(rv.docs) - set(rv.scope))
    pending = [c["title"] for c in rv.cat["controls"] if "pending" in c["source"]]
    not_run = sorted({r["title"] for r in rv.results.values() if r["state"] == "NOT_ASSESSED" and not rv.docs[r["app"]].get("failures")})
    outside = [c["title"] for c in rv.cat["controls"] if c.get("usually_outside") and "pending" not in c["source"]]
    possible = sum(1 for k, r in rv.results.items() if r["possible"] and not rv.doc["outcomes"].get(k))
    ref = A.reference_status()
    return {"client": rv.run.get("client"), "run": rv.doc["run"], "generated": RV.iso(at),
            "statement": {"apps": len(rv.scope), "chosen_by": rv.doc["scope"]["chosen_by"], "reviewers": reviewers, "audited": rv.audited(),
                          "auditor": rv.doc.get("auditor") if rv.audited() else None,
                          "firings": [{"at": f["at"][:10], "controls": [rv.ctl.get(c, {}).get("title", c) for c in f["controls"]], "outcomes": len(f["outcomes"]),
                                       "from_run": f.get("from_run"), "cleared": f["cleared"]} for f in rv.firings_all],
                          "date": RV.iso(at)[:10]},
            "summary": st, "apps": apps, "out_of_scope": out_of_scope,
            "findings": sorted(findings.values(), key=lambda f: (-f["apps"], f["title"])),
            "remedies": sorted(({**m, "apps": len(m["apps"])} for m in remedies.values()), key=lambda m: (-m["gaps"], m["title"])),
            "not_looked_at": {"no_detector": pending, "not_run": not_run, "usually_outside": outside, "possible_issues": possible,
                              "reference": "support dates: reference data %s, as of %s (%s)" % (ref["status"], ref["as_of"], ref["source"])}}


# ---------- rendering ----------

def _e(v):
    return html.escape(str(v if v is not None else ""), quote=True)


CSS = """.cf{max-width:1180px;margin:0 auto;padding:22px}.cf h1{font-size:22px;margin:0 0 4px}.cf h2{font-size:15px;margin:18px 0 8px}.cf h3{font-size:14px;margin:14px 0 6px}
.cf .card{padding:14px;margin-top:12px}.cf .tiny{color:#6e819e;font-size:11px}.cf pre{white-space:pre-wrap;background:#f6f9fd;border-radius:6px;padding:6px 8px;margin:4px 0;font-size:11px}
.cf .cell{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700;background:#eef2f7;color:#41566f}.cf .cell.hg{background:#fff0e0;color:#a65a00;border:1px solid #f0a040}
.cf .cell.g{background:#fff7e7;color:#8a6200}.cf .cell.ok{background:#e7f9f1;color:#16986a}.cf table{width:100%;border-collapse:collapse}.cf th,.cf td{text-align:left;padding:6px 8px;border-bottom:1px solid #edf2f7;vertical-align:top;font-size:12px}
.cf li.res{margin:8px 0;list-style:none}.cf ul{padding-left:0}.cf .out{font-weight:700}"""


def _cls(label):
    return "hg" if label == "High gaps" else "g" if label == "Gaps" else "ok" if label.startswith("In place") else ""


def render(m):
    s, st = [], m["statement"]
    a_ = s.append
    a_('<!doctype html><html lang="en" data-generated="%s"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">' % _e(m["generated"]))
    a_("<title>app-insight · client file</title><style>%s\n%s</style></head><body><div class=\"cf\">" % (R._ui("theme.css"), CSS))
    a_("<h1>%s: reviewed applications</h1><p class=\"tiny\">Run %s · %s</p>" % (_e(m["client"]), _e(m["run"]), _e(st["date"])))
    a_('<section class="card" id="statement"><h2>Review statement</h2><ul>')
    a_('<li>Scope: %d application(s), chosen by: %s</li>' % (st["apps"], _e(st["chosen_by"])))
    a_('<li>Reviewed by: %s</li>' % _e(", ".join(st["reviewers"])))
    a_('<li data-audited="%s">Audited by a second person: %s</li>' % ("yes" if st["audited"] else "no", "yes (%s)" % _e(st["auditor"]) if st["audited"] else "no"))
    if st["firings"]:
        for f in st["firings"]:
            a_('<li>Stop rule fired %s on %s (%d outcome(s) that count as a tool error)%s; every result of those controls was then reviewed one by one</li>' % (
                _e(f["at"]), _e(", ".join(f["controls"])), f["outcomes"], " (carried from run %s)" % _e(f["from_run"]) if f["from_run"] else ""))
    else:
        a_("<li>Stop rule: did not fire</li>")
    a_("<li>Date: %s</li><li>%s</li></ul></section>" % (_e(st["date"]), _e(MARKER)))
    sm = m["summary"]
    a_('<section class="card"><h2>Applications</h2><p class="summary-row" data-n="%d" data-m="%d" data-k="%d" data-j="%d">%d of %d applications in scope shown; %d not yet reviewed; %d not available</p>' % (
        sm["n"], sm["m"], sm["k"], sm["j"], sm["n"], sm["m"], sm["k"], sm["j"]))
    first = next((a for a in m["apps"] if a["status"] == "shown"), None)
    heads = [x["title"] for x in first["aspects"]] if first else []
    a_("<div class=\"table-scroll\"><table><thead><tr><th>Application</th><th>Status</th><th>Problems found</th><th>High gaps</th><th>Gaps</th><th>Disputes</th>%s</tr></thead><tbody>" % "".join("<th>%s</th>" % _e(h) for h in heads))
    for a in m["apps"]:
        if a["status"] != "shown":
            a_('<tr data-app="%s" data-status="%s"><td>%s</td><td colspan="%d">%s</td></tr>' % (_e(a["app"]), a["status"], _e(a["app"]), 5 + len(heads), _e(a["label"])))
            continue
        c = a["counts"]
        a_('<tr data-app="%s" data-status="shown" data-issues="%d" data-high="%d" data-gaps="%d" data-disputes="%d"><td><a href="#app-%s">%s</a></td><td>Reviewed</td><td>%d</td><td>%d</td><td>%d</td><td>disputes: %d</td>%s</tr>' % (
            _e(a["app"]), c["issues"], c["high"], c["gaps"], c["disputes"], _e(a["app"]), _e(a["app"]), c["issues"], c["high"], c["gaps"], c["disputes"],
            "".join('<td data-row="%s" data-aspect="%s" data-cell="%s"><span class="cell %s">%s</span></td>' % (_e(a["app"]), _e(x["id"]), _e(x["cell"]), _cls(x["cell"]), _e(x["cell"])) for x in a["aspects"])))
    a_("</tbody></table></div>")
    if m["out_of_scope"]:
        a_('<details data-out-of-scope="%d"><summary>Not in this review: %d application(s)</summary><p>%s</p></details>' % (
            len(m["out_of_scope"]), len(m["out_of_scope"]), ", ".join('<span data-oos="%s">%s</span>' % (_e(x), _e(x)) for x in m["out_of_scope"])))
    a_("</section>")
    if m["findings"]:
        a_('<section class="card"><h2>Gaps across the reviewed applications</h2><table><thead><tr><th>Control</th><th>Aspect</th><th>Applications</th></tr></thead><tbody>')
        for f in m["findings"]:
            a_('<tr data-control="%s" data-apps="%d"><td>%s</td><td>%s</td><td>%d</td></tr>' % (_e(f["control"]), f["apps"], _e(f["title"]), _e(f["aspect"]), f["apps"]))
        a_("</tbody></table></section>")
    if m["remedies"]:
        a_('<section class="card"><h2>Remedies for the reviewed gaps</h2><table><thead><tr><th>Remedy</th><th>Gaps it addresses</th><th>Applications</th></tr></thead><tbody>')
        for x in m["remedies"]:
            a_('<tr data-remedy="%s" data-gaps="%d" data-apps="%d"><td>%s%s</td><td>%d</td><td>%d</td></tr>' % (
                _e(x["id"]), x["gaps"], x["apps"], "<code>%s</code> " % _e(x["cmd"]) if x["cmd"] else "", _e(x["title"]), x["gaps"], x["apps"]))
        a_("</tbody></table></section>")
    for a in m["apps"]:
        if a["status"] != "shown":
            continue
        a_('<section class="card" id="app-%s" data-app-detail="%s"><h2>%s</h2>' % (_e(a["app"]), _e(a["app"]), _e(a["app"])))
        if a["facts"]:
            a_('<p class="tiny">%s · <i>%s</i></p>' % (" · ".join("%s: %s" % (_e(f["label"]), _e(f["value"])) for f in a["facts"]), FACT_LABEL))
        for x in a["aspects"]:
            a_('<h3>%s <span class="cell %s">%s</span></h3><ul>' % (_e(x["title"]), _cls(x["cell"]), _e(x["cell"])))
            for d in x["results"]:
                a_(_result(d))
            a_("</ul>")
        a_("</section>")
    nl = m["not_looked_at"]
    a_('<section class="card" id="scope"><h2>What was not looked at</h2><ul>')
    a_("<li>Controls with no detector yet (%d): %s</li>" % (len(nl["no_detector"]), _e(", ".join(nl["no_detector"])) or "none"))
    a_("<li>Tool runs not done: %s</li>" % (_e(", ".join(nl["not_run"])) or "none"))
    a_("<li>Usually set outside the repository, confirmed with the team or the consultant: %s</li>" % (_e(", ".join(nl["usually_outside"])) or "none"))
    a_('<li data-possible="%d">Possible issues not reviewed, not shown and not counted: %d</li>' % (nl["possible_issues"], nl["possible_issues"]))
    a_("<li>%s</li></ul></section>" % _e(nl["reference"]))
    a_("</div></body></html>\n")
    return "".join(s)


def _result(d):
    if d["outcome"] == "none":
        return '<li class="res" data-key="%s" data-outcome="none"><b>%s</b>: <span class="out">Not reviewed</span></li>' % (_e(d["key"]), _e(d["title"]))
    p = ['<li class="res" data-key="%s" data-outcome="%s" data-remedies="%s"><b>%s</b>: <span class="out">%s</span>' % (
        _e(d["key"]), _e(d["outcome"]), _e(",".join(x["id"] for x in d["remedies"])), _e(d["title"]), _e(d["text"]))]
    if d.get("mode"):
        p.append(' <span class="tiny">(%s)</span>' % _e(d["mode"]))
    if d.get("detail"):
        p.append('<div class="tiny">%s</div>' % _e(d["detail"]))
    for ev in d["evidence"]:
        p.append('<div class="tiny">%s</div><pre>%s</pre>' % (_e(ev["at"]), _e(ev["line"])))
    if d.get("searched"):
        s = d["searched"]
        p.append('<div class="tiny">Searched for %s in %s</div>' % (_e(s.get("for")), _e(", ".join("%s (%s file%s)" % (w["area"], w.get("count", 0), "" if w.get("count") == 1 else "s") for w in s.get("in") or []))))
    for k, lbl in (("reason", "Reason"), ("note", "Note"), ("who", "Stated by"), ("person_evidence", "Evidence")):
        if d.get(k):
            p.append('<div class="tiny">%s: %s</div>' % (lbl, _e(d[k])))
    if d.get("reference"):
        p.append('<div class="tiny">%s</div>' % _e(d["reference"]))
    if d["remedies"]:
        p.append('<div class="tiny">Remedy%s: %s</div>' % (" (%s)" % _e(d["remedy_label"]) if d["remedy_label"] else "", "; ".join(
            ("<code>%s</code> " % _e(x["cmd"]) if x["cmd"] else "") + _e(x["title"]) for x in d["remedies"])))
    p.append("</li>")
    return "".join(p)


# ---------- publishing (8.8) ----------

def publish(rv, at=None):
    """Write the client file under a temporary name, verify it, and only then give it its name. A run-level failure deletes it; a
    per-application failure makes that application "Not available: verification failed" and the file is regenerated."""
    at = at or RV.now()
    refused = rv.blockers()
    if refused:
        return {"ok": False, "refused": refused, "problems": []}
    rd = rv.run_dir
    pending, final = os.path.join(rd, PENDING), os.path.join(rd, NAME)
    unavailable = set()
    for _ in range(len(rv.scope) + 1):
        RV.atomic_write(pending, render(model(rv, unavailable, at)))
        rv.save()
        res = V.check(rd, rv.cat)
        probs = res["problems"] + V.check_client(rd, pending, rv.cat)["problems"]
        run_level = [p for p in probs if V.client_level(p["rule"]) == "run"]
        per_app = {p["app"] for p in probs if V.client_level(p["rule"]) == "app" and p["app"] in rv.scope} - unavailable
        if run_level:
            os.remove(pending)
            # which file and rule failed, never the value (the details name a place, not what is there)
            return {"ok": False, "refused": [], "problems": [{"rule": p["rule"], "where": p["app"], "control": p["control"]} for p in run_level]}
        if per_app:
            unavailable |= per_app
            continue
        os.replace(pending, final)
        rec = {"file": NAME, "at": RV.iso(at), "not_available_verify": sorted(unavailable), "verify": {"ok": True, "checked": res["checked"]}}
        RV.atomic_write(os.path.join(rd, "client-verify.json"), json.dumps({"ok": True, "checked": res["checked"], "not_available_verify": sorted(unavailable),
                                                                          "per_app_problems": [{"rule": p["rule"], "app": p["app"], "control": p["control"]} for p in probs if p["app"] in unavailable]}, indent=1, sort_keys=True))
        rv.doc["published"] = rec
        rv.save()
        return {"ok": True, "path": final, "not_available": sorted(unavailable), "problems": []}
    os.remove(pending)
    return {"ok": False, "refused": ["verification did not settle"], "problems": []}
