"""The sanitising check for fixtures written from disputes (design 8.4, T-2.3b): before a fixture leaves the client workspace it
must not hold any of the workspace's application names, package prefixes or hostnames (R-08, R-09). The check reports which
kind of name matched and where, by line, so the engineer can rename it."""
from __future__ import annotations

import json
import os
import re
from urllib.parse import urlparse

from . import engine_path  # noqa: F401

import evidence  # engine

PACKAGE = re.compile(r"^\s*package\s+([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+)\s*;?", re.M)
URL_HOST = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://(?:[^/\s:@\"'<>]+(?::[^/\s@\"'<>]*)?@)?([a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+)")
SCP_HOST = re.compile(r"^[\w.-]+@([\w.-]+):")
# names every fixture may use: loopback, reserved example domains (RFC 2606) and the generic sample package
NEUTRAL_HOSTS = re.compile(r"(?i)^(localhost|127\.0\.0\.1|0\.0\.0\.0|(?:[\w-]+\.)*(?:example|invalid|test|localhost)(?:\.(?:com|org|net))?)$")
NEUTRAL_PACKAGES = {"com.example", "org.example", "net.example", "com.mycompany", "com.acme.example"}
MIN_NAME = 4  # an application called "api" would make every fixture fail; names this short identify nothing


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def names(ws):
    """The workspace's identifying names, from every run: application names, the package prefixes declared in the analysed
    repositories' sources (first three segments, or two when that is all there is), and hostnames from source URLs and the
    relationship graph. Reading only."""
    apps, pkgs, hosts = set(), set(), set()
    runs = os.path.join(ws, "runs")
    for run in sorted(os.listdir(runs)) if os.path.isdir(runs) else []:
        rd = os.path.join(runs, run)
        man = os.path.join(rd, "analysis", "manifest.json")
        if not os.path.isfile(man):
            continue
        m = _read(man)
        rj = _read(os.path.join(rd, "run.json")) if os.path.isfile(os.path.join(rd, "run.json")) else {}
        for s in rj.get("sources") or []:
            if s.get("name"):
                apps.add(s["name"])
            spec = s.get("spec") or ""
            h = urlparse(spec).hostname if "://" in spec else (SCP_HOST.match(spec).group(1) if SCP_HOST.match(spec) else None)
            if h:
                hosts.add(h.lower())
        for x in m["applications"]:
            apps.add(x["app"])
            repo = x.get("repo")
            if repo and os.path.isdir(repo):
                for f in evidence.walk(repo):
                    if f.endswith((".java", ".kt", ".groovy", ".scala")):
                        for p in PACKAGE.findall("\n".join((evidence.read_lines(repo, f) or [])[:60])):
                            seg = p.split(".")
                            pkgs.add(".".join(seg[:3]))
        rel = os.path.join(rd, "analysis", "portfolio", "relationships.json")
        if os.path.isfile(rel):
            hosts |= {h.lower() for h in URL_HOST.findall(open(rel, encoding="utf-8").read())}
            for n in _read(rel).get("nodes") or []:
                a = n.get("attrs") or {}
                for h in (a.get("host"), (a.get("connection") or {}).get("host")):
                    if isinstance(h, str) and "." in h:
                        hosts.add(h.lower())
    return {"applications": sorted(a for a in apps if len(a) >= MIN_NAME), "packages": sorted(p for p in pkgs if p not in NEUTRAL_PACKAGES and "." in p),
            "hostnames": sorted(h for h in hosts if not NEUTRAL_HOSTS.match(h))}


def check(text, found):
    """[(kind, line number)] for every identifying name in the text, matched whole (not inside a longer word)."""
    hits = []
    for kind, vals in (("application name", found["applications"]), ("package prefix", found["packages"]), ("hostname", found["hostnames"])):
        for v in vals:
            # a package prefix may continue (com.acme.payments.api); a hostname may not (a.example.net is not a.example.net.other)
            rx = re.compile(r"(?<![\w.-])%s(?![\w-]%s)" % (re.escape(v), "|\\.[\\w-]" if kind == "hostname" else ""), re.I)
            for n, ln in enumerate(text.splitlines(), 1):
                if rx.search(ln):
                    hits.append((kind, n))
    return sorted(set(hits), key=lambda x: (x[1], x[0]))


def check_file(path, ws):
    """True when the fixture is clean. Paths of a directory are checked file by file."""
    found = names(ws)
    files = [os.path.join(r, f) for r, _, fs in os.walk(path) for f in sorted(fs)] if os.path.isdir(path) else [path]
    hits = []
    for p in sorted(files):
        try:
            text = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        hits += [(p, k, n) for k, n in check(text, found)]
    return hits, found
