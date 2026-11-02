#!/usr/bin/env python3
"""Schema + evidence validation, and the only sanctioned path for LLM output into discovery.json.

  validate.py check  discovery.json [--repo REPO]      schema, fingerprint and (with --repo) evidence re-verify
  validate.py merge-llm discovery.json fill.json       merge narrative/resolutions (rejects anything else)

fill.json: {"narrative": {"text": "...", "cites": ["tests.coverage_state"]},
            "resolutions": [{"ambiguity_id": "amb-ci-system", "answer": "...", "cites": ["build_ci.ci_system"]}]}
An LLM can never write status/evidence/value: unknown keys are rejected, and every cite must be a real fact or criterion id.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evidence  # noqa: E402

SCHEMA_PATH = os.path.join(HERE, "..", "schemas", "discovery.v1.schema.json")


def fingerprint(doc: dict) -> str:
    """Hash of the facts layer only: excludes run_meta (timestamp) and llm_fill (model output)."""
    return evidence.canonical_hash({k: v for k, v in doc.items() if k not in ("run_meta", "llm_fill")})


def _mini(schema, inst, root, path, errs):
    """Subset of JSON Schema 2020-12 (type/enum/const/required/properties/additionalProperties/items/$ref/minimum)
    so the CLI runs with the stdlib only. jsonschema is used instead when installed."""
    if "$ref" in schema:
        node = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            node = node[part]
        return _mini(node, inst, root, path, errs)
    if "const" in schema and inst != schema["const"]:
        errs.append("%s: expected %r" % (path, schema["const"]))
    if "enum" in schema and inst not in schema["enum"]:
        errs.append("%s: %r not in %s" % (path, inst, schema["enum"]))
    t = schema.get("type")
    if t:
        ok = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None),
              "integer": int, "number": (int, float)}
        for tt in (t if isinstance(t, list) else [t]):
            if isinstance(inst, ok[tt]) and not (tt in ("integer", "number") and isinstance(inst, bool)):
                break
        else:
            errs.append("%s: wrong type, expected %s" % (path, t))
            return
    if isinstance(inst, (int, float)) and not isinstance(inst, bool):
        if "minimum" in schema and inst < schema["minimum"]:
            errs.append("%s: below minimum" % path)
        if "maximum" in schema and inst > schema["maximum"]:
            errs.append("%s: above maximum" % path)
    if isinstance(inst, dict):
        for k in schema.get("required", []):
            if k not in inst:
                errs.append("%s: missing %s" % (path, k))
        props = schema.get("properties", {})
        ap = schema.get("additionalProperties", True)
        for k, v in sorted(inst.items()):
            if k in props:
                _mini(props[k], v, root, "%s.%s" % (path, k), errs)
            elif ap is False:
                errs.append("%s: unexpected key %s" % (path, k))
            elif isinstance(ap, dict):
                _mini(ap, v, root, "%s.%s" % (path, k), errs)
    if isinstance(inst, list) and "items" in schema:
        for i, v in enumerate(inst):
            _mini(schema["items"], v, root, "%s[%d]" % (path, i), errs)


def provenance(doc: dict) -> list:
    """Every CONFIRMED fact must cite evidence or declare a derivation. A derivation names its rule and input facts,
    and every input must itself be supported (cites evidence, or has a valid derivation). Cycles are rejected."""
    facts = dict(evidence.iter_facts(doc))
    errs, memo = [], {}

    def supported(fid, stack):
        if fid in memo:
            return memo[fid]
        f = facts.get(fid)
        if f is None:
            return False
        if f["evidence"] or f["status"] == "NOT_FOUND":  # a bounded search that found nothing is a valid observation
            memo[fid] = True
            return True
        d = f.get("derivation")
        if not d or f["status"] not in ("CONFIRMED", "INFERRED"):
            memo[fid] = False
            return False
        if fid in stack:
            errs.append("%s: derivation cycle %s" % (fid, " -> ".join(stack + [fid])))
            return False
        ok = bool(d["inputs"])
        if not ok:
            errs.append("%s: derivation %r names no input facts" % (fid, d["rule"]))
        for i in d["inputs"]:
            if i not in facts:
                errs.append("%s: derivation input %r does not exist" % (fid, i))
                ok = False
            elif not supported(i, stack + [fid]):
                errs.append("%s: derivation input %r is not supported by evidence" % (fid, i))
                ok = False
        memo[fid] = ok
        return ok

    for fid, f in facts.items():
        if f["status"] == "CONFIRMED" and not supported(fid, []):
            if not f["evidence"] and not f.get("derivation"):
                errs.append("%s: CONFIRMED but cites no evidence and declares no derivation" % fid)
    return sorted(set(errs))


def validate(doc: dict) -> list:
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        schema = json.load(fh)
    try:
        import jsonschema
        v = jsonschema.Draft202012Validator(schema)
        errs = sorted("%s: %s" % ("/".join(map(str, e.path)), e.message) for e in v.iter_errors(doc))
    except ImportError:
        errs = []
        _mini(schema, doc, schema, "$", errs)
    return errs + (provenance(doc) if not errs else [])


def known_ids(doc: dict) -> set:
    ids = {fid for fid, _ in evidence.iter_facts(doc)}
    ids |= {c["id"] for c in doc.get("maturity", {}).get("criteria", [])}
    return ids


def merge_llm(doc: dict, fill: dict) -> list:
    errs = []
    extra = set(fill) - {"narrative", "resolutions"}
    if extra:
        errs.append("fill.json: unexpected keys %s (llm may not write facts)" % sorted(extra))
    ids = known_ids(doc)
    amb = {a["id"] for a in doc["llm_fill"]["ambiguities"]}

    def cites_ok(where, cites):
        for c in cites:
            if c not in ids:
                errs.append("%s: cites unknown fact %r" % (where, c))

    nar = fill.get("narrative")
    if nar is not None:
        if set(nar) - {"text", "cites"}:
            errs.append("narrative: unexpected keys %s" % sorted(set(nar) - {"text", "cites"}))
        if not nar.get("cites"):
            errs.append("narrative: must cite at least one fact id")
        cites_ok("narrative", nar.get("cites", []))
    res = fill.get("resolutions", [])
    for i, r in enumerate(res):
        if set(r) - {"ambiguity_id", "answer", "cites"}:
            errs.append("resolutions[%d]: unexpected keys %s" % (i, sorted(set(r) - {"ambiguity_id", "answer", "cites"})))
        if r.get("ambiguity_id") not in amb:
            errs.append("resolutions[%d]: unknown ambiguity %r" % (i, r.get("ambiguity_id")))
        cites_ok("resolutions[%d]" % i, r.get("cites", []))
    if errs:
        return errs
    if nar is not None:
        doc["llm_fill"]["narrative"] = {"source": "llm", "text": nar["text"], "cites": sorted(nar["cites"])}
    doc["llm_fill"]["resolutions"] = [{"source": "llm", "ambiguity_id": r["ambiguity_id"], "answer": r["answer"],
                                       "cites": sorted(r.get("cites", []))} for r in res]
    return validate(doc)


def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) >= 2 and a[0] == "check":
        doc = json.load(open(a[1], encoding="utf-8"))
        errs = validate(doc)
        if doc.get("run_meta", {}).get("fingerprint") != fingerprint(doc):
            errs.append("fingerprint mismatch: facts were edited after generation")
        if "--repo" in a:
            repo = a[a.index("--repo") + 1]
            if doc["run_meta"].get("inventory_fingerprint") != evidence.inventory_fingerprint(repo, evidence.walk(repo)):
                errs.append("STALE: the repository changed since this discovery was generated (inventory fingerprint differs)")
            for fid, f in evidence.iter_facts(doc):
                for e in f["evidence"]:
                    bad = evidence.verify(repo, e)
                    if bad:
                        errs.append("%s: %s" % (fid, bad))
    elif len(a) == 3 and a[0] == "merge-llm":
        doc = json.load(open(a[1], encoding="utf-8"))
        errs = merge_llm(doc, json.load(open(a[2], encoding="utf-8")))
        if not errs:
            with open(a[1] + ".tmp", "w", encoding="utf-8") as fh:
                json.dump(evidence.redact_tree(doc), fh, indent=2, sort_keys=True)
                fh.write("\n")
            os.replace(a[1] + ".tmp", a[1])
    else:
        print(__doc__, file=sys.stderr)
        return 2
    for e in errs:
        print("INVALID: " + e)
    print("OK" if not errs else "%d problem(s)" % len(errs))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
