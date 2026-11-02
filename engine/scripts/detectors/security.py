from __future__ import annotations

import json
import os
import re

from evidence import fact, file_ev, grep_files, read_lines, run, walk

# category -> regex over CI files, build files and tool config. Tool names follow registry/dod.yaml.
CATEGORIES = {
    "secret_scanning": r"gitguardian|ggshield|gitleaks|trufflehog|Security/Secret-Detection",
    "dependency_scanning": r"\bsnyk\b(?![-_ ]code)|dependency-?check|Security/Dependency-Scanning|\bosv-scanner\b|\btrivy\b|dependency-review-action|\bfossa",
    "cloud_scanning": r"\bwiz(cli|-cli)?\b|prisma.?cloud|\bcheckov\b",
    # codeql-action/upload-sarif only uploads someone else's report (OpenSSF Scorecard, CIFuzz); it is not an analysis
    "sast": r"sonar|semgrep|codeql(?!-action/upload-sarif)|Security/SAST|spotbugs|find-?sec-?bugs|snyk[-_ ]code",
}
PATH_ONLY = re.compile(r"cache|~/|/reports/|destination|store_artifacts|\.html\b", re.I)
CONFIG_FILES = (".github/dependabot.yml", "renovate.json", ".snyk", ".gitguardian.yml",
                ".gitleaks.toml", "sonar-project.properties")


VERSION = "0.4.0"

UPDATE_FILES = (".github/dependabot.yml", ".github/dependabot.yaml", "renovate.json", "renovate.json5", ".renovaterc",
                ".renovaterc.json", ".github/renovate.json", ".github/renovate.json5")

SEVERITIES = ("critical", "high", "medium", "low")
# basename pattern -> (tool label, extractor of severity strings from the parsed JSON)
REPORTS = (
    (re.compile(r"^dependency-check-report\.json$"), "OWASP Dependency-Check",
     lambda d: [v.get("severity") for x in d.get("dependencies", []) for v in x.get("vulnerabilities", [])]),
    (re.compile(r"^gl-(dependency|container)-scanning-report\.json$"), "GitLab scanning",
     lambda d: [v.get("severity") for v in d.get("vulnerabilities", [])]),
    (re.compile(r"^snyk[\w.-]*\.json$"), "Snyk",
     lambda d: [v.get("severity") for v in (d.get("vulnerabilities") or [])]),
    (re.compile(r"^trivy[\w.-]*\.json$"), "Trivy",
     lambda d: [v.get("Severity") for r in (d.get("Results") or []) for v in (r.get("Vulnerabilities") or [])]),
)


def _reports(ctx) -> dict:
    """Vulnerability scanner reports already on disk. Parsed, never produced: this scan runs no scanner."""
    r, found = ctx.repo, []
    head = run(["git", "log", "-1", "--format=%ct"], r)
    for rel in walk(r, include_build=True):
        for rx, tool, pick in REPORTS:
            if not rx.match(os.path.basename(rel)):
                continue
            lines = read_lines(r, rel)
            try:
                doc = json.loads("\n".join(lines or []))
                sev = [str(x or "").lower().replace("moderate", "medium") for x in pick(doc)]
            except (ValueError, AttributeError, TypeError):
                continue
            counts = {k: sev.count(k) for k in SEVERITIES}
            stale = bool(head[0] == 0 and head[1].isdigit() and os.path.getmtime(os.path.join(r, rel)) < int(head[1]))
            found.append((rel, lines, dict(counts, total=len(sev), tool=tool, path=rel, stale=stale)))
    if not found:
        return fact([], "NOT_FOUND", [], "no scanner report on disk; this scan does not run a vulnerability scanner")
    stale = any(x[2]["stale"] for x in found)
    return fact([x[2] for x in found], "INFERRED" if stale else "CONFIRMED",
                [file_ev(x[0], 1, (x[1] or [""])[0]) for x in found][:3],
                ("STALE: a report is older than the HEAD commit. " if stale else "")
                + "parsed from a report already on disk; not produced by this scan")


PIPELINE_CATS = ('secret_scanning', 'dependency_scanning', 'sast')

# --- literal secrets committed to the repository -------------------------------------------------------------------
# A secret is a literal value, never a reference: ${VAR}, $VAR, <placeholder>, an ALL_CAPS environment name or an empty value is not one.
# The setting's name must end in the secret word: sharedSecret is one, sharedSecretsVersion is not.
SECRET_NAME = r"(?:pass(?:word|wd|phrase)?|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret)(?:[_-]?key)?"
CONFIG_SECRET = re.compile(r"(?i)^\s*(?:-\s+)?[\"']?[\w.\-\[\]]*?" + SECRET_NAME + r"[\"']?\s*[:=]\s*[\"']?(?![\$\{<*\[%])([^\s\"'#,;]{4,})")
DEFAULT_SECRET = re.compile(r"(?i)^\s*[\"']?[\w.\-\[\]]*?" + SECRET_NAME + r"[\"']?\s*[:=]\s*[\"']?\$\{[\w.\-]+:([^}\s]{8,})\}")  # a committed default
CODE_SECRET = re.compile(r"(?i)\b\w*?" + SECRET_NAME + r"(?!\w)\s*(?:=|:|\(|\s)\s*([\"'])(?![\$\{<])([^\"'\s]{4,})\1")
URL_SECRET = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@$]+:(?![\$\{<])([^/\s@]{3,})@")
WEBHOOK_SECRET = re.compile(r"(?i)(?:hooks\.slack\.com/(?:services|workflows|triggers)/|discord(?:app)?\.com/api/webhooks/|webhook\.office\.com/webhookb2/)([A-Za-z0-9/_\-]{12,})")
QUERY_SECRET = re.compile(r"(?i)[?&](?:access_token|token|api_?key|apikey|sig|signature|secret|password)=([^&\s\"'<>${]{6,})")
PROP_SECRET = re.compile(r"(?i)\bproperty\s*\(?\s*[\"'][^\"']*(?:pass(?:word|wd)|secret|token)[^\"']*[\"']\s*,\s*[\"']([^\"'$]{4,})[\"']")
LONG_SECRET = re.compile(r"(?i)^\s*[\w.\-]*(?:key|secret|token|salt)[\w.\-]*\s*[:=]\s*[\"']?([A-Fa-f0-9]{32,}|[A-Za-z0-9+/_\-]{40,}={0,2})[\"']?\s*$")
IN_MEMORY_DB = re.compile(r"(?i)jdbc:(?:h2|hsqldb|derby):mem|jdbc:h2:mem")
TOKEN_SECRET = re.compile(r"\b((?:ghp_|gho_|glpat-|AKIA|xox[abp]-|sk-)[A-Za-z0-9_\-]{12,})")
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----")
# placeholders, not values; a literal "password" is a (weak) secret for a real database, so it is judged in context instead
NOT_A_SECRET = re.compile(r"(?i)^(?:true|false|null|none|example|placeholder|xxx+|\*+|required|optional)$")
BASIC_SECRET = re.compile(r"BasicAuth\w*\s*\(\s*[\"'][^\"']*[\"']\s*,\s*[\"']([^\"']{4,})[\"']")
KEY_PATH = re.compile(r"[/\\~]|\.(?:pem|key|p12|jks|crt|pub)$")  # --private-key=path/to/key names a file, it is not the key
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")  # case-sensitive on purpose: DB_PASSWORD names a variable, hzpw is a value
GENERATED = re.compile(r"(^|/)(?:bin|build|target|out|dist|\.gradle)/|(^|/)(?:package(?:-lock)?\.json|yarn\.lock|composer\.lock|npm-shrinkwrap\.json)$")
CONFIG_EXT = re.compile(r"\.(?:ya?ml|properties|env|conf|cfg|ini|toml|json|j2|xml)$|(^|/)\.env(\.\w+)?$|(^|/)(?:group|host)_vars/[^/]+(?:/[^/]+)?$")


def _secret_files(ctx):
    test = re.compile(r"(^|/)src/(?:test|it|integration-test|integrationTest)/|(^|/)(?:tests?|fixtures?|testdata)/")
    files = [f for f in ctx.files if not ctx._aux(f) and not test.search(f) and "/node_modules/" not in f and not f.startswith(".git/") and not GENERATED.search(f)]
    config = [f for f in files if CONFIG_EXT.search(f) and f not in ctx.ci_files and f not in ctx.build_files and not f.endswith("gradle.properties")]
    code = [f for f in files if f in ctx.ci_files or f in ctx.build_files or f.endswith(("gradle.properties",))
            or re.search(r"\.(?:java|kt|groovy|scala|sh|py|js|ts|go|rb)$", f)]
    return config, code, files


def _scan_secrets(ctx, files, rx_list, cap=200):
    hits = []
    for f in files[:4000]:
        lines = read_lines(ctx.repo, f) or []
        mem = bool(IN_MEMORY_DB.search("\n".join(lines[:400])))  # sa / password for an in-memory test database is not a credential
        for i, ln in enumerate(lines[:cap * 20], 1):
            t = ln.strip()
            if not t or t.startswith(("#", "//", "*", "<!--")):
                continue
            for rx in rx_list:
                m = rx.search(ln)
                val = ((m.groups() or ("",))[-1] or "") if m else ""
                if m and mem and val.lower() in ("password", "sa", "secret", "") :
                    continue
                if m and not NOT_A_SECRET.match(val) and not ENV_NAME.match(val) and not (KEY_PATH.search(val) and rx is not WEBHOOK_SECRET):
                    hits.append(file_ev(f, i, ln))
                    break
    return hits


def secrets(ctx):
    """Two verdicts: literal secrets in configuration files, and in code, build, pipeline or key files. Evidence lines are redacted."""
    config, code, files = _secret_files(ctx)
    in_cfg = _scan_secrets(ctx, config, [WEBHOOK_SECRET, QUERY_SECRET, DEFAULT_SECRET, LONG_SECRET, CONFIG_SECRET, URL_SECRET, TOKEN_SECRET])
    build = [f for f in code if f in ctx.build_files or f.endswith("gradle.properties")]
    # source code needs a quoted literal (password = "x"); build files also use key = value and Groovy's password "x"
    in_code = _scan_secrets(ctx, [f for f in code if f not in build], [WEBHOOK_SECRET, QUERY_SECRET, CODE_SECRET, BASIC_SECRET, URL_SECRET, TOKEN_SECRET]) + \
        _scan_secrets(ctx, build, [PROP_SECRET, WEBHOOK_SECRET, CODE_SECRET, DEFAULT_SECRET, CONFIG_SECRET, URL_SECRET, TOKEN_SECRET])
    keys = [file_ev(f, i, ln) for f in files for ls in [read_lines(ctx.repo, f) or []] for i, ln in enumerate(ls[:3], 1) if PRIVATE_KEY.search(ln)]

    def verdict(hits, where, n):
        if hits:
            files_hit = sorted({e["path"] for e in hits})
            return fact({"state": "ISSUE", "level": "configured", "summary": "%d literal secret%s committed in %s (%s): rotate them and move them to a secret store" % (
                len(hits), "" if len(hits) == 1 else "s", where, ", ".join(files_hit[:4]) + (" and %d more" % (len(files_hit) - 4) if len(files_hit) > 4 else ""))},
                "CONFIRMED", hits[:6])
        # a bounded search that found nothing: the observation is the search itself, so the status is NOT_FOUND with nothing to cite
        return fact({"state": "PRESENT", "level": "declared", "summary": "No literal secret found in the %d %s scanned (values held in ${...} references are not secrets)" % (n, where)},
                    "NOT_FOUND", [])
    return {"secrets_in_config": verdict(in_cfg, "configuration files", len(config)),
            "secrets_committed": verdict(keys + in_code, "code, build, pipeline and key files", len(code))}
# Gradle plugins that attach their tasks to `check`, so a pipeline running `gradle build` or `gradle check` runs them too
CHECK_WIRED = r"apply\s+plugin\s*:\s*['\"](?:findbugs|com\.github\.spotbugs)['\"]|id\s*\(?\s*['\"](?:com\.github\.spotbugs)['\"]"
CI_GRADLE_CHECK = r"gradlew?\b[^\n]*\s(?:build|check)\b"


def _lifecycle_run(ctx, ev):
    """CI evidence that the build lifecycle runs a check-wired security analyser, or []: `gradle build` runs `check`, which runs
    SpotBugs / FindBugs (and the find-sec-bugs rules plugged into them) unless the command excludes it."""
    if not any(re.search(r"find-?sec-?bugs|spotbugs", e["snippet"], re.I) for e in ev):
        return []
    wired = grep_files(ctx.repo, ctx.build_files, CHECK_WIRED, 1)
    runs = [e for e in grep_files(ctx.repo, ctx.ci_files, CI_GRADLE_CHECK, 3) if not re.search(r"-x\s+(?:check|findbugs\w*|spotbugs\w*)", e["snippet"])]
    return (runs[:1] + wired[:1]) if wired and runs else []


def detect(ctx) -> dict:
    r = ctx.repo
    cfg = sorted(set(ctx.ci_files + ctx.build_files + [f for f in ctx.files if f in CONFIG_FILES]))
    unres = ctx.unresolved_ci_includes()
    out = {}
    for cat, rx in CATEGORIES.items():
        # a tool name inside a cache dir / report path is not the tool being run
        hits = [e for f in cfg for e in grep_files(r, [f], rx, 10) if not PATH_ONLY.search(e["snippet"])]
        seen, ev = set(), []
        for e in hits:  # one hit per file
            if e["path"] not in seen:
                seen.add(e["path"])
                ev.append(e)
        ev = ev[:3]
        if not ev:  # tool config files are evidence by name alone
            ev = [file_ev(f, 1, (read_lines(r, f) or [""])[0]) for f in cfg if re.search(rx, f)][:3]
        if cat in PIPELINE_CATS:
            # configured is not the same as run: only a hit inside a CI file shows the pipeline invokes the tool
            ci_hits = [e for e in hits if e["path"] in set(ctx.ci_files)][:3]
            life = _lifecycle_run(ctx, hits) if cat == "sast" and not ci_hits else []
            out[cat + "_in_pipeline"] = fact(True, "CONFIRMED", ci_hits) if ci_hits else \
                fact(True, "INFERRED", life, "the pipeline runs the build lifecycle (%s), which runs the analyser wired into `check`" % life[0]["snippet"].strip()[:60]) if life else \
                fact(False, "UNKNOWN" if unres else "NOT_FOUND", unres[:2] if unres else [],
                     "the tool may live in an included remote template" if unres else
                     "no CI file invokes it" + ("; it is configured in build or tool files only" if ev else ""))
        if ev:
            out[cat] = fact(True, "CONFIRMED", ev)
        elif unres:
            out[cat] = fact(False, "UNKNOWN", unres[:2], "tool may live in an included remote template")
        else:
            out[cat] = fact(False, "NOT_FOUND", [])
    upd = [f for f in UPDATE_FILES if f in ctx.fileset]
    out["dependency_updates"] = fact(True, "CONFIRMED", [file_ev(f, 1, (read_lines(r, f) or [""])[0]) for f in upd[:3]]) if upd \
        else fact(False, "NOT_FOUND", [], "no Dependabot or Renovate config file; it may still be enabled in the hosting platform")
    out["vulnerability_reports"] = _reports(ctx)
    out.update(secrets(ctx))
    return out
