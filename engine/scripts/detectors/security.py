from __future__ import annotations

import json
import os
import re

from evidence import fact, file_ev, grep_files, read_lines, run, walk

# category -> regex over CI files, build files and tool config. Tool names follow registry/dod.yaml.
CATEGORIES = {
    "secret_scanning": r"gitguardian|ggshield|gitleaks|trufflehog|Security/Secret-Detection",
    "dependency_scanning": r"\bsnyk\b(?![-_ ]code)|dependency-?check|Security/Dependency-Scanning|\bosv-scanner\b|\btrivy\b|dependency-review-action|\bfossa",
    "cloud_scanning": r"\bwiz(cli|-cli)?\b|prisma.?cloud|\bcheckov\b",
    # codeql-action/upload-sarif only uploads someone else's report (OpenSSF Scorecard, CIFuzz); it is not an analysis
    "sast": r"sonar|semgrep|codeql(?!-action/upload-sarif)|Security/SAST|spotbugs|find-sec-bugs|snyk[-_ ]code",
}
PATH_ONLY = re.compile(r"cache|~/|/reports/|destination|store_artifacts|\.html\b", re.I)
CONFIG_FILES = (".github/dependabot.yml", "renovate.json", ".snyk", ".gitguardian.yml",
                ".gitleaks.toml", "sonar-project.properties")


VERSION = "0.4.0"

UPDATE_FILES = (".github/dependabot.yml", ".github/dependabot.yaml", "renovate.json", "renovate.json5", ".renovaterc",
                ".renovaterc.json", ".github/renovate.json", ".github/renovate.json5")

SEVERITIES = ("critical", "high", "medium", "low")
# basename pattern -> (tool label, extractor of severity strings from the parsed JSON)
REPORTS = (
    (re.compile(r"^dependency-check-report\.json$"), "OWASP Dependency-Check",
     lambda d: [v.get("severity") for x in d.get("dependencies", []) for v in x.get("vulnerabilities", [])]),
    (re.compile(r"^gl-(dependency|container)-scanning-report\.json$"), "GitLab scanning",
     lambda d: [v.get("severity") for v in d.get("vulnerabilities", [])]),
    (re.compile(r"^snyk[\w.-]*\.json$"), "Snyk",
     lambda d: [v.get("severity") for v in (d.get("vulnerabilities") or [])]),
    (re.compile(r"^trivy[\w.-]*\.json$"), "Trivy",
     lambda d: [v.get("Severity") for r in (d.get("Results") or []) for v in (r.get("Vulnerabilities") or [])]),
)


def _reports(ctx) -> dict:
    """Vulnerability scanner reports already on disk. Parsed, never produced: this scan runs no scanner."""
    r, found = ctx.repo, []
    head = run(["git", "log", "-1", "--format=%ct"], r)
    for rel in walk(r, include_build=True):
        for rx, tool, pick in REPORTS:
            if not rx.match(os.path.basename(rel)):
                continue
            lines = read_lines(r, rel)
            try:
                doc = json.loads("\n".join(lines or []))
                sev = [str(x or "").lower().replace("moderate", "medium") for x in pick(doc)]
            except (ValueError, AttributeError, TypeError):
                continue
            counts = {k: sev.count(k) for k in SEVERITIES}
            stale = bool(head[0] == 0 and head[1].isdigit() and os.path.getmtime(os.path.join(r, rel)) < int(head[1]))
            found.append((rel, lines, dict(counts, total=len(sev), tool=tool, path=rel, stale=stale)))
    if not found:
        return fact([], "NOT_FOUND", [], "no scanner report on disk; this scan does not run a vulnerability scanner")
    stale = any(x[2]["stale"] for x in found)
    return fact([x[2] for x in found], "INFERRED" if stale else "CONFIRMED",
                [file_ev(x[0], 1, (x[1] or [""])[0]) for x in found][:3],
                ("STALE: a report is older than the HEAD commit. " if stale else "")
                + "parsed from a report already on disk; not produced by this scan")


PIPELINE_CATS = ('secret_scanning', 'dependency_scanning', 'sast')


def detect(ctx) -> dict:
    r = ctx.repo
    cfg = sorted(set(ctx.ci_files + ctx.build_files + [f for f in ctx.files if f in CONFIG_FILES]))
    unres = ctx.unresolved_ci_includes()
    out = {}
    for cat, rx in CATEGORIES.items():
        # a tool name inside a cache dir / report path is not the tool being run
        hits = [e for f in cfg for e in grep_files(r, [f], rx, 10) if not PATH_ONLY.search(e["snippet"])]
        seen, ev = set(), []
        for e in hits:  # one hit per file
            if e["path"] not in seen:
                seen.add(e["path"])
                ev.append(e)
        ev = ev[:3]
        if not ev:  # tool config files are evidence by name alone
            ev = [file_ev(f, 1, (read_lines(r, f) or [""])[0]) for f in cfg if re.search(rx, f)][:3]
        if cat in PIPELINE_CATS:
            # configured is not the same as run: only a hit inside a CI file shows the pipeline invokes the tool
            ci_hits = [e for e in hits if e["path"] in set(ctx.ci_files)][:3]
            out[cat + "_in_pipeline"] = fact(True, "CONFIRMED", ci_hits) if ci_hits else \
                fact(False, "UNKNOWN" if unres else "NOT_FOUND", unres[:2] if unres else [],
                     "the tool may live in an included remote template" if unres else
                     "no CI file invokes it" + ("; it is configured in build or tool files only" if ev else ""))
        if ev:
            out[cat] = fact(True, "CONFIRMED", ev)
        elif unres:
            out[cat] = fact(False, "UNKNOWN", unres[:2], "tool may live in an included remote template")
        else:
            out[cat] = fact(False, "NOT_FOUND", [])
    upd = [f for f in UPDATE_FILES if f in ctx.fileset]
    out["dependency_updates"] = fact(True, "CONFIRMED", [file_ev(f, 1, (read_lines(r, f) or [""])[0]) for f in upd[:3]]) if upd \
        else fact(False, "NOT_FOUND", [], "no Dependabot or Renovate config file; it may still be enabled in the hosting platform")
    out["vulnerability_reports"] = _reports(ctx)
    return out
