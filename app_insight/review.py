"""Consultant review (design 8): which results a person checks one by one, which may be confirmed by aspect, the audit sample,
the outcomes a person can record, the stop rule, and marks bound to what was reviewed so they carry forward only when nothing
they rest on changed. State lives in the run's review.json, written atomically after every action, under a single-writer lock.

A person decides every outcome (R-01); this module only checks that the outcome is allowed for the result and stores it. The
review page (review_page.py) and `review --record` both go through Review.record / bulk / audit, so there is one path for a mark.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
import secrets
import shutil
import socket

from . import engine_path  # noqa: F401
from . import aspects as A
from . import verify as V

import evidence  # engine

CONTRACT = "app-insight-review.v1"
FILE, LOCK = "review.json", "review.lock"
EXPIRY_DAYS = 90            # every outcome but Confirmed expires at the next run or after this (8.4)
BUDGET_MIN = 40             # minutes per application (8.1, T-2.0)
DEFAULT_ITEM_S = 60         # until measured: about one minute per item and per bulk screen (8.1)
WINDOW, LIMIT = 30, 2       # stop rule: more than LIMIT tool errors in any WINDOW individually reviewed results (8.5)
HIGH = ("critical", "high")
GAP = set(A.GAP_STATES)
OUTCOMES = {"confirmed": "Confirmed", "corrected": "Corrected by the consultant", "gap_stated": "Gap stated by the consultant",
            "disputed": "Disputed by the consultant", "cannot_confirm": "Cannot confirm", "team_stated": "Stated by the team"}
# the fixed reason list of 8.4: (label, counts as a tool error)
REASONS = {"tool_missed": ("tool missed it", True), "false_pass": ("tool reported it in place wrongly", True),
           "test_or_copy": ("evidence is a test or a copy", True), "wrong_app": ("wrong application", True),
           "wrong_kind": ("wrong kind or severity", True), "outside_repo": ("set outside the repository", False),
           "client_fact": ("client fact", False), "other": ("other, with a note", False)}
# one vocabulary (design 11)
STATE_LABEL = {"PRESENT": "In place", "PARTIAL": "Partly in place", "ABSENT": "Not found", "ISSUE": "Problem found", "UNKNOWN": "Undecided",
               "NOT_APPLICABLE": "Not applicable", "NOT_ASSESSED": "Not checked"}
MODES = {"individual": "checked individually", "aspect": "confirmed with its aspect"}
ITEM = {1: "problem found", 2: "a claim about the team's work (not found or partly in place)", 3: "undecided or not applicable on a high-severity control",
        4: "high-severity, in place below enforced", 5: "earlier outcome other than Confirmed", 6: "stop rule: control under escalation", 7: "undecided"}


class Refused(Exception):
    """An action the review rules do not allow; the message says why and what to do."""


def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def iso(t):
    return t.isoformat()


def parse(s):
    return datetime.datetime.fromisoformat(s)


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def atomic_write(path, text):
    """Write beside the target and rename over it: a crash leaves the old file or the new one, never half of one."""
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _sha(text):
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def mark_text(mark, run=None):
    """How a mark was made, in the client-file words (8.3)."""
    if mark.get("mode") == "carried":
        return "carried forward from run %s, confirmed %s" % (mark["carried_from"]["run"], mark["carried_from"]["at"][:10])
    return MODES.get(mark.get("mode"), "")


# ---------- the lock ----------

def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire(run_dir):
    """Single writer per run (8.7). A lock left by a review that crashed on this machine is taken over; any other is refused."""
    p = os.path.join(run_dir, LOCK)
    me = {"pid": os.getpid(), "host": socket.gethostname(), "at": iso(now())}
    for _ in range(2):
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                held = _read(p)
            except (OSError, ValueError):
                held = {}
            if held.get("host") == me["host"] and isinstance(held.get("pid"), int) and not _alive(held["pid"]):
                os.remove(p)
                continue
            raise Refused("this run is already under review (lock held by pid %s on %s since %s); a second review of the same run is refused"
                          % (held.get("pid"), held.get("host"), held.get("at")))
        with os.fdopen(fd, "w") as fh:
            json.dump(me, fh)
        return p
    raise Refused("could not take the review lock")


def workspace_of(run_dir):
    parent = os.path.dirname(os.path.abspath(run_dir))
    return os.path.dirname(parent) if os.path.basename(parent) == "runs" else None


# ---------- the review ----------

class Review:
    def __init__(self, run_dir, apps=None, chosen_by=None, reviewer=None, auditor=None, first_meeting=None, at=None, seed=None,
                 budget=BUDGET_MIN, lock=True):
        self.run_dir = os.path.abspath(run_dir)
        self.path = os.path.join(self.run_dir, FILE)
        self.lock = acquire(self.run_dir) if lock else None
        self._views, self._temps, self._areas, self._cx = {}, [], {}, {}
        try:
            self._load(apps, chosen_by, reviewer, auditor, first_meeting, at or now(), seed, budget)
        except BaseException:
            self.close()
            raise

    def close(self):
        for t in self._temps:
            shutil.rmtree(t, ignore_errors=True)
        self._temps = []
        if self.lock and os.path.isfile(self.lock):
            os.remove(self.lock)
        self.lock = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ----- loading -----
    def _load(self, apps, chosen_by, reviewer, auditor, first_meeting, at, seed, budget):
        rd = self.run_dir
        self.run = _read(os.path.join(rd, "run.json"))
        self.out = os.path.join(rd, "analysis")
        self.man = _read(os.path.join(self.out, "manifest.json"))
        self.cat = A.load_catalogue()
        self.packs = A.load_remedy_packs(self.run["remedy_packs"])
        self.ctl = {c["id"]: c for c in self.cat["controls"]}
        self.ctl_order = {c["id"]: i for i, c in enumerate(self.cat["controls"])}
        self.asp_order = {a["id"]: a["order"] for a in self.cat["aspects"]}
        self.asp_title = {a["id"]: a["title"] for a in self.cat["aspects"]}
        self.docs = {x["app"]: _read(os.path.join(self.out, x["app"], "aspects.json")) for x in self.man["applications"]
                     if os.path.isfile(os.path.join(self.out, x["app"], "aspects.json"))}
        self.ws = workspace_of(rd)
        doc = _read(self.path) if os.path.isfile(self.path) else None
        fresh = doc is None
        if doc:
            if apps and sorted(apps) != doc["scope"]["apps"]:
                raise Refused("this run's review covers %s; a different scope is a new review of a new run" % ", ".join(doc["scope"]["apps"]))
            if chosen_by and chosen_by != doc["scope"]["chosen_by"]:
                raise Refused("this review's scope was chosen by the %s" % doc["scope"]["chosen_by"])
        else:
            if not apps or chosen_by not in ("consultant", "client") or not reviewer:
                raise Refused("a new review needs --apps, --chosen-by consultant|client and --reviewer")
            unknown = sorted(set(apps) - set(self.docs))
            if unknown:
                raise Refused("not analysed in this run: %s" % ", ".join(unknown))
            doc = {"contract": CONTRACT, "run": os.path.basename(rd), "client": self.run.get("client"), "created_at": iso(at),
                   "scope": {"apps": sorted(set(apps)), "chosen_by": chosen_by}, "first_meeting": bool(first_meeting),
                   "seed": seed if seed is not None else secrets.randbelow(2 ** 31), "reviewers": [], "auditor": None,
                   "outcomes": {}, "audit": {}, "audit_doublings": 0, "log": [], "bulk_screens": [], "firings": [], "carried_firings": []}
        self.doc = doc
        if reviewer and reviewer not in doc["reviewers"]:
            doc["reviewers"].append(reviewer)
        if auditor:
            if auditor in doc["reviewers"] or auditor == reviewer:
                raise Refused("the audit sample is presented to a second person: the auditor must not be a reviewer")
            doc["auditor"] = auditor
        if first_meeting:
            doc["first_meeting"] = True
        self.reviewer = reviewer  # marks are attributed only to the person named for this session, never to an earlier one
        self.scope = doc["scope"]["apps"]
        self.results = {}
        for app in self.scope:
            for asp in self.docs[app]["aspects"]:
                for c in asp["controls"]:
                    if c.get("pending"):
                        continue  # no detector: listed once as out of scope (R-17), never per application
                    self.results["%s::%s" % (app, c["id"])] = self._result(app, c)
        self.prior, prior_firings = self._prior()
        if fresh:  # a new review: carry forward, carry the stop rule, check the budget
            doc["carried_firings"] = prior_firings
            self._carry_forward()
            self._refresh()
            p = self.plan()
            if p["projected_min"] > budget * len(self.scope):
                raise Refused("projected review effort %d min exceeds the budget of %d min (%d per application); reduce the scope "
                              "(must-review items are never dropped). Per application: %s" % (
                                  p["projected_min"], budget * len(self.scope), budget,
                                  ", ".join("%s %d min" % (a, m) for a, m in sorted(p["per_app"].items(), key=lambda x: -x[1]))))
        self._refresh()
        self.save()

    def _result(self, app, c):
        ctl = self.ctl.get(c["id"]) or {"id": c["id"], "aspect": c["aspect"], "severity": "medium"}
        st = c["state"]
        sev = c["severity"] if st in GAP and c.get("severity") else ctl.get("severity", "medium")
        need = (ctl.get("applies") or {}).get("needs")
        return dict(c, app=app, key="%s::%s" % (app, c["id"]), ctl=ctl, sev=sev, high=sev in HIGH,
                    possible=st == "ISSUE" and c.get("confirmed") is False,
                    not_seen=st == "UNKNOWN" and bool(ctl.get("usually_outside")) and c["summary"].startswith("Not seen in the repository"),
                    need_na=st == "NOT_APPLICABLE" and bool(need) and c["summary"] == A.NEED_TEXT.get(need),
                    order=(A.SEVERITY_ORDER.get(sev, 9), self.asp_order.get(c["aspect"], 99), self.ctl_order.get(c["id"], 999), app))

    def _prior(self):
        """Marks from earlier runs of the same workspace (latest wins per application and control), and the stop-rule firings an
        earlier review of the same scope left incomplete: a re-run does not clear them (8.5)."""
        marks, firings = {}, []
        runs = os.path.join(self.ws, "runs") if self.ws else None
        me = os.path.basename(self.run_dir)
        for name in sorted(os.listdir(runs)) if runs and os.path.isdir(runs) else []:
            p = os.path.join(runs, name, FILE)
            if name >= me or not os.path.isfile(p):
                continue
            d = _read(p)
            for k, o in d.get("outcomes", {}).items():
                marks[k] = dict(o, run=name)
            if sorted(d["scope"]["apps"]) == self.scope:
                firings = [dict(f, from_run=f.get("from_run") or name, cleared=False) for f in d.get("firings", []) + d.get("carried_firings", [])
                           if not f.get("cleared")]
        return marks, firings

    def _carry_forward(self):
        for key, r in self.results.items():
            m = self.prior.get(key)
            if not m or m["outcome"] != "confirmed" or not same_binding(m.get("binding"), self.binding(key)):
                continue
            src = m.get("carried_from") or {"run": m["run"], "at": m["at"]}  # the date of the confirmation itself, however often carried
            self.doc["outcomes"][key] = dict({k: v for k, v in m.items() if k not in ("run", "seconds")}, mode="carried", carried_from=src, binding=self.binding(key))

    # ----- binding (8.7) -----
    def _context(self, app):
        if app not in self._cx:
            d = os.path.join(self.out, app)
            rd = lambda n: _read(os.path.join(d, n)) if os.path.isfile(os.path.join(d, n)) else None  # noqa: E731
            self._cx[app] = (A.Context(app, rd("discovery.json") or {}, rd("relationships.json"), rd("resilience.json"), rd("safetynet.json"),
                                       rd("dimensions.json"), _read(os.path.join(self.out, "portfolio", "relationships.json"))),
                             rd("discovery.json") or {}, rd("relationships.json") or {}, rd("resilience.json") or {}, rd("safetynet.json") or {},
                             rd("dimensions.json") or {})
        return self._cx[app]

    def detectors(self, app, ctl):
        """The versions of the detectors and engine steps a control's answer depends on."""
        cx, disc, rel, res, sn, dims = self._context(app)
        ver = {d["id"]: d["version"] for d in (disc.get("run_meta") or {}).get("detectors") or []}
        tool = self.man.get("tool") or {}
        ver["relationships"] = "%s/%s" % ((rel.get("meta") or {}).get("extractor_version"), tool.get("resolver"))
        ver["safetynet"], ver["availability"], ver["dimensions"] = sn.get("version"), res.get("version"), dims.get("contract")
        return {n: ver.get(n) for n in sorted(A.reads(ctl, cx))}

    def _view(self, app):
        """The repository as it was at the run (verify's own reader: the working tree if unchanged, else an export of the commit)."""
        if app not in self._views:
            x = next(m for m in self.man["applications"] if m["app"] == app)
            src = next((s for s in self.run.get("sources") or [] if s.get("path") and os.path.abspath(s["path"]) == os.path.abspath(x.get("repo") or "")), None)
            d, tmp, _why = V.source_view(x.get("repo"), x.get("inventory_fingerprint"), src)
            if tmp:
                self._temps.append(tmp)
            self._views[app] = d
        return self._views[app]

    def _area_files(self, app):
        if app not in self._areas:
            view = self._view(app)
            if not view:
                self._areas[app] = None
            else:
                from detectors import Ctx  # engine
                from detectors.scope import _areas  # engine: the same areas the scan's search records name
                cx = Ctx(view)
                self._areas[app] = dict(_areas(cx), all=cx.files, _root=view)
        return self._areas[app]

    def scope_hash(self, r):
        """A content hash of the files in the control's search scope, over redacted text only. None when the files cannot be read
        as they were at the run (such a mark never carries forward)."""
        ar = self._area_files(r["app"])
        if ar is None:
            return None
        ctl = r["ctl"]
        spec = ctl.get("search") or A.NEED_SEARCH.get((ctl.get("applies") or {}).get("needs")) or {}
        areas = [w["area"] for w in (r.get("searched") or {}).get("in") or []] or spec.get("in") or ["all"]
        root, files = ar["_root"], set()
        for a in areas:
            if a == "repo":
                files |= {n for n in spec.get("names") or [] if os.path.isfile(os.path.join(root, n))} if spec.get("names") else set(ar["all"])
            else:
                files |= set(ar.get(a) or [])
        h = hashlib.sha256()
        for f in sorted(files):
            lines = evidence.read_lines(root, f)
            h.update(("%s\0%s\n" % (f, _sha(evidence.redact("\n".join(lines))) if lines is not None else "unreadable")).encode())
        return h.hexdigest()

    def binding(self, key):
        r = self.results[key]
        ctl, st = r["ctl"], r["state"]
        keys = [[p["id"], sorted((p.get("controls") or {}).get(ctl["id"]) or (p.get("aspects") or {}).get(ctl.get("aspect")) or [])] for p in self.packs]
        b = {"definition": evidence.canonical_hash({"severity": ctl.get("severity"), "search": ctl.get("search"), "remedies": keys}),
             "detectors": self.detectors(r["app"], ctl), "state": st,
             "remedies": sorted("%s:%s" % (x.get("pack"), x.get("key")) for x in r.get("remedies") or [])}
        if st in ("PRESENT", "PARTIAL", "ISSUE"):
            ev = [[e.get("kind"), e.get("path"), e.get("line_start"), e.get("line_end"), e.get("snippet"), e.get("cmd")] for e in r.get("evidence") or []]
            b["evidence"] = evidence.canonical_hash(evidence.redact_tree(ev))
        # a "not there" result rests on the files searched; so does a pass that cites nothing (a negative scan): conservative
        if st in ("ABSENT", "UNKNOWN", "NOT_APPLICABLE", "PARTIAL") or (st == "PRESENT" and not r.get("evidence")):
            b["scope"] = self.scope_hash(r)
        return b

    # ----- what must be reviewed -----
    def _refresh(self):
        self.firings_all = self._firings() + self.doc.get("carried_firings", [])
        ctls = {c for f in self.firings_all for c in f["controls"]}
        self.item6 = {k for k, r in self.results.items() if r["id"] in ctls and r["state"] != "NOT_ASSESSED"}
        for f in self.firings_all:  # cleared once every result of its controls was reviewed one by one, and the raised audit is done
            keys = [k for k in self.item6 if self.results[k]["id"] in f["controls"]]
            f["cleared"] = all(self.resolved(k) for k in keys) and (not self.doc.get("auditor") or not self.audit_pending())
        self.doc["firings"] = [f for f in self.firings_all if not f.get("from_run")]
        self.doc["carried_firings"] = [f for f in self.firings_all if f.get("from_run")]

    def expired(self, o, at=None):
        return o["outcome"] != "confirmed" and (at or now()) - parse(o["at"]) > datetime.timedelta(days=EXPIRY_DAYS)

    def earlier(self, key):
        """The outcome other than Confirmed this result carried before: from an earlier run, or expired in this review (8.2 item 5)."""
        o = self.doc["outcomes"].get(key)
        if o and self.expired(o):
            return dict(o, run=self.doc["run"])
        m = self.prior.get(key)
        return m if m and m["outcome"] != "confirmed" else None

    def reasons(self, key):
        r = self.results[key]
        st, out = r["state"], []
        if st == "ISSUE" and not r["possible"]:
            out.append(1)
        if st in ("ABSENT", "PARTIAL"):
            out.append(2)
        if r["high"] and (st == "UNKNOWN" or r["need_na"]):
            out.append(3)
        if r["high"] and st == "PRESENT" and r.get("level") not in ("enforced", "verified"):
            out.append(4)
        if self.earlier(key):
            out.append(5)
        if key in self.item6:
            out.append(6)
        if st == "UNKNOWN" and 3 not in out:
            out.append(7)
        return out

    def resolved(self, key):
        o = self.doc["outcomes"].get(key)
        if not o or self.expired(o):
            return False
        return key not in self.item6 or o["mode"] == "individual"

    def must(self):
        return sorted((k for k in self.results if self.reasons(k)), key=lambda k: self.results[k]["order"])

    def bulkable(self, key):
        r = self.results[key]
        return r["state"] in ("PRESENT", "NOT_APPLICABLE") and not self.reasons(key)

    def bulk_screens(self):
        """One screen per application and aspect: its PRESENT and NOT_APPLICABLE results outside the must-review set."""
        by = {}
        for k in sorted(self.results, key=lambda k: self.results[k]["order"]):
            if self.bulkable(k):
                r = self.results[k]
                by.setdefault((r["app"], r["aspect"]), []).append(k)
        return [{"app": a, "aspect": s, "title": self.asp_title.get(s, s), "keys": ks, "open": [k for k in ks if k not in self.doc["outcomes"]]}
                for (a, s), ks in sorted(by.items(), key=lambda x: (self.asp_order.get(x[0][1], 99), x[0][0]))]

    def optional(self):
        """Possible issues: never in the client file unless reviewed one by one, and never confirmable in bulk."""
        return sorted((k for k, r in self.results.items() if r["possible"] and not self.reasons(k)), key=lambda k: self.results[k]["order"])

    # ----- the audit sample (8.3) -----
    def audit_population(self):
        return sorted(k for k, o in self.doc["outcomes"].items() if o["mode"] in ("aspect", "carried") and k in self.results)

    def audit_order(self):
        seed = self.doc["seed"]
        return sorted(self.audit_population(), key=lambda k: (_sha("%s:%s" % (seed, k)), k))  # extended, never redrawn

    def audit_size(self):
        pop = self.audit_population()
        if not pop:
            return 0
        rate = 0.25 if self.firings_all else 0.10
        return min(len(pop), max(5, math.ceil(rate * len(pop))) * 2 ** self.doc.get("audit_doublings", 0))

    def audit_pending(self):
        return [k for k in self.audit_order()[:self.audit_size()] if k not in self.doc["audit"]]

    # ----- the stop rule (8.5) -----
    def _firings(self):
        seq = [e for e in self.doc["log"] if e["kind"] in ("individual", "audit")]
        out, start = [], 0
        for i in range(len(seq)):
            win = seq[max(start, i - WINDOW + 1):i + 1]
            hits = [e for e in win if e.get("tool_error")]
            if len(hits) > LIMIT:
                out.append({"at": seq[i]["at"], "controls": sorted({e["control"] for e in hits}), "outcomes": [e["key"] for e in hits], "window": len(win)})
                start = i + 1  # the next firing needs new outcomes
        return out

    def tool_error(self, r, rec):
        """Decided by the change, not by the outcome or the reason picked (8.4)."""
        o, st = rec["outcome"], r["state"]
        if o == "confirmed":
            return False
        if st == "UNKNOWN" and r["ctl"].get("usually_outside"):
            return False  # the tool could not see it by design
        if st in ("PRESENT", "NOT_APPLICABLE") and (o == "gap_stated" or (o in ("corrected", "team_stated") and rec.get("state") in GAP)):
            return True
        return REASONS.get(rec.get("reason"), ("", False))[1]

    # ----- recording -----
    def _mark(self, key, e, reviewer, at, seconds, mode):
        if key not in self.results:
            raise Refused("%s is not a result in this review's scope" % key)
        r, o = self.results[key], e.get("outcome")
        st = r["state"]
        if o not in OUTCOMES:
            raise Refused("outcome must be one of %s" % ", ".join(OUTCOMES))
        if e.get("reason") and e["reason"] not in REASONS:
            raise Refused("reason must be one of %s" % ", ".join(REASONS))
        if o == "corrected" and (e.get("state") not in A.STATES or not e.get("reason")):
            raise Refused("a correction needs one of the seven states and a reason")
        if o == "gap_stated" and st not in ("PRESENT", "NOT_APPLICABLE", "UNKNOWN"):
            raise Refused("a gap is stated only on a result the tool shows in place or undecided")
        if o == "disputed" and (st not in GAP or not e.get("reason")):
            raise Refused("a dispute is recorded on a gap, with a reason")
        if o == "team_stated" and (st != "UNKNOWN" or not e.get("answer") or not e.get("who") or e.get("state") not in A.STATES):
            raise Refused("a team statement is recorded on an undecided or not-seen result, with the answer, who stated it and the state it means")
        if e.get("reason") == "other" and not e.get("note"):
            raise Refused("the reason 'other' needs a note")
        if o == "confirmed" and r["state"] == "NOT_ASSESSED":
            raise Refused("a result that was not checked cannot be confirmed")
        rec = {"outcome": o, "tool_state": st, "reviewer": reviewer, "at": iso(at), "seconds": round(float(seconds or 0), 1), "mode": mode}
        for f in ("state", "reason", "note", "answer", "who", "evidence"):
            if e.get(f):
                rec[f] = evidence.redact(str(e[f]))[:2000]  # redacted at write (8.8): a pasted token never reaches review.json
        if o == "confirmed" and st in GAP:
            rec["remedy_confirmed"] = bool(e.get("remedy_confirmed"))
        rec["tool_error"] = self.tool_error(r, rec)
        rec["binding"] = self.binding(key)
        return rec

    def _need_reviewer(self, who):
        if not who:
            raise Refused("no reviewer named (--reviewer)")

    def record(self, e, at=None, seconds=0):
        """One individually reviewed result."""
        self._need_reviewer(self.reviewer)
        at = at or now()
        key = e.get("key") or "%s::%s" % (e.get("app"), e.get("control"))
        rec = self._mark(key, e, self.reviewer, at, seconds, "individual")
        self.doc["outcomes"][key] = rec
        self.doc["audit"].pop(key, None)
        self.doc["log"].append({"kind": "individual", "key": key, "control": self.results[key]["id"], "outcome": rec["outcome"], "tool_error": rec["tool_error"],
                                "reviewer": self.reviewer, "at": rec["at"], "seconds": rec["seconds"]})
        return self._done(rec)

    def bulk(self, app, aspect, keys=None, at=None, seconds=0):
        """Confirm one application's aspect screen: only PRESENT and NOT_APPLICABLE results outside the must-review set."""
        self._need_reviewer(self.reviewer)
        at = at or now()
        scr = next((s for s in self.bulk_screens() if s["app"] == app and s["aspect"] == aspect), None)
        keys = list(keys) if keys is not None else (scr["open"] if scr else [])
        bad = [k for k in keys if k not in self.results or not self.bulkable(k)]
        if bad:
            raise Refused("not confirmable in bulk (must be reviewed one by one): %s" % ", ".join(bad))
        if not keys:
            raise Refused("nothing to confirm in bulk for %s / %s" % (app, aspect))
        for k in keys:
            self.doc["outcomes"][k] = self._mark(k, {"outcome": "confirmed"}, self.reviewer, at, 0, "aspect")
        self.doc["bulk_screens"].append({"app": app, "aspect": aspect, "count": len(keys), "reviewer": self.reviewer, "at": iso(at), "seconds": round(float(seconds or 0), 1)})
        self.doc["log"].append({"kind": "bulk", "keys": keys, "app": app, "aspect": aspect, "reviewer": self.reviewer, "at": iso(at), "seconds": round(float(seconds or 0), 1)})
        return self._done({"confirmed": len(keys)})

    def audit(self, e, at=None, seconds=0):
        """The second person's check of one sampled bulk-confirmed or carried-forward result. Anything but Confirmed reverts every
        bulk confirmation of that aspect and application to "Not reviewed" and doubles the sample."""
        who = self.doc.get("auditor")
        if not who:
            raise Refused("no auditor named (--auditor): the audit sample is presented to a second person")
        at = at or now()
        key = e.get("key") or "%s::%s" % (e.get("app"), e.get("control"))
        if key not in self.audit_order()[:self.audit_size()]:
            raise Refused("%s is not in the audit sample" % key)
        rec = self._mark(key, e, who, at, seconds, "individual")
        self.doc["audit"][key] = rec
        self.doc["log"].append({"kind": "audit", "key": key, "control": self.results[key]["id"], "outcome": rec["outcome"], "tool_error": rec["tool_error"],
                                "reviewer": who, "at": rec["at"], "seconds": rec["seconds"]})
        if rec["outcome"] != "confirmed":
            r = self.results[key]
            gone = [k for k, o in self.doc["outcomes"].items() if k != key and o["mode"] in ("aspect", "carried")
                    and self.results.get(k, {}).get("app") == r["app"] and self.results[k]["aspect"] == r["aspect"]]
            for k in gone:
                del self.doc["outcomes"][k]
                self.doc["audit"].pop(k, None)
            self.doc["outcomes"][key] = rec
            self.doc["audit_doublings"] = self.doc.get("audit_doublings", 0) + 1
            self.doc["log"].append({"kind": "revert", "keys": sorted(gone), "app": r["app"], "aspect": r["aspect"], "at": rec["at"], "reviewer": who})
        return self._done(rec)

    def _done(self, res):
        self._refresh()
        self.save()
        return res

    # ----- reading the state -----
    def plan(self):
        """Effort projected by item counts: must-review items and bulk screens, at the measured mean time when there is one."""
        t_item, t_screen = self.measured()
        per = {}
        must = self.must()
        for a in self.scope:
            n = sum(1 for k in must if self.results[k]["app"] == a and not self.resolved(k))
            s = sum(1 for x in self.bulk_screens() if x["app"] == a and x["open"])
            per[a] = (n * t_item + s * t_screen) / 60.0
        return {"per_app": {a: round(m) for a, m in per.items()}, "projected_min": round(sum(per.values())), "seconds_per_item": t_item, "seconds_per_screen": t_screen}

    def measured(self):
        """Mean seconds per individually reviewed item and per bulk screen across this workspace's reviews; the 8.1 assumption until
        there are enough of them."""
        items, screens = [], []
        runs = os.path.join(self.ws, "runs") if self.ws else None
        me = os.path.basename(self.run_dir)
        docs = [_read(os.path.join(runs, n, FILE)) for n in sorted(os.listdir(runs)) if n != me and os.path.isfile(os.path.join(runs, n, FILE))] if runs and os.path.isdir(runs) else []
        for d in docs + [self.doc]:
            items += [e["seconds"] for e in d.get("log", []) if e["kind"] in ("individual", "audit") and e.get("seconds")]
            screens += [s["seconds"] for s in d.get("bulk_screens", []) if s.get("seconds")]
        return (sum(items) / len(items) if len(items) >= 10 else DEFAULT_ITEM_S), (sum(screens) / len(screens) if len(screens) >= 3 else DEFAULT_ITEM_S)

    def blockers(self):
        """Why a client file cannot be produced now (8.5, D-7b). Unreviewed must-review items are not a blocker: those
        applications show "Not yet reviewed"."""
        out = []
        for f in self.firings_all:
            if not f["cleared"]:
                left = [k for k in self.item6 if self.results[k]["id"] in f["controls"] and not self.resolved(k)]
                out.append("stop-rule escalation incomplete (%s): %d result(s) still to review one by one%s" % (
                    ", ".join(f["controls"]), len(left), "; audit sample incomplete" if self.doc.get("auditor") and self.audit_pending() else ""))
        if self.doc.get("first_meeting") and (not self.doc.get("auditor") or self.audit_pending()):
            out.append("a first client meeting needs the audit sample completed by a second person (--auditor)")
        return out

    def audited(self):
        return bool(self.doc.get("auditor") and self.doc["audit"] and not self.audit_pending())

    def backlog(self):
        """Tool errors, for synthetic fixtures (8.4): stored in the client workspace only, never with client code."""
        out = []
        for k, o in sorted(self.doc["outcomes"].items()):  # an audit disagreement becomes the result's outcome, so it is here too
            if o.get("tool_error"):
                r = self.results.get(k) or {}
                out.append({"run": self.doc["run"], "app": r.get("app"), "control": r.get("id"), "tool_state": o["tool_state"], "outcome": o["outcome"],
                            "state": o.get("state"), "reason": o.get("reason"), "note": o.get("note"), "reviewer": o["reviewer"], "at": o["at"]})
        return sorted(out, key=lambda b: (b["at"], b["app"] or "", b["control"] or ""))

    def must_extra(self):
        """What verify cannot see from the states alone: results made must-review by history (item 5) or by the stop rule (item 6,
        which needs a one-by-one outcome)."""
        return {k: ("individual" if k in self.item6 else "any") for k in self.results if set(self.reasons(k)) & {5, 6}}

    def save(self):
        self.doc["updated_at"] = iso(now())
        self.doc["must_extra"] = self.must_extra()
        atomic_write(self.path, json.dumps(evidence.redact_tree(self.doc), indent=1, sort_keys=True))
        if self.ws:
            bl = self.backlog()
            d = os.path.join(self.ws, "backlog")
            p = os.path.join(d, "%s.json" % self.doc["run"])
            if bl or os.path.isfile(p):
                os.makedirs(d, exist_ok=True)
                atomic_write(p, json.dumps(evidence.redact_tree({"contract": "app-insight-backlog.v1", "run": self.doc["run"], "items": bl}), indent=1, sort_keys=True))

    def item(self, key):
        """One result as the page shows it: the stored (already redacted) summary, evidence lines, search record and remedies."""
        r = self.results[key]
        o = self.doc["outcomes"].get(key)
        e = self.earlier(key)
        return {"key": key, "app": r["app"], "control": r["id"], "title": r["title"], "aspect": self.asp_title.get(r["aspect"], r["aspect"]),
                "state": r["state"], "label": "Possible issue" if r["possible"] else "Not seen here" if r["not_seen"] else STATE_LABEL.get(r["state"], r["state"]),
                "severity": r["sev"], "level": r.get("level"), "summary": r["summary"], "evidence": r.get("evidence") or [], "searched": r.get("searched"),
                "remedies": r.get("remedies") or [], "reference": r.get("reference"), "why": [ITEM[i] for i in self.reasons(key)],
                "gap": r["state"] in GAP, "undecided": r["state"] == "UNKNOWN", "usually_outside": bool(r["ctl"].get("usually_outside")),
                "outcome": o and {k: v for k, v in o.items() if k != "binding"}, "mode": o and mark_text(o),
                "earlier": e and {k: e.get(k) for k in ("outcome", "state", "reason", "note", "answer", "reviewer", "at", "run")}}

    def state(self):
        must = self.must()
        scr = self.bulk_screens()
        return {"run": self.doc["run"], "scope": self.doc["scope"], "reviewer": self.reviewer, "auditor": self.doc.get("auditor"), "first_meeting": self.doc.get("first_meeting"),
                "must": [{"key": k, "done": self.resolved(k)} for k in must], "optional": [{"key": k, "done": k in self.doc["outcomes"]} for k in self.optional()],
                "screens": [{"app": s["app"], "aspect": s["aspect"], "title": s["title"], "keys": s["keys"], "open": len(s["open"])} for s in scr],
                "audit": self.audit_pending() if self.doc.get("auditor") else [], "audit_size": self.audit_size(),
                "firings": self.firings_all, "blockers": self.blockers(), "plan": self.plan(), "reasons": {k: v[0] for k, v in REASONS.items()},
                "states": {s: STATE_LABEL[s] for s in A.STATES}, "published": self.doc.get("published")}


def same_binding(a, b):
    """Carried forward only when every bound term is unchanged, and a term that could not be computed never matches."""
    return bool(a) and bool(b) and a == b and ("scope" not in b or b["scope"] is not None)


def apply_file(rv, path):
    """`review --record`: apply outcomes from a JSON file through the same functions the page uses. Entries are
    {app, control, outcome, ...}, {bulk: <aspect>, app}, or {audit: true, app, control, outcome, ...}."""
    doc = _read(path)
    entries = doc.get("outcomes", []) if isinstance(doc, dict) else doc
    done = []
    for e in entries:
        if e.get("bulk"):
            done.append(("bulk", rv.bulk(e["app"], e["bulk"], e.get("keys"), seconds=e.get("seconds", 0))))
        elif e.get("audit"):
            done.append(("audit", rv.audit(e, seconds=e.get("seconds", 0))))
        else:
            done.append(("individual", rv.record(e, seconds=e.get("seconds", 0))))
    return done


def print_state(rv, out=None):
    import sys
    out = out or sys.stdout
    st = rv.state()
    must = st["must"]
    print("━━ APP-INSIGHT-REVIEW ━━", file=out)
    print("run:           %s (%s)" % (st["run"], rv.run.get("client")), file=out)
    print("scope:         %d application(s), chosen by the %s; %d analysed applications not in this review" % (
        len(st["scope"]["apps"]), st["scope"]["chosen_by"], len(rv.docs) - len(st["scope"]["apps"])), file=out)
    print("reviewers:     %s; second person: %s" % (", ".join(rv.doc["reviewers"]) or "-", rv.doc.get("auditor") or "none"), file=out)
    print("must-review:   %d of %d resolved" % (sum(1 for m in must if m["done"]), len(must)), file=out)
    print("bulk screens:  %d of %d confirmed" % (sum(1 for s in st["screens"] if not s["open"]), len(st["screens"])), file=out)
    print("audit sample:  %d of %d pending%s" % (len(rv.audit_pending()), st["audit_size"], "" if rv.doc.get("auditor") else " (no second person named)"), file=out)
    print("effort:        %d min projected for what is left (%.0f s per item, %.0f s per bulk screen)" % (st["plan"]["projected_min"], st["plan"]["seconds_per_item"], st["plan"]["seconds_per_screen"]), file=out)
    for f in st["firings"]:
        print("stop rule:     fired %s on %s%s; %s" % (f["at"][:10], ", ".join(f["controls"]), " (carried from run %s)" % f["from_run"] if f.get("from_run") else "",
                                                     "cleared" if f["cleared"] else "escalation incomplete"), file=out)
    for b in st["blockers"]:
        print("client file:   refused: %s" % b, file=out)
    if st["published"]:
        print("client file:   %s (%s)" % (st["published"]["file"], st["published"]["at"]), file=out)
    print("━━ END ━━", file=out)
