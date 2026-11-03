#!/usr/bin/env python3
"""app-discovery relationship platform CLI. No model, no network; target repositories are only read.

  relate.py analyse REPO [REPO ...] --out OUT [--criticality FILE]
        per application: discovery.json, relationships.json, safetynet.json, dimensions.json; then the resolved portfolio graph
  relate.py impact --out OUT --scenario SCENARIO [--app NAME ...] [--to V] [--from-tech T --to-tech T] [--topic NAME]
                   [--endpoint "VERB /path"] [--coordinate G:A] [--platform P] [--old-spec F --new-spec F] [--old-schema F --new-schema F]
  relate.py c4 --out OUT --view context|container|component [--app NAME] [--format svg|mermaid] [--file FILE]
  relate.py diff --base OUT_A --head OUT_B [--format md|json] [--fail-on-breaking]
  relate.py report --out OUT --html FILE
  relate.py validate --out OUT

Exit codes: 0 ok | 1 produced, but integrity or evidence checks failed | 2 could not run.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import discover  # noqa: E402
import evidence  # noqa: E402
import validate  # noqa: E402
from graph import c4, dimensions, extract, impact, model, resilience, resolve, safetynet  # noqa: E402
from graph import diff as graphdiff  # noqa: E402

SCHEMA = os.path.join(HERE, "..", "schemas", "relationships.v1.schema.json")


def _write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    model.dump(doc, path)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def schema_errors(doc):
    schema = _read(SCHEMA)
    errs = []
    validate._mini(schema, doc, schema, "$", errs)
    return errs


def load_aliases(path):
    """Flat `host: target` file (YAML-ish or JSON). Lines starting with # are comments."""
    text = open(path, encoding="utf-8").read()
    try:
        d = json.loads(text)
        return {str(k): str(v) for k, v in d.items()}
    except ValueError:
        pass
    out = {}
    for ln in text.splitlines():
        m = re.match(r"^\s*[\"']?([^\s:#\"']+)[\"']?\s*:\s*[\"']?([^\s#\"']+)[\"']?\s*(?:#.*)?$", ln)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def _why(e):
    """A failure as recorded: the exception type and a short, redacted message (a message can quote a file line)."""
    return "%s: %s" % (type(e).__name__, evidence.redact(str(e))[:160])


def _unique_ids(built):
    """Two repositories with the same application id are both analysed: the later ones get the parent folder's name as a
    suffix (then a number), recorded on the id fact. A duplicate never aborts the portfolio."""
    seen, renamed = {}, []
    for r, disc in built:
        f = disc["identity"]["app_id"]
        name = base = f["value"]
        if name in seen:
            name = "%s-%s" % (base, re.sub(r"[^\w.-]+", "_", os.path.basename(os.path.dirname(r))) or "repo")
            i = 2
            while name in seen:
                name, i = "%s-%d" % (base, i), i + 1
            f["value"], f["note"] = name, "renamed from %s: another repository in this analysis (%s) has that id" % (base, seen[base])
            renamed.append({"repo": r, "from": base, "to": name})
        seen[name] = r
    return renamed


def _empty_graph(app, disc, why):
    g = model.Graph("application")
    g.node("app:" + app, "Application", app, {"identity_keys": [], "declared_hosts": [], "context_path": None, "artifact_kind": None, "language": None}, app=app)
    return g.to_doc({"extractor_version": extract.EXTRACTOR_VERSION, "application": app, "repository_fingerprint": disc["run_meta"]["inventory_fingerprint"],
                     "discovery_fingerprint": disc["run_meta"]["fingerprint"], "static_analysis_only": True, "external_sources": {}, "integrity_errors": [],
                     "failed": why, "limitations": ["Relationship extraction failed on this repository (%s): its relationships are not known." % why]})


def cmd_analyse(a) -> int:
    repos = {}
    for r in a.repos:
        r = os.path.abspath(r)
        if not os.path.isdir(r):
            print("repo not found: %s" % r, file=sys.stderr)
            return 2
    # every step is isolated per repository: one repository that breaks a step is recorded and the others go on
    built, failed = [], []
    for r in sorted(os.path.abspath(x) for x in a.repos):
        try:
            built.append((r, discover.build(r)))
        except Exception as e:  # noqa: BLE001  the whole discovery failed: no application can be described, so none is invented
            failed.append({"repo": r, "step": "discovery", "error": _why(e)})
            print("%s: discovery failed (%s); the other repositories go on" % (r, _why(e)), file=sys.stderr)
    renamed = _unique_ids(built)
    docs, rc = [], 1 if failed else 0
    criticality = _read(a.criticality) if a.criticality else None
    sns, discs, res_docs = {}, {}, {}

    def step(app, disc, name, fn, fallback):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            nonlocal rc
            rc = 1
            disc["run_meta"]["failures"].append("%s: %s" % (name, _why(e)))  # the controls this step feeds become NOT_ASSESSED
            print("%s: %s failed (%s); its results are not assessed" % (app, name, _why(e)), file=sys.stderr)
            return fallback(_why(e))
    for r, disc in built:
        app = disc["identity"]["app_id"]["value"]
        repos[app] = r
        discs[app] = disc
        g = step(app, disc, "relationships", lambda: extract.extract(r, disc, profile=a.profile, config_dirs=a.config_dir or ()), lambda w: _empty_graph(app, disc, w))
        errs = schema_errors(g) + g["meta"]["integrity_errors"]
        if errs:
            print("%s: relationships invalid:\n  %s" % (app, "\n  ".join(errs[:10])), file=sys.stderr)
            rc = 1
        sns[app] = step(app, disc, "safetynet", lambda: safetynet.map_application(r, g, disc),
                        lambda w: {"contract": safetynet.CONTRACT, "application": app, "version": safetynet.VERSION, "repository_level": {}, "components": [], "summary": {},
                                   "failed": w, "limitations": ["The safety-net mapping failed on this repository (%s)." % w]})
        res_docs[app] = step(app, disc, "availability", lambda: resilience.assess(r, disc),
                             lambda w: {"contract": resilience.CONTRACT, "version": resilience.VERSION, "application": app, "state": "not_assessed", "platforms": [],
                                        "workloads": [], "summary": [], "groups": resilience.GROUPS, "ignored": [], "unread": None, "failed": w,
                                        "reason": "the deployment check failed on this repository (%s)" % w, "limitations": []})
        _write(os.path.join(a.out, app, "resilience.json"), res_docs[app])
        docs.append(g)
        d = os.path.join(a.out, app)
        _write(os.path.join(d, "relationships.json"), g)
        _write(os.path.join(d, "safetynet.json"), sns[app])
    aliases = load_aliases(a.aliases) if a.aliases else None
    P = resolve.resolve(docs, aliases)
    ext_all = {}
    for g_ in docs:
        ext_all.update(g_["meta"].get("external_sources", {}))
    errs = schema_errors(P) + model.validate_integrity(P, repos, ext_all)
    if errs:
        print("portfolio graph invalid:\n  " + "\n  ".join(errs[:10]), file=sys.stderr)
        rc = 1
    _write(os.path.join(a.out, "portfolio", "relationships.json"), P)
    for r, disc in built:
        app = disc["identity"]["app_id"]["value"]
        own = next(g for g in docs if g["meta"]["application"] == app)
        dims = step(app, disc, "dimensions", lambda: dimensions.assess(disc, own, None if sns[app].get("failed") else sns[app], criticality, portfolio_graph=P,
                                                    resilience=None if res_docs[app].get("failed") else res_docs[app]),
                    lambda w: {"contract": dimensions.CONTRACT, "application": app, "failed": w, "statement": "The dimensions step failed on this repository (%s)." % w,
                               "dimensions": {k: dict(dimensions._d("not_assessed", "Not assessed: the dimensions step failed on this repository"), title=dimensions.TITLES[k])
                                              for k in dimensions.ORDER}})
        _write(os.path.join(a.out, app, "dimensions.json"), dims)
        _write(os.path.join(a.out, app, "discovery.json"), disc)  # last, so it carries every step's failure
    manifest = {"contract": "analysis-manifest.v1", "applications": [{"app": app, "repo": repos[app], "inventory_fingerprint": discs[app]["run_meta"]["inventory_fingerprint"],
                                                                     "failures": discs[app]["run_meta"]["failures"]} for app in sorted(repos)],
                "failed": failed, "renamed": renamed,
                "external_sources": ext_all, "options": {"profile": a.profile, "aliases": bool(a.aliases), "config_dirs": len(a.config_dir or [])}, "generated_at": os.environ.get("DISCOVERY_FIXED_TIME") or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "tool": {"extractor": extract.EXTRACTOR_VERSION, "resolver": resolve.RESOLVER_VERSION,
                                                                                         "safetynet": safetynet.VERSION, "impact": impact.ENGINE_VERSION}}
    _write(os.path.join(a.out, "manifest.json"), manifest)
    print("━━ APP-DISCOVERY-RELATIONSHIPS ━━")
    print("applications:  %d%s" % (len(repos), "; %d repositories could not be analysed" % len(failed) if failed else ""))
    print("nodes/edges:   %d / %d (portfolio)" % (len(P["nodes"]), len(P["edges"])))
    st = {}
    for e in P["edges"]:
        st[e["resolution"]["state"]] = st.get(e["resolution"]["state"], 0) + 1
    print("resolution:    " + ", ".join("%d %s" % (v, k) for k, v in sorted(st.items())))
    print("integrity:     %s" % ("ok" if not errs else "%d error(s)" % len(errs)))
    print("output:        %s" % a.out)
    return rc


def _load_graph(out):
    return _read(os.path.join(out, "portfolio", "relationships.json"))


def _views(out):
    m = _read(os.path.join(out, "manifest.json"))
    views, sns = {}, {}
    for x in m["applications"]:
        disc = _read(os.path.join(out, x["app"], "discovery.json"))
        views[x["app"]] = impact.AppView(x["app"], x["repo"], disc)
        sns[x["app"]] = _read(os.path.join(out, x["app"], "safetynet.json"))
    return views, sns


def cmd_impact(a) -> int:
    g = _load_graph(a.out)
    views, sns = _views(a.out)
    sc = {"type": a.scenario}
    if a.app:
        sc["apps"] = a.app if a.scenario in ("java_runtime", "spring_boot", "dependency_major") else None
        if a.scenario in ("api_contract",):
            sc["app"] = a.app[0]
    for k in ("to", "from_tech", "to_tech", "topic", "endpoint", "coordinate", "platform", "old_spec", "new_spec", "old_schema", "new_schema", "change"):
        v = getattr(a, k, None)
        if v is not None:
            sc[k] = v
    if a.scenario == "java_runtime" and "to" in sc:
        sc["to"] = int(sc["to"])
    if a.scenario == "java_runtime" and a.from_version:
        sc["from"] = int(a.from_version)
    sc = {k: v for k, v in sc.items() if v is not None}
    try:
        res = impact.assess(sc, g, views, sns)
    except (ValueError, KeyError) as e:
        print("cannot assess: %s" % e, file=sys.stderr)
        return 2
    name = "-".join([a.scenario] + [str(sc[k]) for k in ("to", "topic", "coordinate", "platform", "from_tech") if k in sc])
    name = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    path = os.path.join(a.out, "impact", name + ".json")
    _write(path, res)
    print("━━ APP-DISCOVERY-IMPACT ━━")
    print("scenario:      %s" % json.dumps(sc, sort_keys=True))
    print("confirmed:     %d incompatibilities" % len(res["confirmed_incompatibilities"]))
    print("potential:     %d risks, %d downstream components" % (len(res["potential_risks"]), len(res["downstream_impact"])))
    print("unknowns:      %d" % len(res["unknowns"]))
    print("output:        %s" % path)
    return 0


def cmd_c4(a) -> int:
    g = _load_graph(a.out)
    if a.view == "context":
        v = c4.context(g)
    else:
        if not a.app:
            print("--app is required for the %s view" % a.view, file=sys.stderr)
            return 2
        if "app:" + a.app not in {n["id"] for n in g["nodes"]}:
            print("unknown application %s" % a.app, file=sys.stderr)
            return 2
        v = c4.container(g, a.app) if a.view == "container" else c4.component(g, a.app)
    text = c4.render_svg(v, standalone=True) if a.format == "svg" else c4.render_mermaid(v)
    if a.file:
        with open(a.file, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("wrote %s" % a.file)
    else:
        print(text)
    return 0


def cmd_diff(a) -> int:
    d = graphdiff.diff(_load_graph(a.base), _load_graph(a.head))
    text = json.dumps(d, indent=2, sort_keys=True) + "\n" if a.format == "json" else graphdiff.to_markdown(d)
    if a.file:
        with open(a.file, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("wrote %s" % a.file)
    else:
        print(text, end="")
    return 3 if (a.fail_on_breaking and d["breaking"]) else 0


def cmd_report(a) -> int:
    print("the HTML report is built by the product: app-insight report <run-dir>", file=sys.stderr)
    return 2


def cmd_validate(a) -> int:
    m = _read(os.path.join(a.out, "manifest.json"))
    repos = {x["app"]: x["repo"] for x in m["applications"]}
    P = _load_graph(a.out)
    errs = schema_errors(P) + model.validate_integrity(P, repos, m.get("external_sources") or {})
    stale = []
    for x in m["applications"]:
        from detectors import Ctx
        now = evidence.inventory_fingerprint(x["repo"], Ctx(x["repo"]).files)
        if now != x["inventory_fingerprint"]:
            stale.append(x["app"])
    for s in stale:
        print("STALE: %s changed since the analysis" % s)
    for e in errs:
        print("INVALID: " + e)
    print("validate: %d error(s), %d stale application(s)" % (len(errs), len(stale)))
    return 1 if errs or stale else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("analyse")
    p.add_argument("repos", nargs="+")
    p.add_argument("--out", required=True)
    p.add_argument("--criticality")
    p.add_argument("--profile", help="Spring profile to apply over the base configuration (default: keep every profile and report keys whose values differ)")
    p.add_argument("--config-dir", action="append", help="directory of application*.yml / <app>.yml files (Spring Cloud Config style) that override the repository's own")
    p.add_argument("--aliases", help="flat `host: application-or-system` file mapping hosts to analysed applications or named external systems")
    p.set_defaults(fn=cmd_analyse)
    p = sub.add_parser("impact")
    p.add_argument("--out", required=True)
    p.add_argument("--scenario", required=True, choices=impact.SCENARIOS)
    p.add_argument("--app", action="append")
    p.add_argument("--to")
    p.add_argument("--from", dest="from_version")
    for k in ("from-tech", "to-tech", "topic", "endpoint", "coordinate", "platform", "old-spec", "new-spec", "old-schema", "new-schema", "change"):
        p.add_argument("--" + k)
    p.set_defaults(fn=cmd_impact)
    p = sub.add_parser("c4")
    p.add_argument("--out", required=True)
    p.add_argument("--view", required=True, choices=("context", "container", "component"))
    p.add_argument("--app")
    p.add_argument("--format", choices=("svg", "mermaid"), default="svg")
    p.add_argument("--file")
    p.set_defaults(fn=cmd_c4)
    p = sub.add_parser("diff")
    p.add_argument("--base", required=True, help="analysis directory of the target branch")
    p.add_argument("--head", required=True, help="analysis directory of the merge-request branch")
    p.add_argument("--format", choices=("md", "json"), default="md")
    p.add_argument("--file")
    p.add_argument("--fail-on-breaking", action="store_true", help="exit 3 when a breaking change is found")
    p.set_defaults(fn=cmd_diff)
    p = sub.add_parser("report")
    p.add_argument("--out", required=True)
    p.add_argument("--html", required=True)
    p.set_defaults(fn=cmd_report)
    p = sub.add_parser("validate")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_validate)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
