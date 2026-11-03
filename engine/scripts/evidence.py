"""Evidence model for app-discovery.

Every fact the detectors emit is {value, status, evidence[]}. Evidence is either a file citation
(path + line + the exact line text) or a command capture. `verify()` re-reads cited lines so a
claim whose evidence no longer matches the repo is rejected. No model is involved anywhere here.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from typing import Dict, Iterable, List, Optional

STATUSES = ("CONFIRMED", "INFERRED", "NOT_FOUND", "UNKNOWN")
SKIP_DIRS = {".git", "node_modules", ".idea", ".gradle", ".venv", "__pycache__", ".modernise"}
BUILD_DIRS = {"target", "build", "out"}
MAX_BYTES = 2_000_000
SNIPPET_MAX = 200
COMMENT_PREFIXES = ("#", "//", "*", "/*")


# Keywords may sit inside identifiers (DB_PASSWORD, -Ppassword), so no leading \b. Plain-prose words are not
# keys: a bare "pass"/"token" followed by a word is left alone; only key=value / key: value pairs are masked.
_SECRET_KV = re.compile(
    r"(?i)(pass(?:word|wd)|secret|token|api[_-]?key|access[_-]?key|private[_-]?key)([\w-]*\s*[:=]\s*)"
    r"(?![\$\{<*\[])[\"']?[^\s\"',;]{4,}")
_SECRET_AUTH = re.compile(
    r"(?i)\b(authorization|bearer)(\s*[:=]\s*|\s+)(?:bearer\s+|basic\s+)?(?![\$\{<*\[])[^\s\"',;]{6,}")
# Groovy / Gradle call style: password "example1", token 'abc123'
_SECRET_CALL = re.compile(r"(?i)\b(pass(?:word|wd)|secret|token|api[_-]?key|access[_-]?key)(\s+)([\"'])(?![\$\{<])[^\"'\s]{4,}\3")
# credentials passed positionally to a basic-auth constructor: BasicAuthRequestInterceptor("user", "pass")
_SECRET_BASIC = re.compile(r"(BasicAuth\w*\s*\(\s*[\"'][^\"']*[\"']\s*,\s*[\"'])[^\"']+([\"'])")
# a default committed inside a reference: ${JWT_SECRET:the-default}
_SECRET_DEFAULT = re.compile(r"(?i)((?:pass(?:word|wd)|secret|token|api[_-]?key)[\w-]*\s*[:=]\s*[\"']?\$\{[\w.\-]+:)[^}]+")
# webhook URLs carry their credential in the path; query parameters named like a credential carry it in the value
_SECRET_HOOK = re.compile(r"(?i)((?:hooks\.slack\.com/(?:services|workflows|triggers)/|discord(?:app)?\.com/api/webhooks/|webhook\.office\.com/webhookb2/|"
                          r"outlook\.office(?:365)?\.com/webhook/|chat\.googleapis\.com/v1/spaces/))[^\s\"'<>)\\]+")
_SECRET_QUERY = re.compile(r"(?i)([?&](?:access_token|token|api_?key|apikey|key|sig|signature|secret|password|pwd|auth)=)[^&\s\"'<>]+")
# property "sonar.jdbc.password", "the-value"
_SECRET_PROP = re.compile(r"(?i)(\bproperty\s*\(?\s*[\"'][^\"']*(?:pass(?:word|wd)|secret|token|key)[^\"']*[\"']\s*,\s*[\"'])[^\"']+([\"'])")
# long hex or base64 values held under a key, secret or token name: key.current=04e...
_SECRET_LONG = re.compile(r"(?i)((?:key|secret|token|sig|salt)[\w.\-]*\s*[:=]\s*[\"']?)(?:[A-Fa-f0-9]{32,}|[A-Za-z0-9+/_\-]{40,}={0,2})")
_SECRET_TOK = re.compile(r"\b(ghp_|gho_|glpat-|AKIA|xox[abp]-|sk-)[A-Za-z0-9_\-]{8,}")
# credentials embedded in a connection URL: postgres://user:pw@host, redis://:pw@host, amqp://guest:guest@host
_SECRET_URL = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)(?![\$\{<])[^/\s:@]*:(?![\$\{<])[^/\s@]+@")


def redact(text: str) -> str:
    """Mask secret-looking literals. $VAR / ${VAR} / <placeholder> references are kept: they are not secrets."""
    text = _SECRET_KV.sub(lambda m: m.group(1) + m.group(2) + "[REDACTED]", text)
    text = _SECRET_HOOK.sub(lambda m: m.group(1) + "[REDACTED]", text)
    text = _SECRET_QUERY.sub(lambda m: m.group(1) + "[REDACTED]", text)
    text = _SECRET_PROP.sub(lambda m: m.group(1) + "[REDACTED]" + m.group(2), text)
    text = _SECRET_LONG.sub(lambda m: m.group(1) + "[REDACTED]", text)
    text = _SECRET_BASIC.sub(lambda m: m.group(1) + "[REDACTED]" + m.group(2), text)
    text = _SECRET_DEFAULT.sub(lambda m: m.group(1) + "[REDACTED]", text)
    text = _SECRET_CALL.sub(lambda m: m.group(1) + m.group(2) + m.group(3) + "[REDACTED]" + m.group(3), text)
    text = _SECRET_AUTH.sub(lambda m: m.group(1) + m.group(2) + "[REDACTED]", text)
    text = _SECRET_URL.sub(lambda m: m.group(1) + "[REDACTED]@", text)
    return _SECRET_TOK.sub(lambda m: m.group(1) + "[REDACTED]", text)


def redact_tree(obj):
    """Every string in a document, keys included, passed through redact(): nothing the engine writes can carry a secret,
    whether it came from an evidence line, a relationship target, a URL attribute or a summary."""
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, list):
        return [redact_tree(x) for x in obj]
    if isinstance(obj, dict):
        return {(redact(k) if isinstance(k, str) else k): redact_tree(v) for k, v in obj.items()}
    return obj


def snip(text: str) -> str:
    """Canonical stored form of a source line; verify() applies the same function to the live line."""
    return redact(text.strip())[:SNIPPET_MAX]


def fact(value, status: str, evidence: Optional[List[dict]] = None, note: Optional[str] = None,
         derivation: Optional[dict] = None) -> dict:
    """derivation = {"rule": str, "inputs": [fact ids]} for a fact that is computed from other facts and cites nothing itself."""
    if status not in STATUSES:
        raise ValueError("bad status %r" % status)
    out = {"value": value, "status": status, "evidence": evidence or []}
    if derivation:
        out["derivation"] = {"rule": derivation["rule"], "inputs": sorted(derivation["inputs"])}
    if note:
        out["note"] = note
    return out


def file_ev(path: str, line: int, text: str) -> dict:
    return {"kind": "file", "path": path, "line_start": line, "line_end": line,
            "snippet": snip(text)}


def cmd_ev(cmd: List[str], output: str) -> dict:
    return {"kind": "cmd", "cmd": " ".join(cmd), "snippet": snip(output)}


def run(cmd: List[str], cwd: str, timeout: int = 10):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return 127, ""


def ide_output(path: str) -> bool:
    """An IDE's compiler output folder (Eclipse/Buildship `bin/`): it mirrors the source sets (bin/main, bin/test) or holds
    .class files. Its copies of configuration files are stale, never the application's. A `bin/` of scripts is not one."""
    try:
        names = os.listdir(path)
    except OSError:
        return False
    if any(n in ("main", "test") and os.path.isdir(os.path.join(path, n)) for n in names):
        return True
    seen = 0
    for _, _, fs in os.walk(path):
        if any(f.endswith(".class") for f in fs):
            return True
        seen += len(fs)
        if seen > 500:
            break
    return False


# what a file is, from its path alone: evidence for a control is about the application, never a fixture, example or output
ROLE_RULES = [
    ("build_output", re.compile(r"(^|/)(?:target|build|out)/")),
    ("test_fixture", re.compile(r"(^|/)(?:fixtures?|__fixtures__|testdata|test-data|mocks?|stubs?)/|(^|/)src/test/resources/", re.I)),
    ("example", re.compile(r"(^|/)(?:[\w.-]*[-_])?(?:docs?|documentation|samples?|examples?|snippets?|demos?|archetype-resources)(?:[-_][\w.-]*)?/", re.I)),
    ("test", re.compile(r"(^|/)src/(?:test|it|integrationTest|integration-test|intTest|testFixtures)/")),
]


def role(rel: str) -> str:
    """Only folders above src/ count for the fixture and example rules: a Java package named `example` (com/example/...) is code."""
    head = ("/" + rel).split("/src/")[0] + "/" if "/src/" in "/" + rel else rel
    for name, rx in ROLE_RULES:
        if rx.search(rel if name == "test" or (name == "test_fixture" and "src/test/resources/" in rel) else head):
            return name
    return "application"


def walk(repo: str, include_build: bool = False) -> List[str]:
    """Sorted repo-relative posix paths. Deterministic: dirs and files sorted at every level. IDE output folders are never
    read: they hold stale copies of the configuration."""
    skip = set(SKIP_DIRS) | (set() if include_build else BUILD_DIRS)
    out = []
    for root, dirs, names in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if d not in skip and not os.path.islink(os.path.join(root, d))
                         and not (d == "bin" and ide_output(os.path.join(root, d))))
        for n in sorted(names):
            if os.path.islink(os.path.join(root, n)):
                continue  # a symlink can point outside the repo; never read through it
            out.append(os.path.relpath(os.path.join(root, n), repo).replace(os.sep, "/"))
    return out


def read_lines(repo: str, rel: str) -> Optional[List[str]]:
    p = os.path.join(repo, rel)
    try:
        if os.path.islink(p) or not os.path.realpath(p).startswith(os.path.realpath(repo) + os.sep):
            return None
        if os.path.getsize(p) > MAX_BYTES:
            return None
        with open(p, encoding="utf-8", errors="replace") as fh:
            return fh.read().splitlines()
    except OSError:
        return None


def _xml_live_mask(lines: List[str]) -> List[bool]:
    """True for lines that are not inside an XML comment (line-granular, conservative)."""
    mask, in_c = [], False
    for ln in lines:
        s = ln.strip()
        if in_c:
            mask.append(False)
            if "-->" in s:
                in_c = False
            continue
        if s.startswith("<!--"):
            mask.append(False)
            if "-->" not in s:
                in_c = True
            continue
        mask.append(True)
    return mask


def find_lines(repo: str, rel: str, pattern: str, limit: int = 5, flags: int = re.I,
               skip_comments: bool = True, continuation: bool = False) -> List[dict]:
    """Evidence for every live line in `rel` matching `pattern` (first `limit`)."""
    lines = read_lines(repo, rel)
    if lines is None:
        return []
    rx = re.compile(pattern, flags)
    live = _xml_live_mask(lines) if rel.endswith((".xml", ".pom")) else None
    out = []
    skip_to = 0
    for i, ln in enumerate(lines, 1):
        if i <= skip_to:
            continue
        if live is not None and not live[i - 1]:
            continue
        s = ln.strip()
        if skip_comments and s.startswith(COMMENT_PREFIXES) and not rel.endswith(".xml"):
            continue
        text = ln
        if continuation and ln.rstrip().endswith("\\"):
            # a shell command continued with a trailing backslash is one logical line; the evidence cites its first line
            j = i
            while j < len(lines) and lines[j - 1].rstrip().endswith("\\"):
                j += 1
            text = " ".join(x.rstrip().rstrip("\\") for x in lines[i - 1:j][:12])
            skip_to = j
        if rx.search(text):
            out.append(file_ev(rel, i, ln))
            if len(out) >= limit:
                break
    return out


def grep_files(repo: str, rels: Iterable[str], pattern: str, limit: int = 5, **kw) -> List[dict]:
    out: List[dict] = []
    for rel in rels:
        out.extend(find_lines(repo, rel, pattern, limit=limit - len(out), **kw))
        if len(out) >= limit:
            break
    return out


def verify(repo: str, ev: dict) -> Optional[str]:
    """Return None if the evidence still matches the repo, else a reason string."""
    if ev.get("kind") != "file":
        return None
    lines = read_lines(repo, ev["path"])
    if lines is None:
        return "unreadable: %s" % ev["path"]
    n = ev["line_start"]
    if n < 1 or n > len(lines):
        return "line out of range: %s:%d" % (ev["path"], n)
    if snip(lines[n - 1]) != ev["snippet"]:
        return "snippet mismatch at %s:%d" % (ev["path"], n)
    return None


def iter_facts(doc: dict):
    """Yield (fact_id, fact) for every fact-shaped dict in the section maps."""
    for sec in ("identity", "stack", "build_ci", "tests", "api", "resilience", "security", "runtime"):
        for k, f in sorted((doc.get(sec) or {}).items()):
            if isinstance(f, dict) and "status" in f and "evidence" in f:
                yield "%s.%s" % (sec, k), f


def inventory_fingerprint(repo: str, files: List[str]) -> str:
    """Hash of every scanned file's path and bytes: identifies the exact input a discovery describes."""
    h = hashlib.sha256()
    for rel in files:
        p = os.path.join(repo, rel)
        try:
            if os.path.getsize(p) > MAX_BYTES:
                body = "oversize:%d" % os.path.getsize(p)
            else:
                with open(p, "rb") as fh:
                    body = hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            body = "unreadable"
        h.update(("%s\0%s\n" % (rel, body)).encode())
    return h.hexdigest()


def safe_xml_root(repo: str, rel: str):
    """Parse an XML file already inside the repo; refuse entity declarations and DOCTYPE internal subsets."""
    import xml.etree.ElementTree as ET
    p = os.path.join(repo, rel)
    if os.path.islink(p):
        return None
    with open(p, "rb") as fh:
        data = fh.read(MAX_BYTES + 1)
    # Real JaCoCo reports start with <!DOCTYPE report PUBLIC ... "report.dtd">; that is harmless (no external fetch).
    # Entity declarations and DOCTYPE internal subsets ([ ... ]) are what enable expansion attacks.
    if len(data) > MAX_BYTES or b"<!ENTITY" in data.upper() or re.search(rb"<!DOCTYPE[^>]*\[", data, re.I):
        return None
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        return None


def canonical_hash(obj) -> str:
    import json
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
