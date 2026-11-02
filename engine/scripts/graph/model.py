"""Canonical relationship model: nodes, edges, stable ids, integrity validation. Pure data, no repository access."""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Dict, Iterable, List, Optional

CONTRACT = "relationships.v1"

NODE_TYPES = ("Application", "Module", "Service", "ApiEndpoint", "Database", "MessageBroker", "Topic", "ExternalSystem",
              "InfrastructureResource")
EDGE_TYPES = ("CONTAINS", "EXPOSES_API", "CALLS_API", "PUBLISHES_TO", "CONSUMES_FROM", "READS_FROM", "WRITES_TO", "DEPENDS_ON",
              "DEPLOYED_ON")
# How the relationship was learned
BASES = ("observed_runtime", "static_configured", "declared", "inferred", "unresolved")
MECHANISMS = ("source_annotation", "source_call", "configuration", "dependency_declaration", "build_metadata",
              "deployment_descriptor", "runtime_observation", "cross_repo_resolution")
CONFIDENCE = ("high", "medium", "low")
RESOLUTION_STATES = ("resolved", "unresolved", "ambiguous", "not_applicable")


def sid(*parts: str) -> str:
    """Short stable digest of the parts: the same facts always give the same id."""
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:12]


def norm_path(p: str) -> str:
    """Compare URL paths on shape: `/orders/{id}` == `/orders/{orderId}` == `/orders/:id`; trailing slash and case of literals kept apart."""
    p = "/" + (p or "").strip().split("?")[0].strip("/")
    p = re.sub(r"\{[^}/]*\}|:[A-Za-z_]\w*|\$\{[^}]*\}", "{}", p)
    return p


class Graph:
    def __init__(self, scope: str = "application"):
        self.scope = scope
        self.nodes: Dict[str, dict] = {}
        self.edges: Dict[str, dict] = {}
        self.unmatched: List[dict] = []  # things looked for and deliberately not turned into relationships

    # ---- construction
    def node(self, nid: str, ntype: str, name: str, attrs: Optional[dict] = None, evidence: Optional[List[dict]] = None,
             app: Optional[str] = None) -> str:
        if ntype not in NODE_TYPES:
            raise ValueError("bad node type %r" % ntype)
        n = self.nodes.get(nid)
        if n is None:
            n = self.nodes[nid] = {"id": nid, "type": ntype, "name": name, "app": app, "attrs": {}, "evidence": []}
        if attrs:
            for k, v in attrs.items():
                n["attrs"].setdefault(k, v)
        for e in evidence or []:
            if e not in n["evidence"] and len(n["evidence"]) < 6:
                n["evidence"].append(e)
        return nid

    def edge(self, etype: str, source: str, target: str, mechanism: str, basis: str, confidence: str,
             evidence: List[dict], resolution: Optional[dict] = None, attrs: Optional[dict] = None, note: Optional[str] = None) -> str:
        if etype not in EDGE_TYPES or mechanism not in MECHANISMS or basis not in BASES or confidence not in CONFIDENCE:
            raise ValueError("bad edge %s %s %s %s" % (etype, mechanism, basis, confidence))
        key = [etype, source, target, mechanism]
        if evidence:
            key.append("%s:%s" % (evidence[0].get("path", evidence[0].get("cmd", "")), evidence[0].get("line_start", "")))
        eid = "e-" + sid(*key)
        if eid in self.edges:
            return eid
        e = {"id": eid, "type": etype, "source": source, "target": target, "mechanism": mechanism, "basis": basis,
             "confidence": confidence, "status": "CONFIRMED" if basis in ("static_configured", "observed_runtime") or (basis == "declared" and evidence) else "INFERRED",
             "resolution": resolution or {"state": "resolved"}, "evidence": evidence, "attrs": attrs or {}}
        if basis == "unresolved":
            e["status"] = "UNKNOWN"
        if note:
            e["note"] = note
        self.edges[eid] = e
        return eid

    def skip(self, what: str, why: str, evidence: Optional[List[dict]] = None):
        """Record a candidate that was NOT made a relationship (so a reviewer can see the rule, and tests can assert it)."""
        self.unmatched.append({"what": what, "why": why, "evidence": evidence or []})

    # ---- output
    def to_doc(self, meta: Optional[dict] = None) -> dict:
        doc = {"contract": CONTRACT, "scope": self.scope,
               "nodes": [self.nodes[k] for k in sorted(self.nodes)],
               "edges": [self.edges[k] for k in sorted(self.edges)],
               "not_relationships": sorted(self.unmatched, key=lambda u: (u["what"], u["why"]))}
        doc["meta"] = meta or {}
        return doc


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def dump(doc: dict, path: str):
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        import evidence  # redacted on the way out: no secret reaches a written file
        json.dump(evidence.redact_tree(doc), fh, indent=2, sort_keys=True)
        fh.write("\n")
    import os
    os.replace(path + ".tmp", path)


def validate_integrity(doc: dict, repos: Optional[Dict[str, str]] = None, external: Optional[Dict[str, object]] = None) -> List[str]:
    """Reference and evidence integrity. repos maps application id -> repo path; when given, every file citation is re-read."""
    errs: List[str] = []
    if doc.get("contract") != CONTRACT:
        errs.append("contract must be %s" % CONTRACT)
    ids = set()
    for n in doc.get("nodes", []):
        if n["id"] in ids:
            errs.append("duplicate node id %s" % n["id"])
        ids.add(n["id"])
        if n["type"] not in NODE_TYPES:
            errs.append("node %s: bad type %r" % (n["id"], n["type"]))
    eids = set()
    for e in doc.get("edges", []):
        if e["id"] in eids:
            errs.append("duplicate edge id %s" % e["id"])
        eids.add(e["id"])
        for end in ("source", "target"):
            if e[end] not in ids:
                errs.append("edge %s: %s %s is not a node" % (e["id"], end, e[end]))
        if e["type"] not in EDGE_TYPES:
            errs.append("edge %s: bad type" % e["id"])
        if e["basis"] not in BASES or e["mechanism"] not in MECHANISMS or e["confidence"] not in CONFIDENCE:
            errs.append("edge %s: bad basis/mechanism/confidence" % e["id"])
        if e["resolution"].get("state") not in RESOLUTION_STATES:
            errs.append("edge %s: bad resolution state" % e["id"])
        # never invent: a relationship needs evidence or an explicit reason it has none
        if not e["evidence"] and e["mechanism"] != "cross_repo_resolution":
            errs.append("edge %s: no evidence" % e["id"])
        if e["mechanism"] == "cross_repo_resolution" and not (e["resolution"].get("reasoning") or e["attrs"].get("reasoning")):
            errs.append("edge %s: cross-repository edge without reasoning" % e["id"])
        if e["basis"] == "unresolved" and e["resolution"]["state"] == "resolved":
            errs.append("edge %s: basis unresolved but resolution resolved" % e["id"])
        if e["resolution"]["state"] == "ambiguous" and not e["resolution"].get("candidates"):
            errs.append("edge %s: ambiguous without candidates" % e["id"])
        for ev in e["evidence"]:
            if ev.get("kind") == "file" and ev.get("external"):
                src = (external or {}).get(ev.get("path"))
                path = src.get("path") if isinstance(src, dict) else src
                if not path or not os.path.isfile(path) or os.path.islink(path):
                    errs.append("edge %s: external evidence %s cannot be verified: no source supplied" % (e["id"], ev.get("path")))
                    continue
                if isinstance(src, dict) and src.get("sha256") and hashlib.sha256(open(path, "rb").read()).hexdigest() != src["sha256"]:
                    errs.append("edge %s: external source %s changed since the analysis" % (e["id"], ev.get("path")))
                    continue
                import evidence as _ev
                ls = open(path, encoding="utf-8", errors="replace").read().splitlines()
                n = ev.get("line_start", 0)
                if n < 1 or n > len(ls) or _ev.snip(ls[n - 1]) != ev.get("snippet"):
                    errs.append("edge %s: external evidence %s:%s: snippet mismatch" % (e["id"], ev.get("path"), n))
        if repos:
            import evidence
            for ev in e["evidence"]:
                if ev.get("kind") == "file" and ev.get("external"):
                    continue  # verified below, whether or not repositories were supplied
                if ev.get("kind") != "file":
                    continue  # command captures cannot be re-read
                root = repos.get(ev.get("app") or e.get("app") or "")
                if root is None and len(repos) == 1:
                    root = next(iter(repos.values()))
                bad = evidence.verify(root, ev) if root else "no repository for evidence"
                if bad:
                    errs.append("edge %s: evidence %s:%s: %s" % (e["id"], ev.get("path"), ev.get("line_start"), bad))
    return errs
