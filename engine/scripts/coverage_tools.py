"""Coverage tools for JVM projects (Java and Kotlin): how each is configured, enforced, and how its report is read.

Adding a tool = one entry in TOOLS (build-file patterns) and, for report reading, one entry in REPORTS plus a parser.
Parsers only read files already on disk; nothing here runs a build. Every parser returns
(counts, size, line) where counts is {LINE|BRANCH|INSTRUCTION|METHOD|CLASS|COMPLEXITY: percent} and line is the
1-based line the totals were read from (so the evidence can cite it)."""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

from evidence import file_ev, grep_files, read_lines, safe_xml_root, walk

# id -> how it is configured. `rate_scale`: a threshold of <= 1 is a fraction (JaCoCo's 0.80), not a percent.
TOOLS = [
    {"id": "jacoco", "config": r"jacoco",
     "enforce": r"jacoco:check|<goal>check</goal>|jacocoTestCoverageVerification|violationRules|<haltOnFailure>\s*true",
     "threshold": [r"<minimum>\s*([\d.]+)", r"\bminimum\b\W.*?(\d+(?:\.\d+)?)"], "rate_scale": True},
    {"id": "kover", "config": r"org\.jetbrains\.kotlinx\.kover|kover-maven-plugin|\bkover\b",
     "enforce": r"\bminBound\s*\(|koverVerify|\bminValue\s*=",
     "threshold": [r"\bminBound\s*\(\s*(\d+(?:\.\d+)?)", r"\bminValue\s*=\s*(\d+(?:\.\d+)?)"], "rate_scale": False},
    {"id": "cobertura", "config": r"cobertura",
     "enforce": r"<check>|coverageThreshold|<totalLineRate>|<haltOnFailure>\s*true",
     "threshold": [r"<(?:totalLineRate|lineRate)>\s*(\d+(?:\.\d+)?)"], "rate_scale": False},
    {"id": "clover", "config": r"clover",
     "enforce": r"<targetPercentage>|targetPercentage|clover:check",
     "threshold": [r"targetPercentage\W+(\d+(?:\.\d+)?)"], "rate_scale": False},
]


def _pct(cov, tot) -> Optional[float]:
    return round(100.0 * cov / tot, 2) if tot else None


def _num(t: str) -> Optional[int]:
    t = re.sub(r"<[^>]+>|[,\s]", "", t)
    return int(t) if t.isdigit() else None


def _line_of(repo: str, rel: str, needle: str) -> int:
    for i, ln in enumerate(read_lines(repo, rel) or [], 1):
        if needle in ln:
            return i
    return 1


def parse_jacoco_xml(repo: str, rel: str):
    """JaCoCo and Kover (`koverXmlReport`) share this format: <counter type= missed= covered=> under the report root."""
    root = safe_xml_root(repo, rel)
    if root is None or root.tag != "report":
        return None
    res, size = {}, 0
    for c in root.findall("counter"):
        miss, cov = int(c.get("missed", 0)), int(c.get("covered", 0))
        if miss + cov:
            res[c.get("type")] = _pct(cov, miss + cov)
            if c.get("type") == "INSTRUCTION":
                size = miss + cov
    return (res, size, 1) if res else None


def parse_jacoco_csv(repo: str, rel: str):
    lines = read_lines(repo, rel) or []
    if not lines or "INSTRUCTION_MISSED" not in lines[0]:
        return None
    head = lines[0].split(",")
    tot: Dict[str, int] = {}
    for ln in lines[1:]:
        for h, v in zip(head, ln.split(",")):
            if h.endswith(("_MISSED", "_COVERED")) and v.strip().isdigit():
                tot[h] = tot.get(h, 0) + int(v)
    res = {}
    for k in ("INSTRUCTION", "BRANCH", "LINE", "COMPLEXITY", "METHOD", "CLASS"):
        v = _pct(tot.get(k + "_COVERED", 0), tot.get(k + "_MISSED", 0) + tot.get(k + "_COVERED", 0))
        if v is not None:
            res[k] = v
    return (res, tot.get("INSTRUCTION_MISSED", 0) + tot.get("INSTRUCTION_COVERED", 0), 1) if res else None


def parse_jacoco_html(repo: str, rel: str):
    text = "\n".join(read_lines(repo, rel) or [])
    m = re.search(r"<tfoot>(.*?)</tfoot>", text, re.S)
    if not m:
        return None
    cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", m.group(1), re.S)]
    if len(cells) < 13:
        return None

    def pair(a, b=None):  # "1,234 of 5,678" (missed of total) or two cells missed, total
        if b is None:
            mm = re.match(r"([\d,]+)\s+of\s+([\d,]+)", a)
            return (_num(mm.group(1)), _num(mm.group(2))) if mm else (None, None)
        return _num(a), _num(b)
    spec = (("INSTRUCTION", pair(cells[1])), ("BRANCH", pair(cells[3])), ("COMPLEXITY", pair(cells[5], cells[6])),
            ("LINE", pair(cells[7], cells[8])), ("METHOD", pair(cells[9], cells[10])), ("CLASS", pair(cells[11], cells[12])))
    res, size = {}, 0
    for k, (miss, tot) in spec:
        if miss is not None and tot:
            res[k] = _pct(tot - miss, tot)
            if k == "INSTRUCTION":
                size = tot
    line = next((i for i, ln in enumerate(read_lines(repo, rel) or [], 1) if "<tfoot>" in ln), 1)
    return (res, size, line) if res else None


def parse_kover_html(repo: str, rel: str):
    """Kover's HTML summary: a header row (Class, Method, Branch, Line, Instruction) and an `all classes` row of (covered/total)."""
    lines = read_lines(repo, rel) or []
    text = "\n".join(lines)
    m = re.search(r'<table class="coverageStats">(.*?)</table>', text, re.S)
    if not m:
        return None
    heads = [re.sub(r"<[^>]+>|,\s*%", "", h).strip().upper() for h in re.findall(r"<th[^>]*>(.*?)</th>", m.group(1), re.S)][1:]
    row = re.search(r'<td class="name">\s*all classes\s*</td>(.*?)</tr>', m.group(1), re.S)
    if not row:
        return None
    vals = re.findall(r"\((\d+)/(\d+)\)", row.group(1))
    res, size = {}, 0
    for h, (cov, tot) in zip(heads, vals):
        v = _pct(int(cov), int(tot))
        if v is not None:
            res[h] = v
            if h == "INSTRUCTION":
                size = int(tot)
    return (res, size, _line_of(repo, rel, "all classes")) if res else None


def parse_cobertura_or_clover_xml(repo: str, rel: str):
    root = safe_xml_root(repo, rel)
    if root is None or root.tag != "coverage":
        return None
    proj = root.find("project")
    if proj is not None and proj.find("metrics") is not None:  # OpenClover / Clover
        a = proj.find("metrics").attrib
        res = {}
        for k, c, t in (("LINE", "coveredstatements", "statements"), ("BRANCH", "coveredconditionals", "conditionals"),
                        ("METHOD", "coveredmethods", "methods")):
            v = _pct(int(a.get(c, 0)), int(a.get(t, 0)))
            if v is not None:
                res[k] = v
        return (res, int(a.get("statements", 0)), 1) if res else None
    res = {}
    for k, attr in (("LINE", "line-rate"), ("BRANCH", "branch-rate")):
        try:
            res[k] = round(float(root.get(attr)) * 100, 2)
        except (TypeError, ValueError):
            pass
    return (res, int(root.get("lines-valid", 0) or 0), 1) if res else None


# (tool, format, path regex, parser); format order doubles as preference: xml and csv are exact, html is read-only fallback
REPORTS = [
    ("jacoco", "xml", r"(^|/)(target|build)/.*jacoco[^/]*\.xml$", parse_jacoco_xml),
    ("jacoco", "csv", r"(^|/)(target|build)/.*jacoco[^/]*\.csv$", parse_jacoco_csv),
    ("jacoco", "html", r"(^|/)(target|build)/.*jacoco[^/]*/(?:[^/]+/)*index\.html$", parse_jacoco_html),
    ("kover", "xml", r"(^|/)(target|build)/reports/kover/(?:[^/]+/)*[^/]+\.xml$|(^|/)(target|build)/.*kover[^/]*\.xml$", parse_jacoco_xml),
    ("kover", "html", r"(^|/)(target|build)/reports/kover/(?:html/)?index\.html$", parse_kover_html),
    ("cobertura", "xml", r"(^|/)(target|build)/.*cobertura[^/]*\.xml$|(^|/)(target|build)/site/cobertura/coverage\.xml$", parse_cobertura_or_clover_xml),
    ("clover", "xml", r"(^|/)(target|build)/.*clover[^/]*\.xml$", parse_cobertura_or_clover_xml),
]
FMT_RANK = {"xml": 0, "csv": 1, "html": 2}


def in_plugin(repo: str, rel: str, line: int, name: str) -> bool:
    """True when pom line `line` sits inside a <plugin> whose artifactId mentions `name` (so a `<goal>check</goal>` of
    some other plugin, e.g. a checkstyle rule, is not taken for the coverage gate)."""
    ls = read_lines(repo, rel) or []
    start = next((i for i in range(min(line, len(ls)) - 1, -1, -1) if "<plugin>" in ls[i]), None)
    if start is None:
        return False
    end = next((j for j in range(line, len(ls)) if "</plugin>" in ls[j]), len(ls))
    return bool(re.search(r"<artifactId>[^<]*%s[^<]*</artifactId>" % re.escape(name), "\n".join(ls[start:end]), re.I))


def detect(ctx) -> List[dict]:
    """Tools configured in the build files, with enforcement and threshold read only from files that mention the tool."""
    out = []
    for t in TOOLS:
        hits = grep_files(ctx.repo, ctx.build_files, t["config"], 3)
        if not hits:
            continue
        files = sorted({h["path"] for h in hits})
        enf = grep_files(ctx.repo, files, t["enforce"], 1000)
        if t["id"] == "jacoco":  # a bare <goal>check</goal> counts only inside the JaCoCo plugin's own block
            enf = [e for e in enf if not (e["snippet"].strip() == "<goal>check</goal>"
                                          and not in_plugin(ctx.repo, e["path"], e["line_start"], "jacoco"))]
        enf = enf[:3]
        thr, tv = [], None
        for rx in t["threshold"]:
            thr = grep_files(ctx.repo, files, rx, 3)
            if thr:
                full = (read_lines(ctx.repo, thr[0]["path"]) or [""])[thr[0]["line_start"] - 1]  # snippets are cut at 200 chars
                m = re.search(rx, full)
                tv = float(m.group(1)) if m else None
                if tv is not None and t["rate_scale"] and tv <= 1:
                    tv = round(tv * 100, 2)
                break
        out.append({"id": t["id"], "config_ev": hits, "enforce_ev": enf, "threshold": tv, "threshold_ev": thr})
    return out


def measure(repo: str, configured: List[str]) -> Optional[dict]:
    """Best measured report on disk. Configured tools rank first, then exact formats, then the biggest report
    (a multi-module aggregate has more instructions than any single module); the path breaks ties."""
    order = {t["id"]: i for i, t in enumerate(TOOLS)}
    cands = []
    for rel in walk(repo, include_build=True):
        for tool, fmt, rx, parser in REPORTS:
            if re.search(rx, rel) and "/src/" not in "/" + rel and rel.split("/")[-2:-1] != ["site"]:
                try:
                    r = parser(repo, rel)
                except (OSError, ValueError):
                    r = None
                if r:
                    cands.append(((0 if tool in configured else 1, FMT_RANK[fmt], -r[1], order[tool], rel),
                                  {"tool": tool, "format": fmt, "path": rel, "counts": r[0], "line": r[2]}))
    return min(cands, key=lambda c: c[0])[1] if cands else None


REPRESENTATIVE_MIN = 0.5  # a report is only quoted as the app's coverage if the run behind it executed at least this share of the test classes
_RESULT = re.compile(r"(^|/)(build|target)/(test-results|surefire-reports|failsafe-reports)/.*TEST-[^/]+\.xml$")


def executed_tests(repo: str):
    """Test classes and cases a previous build executed, read from JUnit XML results already on disk.
    Nested classes (Outer$Inner) count toward their outer class. Returns None when no results exist."""
    classes, cases, first = set(), 0, None
    for rel in walk(repo, include_build=True):
        if not _RESULT.search(rel):
            continue
        head = "\n".join((read_lines(repo, rel) or [])[:6])
        tag = re.search(r"<testsuite\b[^>]*>", head)
        name = re.search(r'\bname="([^"]+)"', tag.group(0)) if tag else None
        n = re.search(r'\btests="(\d+)"', tag.group(0)) if tag else None
        if not (name and n):
            continue
        name, n = name.group(1), n.group(1)
        classes.add(name.split("$")[0])
        cases += int(n)
        first = first or rel
    return {"classes": len(classes), "cases": cases, "path": first} if classes else None
