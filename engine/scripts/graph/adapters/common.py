"""Shared, read-only helpers for adapters: comment masking, configuration properties, string-constant resolution."""
from __future__ import annotations

import hashlib
import os
import re
from typing import Dict, List, Optional, Tuple

import evidence
from detectors import integrations as I

PLACEHOLDER = re.compile(r"^\$\{([^}:]+)(?::([^}]*))?\}$")
LOG_LINE = re.compile(r"\b(?:log|logger|LOG|LOGGER|slf4j|println|printStackTrace|print|printf)\b|System\.(?:out|err)|\bKotlinLogging\b", re.I)


def ev(path: str, line: int, lines: List[str], app: str) -> dict:
    e = evidence.file_ev(path, line, lines[line - 1])
    e["app"] = app
    return e


def mask_comments(lines: List[str]) -> List[str]:
    """Same number of lines; text inside // and /* */ comments blanked (a `//` inside a string such as "http://x" is kept)."""
    out, in_block = [], False
    for ln in lines:
        res, i, in_str = [], 0, None
        while i < len(ln):
            two = ln[i:i + 2]
            if in_block:
                if two == "*/":
                    in_block = False
                    i += 2
                else:
                    i += 1
                continue
            c = ln[i]
            if in_str:
                res.append(c)
                if c == "\\" and i + 1 < len(ln):
                    res.append(ln[i + 1])
                    i += 2
                    continue
                if c == in_str:
                    in_str = None
                i += 1
                continue
            if c in "\"'":
                in_str = c
                res.append(c)
            elif two == "//":
                break
            elif two == "/*":
                in_block = True
                i += 2
                continue
            else:
                res.append(c)
            i += 1
        out.append("".join(res))
    return out


def annotation_text(masked: List[str], i: int, span: int = 6) -> str:
    """Text of the annotation starting on line i (0-based): joined until its parentheses balance (max `span` lines)."""
    buf, depth, started = "", 0, False
    for j in range(i, min(i + span, len(masked))):
        for ch in masked[j]:
            buf += ch
            if ch == "(":
                depth += 1
                started = True
            elif ch == ")":
                depth -= 1
                if started and depth == 0:
                    return buf
        buf += " "
        if not started and j > i:
            break
    return buf


def string_literals(text: str) -> List[str]:
    return re.findall(r'"((?:[^"\\]|\\.)*)"', text)


SECRET_NAME = re.compile(r"(?i)pass(?:word|wd)?|secret|token|api[_-]?key|private|credential|signing|cert")
NOT_SECRET_SUFFIX = re.compile(r"(?i)_(?:URL|URI|HOST|HOSTNAME|ENDPOINT|PORT)$")


def _config_dir_files(d, app, profile):
    """Regular, non-symlink, size-capped property/YAML files directly inside the config directory (evidence-rules 7: symlinks are never read).
    The directory itself must not be a symlink and every file must resolve inside it."""
    if os.path.islink(d) or not os.path.isdir(d):
        return []
    real = os.path.realpath(d)
    out = []
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name)
        if os.path.islink(p) or not os.path.isfile(p) or not re.search(r"\.(?:properties|ya?ml)$", name):
            continue
        if not (name.startswith(("application", "bootstrap")) or name.startswith(app)):
            continue
        m = re.match(r"(?:application|bootstrap|%s)-([\w.-]+)\.(?:properties|ya?ml)$" % re.escape(app), name)
        if m and profile and m.group(1) != profile:
            continue
        if os.path.getsize(p) > evidence.MAX_BYTES or os.path.dirname(os.path.realpath(p)) != real:
            continue
        out.append((name, p))
    return out


_PROFILE_FILE = re.compile(r"(?:^|/)(?:application|bootstrap)-([\w.-]+)\.(?:properties|ya?ml)$")
_APP_FILE = re.compile(r"(?:^|/)(?:application|bootstrap)(?:-([\w.-]+))?\.(?:properties|ya?ml)$")


def env_name(key: str) -> str:
    """Spring's relaxed binding: `ledger.audit-url` is supplied by the environment variable LEDGER_AUDITURL (and LEDGER_AUDIT_URL)."""
    return re.sub(r"[^A-Za-z0-9]", "_", key).upper()


class Config:
    """Application properties with Spring-style layering.

    Layers, lowest to highest precedence: base files, the selected profile's files, an external config directory (Spring Cloud Config style),
    environment values found in deployment files. With no profile selected, the values of ALL profiles are kept and a key whose values differ
    is reported as such (nothing is silently picked); with `profile` set the selected profile overrides the base and other profiles are ignored."""

    def __init__(self, ctx, app: str, profile: Optional[str] = None, config_dirs=(), use_env: bool = True):
        self.app, self.profile, self.ctx = app, profile, ctx
        self._props_prefix = None
        self._text: Dict[str, str] = {}
        self.values: Dict[str, List[Tuple[str, dict, str]]] = {}  # key -> [(value, evidence, layer)]
        self.env: Dict[str, Tuple[str, dict]] = {}
        files = sorted(f for f in ctx.files if re.search(r"(?:^|/)(?:application|bootstrap)[^/]*\.(?:properties|ya?ml)$", f)
                       and "/src/main/" in "/" + f and not ctx._aux(f) and not ctx._test_module(f))
        self.files = files
        for f in files:
            m = _PROFILE_FILE.search(f)
            layer = ("profile:" + m.group(1)) if m else "base"
            lines = evidence.read_lines(ctx.repo, f) or []
            kind = "yaml" if f.endswith((".yml", ".yaml")) else "props"
            for key, val, i in I.flatten(lines, kind):
                self.values.setdefault(key, []).append((val.strip(), ev(f, i, lines, app), layer))
        self.external: Dict[str, dict] = {}   # display name -> {"path", "sha256"}: what an external citation is verified against
        for d in config_dirs:  # files outside the repository: cited as such, hashed, and read only through regular files inside the directory
            for name, path_ in _config_dir_files(d, app, profile):
                lines = open(path_, encoding="utf-8", errors="replace").read().splitlines()
                display = "[config-dir] " + name
                self.external[display] = {"path": path_, "sha256": hashlib.sha256(open(path_, "rb").read()).hexdigest()}
                kind = "yaml" if name.endswith((".yml", ".yaml")) else "props"
                for key, val, i in I.flatten(lines, kind):
                    e = evidence.file_ev(display, i, lines[i - 1])
                    e.update(app=app, external=True)
                    self.values.setdefault(key, []).append((val.strip(), e, "external"))
        if use_env:
            for f in ctx.deploy_files + [x for x in ctx.files if os.path.basename(x).startswith(".env") and not ctx._aux(x)]:
                lines = evidence.read_lines(ctx.repo, f) or []
                for i, ln in enumerate(lines, 1):
                    m = re.match(r"^\s*-\s*name:\s*[\"']?([A-Z][A-Z0-9_]+)[\"']?\s*$", ln)  # k8s env entry: `- name: X` then `value: Y`
                    if m and SECRET_NAME.search(m.group(1)) and not NOT_SECRET_SUFFIX.search(m.group(1)):
                        continue  # a secret-named variable: its value is never read, so it can never be cited
                    if m and i < len(lines):
                        v = re.match(r"^\s*value:\s*[\"']?([^\"'#\s][^\"'#]*?)[\"']?\s*(?:#.*)?$", lines[i])
                        if v and "{{" not in v.group(1):
                            self.env.setdefault(m.group(1), (v.group(1).strip(), ev(f, i + 1, lines, app)))
                        continue
                    m = re.match(r"^\s*-?\s*([A-Z][A-Z0-9_]+)\s*[=:]\s*[\"']?([^\"'#\s][^\"'#]*?)[\"']?\s*(?:#.*)?$", ln)  # compose / .env `X=Y`
                    if m and "{{" not in m.group(2) and "${" not in m.group(2) and not (SECRET_NAME.search(m.group(1)) and not NOT_SECRET_SUFFIX.search(m.group(1))):
                        self.env.setdefault(m.group(1), (m.group(2).strip(), ev(f, i, lines, app)))

    def _pick(self, hits):
        """Apply layering to the hits of one key. Returns (value, evidence, reason)."""
        if self.profile:
            keep = [h for h in hits if h[2] in ("base", "profile:" + self.profile, "external")]
            order = {"base": 0, "profile:" + self.profile: 1, "external": 2}
            top = max(keep, key=lambda h: order[h[2]]) if keep else None
            return (top[0], top[1], None) if top else (None, None, None)
        ext = [h for h in hits if h[2] == "external"]
        use = ext or hits
        vals = {h[0] for h in use}
        if len(vals) > 1:
            return None, use[0][1], "property differs between profiles (%s): rerun with a profile selected" % ", ".join(sorted(vals)[:3])
        return use[0][0], use[0][1], None

    def get(self, key: str):
        """(value, evidence, reason). value None when unknown; reason says why (absent, differs between profiles)."""
        e = self.env.get(env_name(key)) or self.env.get(key)
        if e:
            return e[0], e[1], None  # in Spring the environment outranks property files
        hits = self.values.get(key) or self._relaxed(key)
        if not hits:
            return None, None, "property %s is not set in the application configuration" % key
        v, e2, why = self._pick(hits)
        if v is None and why is None:
            return None, None, "property %s is only set in other profiles" % key
        return v, e2, why

    # ---- values that reach the code through binding, not through a literal ----------------------------------------------------
    def _file_text(self, path):
        if path not in self._text:
            self._text[path] = "\n".join(mask_comments(evidence.read_lines(self.ctx.repo, path) or []))
        return self._text[path]

    def _prefixes(self):
        """ConfigurationProperties class name -> prefix, across the application's main sources."""
        if self._props_prefix is None:
            self._props_prefix = {}
            for f in self.ctx.src_main_java:
                t = self._file_text(f)
                if "ConfigurationProperties" not in t:
                    continue
                for m in re.finditer(r"@ConfigurationProperties\s*\(\s*(?:(?:prefix|value)\s*=\s*)?\"([^\"]+)\"[^)]*\)[\s\S]{0,200}?\b(?:class|data class)\s+(\w+)", t):
                    self._props_prefix[m.group(2)] = m.group(1)
        return self._props_prefix

    @staticmethod
    def _kebab(name):
        return re.sub(r"(?<=[a-z0-9])([A-Z])", r"-\1", name).lower()

    def bound_property(self, expr, path):
        """`kafkaConfig.publisher.topics.paymentEventTopic` -> value of `<prefix of KafkaConfig>.publisher.topics.payment-event-topic` (Spring's relaxed
        binding of a @ConfigurationProperties class). The prefix comes from the class the variable is declared with in the same file.
        Returns (value, evidence, how) or (None, None, reason)."""
        m = re.match(r"^(\w+)\.((?:\w+\.)*\w+)$", expr.strip())
        if not m:
            return None, None, "not a property path"
        var, rest = m.group(1), m.group(2).split(".")
        t = self._file_text(path)
        tm = re.search(r"\b%s\s*:\s*(\w+)" % re.escape(var), t) or re.search(r"\b(\w+)(?:<[^>]*>)?\s+%s\s*[;,)=]" % re.escape(var), t)
        cls = tm.group(1) if tm else None
        prefix = self._prefixes().get(cls) if cls else None
        if prefix is None:
            return None, None, "%s is not a @ConfigurationProperties class that could be found" % (cls or var)
        key = prefix + "." + ".".join(self._kebab(x) for x in rest)
        v, e, why = self.get(key)
        if v is None:
            return None, e, "bound property %s: %s" % (key, why or "no value")
        return v, e, "configuration properties"

    def value_injected(self, ident, path):
        """`@Value("${x.y}") private String ident` / Kotlin `@Value("\\${x.y}") val ident` in the same file -> resolved value."""
        t = self._file_text(path)
        m = re.search(r"@Value\(\s*\"\\?(\$\{[^\"]+\})\"\s*\)\s*(?:private\s+|protected\s+|final\s+|lateinit\s+|var\s+|val\s+)*(?:\w+(?:<[^>]*>)?\s+)?%s\b" % re.escape(ident), t)
        if not m:
            return None, None, None
        v, e, why = self.resolve(m.group(1).replace("\\$", "$"))
        return v, e, why

    def all_values(self, key: str):
        """Every (value, evidence) the key has once the selected profile is applied; conflicting values are all returned (nothing is collapsed)."""
        hits = self.values.get(key) or []
        if self.profile:
            hits = [h for h in hits if h[2] in ("base", "profile:" + self.profile, "external")]
        return [(h[0], h[1]) for h in hits]

    def _relaxed(self, key):
        want = re.sub(r"[-_]", "", key).lower()
        for k, hits in self.values.items():
            if re.sub(r"[-_]", "", k).lower() == want:
                return hits
        return None

    def resolve(self, text: str):
        """Resolve a `${key}` / `${key:default}` placeholder. Returns (value, evidence, reason); a literal returns itself."""
        m = PLACEHOLDER.match(text.strip())
        if not m:
            return text, None, None
        val, e, why = self.get(m.group(1))
        if val is None and m.group(2) is not None:
            return m.group(2), None, None  # Spring uses the default when the property is absent
        if val is not None and PLACEHOLDER.match(val):
            return self.resolve(val)
        return val, e, why


def constants(ctx) -> Dict[str, List[Tuple[str, str, int]]]:
    """name -> [(value, path, line)] for `static final String NAME = "x"` / `const val NAME = "x"` / `val NAME: String = "x"` in main sources."""
    rx = re.compile(r'(?:static\s+final\s+String|const\s+val|(?:private\s+|public\s+|internal\s+)?val)\s+(\w+)\s*(?::\s*String)?\s*=\s*"([^"$]*)"')
    out: Dict[str, List[Tuple[str, str, int]]] = {}
    for f in ctx.src_main_java:
        lines = evidence.read_lines(ctx.repo, f) or []
        for i, ln in enumerate(mask_comments(lines), 1):
            for m in rx.finditer(ln):
                out.setdefault(m.group(1), []).append((m.group(2), f, i))
    return out


def resolve_arg(arg: str, cfg: Config, consts, path: str):
    """Resolve the first argument of a call/annotation to (value, evidence_extra, how, reason).
    how: literal | placeholder | constant. value None means it could not be resolved (reason says why)."""
    arg = arg.strip()
    m = re.match(r'^"((?:[^"\\]|\\.)*)"$', arg)
    if m:
        val = m.group(1).replace("\\$", "$")  # Kotlin writes a literal ${property} as "\${property}"
        if PLACEHOLDER.match(val):
            v, e, why = cfg.resolve(val)
            return (v, e, "placeholder", None) if v is not None else (None, e, "placeholder", why)
        if "${" in val:
            return None, None, "literal", "string is built from a placeholder expression"
        return val, None, "literal", None
    if re.match(r"^\w+\.\w+(?:\.\w+)*$", arg) and not re.match(r"^(?:[A-Z]\w*)\.", arg):  # kafkaConfig.publisher.topic: a bound @ConfigurationProperties value
        v, e, how = cfg.bound_property(arg, path)
        if v is not None:
            return v, e, "bound property", None
        if not how.startswith("not a property") and "is not a @ConfigurationProperties" not in how:
            return None, e, "bound property", how
    m0 = re.match(r"^\w+$", arg)
    if m0:  # an identifier injected with @Value
        v, e, why = cfg.value_injected(arg, path)
        if v is not None:
            return v, e, "placeholder", None
        if why:
            return None, e, "placeholder", why
    m = re.match(r"^(?:\w+\.)*([A-Z][A-Z0-9_]*|\w+)$", arg)
    if m:
        hits = consts.get(m.group(1)) or []
        same = [h for h in hits if h[1] == path] or hits
        vals = {h[0] for h in same}
        if len(vals) == 1:
            h = same[0]
            return h[0], None, "constant", None
        if len(vals) > 1:
            return None, None, "constant", "constant %s has several values in the code base: %s" % (m.group(1), ", ".join(sorted(vals)[:4]))
        return None, None, "constant", "%s is not a string constant that could be found" % m.group(1)
    return None, None, "expression", "argument is a computed expression, not a literal or constant"
