"""app-insight: AS-IS discovery and production-readiness assessment across an organisation's applications.

Deterministic and offline once repositories are on disk: no model decides a fact or a verdict, so any coding agent
(Claude Code, Codex, Gemini CLI) or a person can run it and get the same result. One workspace per client keeps
clones, runs and reports apart; nothing is sent anywhere.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys

from . import engine_path  # noqa: F401
from . import aspects as A
from . import report as R
from . import sources as SRC
from . import verify as V

VERSION = "0.1.0"
DEFAULT_PACKS = ["generic"]
# the client-use gate (design section 2): until results are validated and reviewed, every report is for internal preparation
GATE = "Internal: not validated"


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def workspace(a):
    root = os.path.abspath(os.path.expanduser(a.workspace or os.environ.get("APP_INSIGHT_HOME") or "~/app-insight-workspaces"))
    return os.path.join(root, a.client)


def client_config(ws, a):
    """client.json in the workspace remembers the remedy packs (and later, policy) per client; flags override it."""
    p = os.path.join(ws, "client.json")
    cfg = _read(p) if os.path.isfile(p) else {"client": a.client, "remedy_packs": DEFAULT_PACKS}
    if getattr(a, "remedies", None):
        cfg["remedy_packs"] = [x.strip() for x in a.remedies.split(",") if x.strip()]
    _write(p, cfg)
    return cfg


def resolve_run(path_or_ws):
    p = os.path.abspath(os.path.expanduser(path_or_ws))
    if os.path.isfile(os.path.join(p, "run.json")):
        return p
    latest = os.path.join(p, "latest")
    if os.path.isfile(latest):
        with open(latest) as fh:
            return os.path.join(p, "runs", fh.read().strip())
    raise SystemExit("no run found at %s (give a run directory or a client workspace)" % p)


def summarise(run_dir):
    run = _read(os.path.join(run_dir, "run.json"))
    out = os.path.join(run_dir, "analysis")
    port = _read(os.path.join(out, "portfolio", "aspects.json")) if os.path.isfile(os.path.join(out, "portfolio", "aspects.json")) else {"aspects": [], "applications": {}}
    apps = port["applications"]
    per_aspect = []
    for asp in port["aspects"]:
        c = {}
        for st in apps.values():
            c[st.get(asp["id"])] = c.get(st.get(asp["id"]), 0) + 1
        per_aspect.append({"aspect": asp["title"], "issues": c.get("issues", 0), "gaps": c.get("gaps", 0), "in_place": c.get("in_place", 0) + c.get("in_place_partly_checked", 0), "not_assessed": c.get("not_assessed", 0), "not_applicable": c.get("not_applicable", 0)})
    top = {}
    for app in apps:
        doc = _read(os.path.join(out, app, "aspects.json"))
        for asp in doc["aspects"]:
            for ctl in asp["controls"]:
                if ctl["finding"]:
                    t = top.setdefault(ctl["id"], {"control": ctl["title"], "aspect": asp["title"], "severity": ctl["severity"], "state": ctl["state"], "apps": 0, "remedies": sorted({r.get("cmd") or r["title"] for r in ctl["remedies"]})})
                    t["apps"] += 1
    findings = sorted(top.values(), key=lambda x: (A.SEVERITY_ORDER.get(x["severity"], 9), -x["apps"], x["control"]))
    fails = []
    for app in sorted(apps):  # a detector or step that failed: its controls are NOT_ASSESSED, and the run says so
        f = _read(os.path.join(out, app, "aspects.json")).get("failures") or []
        if f:
            fails.append({"app": app, "failed": f})
    vp = os.path.join(run_dir, "verify.json")
    ver = _read(vp) if os.path.isfile(vp) else None
    return {"client": run["client"], "run": os.path.basename(run_dir), "applications": len(apps), "failed_sources": [s for s in run["sources"] if s["status"] == "failed"],
            "gate": GATE, "verify": verify_digest(ver), "detector_failures": fails,
            "aspects": per_aspect, "top_findings": findings[:15], "report": os.path.join(run_dir, V.REPORT), "remedy_packs": run["remedy_packs"]}


def verify_digest(ver):
    """What a reader of the summary or the report needs from verify: passed or not, and which rules failed how often. No detail
    (a detail names a file and line), so it can sit in the report header."""
    if ver is None:
        return {"ok": None, "state": "not run", "failed_rules": {}}
    by = {}
    for p in ver["problems"]:
        by[p["rule"]] = by.get(p["rule"], 0) + 1
    return {"ok": ver["ok"], "state": "passed" if ver["ok"] else "FAILED", "failed_rules": {k: {"count": n, "rule": V.RULES.get(k, "")} for k, n in sorted(by.items())}}


def print_summary(s):
    print("━━ APP-INSIGHT-SUMMARY ━━")
    print("client:        %s" % s["client"])
    print("run:           %s" % s["run"])
    print("use:           %s" % s["gate"])
    v = s["verify"]
    print("verify:        %s%s" % (v["state"], "" if v["ok"] is not False else ": " + ", ".join("%s x%d" % (k, x["count"]) for k, x in v["failed_rules"].items())))
    print("applications:  %d analysed, %d source(s) failed" % (s["applications"], len(s["failed_sources"])))
    for f in s["failed_sources"]:
        print("  failed:      %s (%s)" % (f["spec"], f["error"]))
    for f in s["detector_failures"]:
        print("  not assessed: %s: %s failed; the controls it feeds are NOT_ASSESSED" % (f["app"], ", ".join(f["failed"])))
    print("remedy packs:  %s" % ", ".join(s["remedy_packs"]))
    print("aspects (apps with issues / gaps / in place / not assessed / n/a):")
    w = max([len(x["aspect"]) for x in s["aspects"]] + [10])
    for x in s["aspects"]:
        print("  %s  %3d / %3d / %3d / %3d / %3d" % (x["aspect"].ljust(w), x["issues"], x["gaps"], x["in_place"], x["not_assessed"], x["not_applicable"]))
    print("top findings (severity, applications, remedy):")
    for f in s["top_findings"]:
        print("  [%s] %s: %s (%d) -> %s" % (f["severity"], f["aspect"], f["control"], f["apps"], ", ".join(f["remedies"]) or "-"))
    print("report:        %s" % s["report"])
    print("━━ END ━━")


def cmd_scan(a):
    ws = workspace(a)
    cfg = client_config(ws, a)
    packs = A.load_remedy_packs(cfg["remedy_packs"])
    srcs = SRC.expand(a.inputs)
    if not srcs:
        print("no repositories in the inputs", file=sys.stderr)
        return 2
    stamp = _now().strftime("%Y%m%d-%H%M%S")
    run_dir = os.path.join(ws, "runs", stamp)
    out = os.path.join(run_dir, "analysis")
    print("app-insight %s: %d source(s) for client %s" % (VERSION, len(srcs), a.client), file=sys.stderr)
    done = [0]

    def progress(s):
        done[0] += 1
        print("  [%d/%d] %-8s %s%s" % (done[0], len(srcs), s.status, s.spec, (" (" + s.error + ")") if s.error else ""), file=sys.stderr)
    SRC.fetch_all(srcs, os.path.join(ws, "repos"), jobs=a.jobs, update=not a.no_update, progress=progress)
    pin(srcs, os.path.join(ws, "repos"), stamp)
    ok = [s for s in srcs if s.path and s.status != "failed"]
    run = {"contract": "app-insight-run.v1", "tool_version": VERSION, "client": a.client, "started_at": _now().isoformat(), "inputs": [SRC.mask(x) for x in a.inputs],
           "remedy_packs": cfg["remedy_packs"], "sources": [s.as_dict() for s in srcs]}
    _write(os.path.join(run_dir, "run.json"), run)
    if not ok:
        print("no repository could be read; see %s" % os.path.join(run_dir, "run.json"), file=sys.stderr)
        return 2
    import relate  # engine
    argv = ["analyse"] + [s.path for s in ok] + ["--out", out]
    for k in ("criticality", "profile", "aliases"):
        if getattr(a, k):
            argv += ["--" + k, getattr(a, k)]
    rc = relate.main(argv)
    if rc == 2:
        print("analysis failed before writing results; see the message above", file=sys.stderr)
        return 2
    man = _read(os.path.join(out, "manifest.json"))
    for f in man.get("failed") or []:  # a repository whose discovery broke: recorded with the reason, no row invented
        for src in run["sources"]:
            if src.get("path") and os.path.abspath(src["path"]) == f["repo"]:
                src["status"], src["error"] = "failed", "analysis failed (%s: %s)" % (f["step"], f["error"].split(":")[0])
    run["finished_at"] = _now().isoformat()
    run["analysis_rc"] = rc
    _write(os.path.join(run_dir, "run.json"), run)
    A.build(out, A.load_catalogue(), packs)
    ver = publish(run_dir, packs, run)
    if ver["ok"]:  # a run that failed verify never becomes the latest
        with open(os.path.join(ws, "latest"), "w") as fh:
            fh.write(stamp)
    else:
        print("verify failed: %s was not made the latest run; the report says FAILED in its header" % stamp, file=sys.stderr)
    s = summarise(run_dir)
    print_summary(s) if not a.json else print(json.dumps(s, indent=1))
    if not a.json:
        V.print_result(ver)
    return 0 if rc == 0 and ver["ok"] else 1


def pin(srcs, repos_dir, stamp):
    """Keep each run's commit in our own clones with a local ref, so a later rescan's shallow fetch cannot drop it and verify of
    this run can always re-read it offline (design 8.7). Only clones in the workspace: a local repository is never written to."""
    root = os.path.realpath(repos_dir) + os.sep
    for s in srcs:
        if s.remote and s.path and s.commit and os.path.realpath(s.path).startswith(root):
            SRC._git(["update-ref", "refs/app-insight/runs/" + stamp, s.commit], cwd=s.path, timeout=60)


def cmd_sources(a):
    for s in SRC.expand(a.inputs):
        print("%s\t%s\t%s\t%s" % ("remote" if s.remote else "local", s.spec, s.branch or "", s.slug()))
    return 0


def publish(run_dir, packs, run):
    """Verify first, then write the report: the page is rendered to a pending file, verify checks it with everything else the
    run wrote (citations, consistency, leaks), and only then is the report written, carrying the verify result in its header."""
    out, cat = os.path.join(run_dir, "analysis"), A.load_catalogue()
    pending = os.path.join(run_dir, "report.pending.html")
    R.build(out, pending, cat, packs, run["sources"], run["client"], verify=None, gate=GATE)
    try:
        ver = V.check(run_dir, cat, report_path=pending)
    finally:
        os.remove(pending)
    R.build(out, os.path.join(run_dir, V.REPORT), cat, packs, run["sources"], run["client"], verify=verify_digest(ver), gate=GATE)
    with open(os.path.join(run_dir, "verify.json"), "w", encoding="utf-8") as fh:
        json.dump(ver, fh, indent=1, sort_keys=True)
    return ver


def _rebuild(run_dir, packs_override=None):
    """Re-derive the trace with the current catalogue and packs. A run that has been reviewed (review.json) is never changed in
    place: the rebuild goes into a new run, so the reviewed one stays what was reviewed (design 8.7)."""
    if os.path.isfile(os.path.join(run_dir, "review.json")):
        new = os.path.join(os.path.dirname(run_dir), _now().strftime("%Y%m%d-%H%M%S") + "-rebuild")
        shutil.copytree(run_dir, new, ignore=shutil.ignore_patterns("review.json", "verify.json", "report*.html"))
        print("%s has been reviewed and is kept as it is; rebuilding into %s" % (os.path.basename(run_dir), os.path.basename(new)), file=sys.stderr)
        run_dir = new
    run = _read(os.path.join(run_dir, "run.json"))
    if packs_override:
        run["remedy_packs"] = packs_override
        _write(os.path.join(run_dir, "run.json"), run)
    packs = A.load_remedy_packs(run["remedy_packs"])
    A.build(os.path.join(run_dir, "analysis"), A.load_catalogue(), packs)
    return run_dir, publish(run_dir, packs, run)


def cmd_aspects(a):
    run_dir, ver = _rebuild(resolve_run(a.run), [x.strip() for x in a.remedies.split(",")] if a.remedies else None)
    print_summary(summarise(run_dir))
    V.print_result(ver)
    return 0 if ver["ok"] else 1


def cmd_report(a):
    """Re-render the report only, from the run's own aspects.json (AGENTS.md: rebuild the HTML only); it re-verifies."""
    run_dir = resolve_run(a.run)
    run = _read(os.path.join(run_dir, "run.json"))
    ver = publish(run_dir, A.load_remedy_packs(run["remedy_packs"]), run)
    print(os.path.join(run_dir, V.REPORT))
    if not ver["ok"]:
        V.print_result(ver)
    return 0 if ver["ok"] else 1


def cmd_summary(a):
    s = summarise(resolve_run(a.run))
    print(json.dumps(s, indent=1)) if a.json else print_summary(s)
    return 0


def cmd_verify(a):
    res = V.write(resolve_run(a.run))
    print(json.dumps(res, indent=1)) if a.json else V.print_result(res)
    return 0 if res["ok"] else 1


def cmd_doctor(a):
    ok = True
    print("python   %s" % sys.version.split()[0] + ("" if sys.version_info >= (3, 9) else "  (3.9 or newer needed)"))
    ok &= sys.version_info >= (3, 9)
    g = shutil.which("git")
    print("git      %s" % (subprocess.run(["git", "--version"], capture_output=True, text=True).stdout.strip() if g else "missing (needed for remote repositories)"))
    ok &= bool(g)
    print("engine   %s" % engine_path.ENGINE)
    print("packs    %s" % ", ".join(sorted(f.split(".")[0] for f in os.listdir(os.path.join(A.PACKS, "remedies")))))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="app-insight", description=__doc__.splitlines()[0])
    ap.add_argument("--version", action="version", version=VERSION)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan", help="fetch the repositories, analyse them and build the report")
    p.add_argument("inputs", nargs="+", help="repository paths, folders of repositories, remote URLs, or .csv/.tsv/.xlsx/.txt lists")
    p.add_argument("--client", required=True, help="client or organisation name; selects the workspace")
    p.add_argument("--workspace", help="root folder for client workspaces (default $APP_INSIGHT_HOME or ~/app-insight-workspaces)")
    p.add_argument("--remedies", help="comma-separated remedy packs, highest priority first (ids under packs/remedies or file paths); remembered per client")
    p.add_argument("--jobs", type=int, default=4, help="parallel clones")
    p.add_argument("--no-update", action="store_true", help="reuse existing clones without fetching")
    p.add_argument("--criticality", help="verified business-criticality file")
    p.add_argument("--profile", help="Spring profile to apply over the base configuration")
    p.add_argument("--aliases", help="host: application alias file")
    p.add_argument("--json", action="store_true", help="print the summary as JSON")
    p.set_defaults(fn=cmd_scan)
    p = sub.add_parser("sources", help="show how the inputs are read, without fetching anything")
    p.add_argument("inputs", nargs="+")
    p.set_defaults(fn=cmd_sources)
    p = sub.add_parser("aspects", help="rebuild the aspect trace and report for a run (after changing the catalogue or remedy packs)")
    p.add_argument("run", help="run directory, or a client workspace for its latest run")
    p.add_argument("--remedies")
    p.set_defaults(fn=cmd_aspects)
    p = sub.add_parser("report", help="rebuild the HTML report for a run")
    p.add_argument("run")
    p.set_defaults(fn=cmd_report)
    p = sub.add_parser("summary", help="print the summary of a run (for people and agents)")
    p.add_argument("run")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_summary)
    p = sub.add_parser("verify", help="re-check a run: every cited line against the repositories, every count against every other place it appears")
    p.add_argument("run")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("doctor", help="check the local prerequisites")
    p.set_defaults(fn=cmd_doctor)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
