"""REST adapter: exposed endpoints (Spring MVC/WebFlux, JAX-RS, Micronaut, Ktor) and outbound HTTP clients (Feign, RestTemplate,
WebClient/RestClient, java.net.http, OkHttp). Every relationship cites the source line; non-literal paths and targets stay unresolved."""
from __future__ import annotations

import re
from typing import List, Optional

import evidence
from detectors import integrations as I
from graph.model import Graph, norm_path
from graph.adapters.common import (Config, LOG_LINE, annotation_text, constants, ev, mask_comments, resolve_arg, string_literals)

VERB = {"Get": "GET", "Post": "POST", "Put": "PUT", "Delete": "DELETE", "Patch": "PATCH", "Head": "HEAD", "Options": "OPTIONS"}
SPRING_MAP = re.compile(r"@(Get|Post|Put|Delete|Patch)Mapping\b")
REQ_MAP = re.compile(r"@RequestMapping\b")
JAXRS_VERB = re.compile(r"@(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\b")
MICRO_VERB = re.compile(r"@(Get|Post|Put|Delete|Patch|Head|Options)\b(?!\w)")
CLASS_DECL = re.compile(r"\b(?:class|interface|object)\s+(\w+)")
CONTROLLER = re.compile(r"@(?:RestController|Controller|Path|Controller)\b")
URL_LIT = re.compile(r'"(https?://([A-Za-z0-9][A-Za-z0-9._-]*)(?::(\d+))?([^"\s]*))"')
HTTP_CALL = re.compile(r"getForObject|getForEntity|postForObject|postForEntity|postForLocation|\.exchange\(|\.put\(|\.delete\(|\.patchForObject|\.uri\(|baseUrl\(|"
                       r"WebClient\.create\(|RestClient\.create\(|URI\.create\(|HttpRequest\.newBuilder|new\s+URL\(|HttpGet\(|HttpPost\(|\.url\(|HttpClient|OkHttp|RestTemplate|WebClient|RestClient")


def _args(text: str, name_rx: str) -> str:
    m = re.search(name_rx + r"\s*\((.*)\)", text, re.S)
    return m.group(1) if m else ""


def _kv(args: str, *keys, arrays=False):
    for k in keys:
        m = re.search(r"\b%s\s*=\s*(\{[^}]*\}|\[[^\]]*\]|\"(?:[^\"\\]|\\.)*\"|[\w.]+)" % k, args)
        if m:
            return m.group(1)
    return None


def _first_path(args: str, cfg, consts, path):
    """Path of a mapping annotation: value=/path= or the first positional literal. ('', None) when the mapping has no path."""
    raw = _kv(args, "value", "path")
    if raw is None:
        a = args.strip()
        if not a or re.match(r"^\w+\s*=", a):
            return "", None, None
        raw = a.split(",")[0] if not a.startswith("{") else a
    raw = raw.strip()
    if raw.startswith("{"):
        lits = string_literals(raw)
        if not lits:
            return None, None, "path array is not made of literals"
        raw = '"%s"' % lits[0]  # first alias; others name the same handler
    val, e, how, why = resolve_arg(raw, cfg, consts, path)
    return val, e, why


def _verbs_of_request_mapping(args: str) -> str:
    m = re.search(r"RequestMethod\.(\w+)", args)
    return m.group(1) if m else "ANY"


def _class_blocks(masked):
    """[(decl_line, name, annotation_start)] for every class/interface/object; the annotation block is the run of lines above
    (and on) the declaration that start with `@` or continue an annotation."""
    out = []
    for i, ln in enumerate(masked):
        m = CLASS_DECL.search(ln)
        if not m or re.match(r"\s*(?:import|package)\b", ln):
            continue
        j = i
        while j > 0 and (masked[j - 1].strip().startswith("@") or masked[j - 1].strip().startswith((")", ",")) or masked[j - 1].rstrip().endswith((",", "("))):
            j -= 1
        out.append((i, m.group(1), j))
    return out


def _implements(masked, decl):
    t = " ".join(masked[decl:decl + 3])
    m = re.search(r"\bimplements\s+([\w\s,.<>?]+?)(?:\{|$)", t) or re.search(r"\)\s*:\s*([\w\s,.<>?(]+?)(?:\{|$)", t) or re.search(r"\bclass\s+\w+[^:{]*:\s*([\w\s,.<>?()]+?)(?:\{|$)", t)
    if not m:
        return []
    return [re.sub(r"<.*", "", x).split(".")[-1].strip().rstrip("(") for x in m.group(1).split(",") if x.strip()]


def _scan(g, app, app_node, cfg, consts, f, lines, masked, decl, end, prefix, style, module, cname=None):
    """Endpoints declared by the mapping annotations between `decl` and `end` of one controller (or one interface it implements)."""
    for i in range(decl + 1, end):
        ln = masked[i]
        verb = path_args = None
        if SPRING_MAP.search(ln):
            verb, path_args = VERB[SPRING_MAP.search(ln).group(1)], _args(annotation_text(masked, i), r"@\w+Mapping")
        elif REQ_MAP.search(ln):
            a = annotation_text(masked, i)
            verb, path_args = _verbs_of_request_mapping(a), _args(a, r"@RequestMapping")
        elif style == "jaxrs" and JAXRS_VERB.search(ln):
            verb = JAXRS_VERB.search(ln).group(1)
            near = masked[max(decl + 1, i - 3):i + 4]
            pm = [k for k, x in enumerate(near) if "@Path" in x]
            path_args = _args(annotation_text(near, pm[0]), r"@Path") if pm else ""
        elif style == "micronaut" and MICRO_VERB.search(ln):
            verb = MICRO_VERB.search(ln).group(1).upper()
            path_args = _args(annotation_text(masked, i), r"@%s" % MICRO_VERB.search(ln).group(1))
        if verb is None:
            continue
        e = ev(f, i + 1, lines, app)
        if prefix is None:
            g.skip("endpoint at %s:%d" % (f, i + 1), "class-level path is not a literal, so the full path cannot be stated", [e])
            continue
        v, _, why2 = _first_path(path_args or "", cfg, consts, f)
        if v is None:
            g.skip("endpoint at %s:%d" % (f, i + 1), why2 or "path unresolved", [e])
            continue
        full = "/" + "/".join(x.strip("/") for x in (prefix, v) if x.strip("/"))
        _endpoint(g, app, app_node, verb, full, module, e, "source_annotation", style, {"controller": cname})


def _interfaces(ctx, cfg, consts):
    """name -> (file, lines, masked, decl, end, class-level prefix, style) for every interface that carries mapping annotations."""
    out = {}
    for f in ctx.src_main_java:
        lines = evidence.read_lines(ctx.repo, f) or []
        if not re.search(r"\binterface\b", "\n".join(lines)):
            continue
        masked = mask_comments(lines)
        blocks = _class_blocks(masked)
        for n, (decl, name, start) in enumerate(blocks):
            if not re.search(r"\binterface\s+%s\b" % re.escape(name), masked[decl]):
                continue
            end = blocks[n + 1][2] if n + 1 < len(blocks) else len(masked)
            head = masked[start:decl + 1]
            htxt = "\n".join(head)
            if not any(SPRING_MAP.search(x) or REQ_MAP.search(x) or JAXRS_VERB.search(x) for x in masked[decl + 1:end]):
                continue
            prefix = ""
            style = "jaxrs" if re.search(r"@Path\b", htxt) else "spring"
            tag = "@Path" if style == "jaxrs" else "@RequestMapping"
            if tag in htxt:
                k = [q for q, x in enumerate(head) if tag in x][0]
                prefix = _first_path(_args(annotation_text(masked, start + k), tag), cfg, consts, f)[0]
            out[name] = (f, lines, masked, decl, end, prefix, style)
    return out


def exposed(ctx, g: Graph, app: str, app_node: str, cfg: Config, consts):
    r = ctx.repo
    iface_index = _interfaces(ctx, cfg, consts)
    for f in ctx.src_main_java:
        lines = evidence.read_lines(r, f) or []
        masked = mask_comments(lines)
        text = "\n".join(masked)
        ktor = "io.ktor.server.routing" in text
        if not (CONTROLLER.search(text) or ktor):
            continue
        module = ctx.module_of(f)
        blocks = _class_blocks(masked)
        for n, (decl, name, start) in enumerate(blocks):
            head = masked[start:decl + 1]
            htxt = "\n".join(head)
            end = blocks[n + 1][2] if n + 1 < len(blocks) else len(masked)
            if re.search(r"@(?:RestController|Controller)\b", htxt) is None and not re.search(r"@Path\b", htxt):
                continue
            style, prefix = "spring", ""
            def head_args(tag):
                k = [q for q, x in enumerate(head) if tag in x][0]
                return _args(annotation_text(masked, start + k), tag)
            if re.search(r"@Path\b", htxt):
                style = "jaxrs"
                v, _, why = _first_path(head_args("@Path"), cfg, consts, f)
                prefix = v
            elif re.search(r"@Controller\s*\(", htxt):
                style = "micronaut"
                v, _, why = _first_path(head_args("@Controller"), cfg, consts, f)
                prefix = v
            elif "@RequestMapping" in htxt:
                v, _, why = _first_path(head_args("@RequestMapping"), cfg, consts, f)
                prefix = v
            else:
                why = None
            if prefix is None:
                g.skip("controller %s in %s" % (name, f), why or "class-level path unresolved", [ev(f, decl + 1, lines, app)])
            _scan(g, app, app_node, cfg, consts, f, lines, masked, decl, end, prefix, style, module, name)
            if prefix is not None:  # mappings declared on an interface the controller implements (openapi-generator "interfaceOnly" style)
                own_class_mapping = "@RequestMapping" in htxt
                for iname in _implements(masked, decl):
                    ix = iface_index.get(iname)
                    if ix:
                        ifile, ilines, imasked, idecl, iend, iprefix, istyle = ix
                        _scan(g, app, app_node, cfg, consts, ifile, ilines, imasked, idecl, iend, prefix if own_class_mapping else (iprefix or ""), istyle, module, name)
        if ktor:
            has_route = bool(re.search(r"\broute\(", text))
            for i, ln in enumerate(masked):
                m = re.search(r'\b(get|post|put|delete|patch)\(\s*"([^"]*)"\s*\)\s*\{', ln)
                if m:
                    _endpoint(g, app, app_node, m.group(1).upper(), "/" + m.group(2).strip("/"), module, ev(f, i + 1, lines, app),
                              "source_annotation", "ktor", {"path_may_be_prefixed": True} if has_route else None)


def _endpoint(g, app, app_node, verb, path, module, e, mech, style, extra=None):
    nid = "api:%s:%s %s" % (app, verb, norm_path(path))
    g.node(nid, "ApiEndpoint", "%s %s" % (verb, path), dict({"method": verb, "path": path, "path_shape": norm_path(path), "framework": style, "module": module}, **(extra or {})),
           [e], app)
    g.edge("EXPOSES_API", app_node, nid, mech, "static_configured", "high", [e], attrs={"module": module})


# ---- outbound -----------------------------------------------------------------------------------------------------------

def _target_for_host(g: Graph, host: str, app: str):
    """A host with no dots (inventory-service) names a service the platform resolves; a dotted host is an external system."""
    if "." not in host:
        nid = "svc:" + host.lower()
        g.node(nid, "Service", host.lower(), {"identity": "name"}, app=None)
        return nid, "Service"
    nid = "ext:" + host.lower()
    g.node(nid, "ExternalSystem", host.lower(), {"host": host.lower()}, app=None)
    return nid, "ExternalSystem"


def _unresolved_target(g: Graph, what: str, reason: str, e: dict):
    from graph.model import sid
    nid = "unresolved:http:" + sid(what, e["path"], str(e["line_start"]))
    g.node(nid, "ExternalSystem", "unresolved HTTP target (%s)" % what, {"unresolved": True, "reason": reason}, [e])
    return nid


def feign_clients(ctx, g: Graph, app: str, app_node: str, cfg: Config, consts):
    r = ctx.repo
    srcs = {f: "\n".join(evidence.read_lines(r, f) or []) for f in ctx.src_main_java}
    for f in ctx.src_main_java:
        lines = evidence.read_lines(r, f) or []
        masked = mask_comments(lines)
        for i, ln in enumerate(masked):
            if "@FeignClient" not in ln and "@RegisterRestClient" not in ln and not re.match(r"\s*@Client\b", ln):
                continue
            style = "feign" if "@FeignClient" in ln else "microprofile" if "@RegisterRestClient" in ln else "micronaut"
            if style == "micronaut" and "io.micronaut.http.client.annotation.Client" not in "\n".join(lines[:80]):
                continue
            a = annotation_text(masked, i)
            head = _args(a, r"@(?:FeignClient|RegisterRestClient|Client)")
            name = _kv(head, "name", "value", "id", "configKey", "baseUri") or (head.strip().split(",")[0] if head.strip().startswith('"') else None)
            url = _kv(head, "url")
            base_path = _kv(head, "path")
            e = ev(f, i + 1, lines, app)
            iface = next((CLASS_DECL.search(x).group(1) for x in masked[i:i + 8] if CLASS_DECL.search(x)), None)
            if style == "microprofile" and not name:
                name = None
            # who is called
            tnode = None
            rname = None
            cfg_ev = None
            if url:
                v, ee, how, why = resolve_arg(url, cfg, consts, f)
                cfg_ev = ee
                if v:
                    m = URL_LIT.match('"%s"' % v) if v.startswith("http") else None
                    if m:
                        tnode, _ = _target_for_host(g, m.group(2), app)
                        rname = m.group(2)
                    else:
                        tnode = _unresolved_target(g, "url=" + url, "client url %r is not an absolute http(s) URL" % v, e)
                else:
                    tnode = _unresolved_target(g, "url=" + url, why or "client url unresolved", e)
            elif name:
                v, ee, how, why = resolve_arg(name, cfg, consts, f)
                if v and "${" not in v:
                    tnode, _ = _target_for_host(g, v, app) if "." not in v else _target_for_host(g, v, app)
                    rname = v
                else:
                    tnode = _unresolved_target(g, "name=" + name, why or "client name unresolved", e)
            else:
                g.skip("client at %s:%d" % (f, i + 1), "client names neither a service nor a url", [e])
                continue
            bp = ""
            if base_path:
                v, _, _, why = resolve_arg(base_path, cfg, consts, f)
                bp = v or ""
            # is the interface used anywhere else? (a declared client that nothing references is a declaration, not a call)
            used = bool(iface) and any(re.search(r"\b%s\b" % re.escape(iface), t) for ff, t in srcs.items() if ff != f)
            # the client's own methods: from the annotation to the start of the next class/interface (with its annotations) in the file
            blocks = [b for b in _class_blocks(masked) if b[0] >= i]
            own = next((b for b in blocks if CLASS_DECL.search(masked[b[0]]) and b[1] == iface), None) if iface else None
            nxt = [b for b in blocks if own is None or b[0] > own[0]]
            end = nxt[0][2] if nxt else len(masked)
            methods = []
            for j in range(i, end):
                ln2 = masked[j]
                if SPRING_MAP.search(ln2):
                    methods.append((VERB[SPRING_MAP.search(ln2).group(1)], _args(annotation_text(masked, j), r"@\w+Mapping"), j))
                elif REQ_MAP.search(ln2) and j > i:
                    a2 = annotation_text(masked, j)
                    methods.append((_verbs_of_request_mapping(a2), _args(a2, r"@RequestMapping"), j))
                elif JAXRS_VERB.search(ln2):
                    near = masked[max(i, j - 3):j + 4]
                    pm = [k for k, x in enumerate(near) if "@Path" in x]
                    methods.append((JAXRS_VERB.search(ln2).group(1), _args(annotation_text(near, pm[0]), r"@Path") if pm else "", j))
                elif style == "micronaut" and MICRO_VERB.search(ln2) and j > i:
                    methods.append((MICRO_VERB.search(ln2).group(1).upper(), _args(annotation_text(masked, j), r"@%s" % MICRO_VERB.search(ln2).group(1)), j))
            if not methods:
                _call(g, app, app_node, tnode, None, None, e, "source_annotation", "medium" if used else "low", rname,
                      {"client_interface": iface, "style": style, "referenced_elsewhere": used}, cfg_ev)
            for verb, margs, j in methods:
                v, _, why = _first_path(margs, cfg, consts, f)
                if v is None:
                    g.skip("client method at %s:%d" % (f, j + 1), why or "path unresolved", [ev(f, j + 1, lines, app)])
                    v = None
                path = "/" + "/".join(x.strip("/") for x in (bp, v) if x and x.strip("/")) if v is not None else None
                _call(g, app, app_node, tnode, verb, path, ev(f, j + 1, lines, app), "source_annotation", "high" if used else "low", rname,
                      {"client_interface": iface, "style": style, "referenced_elsewhere": used}, cfg_ev)
    return


FEIGN_TARGET = re.compile(r"\.target\(\s*(\w+)\.class\s*,\s*([^)]+?)\s*\)")


def feign_builders(ctx, g: Graph, app: str, app_node: str, cfg: Config, consts):
    """Feign clients built in code: Feign.builder()...target(Api.class, url), where url is a literal, a constant or an @Value
    property. The annotation-driven extractor above does not see them, so without this the clients are missing from the graph."""
    r = ctx.repo
    srcs = {f: "\n".join(evidence.read_lines(r, f) or []) for f in ctx.src_main_java}
    for f, text in srcs.items():
        if not re.search(r"\bFeign\.(?:builder\s*\(|Builder\b)|\bHystrixFeign\.builder", text):
            continue
        lines = evidence.read_lines(r, f) or []
        masked = mask_comments(lines)
        for i, ln in enumerate(masked):
            m = FEIGN_TARGET.search(ln)
            if not m:
                continue
            iface, arg = m.group(1), m.group(2)
            e = ev(f, i + 1, lines, app)
            v, cfg_ev, how, why = resolve_arg(arg, cfg, consts, f)
            u = URL_LIT.match('"%s"' % v) if v and v.startswith("http") else None
            if u:
                tnode, _ = _target_for_host(g, u.group(2), app)
                rname = u.group(2)
            else:
                tnode, rname = _unresolved_target(g, "target=" + arg, why or "client url %r is not an absolute http(s) URL" % v, e), None
            used = any(re.search(r"\b%s\b" % re.escape(iface), t) for ff, t in srcs.items() if ff != f)
            _call(g, app, app_node, tnode, None, None, e, "source_call", "medium" if used else "low", rname,
                  {"client_interface": iface, "style": "feign_builder", "referenced_elsewhere": used}, cfg_ev)


def _call(g, app, app_node, tnode, verb, path, e, mech, conf, rname, attrs, cfg_ev=None):
    """cfg_ev: the configuration line that supplied the target host, cited next to the source line that makes the call."""
    tgt = g.nodes.get(tnode, {})
    unresolved = tgt.get("attrs", {}).get("unresolved")
    a = dict(attrs)
    if cfg_ev:
        from detectors.integrations import env_of
        a["host_from_configuration"] = cfg_ev["path"]
        a["environment"] = env_of(cfg_ev["path"])
    evs = [e] + ([cfg_ev] if cfg_ev else [])
    a.update({"method": verb, "path": path, "path_shape": norm_path(path) if path else None, "target_name": rname})
    if unresolved:
        g.edge("CALLS_API", app_node, tnode, mech, "unresolved", "low", evs, {"state": "unresolved", "reason": tgt["attrs"]["reason"]}, a)
    else:
        # a name is not yet a resolved service: cross-repository resolution (resolve.py) decides, and only on evidence
        res = {"state": "unresolved", "reason": "service name %r not yet matched to a known application" % rname} if tgt.get("type") == "Service" else {"state": "not_applicable", "reason": "external host"}
        g.edge("CALLS_API", app_node, tnode, mech, "static_configured", conf, evs, res, a)


def http_calls(ctx, g: Graph, app: str, app_node: str, cfg: Config, consts, skip_hosts=()):
    """RestTemplate / WebClient / RestClient / java.net.http / OkHttp calls whose URL is a literal or a resolvable @Value property."""
    r = ctx.repo
    for f in ctx.src_main_java:
        lines = evidence.read_lines(r, f) or []
        masked = mask_comments(lines)
        text = "\n".join(masked)
        if not re.search(r"RestTemplate|WebClient|RestClient|java\.net\.http|okhttp|HttpClient|HttpURLConnection|io\.ktor\.client|URL\(", text):
            continue
        fields = {m.group(2): m.group(1) for m in re.finditer(r'@Value\(\s*"(\$\{[^"]+\})"\s*\)\s*(?:private\s+|protected\s+|final\s+|lateinit\s+|var\s+|val\s+)*(?:String\s+)?(\w+)', text)}
        fields.update({m.group(2): m.group(1) for m in re.finditer(r'@Value\(\s*"(\$\{[^"]+\})"\s*\)\s*(?:private\s+|protected\s+|final\s+)*\w+\s+(\w+)', text)})
        for i, ln in enumerate(masked):
            if not HTTP_CALL.search(ln):
                continue
            if LOG_LINE.search(ln):
                for m in URL_LIT.finditer(ln):
                    g.skip("URL at %s:%d" % (f, i + 1), "appears in a log or print statement, not a call", [ev(f, i + 1, lines, app)])
                continue
            e = ev(f, i + 1, lines, app)
            m = URL_LIT.search(ln)
            if m:
                host = m.group(2)
                from detectors.integrations import ENDPOINT_HOST_NOT
                if ENDPOINT_HOST_NOT.match(host) and not re.search(r"\.svc(?:\.cluster\.local)?$", host, re.I):  # a Kubernetes service DNS name is a real target
                    g.skip("URL at %s:%d" % (f, i + 1), "host %s is local or a documentation placeholder" % host, [e])
                    continue
                if host.lower() in skip_hosts and not (m.group(4) or "") and re.search(r"baseUrl\(|\.create\(|rootUri", ln):
                    continue  # the base URL of an @HttpExchange client: its methods carry the paths
                tnode, _ = _target_for_host(g, host, app)
                p = m.group(4) or ""
                verb = _verb_on_line(ln)
                _call(g, app, app_node, tnode, verb, p if p else None, e, "source_call", "medium", host, {"style": "http-client-call"})
                continue
            for var, prop in fields.items():
                if re.search(r"\b%s\b" % re.escape(var), ln) and HTTP_CALL.search(ln):
                    v, ee, why = cfg.resolve(prop)
                    mm = URL_LIT.match('"%s"' % v) if v else None
                    suffix = re.search(r"\b%s\b\s*\+\s*\"([^\"]*)\"" % re.escape(var), ln)
                    ev_list = [e] + ([ee] if ee else [])
                    if mm:
                        tnode, _ = _target_for_host(g, mm.group(2), app)
                        p = (mm.group(4) or "") + (suffix.group(1) if suffix else "")
                        _call(g, app, app_node, tnode, _verb_on_line(ln), p or None, e, "source_call", "medium", mm.group(2),
                              {"style": "http-client-call", "property": prop})
                        g.edges[[k for k in g.edges if g.edges[k]["source"] == app_node and g.edges[k]["target"] == tnode][-1]]["evidence"] = ev_list
                    else:
                        tnode = _unresolved_target(g, prop, why or "property value is not an absolute URL", e)
                        g.edge("CALLS_API", app_node, tnode, "source_call", "unresolved", "low", [e], {"state": "unresolved", "reason": why or "property value is not an absolute URL"},
                               {"style": "http-client-call", "property": prop})
                    break


def _verb_on_line(ln: str) -> Optional[str]:
    m = re.search(r"\.(get|post|put|delete|patch)\(\)|(get|post|put|patch)For(?:Object|Entity|Location)|\.(GET|POST|PUT|DELETE)\(", ln)
    if m:
        return (m.group(1) or m.group(2) or m.group(3)).upper()
    m = re.search(r"HttpMethod\.(\w+)", ln)
    return m.group(1) if m else None


# ---- Spring 6 declarative clients (@HttpExchange) ------------------------------------------------------------------------
EXCHANGE_VERB = re.compile(r"@(Get|Post|Put|Delete|Patch)Exchange\b")
BASE_URL = re.compile(r'(?:baseUrl|WebClient\.create|RestClient\.create|RestTemplateBuilder[^;]*rootUri|rootUri)\(\s*"(https?://[^"]+)"')


def http_exchange_clients(ctx, g: Graph, app: str, app_node: str, cfg: Config, consts):
    """@HttpExchange interfaces. The target is the interface's own `url`, or the single literal base URL the application configures for a
    WebClient/RestClient in code; with none or several it is an explicit unresolved target. Returns the hosts it attached paths to."""
    r = ctx.repo
    srcs = {f: "\n".join(evidence.read_lines(r, f) or []) for f in ctx.src_main_java}
    bases = sorted({m.group(1) for t in srcs.values() for m in BASE_URL.finditer("\n".join(mask_comments(t.split("\n"))))})
    used = set()
    for f in ctx.src_main_java:
        lines = evidence.read_lines(r, f) or []
        masked = mask_comments(lines)
        if "HttpExchange" not in "\n".join(masked):
            continue
        for decl, name, start in _class_blocks(masked):
            head = "\n".join(masked[start:decl + 1])
            if "@HttpExchange" not in head or not re.search(r"\binterface\b", masked[decl]):
                continue
            a = _args(annotation_text(masked, start + [q for q, x in enumerate(masked[start:decl + 1]) if "@HttpExchange" in x][0]), "@HttpExchange")
            cls_url = _kv(a, "url") or (a.strip().split(",")[0] if a.strip().startswith('"') else None)
            v = resolve_arg(cls_url, cfg, consts, f)[0] if cls_url else ""
            e0 = ev(f, decl + 1, lines, app)
            if v.startswith("http"):
                m = URL_LIT.match('"%s"' % v)
                tnode, _ = _target_for_host(g, m.group(2), app)
                rname, base_path = m.group(2), (m.group(4) or "")
            elif len(bases) == 1:
                m = URL_LIT.match('"%s"' % bases[0])
                tnode, _ = _target_for_host(g, m.group(2), app)
                rname, base_path = m.group(2), (m.group(4) or "") + v
            else:
                tnode = _unresolved_target(g, "declarative client", "the base URL of this @HttpExchange client is set in code that is not a single literal" if not bases else "several base URLs are configured in code", e0)
                rname, base_path = None, v
            end = next((b[2] for b in _class_blocks(masked) if b[0] > decl), len(masked))
            used_iface = bool(re.search(r"\b%s\b" % re.escape(name), "\n".join(t for ff, t in srcs.items() if ff != f))) or any(re.search(r"\b%s\b" % re.escape(name), "\n".join(masked[end:])) for _ in [0])
            for j in range(decl + 1, end):
                mm = EXCHANGE_VERB.search(masked[j])
                if not mm:
                    continue
                margs = _args(annotation_text(masked, j), r"@\w+Exchange")
                pv, _, why = _first_path(margs, cfg, consts, f)
                if pv is None:
                    g.skip("client method at %s:%d" % (f, j + 1), why or "path unresolved", [ev(f, j + 1, lines, app)])
                    continue
                path = "/" + "/".join(x.strip("/") for x in (base_path, pv) if x and x.strip("/"))
                _call(g, app, app_node, tnode, mm.group(1).upper(), path, ev(f, j + 1, lines, app), "source_annotation", "high" if used_iface else "low", rname,
                      {"style": "http-exchange", "referenced_elsewhere": used_iface})
                if rname:
                    used.add(rname)
    return used


# ---- WebFlux functional endpoints ---------------------------------------------------------------------------------------
ROUTE_FIRST = re.compile(r"\b(?:route|andRoute)\(\s*(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\(\s*\"([^\"]*)\"")
ROUTE_BUILDER = re.compile(r"\.(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\(\s*\"([^\"]*)\"\s*,")


def router_functions(ctx, g: Graph, app: str, app_node: str):
    """RouterFunctions.route(GET("/x"), h).andRoute(POST("/y"), h) and route().GET("/x", h) builders. A nested `path(...)` / `nest(...)` prefix is not
    combined: the endpoint says its path may be prefixed."""
    r = ctx.repo
    for f in ctx.src_main_java:
        lines = evidence.read_lines(r, f) or []
        masked = mask_comments(lines)
        text = "\n".join(masked)
        if not re.search(r"RouterFunction|RouterFunctions|\broute\(\)", text):
            continue
        nested = bool(re.search(r"\bnest\(|\.path\(|\bpath\(\s*\"", text))
        module = ctx.module_of(f)
        for i, ln in enumerate(masked):
            for rx in (ROUTE_FIRST, ROUTE_BUILDER):
                for m in rx.finditer(ln):
                    _endpoint(g, app, app_node, m.group(1), "/" + m.group(2).strip("/"), module, ev(f, i + 1, lines, app), "source_call", "webflux-router",
                              {"path_may_be_prefixed": True} if nested else None)
