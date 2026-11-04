"""Accuracy and consistency gate for a run: every claim the report makes is re-checked against the repositories and
against every other place the same number appears. Runs at the end of every scan and on demand (`app-insight verify`).

Accuracy: a cited line still reads what was cited; "in place" cites at least one line; "enforced" cites a CI file;
a control about the build or pipeline does not cite test code; a result is a verdict, not the control's description;
"not found" says where it searched, and is never claimed where the repository points outside the scan.
Consistency: coverage and status recompute from the controls; findings are exactly the gap controls; the portfolio
summary and the report carry the same states as the per-application files.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile

from . import engine_path  # noqa: F401
from . import aspects as A

import evidence  # engine
from detectors import Ctx  # engine
from detectors import security as SEC  # engine
from graph import resilience as RES  # engine

CI_FILE = A.CI_PATH
RULES = {
    "ACC-1": "a cited line no longer reads what was cited",
    "ACC-2": "an in-place, partial or issue result cites no line",
    "ACC-3": "'enforced' is claimed without citing a CI file",
    "ACC-4": "a build or pipeline control cites test code, or any control cites a test fixture, an example or build output",
    "ACC-5": "the result shows the control's description instead of a verdict",
    "ACC-6": "a gap has no severity, or a not-checked result gives no reason",
    "ACC-7": "an in-place result rests on an unknown (version or reference data not known)",
    "ACC-8": "a cited line about a secret shows the secret instead of [REDACTED]",
    "ACC-9": "a file written by the run holds a secret-looking value that is not redacted",
    "ACC-10": "a 'not found' or 'does not apply because not found' result does not say where it searched and what for",
    "ACC-11": "a file written by the run holds a literal value the secret detectors found in the repository",
    "ACC-12": "a file written by the run holds a value matching a credential pattern that redaction does not use",
    "ACC-13": "a result resting on reference data does not carry that data's source and review status",
    "ACC-14": "the evidence cannot be re-read as it was when the run was made",
    "CON-1": "coverage does not recompute from the controls",
    "CON-2": "aspect status does not recompute from the controls",
    "CON-3": "findings are not exactly the controls in a gap state",
    "CON-4": "the portfolio summary disagrees with the application",
    "CON-5": "a state or level outside the catalogue vocabulary",
    "CON-6": "the report shows different data from the analysis",
    "CON-7": "two controls of one application contradict each other",
    "CON-8": "a 'not found' or 'does not apply because not found' result in an area the scan recorded as partly outside its reach",
    "CON-9": "a 'not found' or 'does not apply because not found' result from a check that does not read the application's framework",
    "CON-10": "a dimension headline disagrees with the controls it summarises",
    "CON-11": "a count or derived number in the client file disagrees with a recomputation from the internal results with the review outcomes applied",
    "CON-12": "the client file shows something outside design 8.6 (an unreviewed verdict, an application out of scope, or the internal data)",
}
# design 8.8: these rules fail one application of the client file (it shows "Not available: verification failed"); every other
# rule, including any added later, fails the whole file
PER_APP = {"ACC-1", "ACC-2", "ACC-3", "ACC-4", "ACC-5", "ACC-6", "ACC-7", "ACC-10", "CON-1", "CON-2", "CON-3", "CON-5", "CON-7", "CON-8"}
UNKNOWN_WORDS = re.compile(r"(?i)\bunknown\b|line-specific|not in the reference data|cannot be decided|not recognised")
# (what one control says is not there, the controls whose result shows it is there)
# a second pattern set, independent of evidence.redact: shapes of credentials that redaction does not key on. A hit means a
# value got through that no redaction rule recognised (review F7); it is never repeated, only its file and place.
BROAD = [re.compile(x) for x in (
    r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{8,}",          # a JSON web token
    r"\bA(?:K|S)IA[0-9A-Z]{16}\b",                                                  # an AWS access key id
    r"\bAIza[0-9A-Za-z_-]{35}\b",                                                   # a Google API key
    r"\b(?:sk|rk)_live_[0-9A-Za-z]{16,}",                                            # a Stripe live key
    r"\bgh[pousr]_[A-Za-z0-9]{30,}|\bglpat-[A-Za-z0-9_-]{16,}|\bxox[abposr]-[A-Za-z0-9-]{10,}",  # GitHub, GitLab, Slack tokens
    r"(?i)AccountKey=[A-Za-z0-9+/=]{20,}|SharedAccessSignature=[^\s\"']{20,}",       # Azure storage / service bus
    r"\bMII[A-Za-z0-9+/]{40,}",                                                      # the body of a PEM key or certificate
    r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@\[\]\"'<>]+:[^/\s@\[\]\"'<>$]{3,}@",               # credentials in a URL
)]
CONTRADICTIONS = [
    (A.NEED_TEXT["database"], {"runtime.db_timeouts": ("PRESENT", "PARTIAL", "ABSENT", "ISSUE"), "architecture.no_shared_database": ("PRESENT", "ISSUE")}),
    (A.NEED_TEXT["outbound_http"], {"runtime.http_timeouts": ("PRESENT", "PARTIAL", "ABSENT", "ISSUE")}),
]


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _report_data(path):
    if not os.path.isfile(path):
        return None
    html = open(path, encoding="utf-8").read()
    i = html.find("const D = ")
    if i < 0:
        return None
    j = html.find(";\n", i)
    try:
        return json.loads(html[i + len("const D = "):j])
    except ValueError:
        return None


REPORT = "report-internal.html"  # the internal report; its name says so until the client-use gate passes (design section 2)
GAP, UNDECIDED = {"ABSENT", "PARTIAL", "ISSUE"}, {"NOT_ASSESSED", "UNKNOWN"}


def recompute(controls):
    """Aspect status and coverage from the controls, written here from the rules in design 6 and the catalogue, not by calling
    the writer's rollup: a mistake there must not check itself (review 2 N21). Returns (status, coverage)."""
    pending = [c for c in controls if c.get("pending")]
    applicable = [c for c in controls if not c.get("pending") and c["state"] != "NOT_APPLICABLE"]
    decided = [c for c in applicable if c["state"] not in UNDECIDED]
    high_gap = [c for c in decided if c["state"] == "ISSUE" or (c["state"] in GAP and c.get("severity") == "high")]
    table = [  # first row whose test holds gives the status
        (not applicable and bool(pending), "not_assessed"),
        (not applicable, "not_applicable"),
        (not decided, "not_assessed"),
        (bool(high_gap), "issues"),
        (any(c["state"] in GAP for c in decided), "gaps"),
        (len(decided) < len(applicable) or bool(pending), "in_place_partly_checked"),
        (True, "in_place"),
    ]
    status = next(name for test, name in table if test)
    return status, {"applicable": len(applicable), "assessed": len(decided), "present": sum(1 for c in decided if c["state"] == "PRESENT"),
                    "pending": len(pending)}


def _git(repo, args):
    return subprocess.run(["git", "-C", repo] + args, capture_output=True, timeout=300)


def source_view(repo, fingerprint, src):
    """The repository as it was when the run was made: the working tree when it still matches the run's inventory fingerprint,
    otherwise an export of the recorded commit (read-only: `git archive`, never a checkout of the clone), otherwise None with
    the reason. Returns (directory, temporary directory to remove or None, reason or None)."""
    if not repo or not os.path.isdir(repo):
        return None, None, "the repository is not on disk"
    files = evidence.walk(repo)
    if not fingerprint or evidence.inventory_fingerprint(repo, files) == fingerprint:
        return repo, None, None
    sha = (src or {}).get("commit")
    if not sha:  # the inventory also depends on how this version lists files, so the cause is not claimed
        return None, None, "the files differ from the run's inventory (the repository, or the way this version lists files, changed) and there is no commit to rebuild the run's state from"
    if (src or {}).get("changed_files"):
        return None, None, "the repository changed since the run, and at the run it had %d uncommitted change(s), so its state then cannot be rebuilt" % src["changed_files"]
    if _git(repo, ["cat-file", "-e", sha + "^{commit}"]).returncode != 0:
        return None, None, "the repository changed since the run and commit %s is no longer in it" % sha[:12]
    tmp = tempfile.mkdtemp(prefix="app-insight-verify-")
    arch = _git(repo, ["archive", "--format=tar", sha])
    if arch.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        return None, None, "commit %s could not be exported" % sha[:12]
    tar = os.path.join(tmp, "src.tar")
    with open(tar, "wb") as fh:
        fh.write(arch.stdout)
    root = os.path.join(tmp, "src")
    with tarfile.open(tar) as tf:
        safe = [m for m in tf.getmembers() if not m.issym() and not m.islnk() and not os.path.isabs(m.name) and ".." not in m.name.split("/")]
        tf.extractall(root, members=safe)
    os.remove(tar)
    return root, tmp, None


def check(run_dir, catalogue=None, report_path=None):
    """Returns {"ok", "checked": {...}, "problems": [{rule, app, control, detail}]}. `report_path`: the page to check when it is
    not yet written (a scan verifies the page before writing it)."""
    cat = catalogue or A.load_catalogue()
    out = os.path.join(run_dir, "analysis")
    man = _read(os.path.join(out, "manifest.json"))
    repos = {x["app"]: x.get("repo") for x in man["applications"]}
    run_rec = _read(os.path.join(run_dir, "run.json")) if os.path.isfile(os.path.join(run_dir, "run.json")) else {}
    srcs = {os.path.abspath(x["path"]): x for x in run_rec.get("sources") or [] if x.get("path")}
    views, temps, unread = {}, [], {}
    for x in man["applications"]:  # read every repository as it was when the run was made (review 2 N11)
        d, tmp, why = source_view(x.get("repo"), x.get("inventory_fingerprint"), srcs.get(os.path.abspath(x.get("repo") or "")))
        views[x["app"]] = d
        if tmp:
            temps.append(tmp)
        if why:
            unread[x["app"]] = why
    by_id = {c["id"]: c for c in cat["controls"]}
    descriptions = {c[3] for c in RES.CHECKS} | {c.get("fix") for c in cat["controls"] if c.get("fix")}
    port = _read(os.path.join(out, "portfolio", "aspects.json")) if os.path.isfile(os.path.join(out, "portfolio", "aspects.json")) else {"applications": {}}
    legacy = os.path.join(run_dir, "report.html")  # the name before the internal report was named as such
    rep = _report_data(report_path or (os.path.join(run_dir, REPORT) if os.path.isfile(os.path.join(run_dir, REPORT)) or not os.path.isfile(legacy) else legacy))
    rep_apps = {a["name"]: a for a in (rep or {}).get("apps", [])}
    probs, n = [], {"applications": 0, "controls": 0, "lines_reread": 0}

    def bad(rule, app, ctl, detail):
        probs.append({"rule": rule, "app": app, "control": ctl, "detail": detail})

    for app, repo in sorted(repos.items()):
        p = os.path.join(out, app, "aspects.json")
        if not os.path.isfile(p):
            continue
        doc = _read(p)
        n["applications"] += 1
        if app in unread:
            bad("ACC-14", app, "-", unread[app])
        view = views.get(app)
        gaps = []
        for asp in doc["aspects"]:
            for c in asp["controls"]:
                n["controls"] += 1
                cid, st, src = c["id"], c["state"], (by_id.get(c["id"]) or {}).get("source") or {}
                if st not in cat["states"] or (c["level"] and c["level"] not in cat["levels"]):
                    bad("CON-5", app, cid, "%s / %s" % (st, c["level"]))
                for e in c["evidence"]:
                    if e.get("kind") == "file" and view:
                        n["lines_reread"] += 1
                        why = evidence.verify(view, e)
                        if why:
                            bad("ACC-1", app, cid, why)
                if (by_id.get(cid) or {}).get("source", {}).get("check", "").startswith("security.secrets"):
                    for e in c["evidence"]:
                        if "[REDACTED]" not in (e.get("snippet") or "") and "PRIVATE KEY" not in (e.get("snippet") or ""):
                            bad("ACC-8", app, cid, "%s:%s" % (e.get("path"), e.get("line_start")))
                if st in ("PRESENT", "PARTIAL", "ISSUE") and not c["evidence"] and not (by_id.get(cid) or {}).get("negative_scan"):
                    bad("ACC-2", app, cid, "%s: %s" % (st, c["summary"][:80]))
                if c["level"] == "enforced" and not any(CI_FILE.search(e.get("path") or "") for e in c["evidence"]):
                    bad("ACC-3", app, cid, ", ".join("%s:%s" % (e.get("path"), e.get("line_start")) for e in c["evidence"][:3]) or "no evidence")
                test_ok = src.get("criterion") in A.TEST_CRITERIA or "safetynet" in src
                for e in c["evidence"]:
                    role = evidence.role(e.get("path") or "") if e.get("kind") == "file" else "application"
                    if (not test_ok and A.TEST_PATH.search(e.get("path") or "")) or role in ("example", "build_output") or (role == "test_fixture" and not test_ok):
                        bad("ACC-4", app, cid, "%s:%s" % (e["path"], e.get("line_start")))
                        break
                if st == "PRESENT" and UNKNOWN_WORDS.search(c["summary"]):
                    bad("ACC-7", app, cid, c["summary"][:90])
                if src.get("lifecycle") and st not in ("NOT_APPLICABLE", "NOT_ASSESSED"):  # R-11: a result that used the support dates carries their status
                    ref = c.get("reference") or {}
                    if not ref.get("source") or not ref.get("status") or (ref["status"] != "reviewed" and st != "UNKNOWN" and ref["status"] not in c["summary"]):
                        bad("ACC-13", app, cid, "reference %s" % (ref.get("status") or "missing"))
                if c["summary"] in descriptions:
                    bad("ACC-5", app, cid, c["summary"][:90])
                if (st in A.GAP_STATES and not c["severity"]) or (st in ("NOT_ASSESSED", "UNKNOWN") and not c["summary"]):
                    bad("ACC-6", app, cid, st)
                ctl = by_id.get(cid) or {}
                need = (ctl.get("applies") or {}).get("needs") if st == "NOT_APPLICABLE" and c["summary"] == A.NEED_TEXT.get((ctl.get("applies") or {}).get("needs")) else None
                srch = ctl.get("search") if st == "ABSENT" else A.NEED_SEARCH.get(need) if need else None
                if srch:
                    s = c.get("searched") or {}
                    if not s.get("for") or not s.get("in") or any(w["area"] == "repo" and not w.get("files") for w in s.get("in") or []):
                        bad("ACC-10", app, cid, "no search record" if not s.get("in") else "the search record does not name what it checked")
                    areas = set(srch["blind_to"] if "blind_to" in srch else srch.get("in") or [])
                    blind = [b for b in (doc.get("scope") or {}).get("blind_spots") or [] if b["area"] in areas]
                    if blind and not ctl.get("negative_scan"):
                        bad("CON-8", app, cid, "%s, but %s" % (c["summary"][:60], blind[0]["what"][:60]))
                fw, knows = (doc.get("profile") or {}).get("framework"), ctl.get("understands")
                outside_fw = knows and fw not in knows and (fw or (doc.get("profile") or {}).get("kind") == "service")
                if outside_fw and (st == "ABSENT" and not c.get("framework_neutral") or need):
                    bad("CON-9", app, cid, "%s for %s, which this check does not read" % (st, fw or "an unrecognised framework"))
                if st in A.GAP_STATES:
                    gaps.append(c["finding"])
            status, cov = recompute(asp["controls"])
            if cov != asp["coverage"]:
                bad("CON-1", app, asp["id"], "stored %s, recomputed %s" % (asp["coverage"], cov))
            if status != asp["status"]:
                bad("CON-2", app, asp["id"], "stored %s, recomputed %s" % (asp["status"], status))
            if port["applications"].get(app, {}).get(asp["id"]) != asp["status"]:
                bad("CON-4", app, asp["id"], "portfolio says %s" % port["applications"].get(app, {}).get(asp["id"]))
        by = {c["id"]: c for a in doc["aspects"] for c in a["controls"]}
        for absent_text, shows in CONTRADICTIONS:
            says_none = [c["id"] for c in by.values() if c["summary"] == absent_text]
            says_some = [k for k, sts in shows.items() if k in by and by[k]["state"] in sts]
            if says_none and says_some:
                bad("CON-7", app, says_none[0], "says '%s' but %s found it" % (absent_text, says_some[0]))
        dim_path = os.path.join(out, app, "dimensions.json")
        coup = ((_read(dim_path) if os.path.isfile(dim_path) else {}).get("dimensions") or {}).get("architecture_coupling") or {}
        for where, head in (("dimensions.json", coup.get("headline")), ("aspects context", ((doc.get("context") or {}).get("architecture_coupling") or {}).get("headline"))):
            why = _coupling_disagrees(by.get("architecture.calls_matched"), head, coup)
            if why:
                bad("CON-10", app, "architecture.calls_matched", "%s: %s" % (where, why))
        if sorted(gaps) != sorted(doc["findings"]) or None in gaps:
            bad("CON-3", app, "-", "%d gap controls, %d findings" % (len(gaps), len(doc["findings"])))
        if rep is not None and (app not in rep_apps or rep_apps[app].get("aspects") != doc):
            bad("CON-6", app, "-", "the report does not carry this application's aspects.json")
    if rep is None:
        bad("CON-6", "-", "-", "the report is missing or its data could not be read")
    values = set()
    for repo in sorted({v for v in views.values() if v and os.path.isdir(v)}):  # re-located in memory, at the run's state
        try:
            values |= SEC.secret_values(Ctx(repo))
        except Exception as e:  # noqa: BLE001  without the values the check cannot be made: that is a failure, not a pass
            bad("ACC-11", os.path.basename(repo), "-", "the secret detectors could not be re-run (%s), so written files were not compared" % type(e).__name__)
    for root, _, names in os.walk(run_dir):  # every file the run wrote: analysis JSON, the report, the run record
        for name in names:
            if not name.endswith((".json", ".html", ".md", ".txt")) or name == "verify.json":
                continue
            path, rel = os.path.join(root, name), os.path.relpath(os.path.join(root, name), run_dir)
            text = open(path, encoding="utf-8", errors="replace").read()
            # compare decoded values (a JSON escape is not a secret); the page is its data blob plus the markup around it
            if name.endswith(".json"):
                try:
                    leaked = evidence.redact_tree(json.loads(text)) != json.loads(text)
                except ValueError:
                    leaked = evidence.redact(text) != text
            elif name.endswith(".html") and "const D = " in text and _report_data(path) is not None:
                # every report page, whatever its name: its data blob is compared decoded (a JSON escape is not a secret)
                i = text.find("const D = ")
                j = text.find(";\n", i)
                blob = json.loads(text[i + len("const D = "):j])
                leaked = evidence.redact_tree(blob) != blob or evidence.redact(text[:i] + text[j:]) != text[:i] + text[j:]
            elif name.endswith(".html"):  # a page with no data blob (the client file): each decoded text and attribute value on its own
                leaked = any(evidence.redact(x) != x for x in _html_strings(text))
            else:
                leaked = evidence.redact(text) != text
            if leaked:  # the location only: the value itself is never repeated
                bad("ACC-9", rel, "-", "holds a value that redaction would mask")
            for rule, where in (("ACC-11", _find_values(text, values)), ("ACC-12", _find_broad(text))):
                if where:
                    bad(rule, rel, "-", "at %s" % where)
    for t in temps:
        shutil.rmtree(t, ignore_errors=True)
    return {"ok": not probs, "checked": n, "problems": probs, "rules": RULES}


def _html_strings(text):
    import html.parser
    out = []

    class P(html.parser.HTMLParser):
        def handle_data(self, d):
            out.append(d)

        def handle_starttag(self, tag, attrs):
            out.extend(v for _, v in attrs if v)

    P(convert_charrefs=True).feed(text)
    return out


def _strings(text):
    """(location, string) for every string a written file holds: decoded JSON values (escapes undone) and plain text lines."""
    i = text.find("const D = ")
    if i >= 0:  # the report: its data blob, then the markup around it
        j = text.find(";\n", i)
        try:
            yield from _walk(json.loads(text[i + len("const D = "):j]), "data")
        except ValueError:
            pass
        text = text[:i] + text[j:]
    else:
        try:
            yield from _walk(json.loads(text), "$")
            return
        except ValueError:
            pass
    for n, ln in enumerate(text.splitlines(), 1):
        yield "line %d" % n, ln


def _walk(o, path):
    if isinstance(o, str):
        yield path, o
    elif isinstance(o, list):
        for k, v in enumerate(o):
            yield from _walk(v, "%s[%d]" % (path, k))
    elif isinstance(o, dict):
        for k, v in o.items():
            yield "%s.%s (key)" % (path, k[:40]), k
            yield from _walk(v, "%s.%s" % (path, k[:40]))


def _find_values(text, values):
    if not values or not any(v in text for v in values):  # fast path; a JSON escape is checked below on the decoded strings
        if not values or "\\" not in text:
            return None
    for where, st in _strings(text):
        if any(v in st for v in values):
            return where
    return None


def _find_broad(text):
    for where, st in _strings(text):
        if any(rx.search(st) for rx in BROAD):
            return where
    return None


def _coupling_disagrees(ctl, head, coup):
    """The coupling headline against architecture.calls_matched: an incomplete map is never shown as complete, and the unmatched
    count is the same number in both places. An independent reading of the two stored results, not a recomputation."""
    if not ctl or not head:
        return None
    unres = (coup.get("values") or {}).get("unresolved_or_ambiguous_relationships")
    if ctl["state"] == "UNKNOWN" and "incomplete" not in head:
        return "calls matched is undecided (the map is incomplete), but the headline does not say so"
    m = re.match(r"(\d+) of \d+ relationships not matched", ctl["summary"])
    if ctl["state"] == "PARTIAL" and m and unres is not None and int(m.group(1)) != unres:
        return "calls matched says %s unmatched, the headline %s unresolved" % (m.group(1), unres)
    if ctl["state"] == "PRESENT" and ("incomplete" in head or unres):
        return "calls matched says all matched, the headline does not"
    return None


def client_level(rule):
    return "app" if rule in PER_APP else "run"


class _Page(__import__("html.parser").parser.HTMLParser):
    """The client file's marked elements (data-* attributes) and the text inside each result."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.els, self.stack, self.text = [], [], {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("meta", "br", "img", "input", "link"):
            if any(k.startswith("data-") for k in a):
                self.els.append((tag, a))
            return
        self.stack.append((tag, a.get("data-key")))
        if any(k.startswith("data-") for k in a):
            self.els.append((tag, a))
        if a.get("data-key"):
            self.text[a["data-key"]] = []

    def handle_endtag(self, tag):
        while self.stack:
            t, _ = self.stack.pop()
            if t == tag:
                break

    def handle_data(self, data):
        for _, k in self.stack:
            if k:
                self.text[k].append(data)


def _client_expect(run_dir, cat, at):
    """The client file's numbers recomputed here from aspects.json and review.json, from the rules of design 8.2, 8.4 and 8.6
    written again, not by calling the client file's code (review 2 N21)."""
    import datetime
    rv = _read(os.path.join(run_dir, "review.json"))
    out = os.path.join(run_dir, "analysis")
    ctl = {c["id"]: c for c in cat["controls"]}
    outc, extra = rv["outcomes"], rv.get("must_extra") or {}

    def live(k):
        o = outc.get(k)
        if not o or (o["outcome"] != "confirmed" and at - datetime.datetime.fromisoformat(o["at"]) > datetime.timedelta(days=90)):
            return None
        return o

    exp = {}
    for app in rv["scope"]["apps"]:
        doc = _read(os.path.join(out, app, "aspects.json"))
        res, unresolved = [], False
        for asp in doc["aspects"]:
            for c in asp["controls"]:
                if c.get("pending"):
                    continue
                k, st, cc = "%s::%s" % (app, c["id"]), c["state"], ctl.get(c["id"]) or {}
                csev = cc.get("severity", "medium")
                need = (cc.get("applies") or {}).get("needs")
                high = csev in ("high", "critical")
                must = (st == "ISSUE" and c.get("confirmed") is not False) or st in ("ABSENT", "PARTIAL", "UNKNOWN") or \
                    (high and st == "NOT_APPLICABLE" and bool(need) and c["summary"] == A.NEED_TEXT.get(need)) or \
                    (high and st == "PRESENT" and c.get("level") not in ("enforced", "verified")) or k in extra
                o = live(k)
                if must and (not o or (extra.get(k) == "individual" and o["mode"] != "individual")):
                    unresolved = True
                res.append((asp["id"], k, c, o, csev))
        exp[app] = {"failed": bool(doc.get("failures")), "unresolved": unresolved, "results": res}
    return rv, exp


def _eff(c, o, csev):
    """(class, problem found, high) of a resolved outcome: 8.4's "counts as" column."""
    st = {"confirmed": c["state"], "corrected": o.get("state"), "team_stated": o.get("state"), "gap_stated": "ISSUE?"}.get(o["outcome"])
    if o["outcome"] == "confirmed" and c["state"] == "ISSUE" and c.get("confirmed") is False:
        return "possible", False, False
    sev = (c.get("severity") or csev) if o["outcome"] == "confirmed" else csev
    cls = "gap" if st in ("ABSENT", "PARTIAL", "ISSUE", "ISSUE?") else "pass" if st == "PRESENT" else "na" if st == "NOT_APPLICABLE" else "neutral"
    return cls, cls == "gap" and st == "ISSUE", cls == "gap" and (st == "ISSUE" or sev in ("high", "critical"))


def _cell(rows):
    y, done = len(rows), [(o, _eff(c, o, s)) for c, o, s in rows if o]
    tests = [  # first row whose test holds gives the cell
        (y == 0, "Not checked"),
        (any(e[2] for _, e in done), "High gaps"),
        (any(e[0] == "gap" for _, e in done), "Gaps"),
        (len(done) < y, "Reviewed %d of %d" % (len(done), y)),
        (all(e[0] == "na" for _, e in done), "Not applicable"),
        (not any(e[0] == "pass" for _, e in done), "Reviewed, nothing confirmed"),
        (any(e[0] in ("neutral", "possible") for _, e in done), "Partly confirmed"),
        (any(e[0] == "pass" and o["outcome"] in ("corrected", "team_stated") for o, e in done), "In place (stated)"),
        (True, "In place"),
    ]
    return next(name for test, name in tests if test)


def check_client(run_dir, path, catalogue=None):
    """The client-count rule (CON-11) and the whitelist rule (CON-12) over a client file, against review.json and aspects.json."""
    import datetime
    cat = catalogue or A.load_catalogue()
    probs = []

    def bad(rule, app, ctl, detail):
        probs.append({"rule": rule, "app": app, "control": ctl, "detail": detail})

    text = open(path, encoding="utf-8").read()
    pg = _Page()
    pg.feed(text)
    root = next((a for t, a in pg.els if t == "html"), {})
    at = datetime.datetime.fromisoformat(root.get("data-generated") or "1970-01-01T00:00:00+00:00")
    rv, exp = _client_expect(run_dir, cat, at)
    scope = rv["scope"]["apps"]
    if "const D = " in text or "<script" in text.lower():
        bad("CON-12", "-", "-", "the client file carries a script or the internal report's data")
    rows = {a["data-app"]: a for t, a in pg.els if "data-app" in a and "data-status" in a}
    for app in sorted(set(rows) - set(scope)):
        bad("CON-12", app, "-", "an application outside the review's scope has a row")
    oos = sorted(a["data-oos"] for t, a in pg.els if "data-oos" in a)
    if oos != sorted({x["app"] for x in _read(os.path.join(run_dir, "analysis", "manifest.json"))["applications"]} - set(scope)):
        bad("CON-11", "-", "-", "the applications listed as not in this review are not the analysed applications outside the scope")
    shown, n = {}, {"n": 0, "k": 0, "j": 0}
    for app in scope:
        row, e = rows.get(app), exp[app]
        if not row:
            bad("CON-11", app, "-", "an application in scope has no row")
            continue
        st = row["data-status"]
        want = "na_analysis" if e["failed"] else "not_yet" if e["unresolved"] else "shown"
        if st != want and not (st == "na_verify" and want != "na_analysis"):  # withholding after a failed check never overclaims
            bad("CON-11", app, "-", "status %s, recomputed %s" % (st, want))
        n["n" if st == "shown" else "k" if st == "not_yet" else "j"] += 1
        if st == "shown":
            shown[app] = e
    s = next((a for t, a in pg.els if "data-n" in a), {})
    if [s.get("data-%s" % k) for k in "nmkj"] != [str(n["n"]), str(len(scope)), str(n["k"]), str(n["j"])]:
        bad("CON-11", "-", "-", "summary row %s, recomputed %d of %d; %d; %d" % ([s.get("data-%s" % k) for k in "nmkj"], n["n"], len(scope), n["k"], n["j"]))
    keyed = {a["data-key"]: a for t, a in pg.els if "data-key" in a}
    for k in keyed:
        if k.split("::")[0] not in shown:
            bad("CON-12", k.split("::")[0], k.split("::")[1] if "::" in k else "-", "a result is shown for an application that is not shown as reviewed")
    find, rem = {}, {}
    cells = {(a.get("data-row"), a["data-aspect"]): a["data-cell"] for t, a in pg.els if "data-cell" in a}
    for app, e in shown.items():
        cnt = {"issues": 0, "high": 0, "gaps": 0, "disputes": 0}
        by = {}
        for aid, k, c, o, csev in e["results"]:
            if c["state"] == "NOT_ASSESSED" or (c["state"] == "ISSUE" and c.get("confirmed") is False and not o):
                if k in keyed:
                    bad("CON-12", app, c["id"], "a result that is not shown in a client file (not checked, or a possible issue nobody reviewed) is shown")
                continue
            by.setdefault(aid, []).append((c, o, csev))
            el = keyed.get(k)
            if el is None:
                bad("CON-11", app, c["id"], "a result is missing")
                continue
            if (el.get("data-outcome") or "none") != (o["outcome"] if o else "none"):
                bad("CON-11", app, c["id"], "outcome %s, review.json %s" % (el.get("data-outcome"), o["outcome"] if o else "none"))
            if not o:
                if "".join(pg.text.get(k, [])).strip() != "%s: Not reviewed" % c["title"]:
                    bad("CON-12", app, c["id"], "a result with no outcome shows more than 'Not reviewed'")
                continue
            cls, issue, high = _eff(c, o, csev)
            cnt["issues"] += issue
            cnt["high"] += high
            cnt["gaps"] += cls == "gap"
            cnt["disputes"] += o["outcome"] == "disputed"
            ids = [x for x in (el.get("data-remedies") or "").split(",") if x]
            if ids and cls != "gap":
                bad("CON-12", app, c["id"], "a remedy is shown on a result that is not a reviewed gap")
            if o["outcome"] == "confirmed" and cls == "gap" and ids != ["%s:%s" % (r["pack"], r["key"]) for r in c.get("remedies") or []]:
                bad("CON-11", app, c["id"], "the remedies shown are not the result's remedies")
            if cls == "gap":
                find[c["id"]] = find.get(c["id"], 0) + 1
                for x in ids:
                    rem.setdefault(x, [0, set()])
                    rem[x][0] += 1
                    rem[x][1].add(app)
        row = rows[app]
        for kk, v in cnt.items():
            if row.get("data-" + kk) != str(v):
                bad("CON-11", app, "-", "%s %s, recomputed %d" % (kk, row.get("data-" + kk), v))
        for aid, rs in by.items():
            got = cells.get((app, aid))
            if got != _cell(rs):
                bad("CON-11", app, aid, "aspect cell %s, recomputed %s" % (got, _cell(rs)))
    got_f = {a["data-control"]: int(a["data-apps"]) for t, a in pg.els if "data-control" in a}
    if got_f != find:
        bad("CON-11", "-", "-", "the gap counts across applications do not recompute")
    got_r = {a["data-remedy"]: (int(a["data-gaps"]), int(a["data-apps"])) for t, a in pg.els if "data-remedy" in a}
    if got_r != {k: (v[0], len(v[1])) for k, v in rem.items()}:
        bad("CON-11", "-", "-", "the remedy counts do not recompute")
    audited = next((a["data-audited"] for t, a in pg.els if "data-audited" in a), None)
    if audited == "yes" and not (rv.get("auditor") and rv.get("audit")):
        bad("CON-11", "-", "-", "the statement says a second person audited, but review.json holds no audit")
    return {"ok": not probs, "problems": probs}


def write(run_dir, catalogue=None):
    res = check(run_dir, catalogue)
    with open(os.path.join(run_dir, "verify.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, sort_keys=True)
    return res


def print_result(res, limit=20):
    n = res["checked"]
    head = "%d applications, %d controls, %d cited lines re-read" % (n["applications"], n["controls"], n["lines_reread"])
    if res["ok"]:
        print("verification:  PASS (%s)" % head)
        return
    by = {}
    for p in res["problems"]:
        by.setdefault(p["rule"], []).append(p)
    print("verification:  FAIL, %d problem(s) (%s)" % (len(res["problems"]), head))
    for rule in sorted(by):
        print("  %s %s: %d" % (rule, RULES[rule], len(by[rule])))
        for p in by[rule][:limit]:
            print("      %s  %s  %s" % (p["app"], p["control"], p["detail"]))
