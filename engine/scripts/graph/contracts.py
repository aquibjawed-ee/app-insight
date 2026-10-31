"""Contract / schema compatibility checks used by change-impact analysis. Deterministic, structural, conservative:
a change is `breaking` only when it removes or tightens something a consumer can rely on."""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from graph.model import norm_path

HTTP = ("get", "put", "post", "delete", "options", "head", "patch")


def load_spec(path: str) -> Optional[dict]:
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return None
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        import yaml  # optional; the core engine is stdlib-only
        d = yaml.safe_load(text)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _ops(spec: dict) -> Dict[str, dict]:
    out = {}
    for p, item in (spec.get("paths") or {}).items():
        for m, op in (item or {}).items():
            if m.lower() in HTTP and isinstance(op, dict):
                out["%s %s" % (m.upper(), norm_path(p))] = dict(op, _path=p, _item=item)
    return out


def _required_params(op: dict) -> set:
    ps = list(op.get("parameters") or []) + list((op.get("_item") or {}).get("parameters") or [])
    return {"%s:%s" % (p.get("in"), p.get("name")) for p in ps if isinstance(p, dict) and p.get("required")}


def _resp_codes(op: dict) -> set:
    return {str(c) for c in (op.get("responses") or {})}


def _props(schema, spec, depth=0):
    if not isinstance(schema, dict) or depth > 4:
        return {}
    if "$ref" in schema:
        node = spec
        for part in schema["$ref"].lstrip("#/").split("/"):
            node = (node or {}).get(part) if isinstance(node, dict) else None
        return _props(node, spec, depth + 1)
    return dict(schema.get("properties") or {})


def _resp_props(op, spec):
    out = {}
    for code, r in (op.get("responses") or {}).items():
        if str(code).startswith("2") and isinstance(r, dict):
            for ct, mt in ((r.get("content") or {}).items()):
                for k in _props((mt or {}).get("schema"), spec):
                    out.setdefault(str(code), set()).add(k)
    return out


def diff_openapi(old: dict, new: dict) -> List[dict]:
    """Breaking and non-breaking differences between two OpenAPI documents (paths, required parameters, response codes, response properties)."""
    a, b = _ops(old), _ops(new)
    out = []
    for k in sorted(set(a) | set(b)):
        if k not in b:
            out.append({"endpoint": k, "change": "removed", "breaking": True, "detail": "operation removed"})
        elif k not in a:
            out.append({"endpoint": k, "change": "added", "breaking": False, "detail": "operation added"})
        else:
            added_req = sorted(_required_params(b[k]) - _required_params(a[k]))
            if added_req:
                out.append({"endpoint": k, "change": "required_param_added", "breaking": True, "detail": "new required parameter(s): " + ", ".join(added_req)})
            lost = sorted(_resp_codes(a[k]) - _resp_codes(b[k]))
            if lost:
                out.append({"endpoint": k, "change": "response_removed", "breaking": True, "detail": "response code(s) no longer documented: " + ", ".join(lost)})
            pa, pb = _resp_props(a[k], old), _resp_props(b[k], new)
            for code in sorted(set(pa) & set(pb)):
                gone = sorted(pa[code] - pb[code])
                if gone:
                    out.append({"endpoint": k, "change": "response_property_removed", "breaking": True, "detail": "response %s no longer has: %s" % (code, ", ".join(gone))})
    return out


def diff_avro(old: dict, new: dict) -> List[dict]:
    """Backward compatibility for a record schema where consumers move to the NEW schema and read data written with the OLD one,
    and forward compatibility for old consumers reading new data. Fields only (names, defaults, primitive types)."""
    def fields(s):
        return {f["name"]: f for f in (s.get("fields") or [])}
    a, b = fields(old), fields(new)
    out = []
    for n in sorted(set(a) - set(b)):
        if "default" not in a[n]:
            out.append({"change": "field_removed", "field": n, "breaking": True, "detail": "old consumers require %r but new data no longer carries it and it has no default" % n})
        else:
            out.append({"change": "field_removed", "field": n, "breaking": False, "detail": "removed; old readers fall back to the default"})
    for n in sorted(set(b) - set(a)):
        if "default" not in b[n]:
            out.append({"change": "field_added", "field": n, "breaking": True, "detail": "new field %r has no default: new consumers cannot read old data" % n})
        else:
            out.append({"change": "field_added", "field": n, "breaking": False, "detail": "added with a default"})
    for n in sorted(set(a) & set(b)):
        if json.dumps(a[n].get("type"), sort_keys=True) != json.dumps(b[n].get("type"), sort_keys=True):
            out.append({"change": "type_changed", "field": n, "breaking": True, "detail": "%s: %s -> %s (promotion rules are not evaluated; treat as breaking)" % (
                n, json.dumps(a[n].get("type")), json.dumps(b[n].get("type")))})
    return out
