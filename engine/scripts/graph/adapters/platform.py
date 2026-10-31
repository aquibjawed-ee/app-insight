"""Application identity, modules and deployment adapters. Identity keys are what other repositories can legitimately match on;
each carries a strength so that resolution never rests on a weak name alone."""
from __future__ import annotations

import os
import re
from typing import List

import evidence
from detectors import integrations as I
from graph.model import Graph
from graph.adapters.common import Config, ev

STRONG, MEDIUM, WEAK = "strong", "medium", "weak"


def identity_keys(ctx, app: str, cfg: Config, disc: dict) -> List[dict]:
    keys = []

    def add(kind, value, strength, e):
        if value and "{{" not in value and "${" not in value and not any(k["kind"] == kind and k["value"].lower() == value.lower() for k in keys):
            keys.append({"kind": kind, "value": value, "strength": strength, "evidence": e})
    for k in ("spring.application.name", "quarkus.application.name", "micronaut.application.name"):
        v, e, why = cfg.get(k)
        if v:
            add(k, v, STRONG, e)
    for f in ctx.gradle_settings:
        for hit in evidence.grep_files(ctx.repo, [f], r"rootProject\.name\s*=\s*[\"']([^\"']+)[\"']", 1):
            hit = dict(hit, app=app)
            add("gradle rootProject.name", re.search(r"[\"']([^\"']+)[\"']", hit["snippet"].split("=", 1)[1]).group(1), MEDIUM, hit)
    root_mod = next((m for m in (disc.get("stack", {}).get("module_list", {}).get("value") or []) if m["path"] == "." and m["build"] == "maven"), None)
    if root_mod:
        for hit in evidence.grep_files(ctx.repo, ["pom.xml"], r"<artifactId>\s*%s\s*<" % re.escape(root_mod["name"]), 3):
            add("maven artifactId", root_mod["name"], MEDIUM, dict(hit, app=app))
            break
    for f in ctx.files:
        if os.path.basename(f) == "Chart.yaml" and not ctx._aux(f):
            for hit in evidence.grep_files(ctx.repo, [f], r"^name:\s*([\w.-]+)\s*$", 1, flags=0):
                add("helm chart name", hit["snippet"].split(":", 1)[1].strip(), MEDIUM, dict(hit, app=app))
    for w in k8s_workloads(ctx, app):
        add("kubernetes %s name" % w["kind"], w["name"], STRONG if w["kind"] == "Service" else MEDIUM, w["evidence"])
    aid = disc.get("identity", {}).get("app_id", {})
    if aid.get("value"):
        add("repository name", aid["value"], WEAK, None)
    return keys


def k8s_workloads(ctx, app: str) -> List[dict]:
    """Kubernetes Deployment/StatefulSet/Service documents with a literal name (templated Helm names are not read)."""
    out = []
    for f in sorted(x for x in ctx.deploy_files if x.endswith((".yml", ".yaml")) and not re.match(r"(?i)(?:docker-)?compose|values|Chart", os.path.basename(x))):
        lines = evidence.read_lines(ctx.repo, f) or []
        starts = [0] + [i + 1 for i, l in enumerate(lines) if l.strip() == "---"]
        for n, s in enumerate(starts):
            e_ = (starts[n + 1] - 1) if n + 1 < len(starts) else len(lines)
            doc = lines[s:e_]
            kind = next((re.match(r"^kind:\s*(\w+)", l).group(1) for l in doc if re.match(r"^kind:\s*\w+", l)), None)
            if kind not in ("Deployment", "StatefulSet", "Service", "Ingress", "CronJob", "DaemonSet"):
                continue
            meta = next((i for i, l in enumerate(doc) if re.match(r"^metadata:\s*$", l)), None)
            if meta is None:
                continue
            name = ns = None
            name_line = None
            for j in range(meta + 1, len(doc)):
                if re.match(r"^\S", doc[j]):
                    break
                m = re.match(r"^\s{2}name:\s*[\"']?([^\s\"'#]+)", doc[j])
                if m and name is None:
                    name, name_line = m.group(1), s + j + 1
                m = re.match(r"^\s{2}namespace:\s*[\"']?([^\s\"'#]+)", doc[j])
                if m:
                    ns = m.group(1)
            if not name or "{{" in name:
                continue
            image = next((re.match(r"^\s*-?\s*image:\s*[\"']?([^\s\"']+)", l).group(1) for l in doc if re.match(r"^\s*-?\s*image:\s*\S", l)), None)
            out.append({"kind": kind, "name": name, "namespace": ns, "image": image, "file": f, "evidence": ev(f, name_line, lines, app)})
    return out


def modules(ctx, g: Graph, app: str, app_node: str, disc: dict):
    mods = disc.get("stack", {}).get("module_list", {}).get("value") or []
    ids = {}
    for m in mods:
        nid = "module:%s:%s" % (app, m["path"])
        ids[m["path"]] = nid
        build = ("pom.xml" if m["path"] == "." else m["path"] + "/pom.xml") if m["build"] == "maven" else None
        if build is None:
            build = next((f for f in ctx.gradle if (os.path.dirname(f) or ".") == m["path"]), None)
        e = None
        if build:
            lines = evidence.read_lines(ctx.repo, build) or [""]
            ln = next((i for i, x in enumerate(lines, 1) if x.strip()), 1)
            e = ev(build, ln, lines, app)
        g.node(nid, "Module", m["name"], {"path": m["path"], "build": m["build"], "role": m["role"]}, [e] if e else [], app=app)
        if e:
            g.edge("CONTAINS", app_node, nid, "build_metadata", "declared", "high", [e], attrs={"role": m["role"]})
    # inter-module dependencies
    by_artifact = {}
    for m in mods:
        by_artifact.setdefault(m["name"], []).append(m["path"])
    for m in mods:
        path = m["path"]
        if m["build"] == "maven":
            pom = "pom.xml" if path == "." else path + "/pom.xml"
            for coord, scope, ln in I.maven_deps(ctx, pom) if pom in ctx.poms else []:
                art = coord.split(":")[1]
                tgt = by_artifact.get(art, [])
                if len(tgt) == 1 and tgt[0] != path and scope != "test":
                    lines = evidence.read_lines(ctx.repo, pom) or []
                    g.edge("DEPENDS_ON", ids[path], ids[tgt[0]], "build_metadata", "declared", "high", [ev(pom, ln, lines, app)], attrs={"scope": scope, "via": "maven"})
        else:
            for f in [x for x in ctx.gradle if (os.path.dirname(x) or ".") == path]:
                lines = evidence.read_lines(ctx.repo, f) or []
                for i, l in enumerate(lines, 1):
                    mm = re.match(r"^\s*(\w+)\s*\(?\s*project\(\s*(?:path\s*[:=]\s*)?[\"']:?([\w:.-]+)[\"']", l)
                    if mm and not l.strip().startswith("//") and not re.match(r"(?i)^\w*test", mm.group(1)):
                        d = mm.group(2).replace(":", "/")
                        cand = [p for p in ids if p == d or p.endswith("/" + d) or p == d.split("/")[-1]]
                        if len(cand) == 1 and cand[0] != path:
                            g.edge("DEPENDS_ON", ids[path], ids[cand[0]], "build_metadata", "declared", "high", [ev(f, i, lines, app)], attrs={"scope": "runtime", "via": "gradle"})
                        elif len(cand) > 1:
                            g.skip("project(%s) at %s:%d" % (mm.group(2), f, i), "matches %d module directories" % len(cand), [ev(f, i, lines, app)])


def deployment(ctx, g: Graph, app: str, app_node: str, disc: dict):
    hosting = disc.get("stack", {}).get("hosting", {})
    wl = k8s_workloads(ctx, app)
    for h in hosting.get("value") or []:
        ats = [x for x in (_at(ctx, a, app) for a in h["at"]) if x]
        if h["role"] != "deployment target":
            g.skip("%s (%s)" % (h["target"], h["role"]), "an image registry says where images are stored, not where they run", ats)
            continue
        if not ats:
            continue
        nid = "infra:%s:%s" % (app, h["target"])
        attrs = {"platform": h["target"], "via": h["via"]}
        if h["target"] == "Kubernetes" and wl:
            attrs["workloads"] = [{"kind": w["kind"], "name": w["name"], "namespace": w["namespace"], "image": w["image"]} for w in wl]
        g.node(nid, "InfrastructureResource", h["target"], attrs, ats, app=app)
        mech = "deployment_descriptor" if "pipeline command" not in h["basis"] or len(h["basis"]) > 1 else "configuration"
        g.edge("DEPLOYED_ON", app_node, nid, mech, "static_configured", "high" if mech == "deployment_descriptor" else "medium", ats,
               attrs={"basis": h["basis"], "via": h["via"]},
               note=None if mech == "deployment_descriptor" else "a pipeline command names the platform; the pipeline's execution was not observed")
    if hosting.get("status") == "UNKNOWN":
        g.skip("deployment target", "pipeline templates or server-side jobs may deploy it: not visible offline", hosting.get("evidence", []))


def _at(ctx, at, app):
    path, _, ln = at.rpartition(":")
    lines = evidence.read_lines(ctx.repo, path) or []
    n = int(ln)
    return ev(path, n, lines, app) if 0 < n <= len(lines) else None


# ---- hosts an application declares about itself --------------------------------------------------------------------------
HOST_IN_URL = re.compile(r"https?://([A-Za-z0-9][A-Za-z0-9._-]*)")
SELF_URL_VAR = re.compile(r"^\s*(?:-\s*)?[\"']?(?:BASE_URL|(?:APP|SERVICE|API|TARGET|INTEGRATION|SMOKE)_(?:BASE_)?(?:URL|HOST))[\"']?\s*[:=]\s*[\"']?(https?://[^\s\"']+)")


def declared_hosts(ctx, app: str) -> List[dict]:
    """Hosts this application announces about itself, from files that describe the application, not from files that merely call something:
    OpenAPI/Swagger `servers[].url` / `host` / `x-google-audience` (also the Cloud Endpoints API config), Kubernetes Ingress / Istio / Gateway API / Traefik hosts,
    and the application's own pipeline variable naming its own base URL. Each entry: {host, source, strength, evidence}."""
    out, seen = [], set()

    def add(host, source, strength, e):
        h = host.lower().rstrip(".")
        if "{" in h or "$" in h or h in ("localhost",) or (h, source) in seen:
            return
        seen.add((h, source))
        out.append({"host": h, "source": source, "strength": strength, "evidence": e})
    for f in sorted(ctx.files):
        if ctx._aux(f) or ctx._test_module(f) or "/src/test/" in "/" + f or f.startswith(("node_modules/", "build/")):
            continue
        base = os.path.basename(f)
        if not f.endswith((".yml", ".yaml", ".json")) and not base.startswith(".gitlab-ci"):
            continue
        lines = evidence.read_lines(ctx.repo, f) or []
        text = "\n".join(lines)
        is_spec = bool(re.search(r"^\s*[\"']?(?:openapi|swagger)[\"']?\s*:", text, re.M)) or "x-google-audience" in text or "x-google-endpoints" in text
        is_k8s = bool(re.search(r"^kind:\s*(?:Ingress|IngressRoute|VirtualService|HTTPRoute|Gateway|Route)\b", text, re.M))
        for i, ln in enumerate(lines, 1):
            if ln.strip().startswith("#"):
                continue
            if is_spec:
                m = re.search(r"^\s*(?:-\s*)?[\"']?url[\"']?\s*:\s*[\"']?(https?://[^\s\"'/]+)", ln) if any(re.match(r"^\s*[\"']?servers[\"']?\s*:", x) for x in lines[max(0, i - 8):i]) else None
                if m:
                    add(HOST_IN_URL.match(m.group(1)).group(1), "OpenAPI servers", "strong", ev(f, i, lines, app))
                    continue
                m = re.search(r"x-google-audiences?[\"']?\s*:\s*[\"']?(https?://[^\s\"'/]+)", ln)
                if m:
                    add(HOST_IN_URL.match(m.group(1)).group(1), "API gateway audience", "strong", ev(f, i, lines, app))
                    continue
                m = re.match(r"^[\"']?host[\"']?\s*:\s*[\"']?([A-Za-z0-9][A-Za-z0-9._-]+)", ln)
                if m:
                    add(m.group(1), "API definition host", "strong", ev(f, i, lines, app))
                    continue
            if is_k8s:
                m = re.search(r"^\s*-?\s*host:\s*[\"']?([A-Za-z0-9*][A-Za-z0-9.*_-]*\.[A-Za-z0-9.-]+)", ln) or re.search(r"Host\(`([^`]+)`\)", ln)
                if m:
                    add(m.group(1), "ingress / route host", "strong", ev(f, i, lines, app))
                    continue
                m = re.match(r"^\s*-\s*[\"']?([A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9-]+)+)[\"']?\s*$", ln)
                if m and any(re.match(r"^\s*(?:hosts|hostnames):\s*$", x) for x in lines[max(0, i - 4):i]):
                    add(m.group(1), "ingress / route host", "strong", ev(f, i, lines, app))
                    continue
            if base.startswith(".gitlab-ci"):
                m = SELF_URL_VAR.match(ln)
                if m:
                    add(HOST_IN_URL.match(m.group(1)).group(1), "own pipeline base URL", "medium", ev(f, i, lines, app))
    return out
