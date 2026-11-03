"""The single-file HTML report for one run: AS-IS inventory, the aspect trace, findings, remedies and the roadmap.

Presentation only. Every number comes from the analysis files and aspects.json; C4 views are rendered from the
canonical graph by the engine. No network is used when building or opening the page.
"""
from __future__ import annotations

import json
import os
import re

from . import engine_path  # noqa: F401  (puts engine/scripts on sys.path)
from graph import c4  # noqa: E402

UI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
UI_JS = ["icons.js", "core.js", "shell.js", "aspects.js", "applications.js", "dashboard.js", "discovery.js", "assessment.js", "architecture.js", "findings.js",
         "roadmap.js", "impact.js", "about.js", "main.js"]
FULL_MAP_MAX = 12
# the maturity score and band are not carried: no combined score is shown (R-06); aspects are the assessment
KEEP = ("identity", "stack", "build_ci", "tests", "api", "resilience", "security", "runtime", "gaps_and_risks")


def _no_score(dims):
    """The engineering-maturity dimension without its percentage and band: the criteria counts stay, the score does not."""
    d = json.loads(json.dumps(dims))
    em = (d.get("dimensions") or {}).get("engineering_maturity")
    if em:
        em["headline"] = re.sub(r"^.*?\([\d.]+%\):\s*", "", em.get("headline") or "")
        em["values"] = {k: v for k, v in (em.get("values") or {}).items() if k not in ("score", "band")}
    return d


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _ui(name):
    with open(os.path.join(UI, name), encoding="utf-8") as fh:
        return fh.read()


def collect(out, catalogue, packs, sources=None, client=None, verify=None, gate=None):
    man = _read(os.path.join(out, "manifest.json"))
    P = _read(os.path.join(out, "portfolio", "relationships.json"))
    by_path = {os.path.abspath(s["path"]): s for s in (sources or []) if s.get("path")}
    apps = []
    for x in man["applications"]:
        a, d = x["app"], os.path.join(out, x["app"])
        disc, g = _read(os.path.join(d, "discovery.json")), _read(os.path.join(d, "relationships.json"))
        src = by_path.get(os.path.abspath(x["repo"])) or {}
        apps.append({"name": a, "discovery": {k: disc[k] for k in KEEP if k in disc}, "limitations": disc["run_meta"]["limitations"], "completeness": disc["run_meta"]["completeness"],
                     "dimensions": _no_score(_read(os.path.join(d, "dimensions.json"))), "safetynet": _read(os.path.join(d, "safetynet.json")), "resilience": _read(os.path.join(d, "resilience.json")),
                     "aspects": _read(os.path.join(d, "aspects.json")), "graph_limitations": g["meta"]["limitations"],
                     "source": {k: src.get(k) for k in ("spec", "team", "criticality", "branch", "commit", "remote")},
                     "views": {"container": c4.render_svg(c4.container(P, a)), "component": c4.render_svg(c4.component(P, a)), "container_mermaid": c4.render_mermaid(c4.container(P, a))}})
    impact_dir = os.path.join(out, "impact")
    impacts = [_read(os.path.join(impact_dir, f)) for f in sorted(os.listdir(impact_dir))] if os.path.isdir(impact_dir) else []
    ctx = c4.context(P) if len(apps) <= FULL_MAP_MAX else None  # a diagram of hundreds of applications is unreadable: the UI shows a ranked table instead
    failed = [s for s in (sources or []) if s.get("status") == "failed"]
    return {"generated": man["generated_at"], "tools": man["tool"], "apps": apps, "client": client, "gate": gate or "Internal: not validated",
            "verify": verify or {"ok": None, "state": "not run", "failed_rules": {}},
            "catalogue": {"version": catalogue["version"], "status": catalogue.get("status"), "states": catalogue["states"], "aspects": sorted(catalogue["aspects"], key=lambda x: x["order"])},
            "remedy_packs": [{"id": p["id"], "title": p["title"], "note": p.get("note"), "version": p["version"]} for p in packs], "failed_sources": failed,
            "portfolio": {"graph": {"nodes": P["nodes"], "edges": P["edges"], "not_relationships": P["not_relationships"]}, "resolution_log": P["meta"]["resolution_log"],
                          "views": {"context": c4.render_svg(ctx) if ctx else None, "context_mermaid": c4.render_mermaid(ctx) if ctx else ""}},
            "impacts": impacts}


def render(data):
    import evidence  # engine: the page never carries a secret, whatever the analysis files hold
    blob = json.dumps(evidence.redact_tree(data), sort_keys=True).replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    tpl = _ui("template.html")
    if "/*__DATA__*/null" not in tpl:
        raise ValueError("template has no data placeholder")
    js = "\n".join(_ui(n) for n in UI_JS).replace("</script", "<\\/script")
    return tpl.replace("/*__CSS__*/", _ui("theme.css")).replace("/*__C4STYLE__*/", c4.STYLE).replace("//__JS__", js).replace("/*__DATA__*/null", blob)


def build(out, html_path, catalogue, packs, sources=None, client=None, verify=None, gate=None):
    html = render(collect(out, catalogue, packs, sources, client, verify, gate))
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return html_path
