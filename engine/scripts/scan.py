#!/usr/bin/env python3
"""Opt-in vulnerability scan. Adds `security.vulnerability_scan` to an existing discovery.json.

  scan.py --repo REPO --discovery <dir or discovery.json> [--skip-db-update]

Kept apart from discover.py on purpose: discover.py is offline and reproducible, a scan is neither (the scanner
downloads its vulnerability database, and the same code gets new findings over time). Uses Trivy, which runs
locally and uploads nothing. A zero is only reported when Trivy actually analysed a dependency manifest; if it
found none (typical for Gradle without a lockfile) the result is `could_not_scan`, never "0 vulnerabilities".
Exit codes: 0 scanned, 1 could not scan (written), 2 could not run.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evidence  # noqa: E402
import validate  # noqa: E402

SEV = ("critical", "high", "medium", "low")
SKIP = ("build", "target", ".gradle", "node_modules", ".git")


def trivy_version() -> dict:
    rc, out = evidence.run(["trivy", "version", "--format", "json"], ".", 20)
    try:
        d = json.loads(out)
        return {"version": d.get("Version"), "db_updated": (d.get("VulnerabilityDB") or {}).get("UpdatedAt")}
    except ValueError:
        return {"version": None, "db_updated": None}


def scan(repo: str, skip_db_update: bool, tmp: str) -> dict:
    cmd = ["trivy", "fs", "--scanners", "vuln", "--format", "json", "--quiet", "--output", tmp]
    if skip_db_update:
        cmd.append("--skip-db-update")
    for d in SKIP:
        cmd += ["--skip-dirs", d]
    cmd.append(".")
    rc, out = evidence.run(cmd, repo, 600)
    info = trivy_version()
    base = {"tool": "Trivy", "tool_version": info["version"], "db_updated": info["db_updated"],
            "scanned_at": os.environ.get("DISCOVERY_FIXED_TIME") or
            datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "command": " ".join(cmd)}
    try:
        with open(tmp, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return dict(base, state="failed", reason="Trivy did not produce a report (exit %s)." % rc)
    results = doc.get("Results") or []
    targets = sorted(r.get("Target", "") for r in results)
    if not targets:
        return dict(base, state="could_not_scan", targets=[],
                    reason="No dependency manifest Trivy can read (Gradle needs gradle.lockfile)")
    sev = [str(v.get("Severity", "")).lower() for r in results for v in (r.get("Vulnerabilities") or [])]
    ids = sorted({v.get("VulnerabilityID") for r in results for v in (r.get("Vulnerabilities") or []) if v.get("VulnerabilityID")})
    return dict(base, state="scanned", targets=targets, total=len(sev), vulnerability_ids=ids,
                **{k: sev.count(k) for k in SEV})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--discovery", required=True)
    ap.add_argument("--skip-db-update", action="store_true")
    a = ap.parse_args(argv)
    path = os.path.join(a.discovery, "discovery.json") if os.path.isdir(a.discovery) else a.discovery
    if not os.path.isdir(a.repo) or not os.path.isfile(path):
        print("repo or discovery.json not found", file=sys.stderr)
        return 2
    if evidence.run(["trivy", "--version"], ".", 20)[0] != 0:
        print("trivy is not installed", file=sys.stderr)
        return 2
    tmp = path + ".trivy.tmp"
    res = scan(os.path.abspath(a.repo), a.skip_db_update, tmp)
    if os.path.exists(tmp):
        os.remove(tmp)
    doc = json.load(open(path, encoding="utf-8"))
    ok = res["state"] == "scanned"
    summary = ("%s %s, db %s: %s" % (res["tool"], res["tool_version"], res["db_updated"],
               ("%d vulnerabilities" % res["total"]) if ok else res.get("reason", "")))
    doc["security"]["vulnerability_scan"] = evidence.fact(
        res, "CONFIRMED" if ok else "UNKNOWN", [evidence.cmd_ev(["trivy", "fs"], summary)],
        "opt-in scan (scan.py); results change as the vulnerability database changes")
    doc["run_meta"]["fingerprint"] = validate.fingerprint(doc)
    errs = validate.validate(doc)
    if errs:
        print("\n".join("INVALID: " + e for e in errs), file=sys.stderr)
        return 2
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(path + ".tmp", path)
    print("━━ APP-DISCOVERY-SCAN ━━\nstate: %s\n%s" % (res["state"], summary))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
