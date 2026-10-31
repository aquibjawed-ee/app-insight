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

VERSION = "0.1.0"
DEFAULT_PACKS = ["generic"]


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
        per_aspect.append({"aspect": asp["title"], "issues": c.get("issues", 0), "gaps": c.get("gaps", 0), "in_place": c.get("in_place", 0), "not_assessed": c.get("not_assessed", 0), "not_applicable": c.get("not_applicable", 0)})
    top = {}
    for app in apps:
        doc = _read(os.path.join(out, app, "aspects.json"))
        for asp in doc["aspects"]:
            for ctl in asp["controls"]:
                if ctl["finding"]:
                    t = top.setdefault(ctl["id"], {"control": ctl["title"], "aspect": asp["title"], "severity": ctl["severity"], "state": ctl["state"], "apps": 0, "remedies": sorted({r.get("cmd") or r["title"] for r in ctl["remedies"]})})
                    t["apps"] += 1
    findings = sorted(top.values(), key=lambda x: (A.SEVERITY_ORDER.get(x["severity"], 9), -x["apps"], x["control"]))
    return {"client": run["client"], "run": os.path.basename(run_dir), "applications": len(apps), "failed_sources": [s for s in run["sources"] if s["status"] == "failed"],
            "aspects": per_aspect, "top_findings": findings[:15], "report": os.path.join(run_dir, "report.html"), "remedy_packs": run["remedy_packs"]}


def print_summary(s):
    print("━━ APP-INSIGHT-SUMMARY ━━")
    print("client:        %s" % s["client"])
    print("run:           %s" % s["run"])
    print("applications:  %d analysed, %d source(s) failed" % (s["applications"], len(s["failed_sources"])))
    for f in s["failed_sources"]:
        print("  failed:      %s (%s)" % (f["spec"], f["error"]))
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
    ok = [s for s in srcs if s.path and s.status != "failed"]
    run = {"contract": "app-insight-run.v1", "tool_version": VERSION, "client": a.client, "started_at": _now().isoformat(), "inputs": a.inputs,
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
    A.build(out, A.load_catalogue(), packs)
    R.build(out, os.path.join(run_dir, "report.html"), A.load_catalogue(), packs, run["sources"], a.client)
    run["finished_at"] = _now().isoformat()
    run["analysis_rc"] = rc
    _write(os.path.join(run_dir, "run.json"), run)
    with open(os.path.join(ws, "latest"), "w") as fh:
        fh.write(stamp)
    s = summarise(run_dir)
    print_summary(s) if not a.json else print(json.dumps(s, indent=1))
    return 0 if rc == 0 else 1


def cmd_sources(a):
    for s in SRC.expand(a.inputs):
        print("%s\t%s\t%s\t%s" % ("remote" if s.remote else "local", s.spec, s.branch or "", s.slug()))
    return 0


def _rebuild(run_dir, packs_override=None):
    run = _read(os.path.join(run_dir, "run.json"))
    if packs_override:
        run["remedy_packs"] = packs_override
        _write(os.path.join(run_dir, "run.json"), run)
    packs = A.load_remedy_packs(run["remedy_packs"])
    out = os.path.join(run_dir, "analysis")
    A.build(out, A.load_catalogue(), packs)
    R.build(out, os.path.join(run_dir, "report.html"), A.load_catalogue(), packs, run["sources"], run["client"])
    return run_dir


def cmd_aspects(a):
    run_dir = _rebuild(resolve_run(a.run), [x.strip() for x in a.remedies.split(",")] if a.remedies else None)
    print_summary(summarise(run_dir))
    return 0


def cmd_report(a):
    run_dir = _rebuild(resolve_run(a.run))
    print(os.path.join(run_dir, "report.html"))
    return 0


def cmd_summary(a):
    s = summarise(resolve_run(a.run))
    print(json.dumps(s, indent=1)) if a.json else print_summary(s)
    return 0


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
    p = sub.add_parser("doctor", help="check the local prerequisites")
    p.set_defaults(fn=cmd_doctor)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
