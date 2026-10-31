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


def cmd_analyse(a) -> int:
    repos = {}
    for r in a.repos:
        r = os.path.abspath(r)
        if not os.path.isdir(r):
            print("repo not found: %s" % r, file=sys.stderr)
            return 2
    built = []
    for r in sorted(os.path.abspath(x) for x in a.repos):
        disc = discover.build(r)
        built.append((r, disc))
    names = [d["identity"]["app_id"]["value"] for _, d in built]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        print("two repositories have the same application id %s: rename a directory or fix its git remote" % ", ".join(dup), file=sys.stderr)
        return 2
    docs, rc = [], 0
    criticality = _read(a.criticality) if a.criticality else None
    sns, discs, res_docs = {}, {}, {}
    for r, disc in built:
        app = disc["identity"]["app_id"]["value"]
        repos[app] = r
        discs[app] = disc
        g = extract.extract(r, disc, profile=a.profile, config_dirs=a.config_dir or ())
        errs = schema_errors(g) + g["meta"]["integrity_errors"]
        if errs:
            print("%s: relationships invalid:\n  %s" % (app, "\n  ".join(errs[:10])), file=sys.stderr)
            rc = 1
        sn = safetynet.map_application(r, g, disc)
        sns[app] = sn
        res_docs[app] = resilience.assess(r, disc)
        _write(os.path.join(a.out, app, "resilience.json"), res_docs[app])
        docs.append(g)
        d = os.path.join(a.out, app)
        _write(os.path.join(d, "discovery.json"), disc)
        _write(os.path.join(d, "relationships.json"), g)
        _write(os.path.join(d, "safetynet.json"), sn)
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
        _write(os.path.join(a.out, app, "dimensions.json"), dimensions.assess(disc, own, sns[app], criticality, portfolio_graph=P, resilience=res_docs[app]))
    manifest = {"contract": "analysis-manifest.v1", "applications": [{"app": app, "repo": repos[app], "inventory_fingerprint": discs[app]["run_meta"]["inventory_fingerprint"]} for app in sorted(repos)],
                "external_sources": ext_all, "options": {"profile": a.profile, "aliases": bool(a.aliases), "config_dirs": len(a.config_dir or [])}, "generated_at": os.environ.get("DISCOVERY_FIXED_TIME") or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "tool": {"extractor": extract.EXTRACTOR_VERSION, "resolver": resolve.RESOLVER_VERSION,
                                                                                         "safetynet": safetynet.VERSION, "impact": impact.ENGINE_VERSION}}
    _write(os.path.join(a.out, "manifest.json"), manifest)
    print("━━ APP-DISCOVERY-RELATIONSHIPS ━━")
    print("applications:  %d" % len(repos))
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
