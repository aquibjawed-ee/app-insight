"""C4-style views built directly from the canonical graph (no re-discovery) and rendered to SVG / Mermaid.

Views are plain dicts (nodes, edges, boundaries) so that any renderer can draw them; `render_svg` is a small deterministic layered
layout. Unresolved and ambiguous relationships are drawn, dashed and labelled, never dropped or guessed into place.
  context(graph)            portfolio: applications, external systems, shared data stores, topics
  container(graph, app)     one application: its modules/API, data stores, brokers/topics, services it calls, who calls it
  component(graph, app)     modules and the controllers inside them (only what module analysis can show)
"""
from __future__ import annotations

import html
from collections import defaultdict
from typing import Dict

APP, EXT, DB, TOPIC, BROKER, UNRES, MOD, API = "app", "ext", "db", "topic", "broker", "unresolved", "module", "api"


def _index(g):
    return {n["id"]: n for n in g["nodes"]}


def _app_of(nodes, nid):
    n = nodes[nid]
    if n["type"] == "Application":
        return nid
    if n["type"] in ("ApiEndpoint", "Module") and n.get("app"):
        return "app:" + n["app"]
    return None


def _edge_style(e):
    st = e["resolution"].get("state")
    if st == "ambiguous":
        return "ambiguous"
    if st == "unresolved" or e["basis"] == "unresolved":
        return "unresolved"
    if e["basis"] in ("inferred", "declared") or e["confidence"] == "low":
        return "inferred"
    return "solid"


WORST = {"solid": 0, "inferred": 1, "ambiguous": 2, "unresolved": 3}


class _Agg:
    def __init__(self):
        self.edges: Dict[tuple, dict] = {}

    def add(self, src, tgt, kind, label, e, style=None):
        k = (src, tgt, kind)
        a = self.edges.setdefault(k, {"source": src, "target": tgt, "kind": kind, "label": label, "edge_ids": [], "style": "solid", "n": 0})
        a["edge_ids"].append(e["id"])
        a["n"] += 1
        s = style or _edge_style(e)
        if WORST[s] > WORST[a["style"]]:
            a["style"] = s

    def out(self):
        res = []
        for k in sorted(self.edges):
            a = self.edges[k]
            lab = a["label"] if a["n"] == 1 or a["kind"] != "rest" else "%s ×%d" % (a["label"], a["n"])
            res.append({"id": "v-%s>%s:%s" % k, "source": a["source"], "target": a["target"], "label": lab, "style": a["style"], "kind": a["kind"],
                        "edge_ids": sorted(a["edge_ids"])})
        return res


def _node(vn, nid, label, kind, sub=None, state=None, ref=None, tip=None):
    vn.setdefault(nid, {"id": nid, "label": label, "kind": kind, "sub": sub, "state": state, "ref": ref or nid, "tip": tip or sub})


def _topic_sub(tn):
    h = tn["attrs"].get("cluster_hints") or []
    return "%s \u00b7 %s" % (tn["attrs"].get("broker_family"), ", ".join(h[:2])) if h else "%s \u00b7 cluster not stated" % tn["attrs"].get("broker_family")


def _unresolved_node(vn, nodes, e, t):
    st = e["resolution"].get("state")
    key = "?" + t
    why = e["resolution"].get("reasoning") or e["resolution"].get("reason")
    short = {"ambiguous": "%d candidates" % len(e["resolution"].get("candidates", [])), "unresolved": "weak name match only" if e["resolution"].get("weak_candidates") else "no matching application"}.get(st, st)
    _node(vn, key, ("ambiguous: " if st == "ambiguous" else "unresolved: ") + nodes[t]["name"], UNRES, short, st, tip=why)
    return key


def context(g) -> dict:
    nodes = _index(g)
    vn, agg = {}, _Agg()
    for n in g["nodes"]:
        if n["type"] == "Application":
            _node(vn, n["id"], n["name"], APP, n["attrs"].get("artifact_kind") or "")
    db_users = defaultdict(set)
    for e in g["edges"]:
        if e["target"].startswith("db:") and e["source"].startswith("app:"):
            db_users[e["target"]].add(e["source"])
    for e in g["edges"]:
        s, t = e["source"], e["target"]
        if e["type"] == "CALLS_API":
            ta = _app_of(nodes, t)
            if ta:
                agg.add(s, ta, "rest", "REST", e)
            elif t.startswith("ext:") and not nodes[t]["attrs"].get("unresolved"):
                _node(vn, t, nodes[t]["name"], EXT, "external system")
                agg.add(s, t, "rest", "REST", e)
            else:
                key = _unresolved_node(vn, nodes, e, t)
                agg.add(s, key, "rest", "REST", e)
                for c in e["resolution"].get("candidates", []):
                    agg.add(key, c, "candidate", "candidate", e, "ambiguous")
        elif e["type"] in ("PUBLISHES_TO", "CONSUMES_FROM") and e["resolution"].get("state") == "resolved":
            tn = nodes[t]
            _node(vn, t, tn["name"], TOPIC, _topic_sub(tn))
            if e["type"] == "PUBLISHES_TO":
                agg.add(s, t, "msg", "publishes", e)
            else:
                agg.add(t, s, "msg", "consumed by", e)
        elif e["type"] in ("PUBLISHES_TO", "CONSUMES_FROM"):
            key = "?" + t
            _node(vn, key, "unresolved destination", UNRES, "computed at run time", "unresolved", tip=e["resolution"].get("reason"))
            if e["type"] == "PUBLISHES_TO":
                agg.add(s, key, "msg", "publishes", e)
            else:
                agg.add(key, s, "msg", "consumes", e)
        elif t in db_users and len(db_users[t]) > 1 and e["type"] == "DEPENDS_ON":
            tn = nodes[t]
            _node(vn, t, tn["name"] + " @ " + tn["attrs"]["connection"]["host"], DB, "shared by %d applications" % len(db_users[t]))
            agg.add(s, t, "data", "uses", e)
        elif e["type"] == "DEPENDS_ON" and t.startswith("ext:") and nodes[t]["attrs"].get("role") in ("Identity and access", "Notifications", "Observability", "Configuration, secrets and discovery"):
            _node(vn, t, nodes[t]["name"], EXT, nodes[t]["attrs"].get("role"))
            agg.add(s, t, "dep", "depends on", e)
    return {"level": "context", "title": "System context", "nodes": sorted(vn.values(), key=lambda n: n["id"]), "edges": agg.out(), "boundaries": []}


def container(g, app: str) -> dict:
    nodes = _index(g)
    me = "app:" + app
    vn, agg = {}, _Agg()
    eps = [n for n in g["nodes"] if n["type"] == "ApiEndpoint" and n.get("app") == app]
    mods = [n for n in g["nodes"] if n["type"] == "Module" and n.get("app") == app]
    infra = [nodes[e["target"]] for e in g["edges"] if e["type"] == "DEPLOYED_ON" and e["source"] == me]
    boundary = {"id": "b-" + me, "label": app, "members": [],
                "sub": ("deployed on " + ", ".join(sorted(i["name"] for i in infra))) if infra else "deployment not found in this repository"}
    if eps:
        _node(vn, "api:" + app, "REST API", API, "%d endpoint(s)" % len(eps))
        boundary["members"].append("api:" + app)
    if len(mods) > 1:
        for m in sorted(mods, key=lambda x: x["id"]):
            _node(vn, m["id"], m["name"], MOD, m["attrs"].get("role") or "")
            boundary["members"].append(m["id"])
    if not boundary["members"]:
        _node(vn, me, app, APP, nodes[me]["attrs"].get("artifact_kind") or "")
        boundary["members"].append(me)
    anchor = boundary["members"][0]
    for e in g["edges"]:
        s, t = e["source"], e["target"]
        if s == me:
            if e["type"] == "CALLS_API":
                ta = _app_of(nodes, t)
                if ta:
                    _node(vn, ta, nodes[ta]["name"], APP, "called by this application")
                    agg.add(anchor, ta, "rest", "REST", e)
                elif t.startswith("ext:") and not nodes[t]["attrs"].get("unresolved"):
                    _node(vn, t, nodes[t]["name"], EXT, "external system")
                    agg.add(anchor, t, "rest", "REST", e)
                else:
                    agg.add(anchor, _unresolved_node(vn, nodes, e, t), "rest", "REST", e)
            elif e["type"] in ("DEPENDS_ON", "READS_FROM", "WRITES_TO") and t.startswith("db:"):
                _node(vn, t, nodes[t]["name"], DB, nodes[t]["attrs"].get("role"))
                agg.add(anchor, t, "data", {"DEPENDS_ON": "uses", "READS_FROM": "reads", "WRITES_TO": "writes"}[e["type"]], e)
            elif e["type"] == "DEPENDS_ON" and t.startswith("broker:"):
                _node(vn, t, nodes[t]["name"], BROKER, "message broker")
                agg.add(anchor, t, "msg", "uses", e)
            elif e["type"] in ("PUBLISHES_TO", "CONSUMES_FROM"):
                if e["resolution"].get("state") == "resolved":
                    others = sorted({x["source"][4:] for x in g["edges"] if x["target"] == t and x["source"] != me and x["source"].startswith("app:")})
                    _node(vn, t, nodes[t]["name"], TOPIC, ("also used by " + ", ".join(others)) if others else _topic_sub(nodes[t]), tip=_topic_sub(nodes[t]))
                else:
                    _node(vn, t, "unresolved destination", UNRES, "computed at run time", "unresolved", tip=e["resolution"].get("reason"))
                if e["type"] == "PUBLISHES_TO":
                    agg.add(anchor, t, "msg", "publishes", e)
                else:
                    agg.add(t, anchor, "msg", "consumed by", e)
            elif e["type"] == "DEPENDS_ON" and t.startswith("ext:"):
                _node(vn, t, nodes[t]["name"], EXT, nodes[t]["attrs"].get("role") or "external system")
                agg.add(anchor, t, "dep", "depends on", e)
        elif e["type"] == "CALLS_API" and _app_of(nodes, t) == me:
            _node(vn, s, nodes[s]["name"], APP, "calls this application")
            agg.add(s, anchor, "rest", "REST", e)
    return {"level": "container", "title": "Containers of %s" % app, "nodes": sorted(vn.values(), key=lambda n: n["id"]), "edges": agg.out(), "boundaries": [boundary]}


def component(g, app: str) -> dict:
    vn, agg = {}, _Agg()
    mods = sorted((n for n in g["nodes"] if n["type"] == "Module" and n.get("app") == app), key=lambda n: n["id"])
    boundary = {"id": "b-app:" + app, "label": app, "members": [], "sub": "module level only: classes within a module are not analysed"}
    for m in mods:
        eps = [n for n in g["nodes"] if n["type"] == "ApiEndpoint" and n.get("app") == app and n["attrs"].get("module") == m["attrs"]["path"]]
        ctrls = sorted({n["attrs"].get("controller") for n in eps if n["attrs"].get("controller")})
        sub = "%s%s" % (m["attrs"].get("role") or "", (" · " + ", ".join(ctrls[:3]) + (" …" if len(ctrls) > 3 else "")) if ctrls else "")
        _node(vn, m["id"], m["name"], MOD, sub)
        boundary["members"].append(m["id"])
    for e in g["edges"]:
        if e["type"] == "DEPENDS_ON" and e["source"] in vn and e["target"] in vn:
            agg.add(e["source"], e["target"], "dep", "depends on", e)
    return {"level": "component", "title": "Components of %s" % app, "nodes": sorted(vn.values(), key=lambda n: n["id"]), "edges": agg.out(), "boundaries": [boundary] if mods else []}


# ---- layout and rendering ----------------------------------------------------------------------------------------------

def _layers(view):
    ids = [n["id"] for n in view["nodes"]]
    adj = defaultdict(list)
    for e in view["edges"]:
        if e["kind"] != "candidate" and e["source"] != e["target"]:
            adj[e["source"]].append(e["target"])
    state, back = {}, set()  # cycles are broken deterministically (DFS in id order), then longest-path layering

    def dfs(u):
        state[u] = 1
        for v in sorted(adj[u]):
            if state.get(v) == 1:
                back.add((u, v))
            elif v not in state:
                dfs(v)
        state[u] = 2
    for u in sorted(ids):
        if u not in state:
            dfs(u)
    layer = {i: 0 for i in ids}
    for _ in range(len(ids)):
        ch = False
        for u in sorted(ids):
            for v in adj[u]:
                if (u, v) not in back and layer[v] < layer[u] + 1:
                    layer[v] = layer[u] + 1
                    ch = True
        if not ch:
            break
    # candidates sit one column after the placeholder that names them
    for e in view["edges"]:
        if e["kind"] == "candidate":
            layer[e["target"]] = max(layer[e["target"]], layer[e["source"]] + 1)
    return layer


def _w(text, size=13):
    return int(len(text) * size * 0.56) + 20


def layout(view):
    layer = _layers(view)
    cols = defaultdict(list)
    for n in sorted(view["nodes"], key=lambda n: (layer[n["id"]], n["kind"], n["label"].lower(), n["id"])):
        cols[layer[n["id"]]].append(n)
    # reduce crossings: order each column by the mean row of its neighbours in the previous column (a few deterministic sweeps)
    nbr = defaultdict(list)
    for e in view["edges"]:
        nbr[e["target"]].append(e["source"])
        nbr[e["source"]].append(e["target"])
    order = {n["id"]: i for c in cols for i, n in enumerate(cols[c])}
    for _ in range(4):
        for c in sorted(cols)[1:]:
            def bary(n):
                ps = [order[m] for m in nbr[n["id"]] if m in order and layer[m] != c]
                return (sum(ps) / len(ps) if ps else order[n["id"]], n["label"].lower(), n["id"])
            cols[c].sort(key=bary)
            for i, n in enumerate(cols[c]):
                order[n["id"]] = i
    NH, GX, GY, PAD = 58, 130, 22, 40
    boxes, x, colx = {}, PAD, {}
    for c in sorted(cols):
        w = max([_w(n["label"]) for n in cols[c]] + [_w(n["sub"] or "", 11) for n in cols[c]] + [200])
        colx[c] = (x, min(w, 340))
        x += min(w, 340) + GX
    height = 0
    for c in sorted(cols):
        y = PAD + 28
        for n in cols[c]:
            x0, w = colx[c]
            boxes[n["id"]] = {"x": x0, "y": y, "w": w, "h": NH}
            y += NH + GY
        height = max(height, y)
    bbox = {}
    for b in view["boundaries"]:
        ms = [boxes[m] for m in b["members"] if m in boxes]
        if ms:
            bbox[b["id"]] = {"x": min(m["x"] for m in ms) - 16, "y": min(m["y"] for m in ms) - 34, "w": max(m["x"] + m["w"] for m in ms) - min(m["x"] for m in ms) + 32,
                             "h": max(m["y"] + m["h"] for m in ms) - min(m["y"] for m in ms) + 64}
    return boxes, bbox, max(x - GX + PAD, 360), height + PAD


STYLE = """.c4 text{font:12px system-ui,sans-serif;fill:currentColor}.c4 .t{font-weight:600;font-size:13px}.c4 .s{opacity:.7;font-size:11px}
.c4 .node rect{fill:var(--c4-node,#fff);stroke:var(--c4-line,#555);stroke-width:1.2}.c4 .app rect{fill:var(--c4-app,#dbeafe)}.c4 .ext rect{fill:var(--c4-ext,#e5e7eb)}
.c4 .db rect,.c4 .broker rect{fill:var(--c4-data,#fef3c7)}.c4 .topic rect{fill:var(--c4-topic,#dcfce7)}.c4 .module rect,.c4 .api rect{fill:var(--c4-mod,#f3f4f6)}
.c4 .unresolved rect{fill:var(--c4-unres,#fee2e2);stroke-dasharray:5 3}.c4 .boundary{fill:none;stroke:var(--c4-line,#555);stroke-dasharray:2 4;stroke-width:1}
.c4 .edge path{fill:none;stroke:var(--c4-line,#555);stroke-width:1.4}.c4 .edge.inferred path{stroke-dasharray:6 3}.c4 .edge.unresolved path,.c4 .edge.ambiguous path{stroke:var(--c4-warn,#b91c1c);stroke-dasharray:2 3}
.c4 .edge.candidate path{stroke:var(--c4-warn,#b91c1c);stroke-dasharray:1 4}.c4 .edge text{font-size:11px;paint-order:stroke;stroke:var(--c4-bg,#fff);stroke-width:3px}
.c4 .edge:hover path,.c4 .edge.sel path{stroke-width:2.8}.c4 .node,.c4 .edge{cursor:pointer}"""


def _pt(x1, y1, x2, y2, t):
    mx = (x1 + x2) / 2
    u = 1 - t
    return (u ** 3 * x1 + 3 * u * u * t * mx + 3 * u * t * t * mx + t ** 3 * x2, u ** 3 * y1 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t ** 3 * y2)


def render_svg(view: dict, standalone: bool = False) -> str:
    if not view["nodes"]:
        return '<svg class="c4" xmlns="http://www.w3.org/2000/svg" width="420" height="60" role="img"><text x="10" y="34" class="s">Nothing to draw: no relationships were found for this view.</text></svg>'
    boxes, bbox, W, H = layout(view)
    esc = html.escape
    out = ['<svg class="c4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" role="img" aria-label="%s">' % (W, H, W, H, esc(view["title"]))]
    if standalone:
        out.append("<style>%s</style>" % STYLE)
    out.append('<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="currentColor"/></marker></defs>')
    for b in view["boundaries"]:
        r = bbox.get(b["id"])
        if r:
            out.append('<g><rect class="boundary" x="%d" y="%d" width="%d" height="%d" rx="8"/><text class="t" x="%d" y="%d">%s</text><text class="s" x="%d" y="%d">%s</text></g>' % (
                r["x"], r["y"], r["w"], r["h"], r["x"] + 10, r["y"] + 16, esc(b["label"]), r["x"] + 10, r["y"] + r["h"] - 10, esc(b.get("sub") or "")))
    for e in view["edges"]:
        a, b = boxes.get(e["source"]), boxes.get(e["target"])
        if not a or not b:
            continue
        if a["x"] <= b["x"]:
            x1, y1, x2, y2 = a["x"] + a["w"], a["y"] + a["h"] / 2, b["x"], b["y"] + b["h"] / 2
        else:
            x1, y1, x2, y2 = a["x"], a["y"] + a["h"] / 2, b["x"] + b["w"], b["y"] + b["h"] / 2
        if abs(x1 - x2) < 2:  # same column: route around the side
            x1 = x2 = max(a["x"] + a["w"], b["x"] + b["w"])
            d = "M%d,%d C%d,%d %d,%d %d,%d" % (x1, y1, x1 + 60, y1, x2 + 60, y2, x2, y2)
        else:
            mx = (x1 + x2) / 2
            d = "M%d,%d C%d,%d %d,%d %d,%d" % (x1, y1, mx, y1, mx, y2, x2, y2)
        out.append('<g class="edge %s %s" data-edge-ids="%s" data-view-edge="%s" tabindex="0"><path d="%s" marker-end="url(#arr)" style="color:var(--c4-line,#555)"/>'
                   '<text x="%d" y="%d" text-anchor="middle">%s</text><title>%s</title></g>' % (
                       e["style"], e["kind"], esc(" ".join(e["edge_ids"])), esc(e["id"]), d, _pt(x1, y1, x2, y2, 0.7)[0], _pt(x1, y1, x2, y2, 0.7)[1] - 4, esc(e["label"]),
                       esc("%s → %s (%s)" % (e["source"], e["target"], e["style"]))))
    for n in view["nodes"]:
        r = boxes[n["id"]]
        sub = ('<text class="s" x="%d" y="%d" text-anchor="middle">%s</text>' % (r["x"] + r["w"] / 2, r["y"] + 42, esc((n["sub"] or "")[:60]))) if n.get("sub") else ""
        out.append('<g class="node %s" data-node="%s" tabindex="0"><rect x="%d" y="%d" width="%d" height="%d" rx="6"/><text class="t" x="%d" y="%d" text-anchor="middle">%s</text>%s<title>%s</title></g>' % (
            n["kind"], esc(n["ref"]), r["x"], r["y"], r["w"], r["h"], r["x"] + r["w"] / 2, r["y"] + 24, esc(n["label"]), sub, esc(n.get("tip") or n["sub"] or n["label"])))
    out.append("</svg>")
    return "".join(out)


def render_mermaid(view: dict) -> str:
    """Mermaid flowchart of the same view, for documentation. Structurizr/PlantUML can be generated from the view dict the same way."""
    ident = {n["id"]: "n%d" % i for i, n in enumerate(view["nodes"])}
    shape = {APP: ("[", "]"), EXT: ("[[", "]]"), DB: ("[(", ")]"), TOPIC: ("([", "])"), BROKER: ("[(", ")]"), UNRES: ("{{", "}}"), MOD: ("[", "]"), API: ("[", "]")}
    lines = ["flowchart LR"]
    for n in view["nodes"]:
        o, c = shape.get(n["kind"], ("[", "]"))
        lab = n["label"].replace('"', "'") + ("<br/>" + n["sub"].replace('"', "'")[:60] if n.get("sub") else "")
        lines.append('  %s%s"%s"%s' % (ident[n["id"]], o, lab, c))
    for e in view["edges"]:
        if e["source"] in ident and e["target"] in ident:
            lines.append('  %s %s|"%s"| %s' % (ident[e["source"]], "-->" if e["style"] == "solid" else "-.->", e["label"].replace('"', "'"), ident[e["target"]]))
    return "\n".join(lines) + "\n"
