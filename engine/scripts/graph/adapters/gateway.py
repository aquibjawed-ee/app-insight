"""API-gateway routes (Spring Cloud Gateway): `uri: lb://name` or an absolute URL, with `Path=` predicates. A route is a CALLS_API relationship from the
gateway application to what it forwards to; the path is the route's path pattern (a trailing `/**` is a prefix, not an endpoint)."""
from __future__ import annotations

import re

import evidence
from graph.model import Graph, norm_path
from graph.adapters.common import Config, ev
from graph.adapters.http import _call, _target_for_host, _unresolved_target

ROUTES_KEY = re.compile(r"spring\.cloud\.gateway\.(?:server\.(?:webflux|webmvc)\.|mvc\.)?routes\[(\d+)\]\.(uri|predicates\[\d+\])$")


def _yaml_routes(lines):
    """[(uri, [paths], line_of_uri)] from a YAML `routes:` list under a `gateway:` key (indentation decides the items)."""
    out = []
    for i, ln in enumerate(lines):
        if re.match(r"^\s*routes:\s*$", ln) and any(re.match(r"^\s*gateway:\s*$", x) for x in lines[max(0, i - 8):i]):
            base = len(ln) - len(ln.lstrip())
            cur = None
            for j in range(i + 1, len(lines)):
                l2 = lines[j]
                if l2.lstrip().startswith("#"):
                    continue  # a commented-out route is not a route (evidence-rules 10)
                l2 = re.sub(r"\s+#.*$", "", l2)
                if l2.strip() and (len(l2) - len(l2.lstrip())) <= base and not l2.lstrip().startswith("-"):
                    break
                if re.match(r"^\s*-\s+id:", l2) or (re.match(r"^\s*-\s+uri:", l2) and cur is None):
                    cur = {"uri": None, "paths": [], "line": j + 1}
                    out.append(cur)
                if cur is not None:
                    m = re.search(r"\buri:\s*[\"']?([^\s\"']+)", l2)
                    if m and cur["uri"] is None:
                        cur["uri"], cur["line"] = m.group(1), j + 1
                    for pm in re.finditer(r"Path(?:=|:\s*)\s*([^\s,\"']+)", l2):
                        cur["paths"].append(pm.group(1))
    return [(c["uri"], c["paths"], c["line"]) for c in out if c["uri"]]


def routes(ctx, g: Graph, app: str, app_node: str, cfg: Config):
    r = ctx.repo
    for f in cfg.files:
        lines = evidence.read_lines(r, f) or []
        found = []
        if f.endswith((".yml", ".yaml")):
            found = _yaml_routes(lines)
        else:
            by = {}
            for i, ln in enumerate(lines, 1):
                m = re.match(r"^\s*(spring\.cloud\.gateway\.[\w.\[\]-]*?routes\[(\d+)\]\.(uri|predicates\[\d+\]))\s*[=:]\s*(.+?)\s*$", ln)
                if m:
                    d = by.setdefault(m.group(2), {"uri": None, "paths": [], "line": i})
                    if m.group(3) == "uri":
                        d["uri"], d["line"] = m.group(4), i
                    elif m.group(4).startswith("Path="):
                        d["paths"].append(m.group(4)[5:].split(",")[0])
            found = [(d["uri"], d["paths"], d["line"]) for d in by.values() if d["uri"]]
        for uri, paths, line in found:
            e = ev(f, line, lines, app)
            lb = re.match(r"lb://([\w.-]+)", uri)
            hm = re.match(r"https?://([A-Za-z0-9][A-Za-z0-9._-]*)", uri)
            if lb:
                tnode, _ = _target_for_host(g, lb.group(1), app) if "." not in lb.group(1) else _target_for_host(g, lb.group(1), app)
                rname = lb.group(1)
            elif hm:
                tnode, _ = _target_for_host(g, hm.group(1), app)
                rname = hm.group(1)
            else:
                g.skip("gateway route at %s" % f, "route target %r is not lb:// or an absolute URL" % uri[:60], [e])
                continue
            if not paths:
                _call(g, app, app_node, tnode, None, None, e, "configuration", "medium", rname, {"style": "gateway-route"})
            for p in paths:
                _call(g, app, app_node, tnode, None, p, e, "configuration", "high", rname, {"style": "gateway-route", "route_pattern": p})
