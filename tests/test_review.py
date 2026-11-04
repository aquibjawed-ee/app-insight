"""Phase 2: consultant review and the client file (design 8, T-2.1, T-2.2, T-2.3, T-2.3b). One test per scenario of
specs/accuracy-assurance (from "A review covers a named set of applications" to "Disputes become synthetic fixtures") and of
specs/report-experience "An internal report and a separate client file", plus the review page's security, the lock,
carry-forward and verify of the client file. Fixture secrets are obviously fake."""
import contextlib
import datetime
import http.client
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(1, os.path.join(HERE, "..", "engine", "tests"))
os.environ["DISCOVERY_FIXED_TIME"] = "2026-10-29T00:00:00Z"

from app_insight import aspects as A  # noqa: E402
from app_insight import cli  # noqa: E402
from app_insight import client_file as CF  # noqa: E402
from app_insight import report as R  # noqa: E402
from app_insight import review as RV  # noqa: E402
from app_insight import review_page as RP  # noqa: E402
from app_insight import sanitise as SAN  # noqa: E402
from app_insight import verify as V  # noqa: E402
import graph_fixtures as F  # noqa: E402

FAKE = "Fake-Pass-0000-xyz"  # an obviously fake value, planted only in a throwaway fixture repository
APPS = ["billing-service", "inventory-service", "notifier-a", "orders-service"]
HOOK = "https://hooks.slack.com/services/T0000FAKE/B0000FAKE/FAKEFAKEFAKEFAKEFAKE0000"


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()) as o, contextlib.redirect_stderr(io.StringIO()) as e:
        rc = fn(*a, **k)
    return rc, o.getvalue() + e.getvalue()


def scan(repos, ws, client="c"):
    rc, _ = quiet(cli.main, ["scan", "--client", client, "--workspace", ws, "--json"] + sorted(repos))
    assert rc == 0, rc
    return cli.resolve_run(os.path.join(ws, client))


def copies(base, *names):
    """A fresh client workspace holding copies of one scanned run under the given run names (oldest first)."""
    ws = tempfile.mkdtemp(prefix="rvws-")
    os.makedirs(os.path.join(ws, "runs"))
    for n in names:
        shutil.copytree(base, os.path.join(ws, "runs", n), ignore=shutil.ignore_patterns("review.json", "review.lock", "report-client*", "client-verify.json"))
    return [os.path.join(ws, "runs", n) for n in names]


def at(days=0):
    return RV.now() + datetime.timedelta(days=days)


def confirm_all(rv, skip=(), only_app=None):
    for k in rv.must():
        if k not in skip and (only_app is None or rv.results[k]["app"] == only_app) and not rv.resolved(k):
            rv.record({"key": k, "outcome": "confirmed"}, seconds=30)
    for s in rv.bulk_screens():
        keys = [k for k in s["open"] if k not in skip]
        if keys and (only_app is None or s["app"] == only_app):
            rv.bulk(s["app"], s["aspect"], keys, seconds=20)


def text_of(path):
    import html
    import re
    t = open(path, encoding="utf-8").read()
    return html.unescape(re.sub(r"<[^>]+>", " ", t[t.find("<body"):]))


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, repos = F.make_portfolio(names=APPS)
        cls.repos = repos
        cfg = os.path.join(repos["orders-service"], "src", "main", "resources", "secret.properties")
        os.makedirs(os.path.dirname(cfg), exist_ok=True)
        with open(cfg, "w") as fh:
            fh.write("vault.password=%s\n" % FAKE)
        cls.base = scan(repos.values(), tempfile.mkdtemp(prefix="ws-"))

    def review(self, run=None, apps=APPS, **kw):
        run = run or copies(self.base, "20261101-000000")[0]
        kw.setdefault("budget", 500)
        kw.setdefault("seed", 3)
        rv = RV.Review(run, apps, kw.pop("chosen_by", "consultant"), kw.pop("reviewer", "Rev One"), **kw)
        self.addCleanup(rv.close)
        return rv

    def key(self, rv, app, ctl):
        k = "%s::%s" % (app, ctl)
        self.assertIn(k, rv.results)
        return k


class ScopeTest(Base):
    """A review covers a named set of applications, within a budget."""

    def test_a_scope_over_budget_is_refused_and_no_must_review_item_is_dropped(self):
        run = copies(self.base, "20261101-000000")[0]
        with self.assertRaises(RV.Refused) as e:
            RV.Review(run, APPS, "consultant", "Rev One", budget=10)
        self.assertIn("reduce the scope", str(e.exception))
        self.assertIn("must-review items are never dropped", str(e.exception))
        self.assertFalse(os.path.exists(os.path.join(run, "review.json")))
        self.assertFalse(os.path.exists(os.path.join(run, "review.lock")))
        rv = self.review(run)  # within budget: every result the rules select is in the must-review set, uncapped
        rules = [k for k, r in rv.results.items() if r["state"] in ("ABSENT", "PARTIAL", "UNKNOWN") or (r["state"] == "ISSUE" and not r["possible"])]
        self.assertTrue(set(rules) <= set(rv.must()))
        p = rv.plan()
        self.assertEqual(sorted(p["per_app"]), APPS)
        self.assertEqual(p["seconds_per_item"], RV.DEFAULT_ITEM_S)

    def test_a_first_meeting_scope_chosen_by_the_client_lists_the_others_once(self):
        rv = self.review(apps=["billing-service", "notifier-a"], chosen_by="client")
        confirm_all(rv)
        res = CF.publish(rv)
        self.assertTrue(res["ok"], res)
        t = text_of(res["path"])
        self.assertIn("chosen by: client", t)
        self.assertIn("Not in this review: 2 application(s)", t)
        html = open(res["path"]).read()
        for app in ("inventory-service", "orders-service"):  # listed once; no row, no section, no result of its own
            self.assertEqual(html.count('data-oos="%s"' % app), 1)
            self.assertNotIn('data-app="%s"' % app, html)
            self.assertNotIn("%s::" % app, html)
        self.assertIn("2 of 2 applications in scope shown; 0 not yet reviewed; 0 not available", t)

    def test_time_is_recorded_per_item_and_per_bulk_screen_and_replaces_the_assumption(self):
        rv = self.review()
        confirm_all(rv)
        self.assertTrue(all(e["seconds"] == 30 for e in rv.doc["log"] if e["kind"] == "individual"))
        self.assertTrue(rv.doc["bulk_screens"] and all(s["seconds"] == 20 for s in rv.doc["bulk_screens"]))
        self.assertEqual(rv.measured(), (30, 20))


class MustReviewTest(Base):
    """Must-review results are reviewed one by one."""

    def test_must_review_order_is_severity_aspect_control_application(self):
        rv = self.review()
        m = rv.must()
        self.assertEqual(m, sorted(m, key=lambda k: rv.results[k]["order"]))
        self.assertEqual(rv.results[m[0]]["sev"], "high")
        for k in m:
            with self.assertRaises(RV.Refused):
                rv.bulk(rv.results[k]["app"], rv.results[k]["aspect"], [k])

    def test_a_known_false_pass_after_expiry_is_presented_with_last_months_outcome(self):
        old, new = copies(self.base, "20261001-000000", "20261101-000000")
        rv = self.review(old)
        k = self.key(rv, "orders-service", "testing.integration")  # a medium result the tool shows in place
        self.assertTrue(rv.bulkable(k))
        rv.record({"key": k, "outcome": "gap_stated", "note": "only one of three clients has them"}, at=at(-30))
        rv.close()
        rv2 = self.review(new)
        self.assertIn(5, rv2.reasons(k))
        self.assertFalse(rv2.bulkable(k))
        self.assertIn(k, rv2.must())
        e = rv2.item(k)["earlier"]
        self.assertEqual((e["outcome"], e["note"], e["reviewer"], e["run"]), ("gap_stated", "only one of three clients has them", "Rev One", "20261001-000000"))
        with self.assertRaises(RV.Refused):
            rv2.bulk("orders-service", "testing", [k])

    def test_an_outcome_other_than_confirmed_expires_after_90_days(self):
        rv = self.review()
        k = self.key(rv, "orders-service", "delivery.deploy")
        rv.record({"key": k, "outcome": "disputed", "reason": "outside_repo"}, at=at(-91))
        self.assertFalse(rv.resolved(k))
        self.assertIn(5, rv.reasons(k))
        rv.record({"key": k, "outcome": "confirmed"}, at=at(-200))
        self.assertTrue(rv.resolved(k))  # a confirmation does not expire

    def test_possible_issues_are_left_out_of_the_client_file_unless_reviewed(self):
        rv = self.review(apps=["billing-service"])
        k = next(k for k, r in rv.results.items() if r["state"] == "ISSUE")
        rv.results[k]["possible"] = True  # a heuristic match (none of today's detectors makes one)
        self.assertNotIn(k, rv.must())
        self.assertIn(k, rv.optional())
        confirm_all(rv)
        m = CF.model(rv)
        keys = [d["key"] for a in m["apps"] for x in a.get("aspects", []) for d in x["results"]]
        self.assertNotIn(k, keys)
        self.assertEqual(m["not_looked_at"]["possible_issues"], 1)


class BulkAuditTest(Base):
    """Bulk confirmation is limited, recorded and audited."""

    def test_an_audit_sample_disagreement_reverts_the_aspect_and_doubles_the_sample(self):
        rv = self.review(auditor="Second Person")
        confirm_all(rv)
        size = rv.audit_size()
        k = next(k for k in rv.audit_order()[:size] if sum(1 for s in rv.bulk_screens() for x in s["keys"]
                                                          if x == k and len(s["keys"]) > 1))
        r = rv.results[k]
        same = [x for x, o in rv.doc["outcomes"].items() if o["mode"] == "aspect" and rv.results[x]["app"] == r["app"] and rv.results[x]["aspect"] == r["aspect"]]
        self.assertGreater(len(same), 1)
        rv.audit({"key": k, "outcome": "gap_stated", "note": "the endpoint is not exposed"})
        for x in same:
            if x != k:
                self.assertNotIn(x, rv.doc["outcomes"])  # back to "Not reviewed"
        self.assertEqual(rv.doc["outcomes"][k]["outcome"], "gap_stated")
        self.assertEqual(rv.doc["audit_doublings"], 1)
        self.assertEqual(rv.audit_size(), min(len(rv.audit_population()), max(5, -(-len(rv.audit_population()) // 10)) * 2))

    def test_a_small_bulk_population_gives_a_sample_of_five(self):
        rv = self.review()
        keys = [k for s in rv.bulk_screens() for k in s["keys"]][:12]
        for s in rv.bulk_screens():
            ks = [k for k in s["keys"] if k in keys]
            if ks:
                rv.bulk(s["app"], s["aspect"], ks)
        self.assertEqual(len(rv.audit_population()), 12)
        self.assertEqual(rv.audit_size(), 5)

    def test_the_sample_is_seeded_and_extended_in_the_same_order(self):
        rv = self.review()
        confirm_all(rv)
        order = rv.audit_order()
        self.assertEqual(rv.doc["seed"], 3)
        rv.doc["audit_doublings"] = 1
        self.assertEqual(rv.audit_order()[:rv.audit_size()][:5], order[:5])

    def test_confirmation_mode_is_shown(self):
        rv = self.review(apps=["billing-service"])
        confirm_all(rv)
        res = CF.publish(rv)
        self.assertTrue(res["ok"], res)
        t = text_of(res["path"])
        self.assertIn("(confirmed with its aspect)", t)
        self.assertIn("(checked individually)", t)

    def test_a_first_meeting_needs_the_audit_by_a_second_person(self):
        rv = self.review(apps=["billing-service"], first_meeting=True)
        confirm_all(rv)
        res = CF.publish(rv)
        self.assertFalse(res["ok"])
        self.assertTrue(any("second person" in r for r in res["refused"]))
        self.assertFalse(os.path.exists(os.path.join(rv.run_dir, CF.NAME)))
        with self.assertRaises(RV.Refused):
            RV.Review(rv.run_dir, ["billing-service"], "consultant", "Rev One", auditor="Rev One")


class OutcomeTest(Base):
    """Every review situation has an outcome."""

    def test_right_state_wrong_evidence(self):
        rv = self.review(apps=["orders-service"])
        k = self.key(rv, "orders-service", "testing.integration")
        rv.record({"key": k, "outcome": "corrected", "state": "PRESENT", "reason": "test_or_copy", "note": "the real suite is under it/"})
        confirm_all(rv)
        d = self._shown(rv, k)
        self.assertEqual((d["text"], d["reason"]), ("Corrected by the consultant: In place", "evidence is a test or a copy"))
        self.assertTrue(rv.doc["outcomes"][k]["tool_error"])

    def test_truth_unknown_before_the_meeting(self):
        rv = self.review(apps=["orders-service"])
        k = self.key(rv, "orders-service", "runtime.http_timeouts")
        self.assertEqual(rv.results[k]["sev"], "high")
        rv.record({"key": k, "outcome": "cannot_confirm"})
        self.assertTrue(rv.resolved(k))
        confirm_all(rv)
        m = CF.model(rv)
        a = next(x for x in m["apps"] if x["app"] == "orders-service")
        d = self._shown(rv, k, m)
        self.assertEqual(d["text"], "Not reviewed: could not be confirmed")
        self.assertEqual((d["evidence"], d["detail"], d["remedies"]), ([], None, []))
        gaps = sum(1 for x in a["aspects"] for r in x["results"] if r["outcome"] == "confirmed" and rv.results[r["key"]]["state"] in RV.GAP)
        self.assertEqual(a["counts"]["gaps"], gaps)  # neither pass nor gap

    def test_dependabot_at_organisation_level(self):
        rv = self.review(apps=["billing-service"])
        k = self.key(rv, "billing-service", "security.dependency_updates")
        self.assertTrue(rv.results[k]["not_seen"])
        rv.record({"key": k, "outcome": "team_stated", "answer": "enabled at organisation level", "who": "Team Lead", "state": "PRESENT"})
        confirm_all(rv)
        d = self._shown(rv, k)
        self.assertEqual(d["text"], "Stated by the team: enabled at organisation level")
        self.assertEqual(d["mode"], "In place (stated)")
        self.assertTrue(d["who"].startswith("Team Lead, 20"))

    def test_outcomes_are_only_allowed_where_8_4_allows_them(self):
        rv = self.review(apps=["orders-service"])
        gap, ok = self.key(rv, "orders-service", "delivery.deploy"), self.key(rv, "orders-service", "testing.integration")
        for e in ({"key": ok, "outcome": "disputed", "reason": "client_fact"}, {"key": gap, "outcome": "gap_stated"},
                  {"key": gap, "outcome": "team_stated", "answer": "x", "who": "y", "state": "PRESENT"}, {"key": gap, "outcome": "corrected", "state": "PRESENT"},
                  {"key": gap, "outcome": "disputed", "reason": "other"}, {"key": gap, "outcome": "corrected", "state": "PRESENT", "reason": "made-up"}):
            with self.assertRaises(RV.Refused, msg=e):
                rv.record(e)
        self.assertEqual(set(RV.REASONS), {"tool_missed", "false_pass", "test_or_copy", "wrong_app", "wrong_kind", "outside_repo", "client_fact", "other"})
        self.assertEqual({k for k, v in RV.REASONS.items() if v[1]}, {"tool_missed", "false_pass", "test_or_copy", "wrong_app", "wrong_kind"})

    def _shown(self, rv, k, m=None):
        m = m or CF.model(rv)
        return next(d for a in m["apps"] for x in a.get("aspects", []) for d in x["results"] if d["key"] == k)


class StopRuleTest(Base):
    """The stop rule escalates instead of blocking."""

    def test_a_systematic_tool_error(self):
        rv = self.review()
        deploy = [self.key(rv, a, "delivery.deploy") for a in APPS]
        for k in deploy[:3]:
            rv.record({"key": k, "outcome": "corrected", "state": "PRESENT", "reason": "tool_missed", "note": "a shared library deploys it"})
        self.assertEqual(len(rv.firings_all), 1)
        self.assertEqual(rv.firings_all[0]["controls"], ["delivery.deploy"])
        self.assertTrue(all(6 in rv.reasons(k) for k in deploy))
        confirm_all(rv, skip=deploy)
        res = CF.publish(rv)
        self.assertFalse(res["ok"])
        self.assertTrue(any("stop-rule escalation incomplete" in r for r in res["refused"]))
        rv.record({"key": deploy[3], "outcome": "confirmed"})
        self.assertTrue(rv.firings_all[0]["cleared"])
        res = CF.publish(rv)
        self.assertTrue(res["ok"], res)
        self.assertIn("Stop rule fired", text_of(res["path"]))

    def test_three_false_passes_on_one_control(self):
        rv = self.review()
        ks = [self.key(rv, a, "config.secrets_externalised") for a in APPS]
        self.assertTrue(all(rv.results[k]["state"] == "PRESENT" for k in ks[:3]))
        for k in ks[:3]:
            rv.record({"key": k, "outcome": "gap_stated", "note": "a literal in the deployment values"})
        self.assertEqual([f["controls"] for f in rv.firings_all], [["config.secrets_externalised"]])
        self.assertTrue(all(6 in rv.reasons(k) for k in ks))
        bl = json.load(open(os.path.join(RV.workspace_of(rv.run_dir), "backlog", "20261101-000000.json")))["items"]
        self.assertEqual(len([b for b in bl if b["control"] == "config.secrets_externalised"]), 3)

    def test_a_bulk_confirmation_of_an_implicated_control_must_be_reviewed_again_one_by_one(self):
        rv = self.review()
        k = next(k for k in (self.key(rv, a, "architecture.calls_matched") for a in APPS) if rv.bulkable(k))
        confirm_all(rv)
        self.assertTrue(rv.resolved(k))
        others = [x for x in rv.must() if rv.results[x]["id"] != "architecture.calls_matched"][:3]
        for x in others:  # three tool errors on other controls do not touch it
            rv.record({"key": x, "outcome": "corrected", "state": "PRESENT", "reason": "tool_missed"})
        self.assertTrue(rv.resolved(k))
        gap = next(x for x in rv.results if rv.results[x]["id"] == "architecture.calls_matched" and rv.results[x]["state"] in RV.GAP)
        for _ in range(3):
            rv.record({"key": gap, "outcome": "corrected", "state": "PRESENT", "reason": "false_pass"})
        self.assertIn(6, rv.reasons(k))
        self.assertFalse(rv.resolved(k))  # its bulk confirmation no longer resolves it
        self.assertEqual(rv.audit_size(), min(len(rv.audit_population()), max(5, -(-len(rv.audit_population()) * 25 // 100))))

    def test_a_rerun_does_not_clear_the_rule(self):
        old, new = copies(self.base, "20261001-000000", "20261101-000000")
        rv = self.review(old, auditor="Second Person")
        deploy = [self.key(rv, a, "delivery.deploy") for a in APPS]
        for k in deploy[:3]:
            rv.record({"key": k, "outcome": "corrected", "state": "PRESENT", "reason": "tool_missed"})
        self.assertFalse(rv.firings_all[0]["cleared"])
        rv.close()
        rv2 = self.review(new, auditor="Second Person")
        self.assertEqual([(f["controls"], f["from_run"]) for f in rv2.firings_all], [(["delivery.deploy"], "20261001-000000")])
        self.assertTrue(all(6 in rv2.reasons(k) for k in deploy))
        confirm_all(rv2)
        self.assertEqual(rv2.audit_size(), min(len(rv2.audit_population()), max(5, -(-len(rv2.audit_population()) * 25 // 100))))
        self.assertTrue(rv2.blockers())

    def test_branch_protection_the_tool_cannot_see(self):
        rv = self.review()
        ks = [k for k, r in rv.results.items() if r["not_seen"]][:3]
        self.assertEqual(len(ks), 3)
        for k in ks:
            rv.record({"key": k, "outcome": "gap_stated", "reason": "tool_missed"})
        self.assertEqual(rv.firings_all, [])
        self.assertFalse(any(rv.doc["outcomes"][k]["tool_error"] for k in ks))

    def test_a_false_pass_recorded_as_a_correction(self):
        rv = self.review()
        k = self.key(rv, "orders-service", "testing.integration")
        rv.record({"key": k, "outcome": "corrected", "state": "ABSENT", "reason": "other", "note": "the cited class is a stub"})
        self.assertTrue(rv.doc["outcomes"][k]["tool_error"])

    def test_a_client_fact_repeated_across_applications(self):
        rv = self.review()
        gaps = [k for k in rv.must() if rv.results[k]["state"] in RV.GAP][:10]
        self.assertEqual(len(gaps), 10)
        for k in gaps:
            rv.record({"key": k, "outcome": "disputed", "reason": "outside_repo"})
        self.assertEqual(rv.firings_all, [])


class BindingTest(Base):
    """A review mark is bound to what was reviewed."""

    def test_a_catalogue_change_to_one_control(self):
        old, new = copies(self.base, "20261001-000000", "20261101-000000")
        rv = self.review(old)
        confirm_all(rv)
        marked = set(rv.doc["outcomes"])
        rv.close()
        cat = A.load_catalogue()
        for c in cat["controls"]:
            if c["id"] == "testing.coverage_gate":
                c["severity"] = "medium" if c["severity"] == "high" else "high"
        with mock.patch.object(A, "load_catalogue", return_value=cat):
            rv2 = self.review(new)
            carried = {k for k, o in rv2.doc["outcomes"].items() if o["mode"] == "carried"}
        gate = {k for k in marked if k.endswith("::testing.coverage_gate")}
        self.assertTrue(gate)
        self.assertEqual(carried, marked - gate)
        self.assertTrue(all(not rv2.resolved(k) for k in gate))

    def test_the_searched_files_changed(self):
        root, repos = F.make_portfolio(names=["orders-service"])
        ws = tempfile.mkdtemp(prefix="ws-")
        run1 = scan(repos.values(), ws)
        rv = self.review(run1, apps=["orders-service"])
        k = self.key(rv, "orders-service", "knowledge.owners")
        self.assertEqual(rv.results[k]["state"], "ABSENT")
        rv.record({"key": k, "outcome": "confirmed"})
        before = rv.doc["outcomes"][k]["binding"]
        rv.close()
        with open(os.path.join(repos["orders-service"], "CODEOWNERS"), "w") as fh:
            fh.write("* @team-a\n")
        with mock.patch.object(cli, "_now", return_value=RV.now() + datetime.timedelta(minutes=5)):
            run2 = scan(repos.values(), ws)
        rv2 = self.review(run2, apps=["orders-service"])
        self.assertNotIn(k, [x for x, o in rv2.doc["outcomes"].items() if o["mode"] == "carried"])
        self.assertNotEqual(rv2.binding(k).get("scope"), before["scope"])

    def test_a_scope_hash_follows_the_files_and_ignores_others(self):
        rv = self.review(apps=["orders-service"])
        k = self.key(rv, "orders-service", "knowledge.owners")
        h = rv.scope_hash(rv.results[k])
        self.assertEqual(h, rv.scope_hash(rv.results[k]))
        repo = self.repos["orders-service"]
        rv._areas.clear()
        with open(os.path.join(repo, "NOTES.txt"), "w") as fh:  # outside the owners search: no change
            fh.write("unrelated\n")
        self.addCleanup(os.remove, os.path.join(repo, "NOTES.txt"))
        self.assertEqual(rv.scope_hash(rv.results[k]), h)
        b = rv.binding(k)
        self.assertEqual(set(b), {"definition", "detectors", "state", "remedies", "scope"})
        self.assertIn("identity", b["detectors"])
        self.assertIn("evidence", rv.binding(self.key(rv, "orders-service", "testing.integration")))

    def test_a_carried_forward_mark(self):
        old, new = copies(self.base, "20261001-000000", "20261101-000000")
        rv = self.review(old, apps=["billing-service"])
        confirm_all(rv)
        rv.close()
        rv2 = self.review(new, apps=["billing-service"])
        self.assertTrue(all(o["mode"] == "carried" for o in rv2.doc["outcomes"].values()))
        res = CF.publish(rv2)
        self.assertTrue(res["ok"], res)
        t = text_of(res["path"])
        self.assertIn("carried forward from run 20261001-000000, confirmed %s" % RV.now().date().isoformat(), t)
        self.assertNotIn("checked individually", t)
        self.assertIn(next(iter(rv2.doc["outcomes"])), rv2.audit_population())  # carried-forward marks are in the audit population

    def test_a_second_reviewer_at_the_same_time_is_refused(self):
        rv = self.review()
        with self.assertRaises(RV.Refused) as e:
            RV.Review(rv.run_dir)
        self.assertIn("already under review", str(e.exception))
        rc, out = quiet(cli.main, ["review", rv.run_dir, "--publish"])
        self.assertEqual(rc, 2)
        rv.close()
        with RV.Review(rv.run_dir) as again:  # free again once the first one stops
            with self.assertRaises(RV.Refused):  # and a mark is never attributed to an earlier session's reviewer
                again.record({"key": again.must()[0], "outcome": "confirmed"})

    def test_a_lock_left_by_a_crashed_review_is_taken_over(self):
        rv = self.review()
        rv.close()
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        p.wait()
        with open(os.path.join(rv.run_dir, RV.LOCK), "w") as fh:
            json.dump({"pid": p.pid, "host": RV.socket.gethostname(), "at": "x"}, fh)
        RV.Review(rv.run_dir).close()

    def test_review_json_is_written_atomically_after_every_action_and_the_run_is_immutable(self):
        rv = self.review(apps=["billing-service"])
        k = rv.must()[0]
        rv.record({"key": k, "outcome": "confirmed"})
        self.assertIn(k, json.load(open(rv.path))["outcomes"])
        self.assertFalse([f for f in os.listdir(rv.run_dir) if f.endswith(".tmp")])
        rv.close()
        (new, _), _ = quiet(cli._rebuild, rv.run_dir)
        self.assertNotEqual(new, rv.run_dir)
        self.assertFalse(os.path.exists(os.path.join(new, "review.json")))


class ClientVerifyTest(Base):
    """The client file is verified after it is written."""

    def test_a_note_holding_a_token_is_redacted_at_write(self):
        rv = self.review(apps=["orders-service"])
        k = self.key(rv, "orders-service", "delivery.deploy")
        rv.record({"key": k, "outcome": "disputed", "reason": "outside_repo", "note": "deploy hook " + HOOK})
        raw = open(rv.path).read()
        self.assertNotIn("FAKEFAKEFAKEFAKEFAKE0000", raw)
        self.assertIn("[REDACTED]", json.loads(raw)["outcomes"][k]["note"])
        res = V.check(rv.run_dir)
        self.assertFalse([p for p in res["problems"] if p["app"] == "review.json"], res["problems"])

    def test_a_leak_in_the_client_file_deletes_it_and_names_the_file_and_rule_never_the_value(self):
        rv = self.review(apps=["billing-service"])
        confirm_all(rv)
        real = CF.render
        with mock.patch.object(CF, "render", side_effect=lambda m: real(m).replace("</body>", "<p>%s</p></body>" % FAKE)):
            res = CF.publish(rv)
        self.assertFalse(res["ok"])
        self.assertFalse(os.path.exists(os.path.join(rv.run_dir, CF.NAME)))
        self.assertFalse(os.path.exists(os.path.join(rv.run_dir, CF.PENDING)))
        self.assertIn(("ACC-11", CF.PENDING), {(p["rule"], p["where"]) for p in res["problems"]})
        self.assertNotIn(FAKE, json.dumps(res))

    def test_one_applications_citation_drifted(self):
        run = copies(self.base, "20261101-000000")[0]
        p = os.path.join(run, "analysis", "inventory-service", "aspects.json")
        doc = json.load(open(p))
        c = next(c for a in doc["aspects"] for c in a["controls"] if c["evidence"] and c["evidence"][0].get("kind") == "file" and "secret" not in c["id"])
        c["evidence"][0]["snippet"] = "not what the file says"
        json.dump(doc, open(p, "w"))
        r = json.load(open(os.path.join(run, "run.json")))
        R.build(os.path.join(run, "analysis"), os.path.join(run, V.REPORT), A.load_catalogue(), A.load_remedy_packs(r["remedy_packs"]), r["sources"], r["client"], gate=cli.GATE)
        rv = self.review(run, apps=["billing-service", "inventory-service", "notifier-a"])
        confirm_all(rv)
        res = CF.publish(rv)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["not_available"], ["inventory-service"])
        t = text_of(res["path"])
        self.assertIn("2 of 3 applications in scope shown; 0 not yet reviewed; 1 not available", t)
        self.assertIn("Not available: verification failed", t)
        self.assertNotIn("inventory-service::", open(res["path"]).read())

    def test_the_client_count_rule_catches_a_wrong_number_and_an_unreviewed_verdict(self):
        rv = self.review(apps=["billing-service", "orders-service"])
        confirm_all(rv, only_app="billing-service")
        res = CF.publish(rv)
        self.assertTrue(res["ok"], res)
        self.assertTrue(V.check_client(rv.run_dir, res["path"])["ok"])
        html = open(res["path"]).read()
        bad = os.path.join(rv.run_dir, "tampered.html")
        for old, new, rule in (('data-n="1"', 'data-n="2"', "CON-11"), ('data-gaps="', 'data-gaps="9', "CON-11"),
                               ('data-outcome="confirmed"', 'data-outcome="none"', "CON-11"), ("</body>", "<script>const D = {}</script></body>", "CON-12")):
            with open(bad, "w") as fh:
                fh.write(html.replace(old, new, 1))
            self.assertIn(rule, {p["rule"] for p in V.check_client(rv.run_dir, bad)["problems"]}, old)
        os.remove(bad)
        self.assertEqual(V.client_level("ACC-1"), "app")
        self.assertEqual(V.client_level("ACC-14"), "run")
        self.assertEqual(V.client_level("CON-11"), "run")


class ClientFileTest(Base):
    """An internal report and a separate client file (report-experience)."""

    def test_an_application_with_an_unresolved_must_review_item(self):
        rv = self.review(apps=["billing-service", "orders-service"])
        confirm_all(rv, skip=[rv.must()[-1]] if rv.results[rv.must()[-1]]["app"] == "orders-service" else [])
        confirm_all(rv, only_app="billing-service")
        left = [k for k in rv.must() if not rv.resolved(k)]
        self.assertTrue(left and all(rv.results[k]["app"] == "orders-service" for k in left))
        res = CF.publish(rv)
        self.assertTrue(res["ok"], res)
        html = open(res["path"]).read()
        self.assertIn('data-app="orders-service" data-status="not_yet"', html)
        self.assertIn("1 of 2 applications in scope shown; 1 not yet reviewed; 0 not available", text_of(res["path"]))
        self.assertNotIn("orders-service::", html)  # no verdicts, no counts, not in the sort
        self.assertNotIn("const D = ", html)

    def test_aspect_cells(self):
        r = lambda st, sev="medium", possible=False: {"state": st, "sev": sev, "ctl": {"severity": sev}, "possible": possible, "not_seen": False}  # noqa: E731
        o = lambda out, **k: dict({"outcome": out, "mode": "individual"}, **k)  # noqa: E731
        conf = o("confirmed")
        cases = [  # (rows, cell): the scenarios of the requirement, then the remaining rules
            ([(r("ABSENT", "high"), conf), (r("PRESENT"), None), (r("PRESENT"), None)], "High gaps"),  # a known gap beside unreviewed passes
            ([(r("PRESENT"), conf), (r("PRESENT"), conf), (r("PRESENT"), None), (r("PRESENT"), None)], "Reviewed 2 of 4"),
            ([(r("PRESENT"), conf)] + [(r("PRESENT"), o("cannot_confirm"))] * 3, "Partly confirmed"),
            ([(r("PRESENT"), o("cannot_confirm"))] * 3, "Reviewed, nothing confirmed"),
            ([(r("PRESENT"), conf), (r("UNKNOWN"), o("team_stated", state="PRESENT", answer="yes"))], "In place (stated)"),
            ([], "Not checked"), ([(r("ABSENT"), conf), (r("PRESENT"), None)], "Gaps"), ([(r("NOT_APPLICABLE"), conf)], "Not applicable"),
            ([(r("PRESENT"), conf), (r("NOT_APPLICABLE"), conf)], "In place"), ([(r("ABSENT", "high"), o("disputed", reason="outside_repo"))], "Reviewed, nothing confirmed"),
        ]
        for rows, want in cases:
            self.assertEqual(CF.cell(rows), want)
            self.assertEqual(V._cell([(dict(x, severity=x["sev"] if x["state"] in RV.GAP else None), y, x["sev"]) for x, y in rows]), want)  # verify's own rule agrees
        self.assertEqual(CF._cls("Reviewed 2 of 4"), "")  # neutral colour
        self.assertEqual(CF._cls("Reviewed, nothing confirmed"), "")

    def test_as_is_facts_are_labelled_read_by_the_tool(self):
        rv = self.review(apps=["billing-service"])
        confirm_all(rv)
        res = CF.publish(rv)
        t = text_of(res["path"])
        boot = next(f["value"] for a in CF.model(rv)["apps"] for f in a["facts"] if f["label"] == "Spring Boot")
        self.assertIn("Spring Boot: %s" % boot, t)
        self.assertIn("read by the tool, not reviewed", t)

    def test_a_disputed_only_application_sorts_after_those_with_confirmed_results(self):
        rv = self.review(apps=["billing-service", "orders-service"])
        gaps = [k for k in rv.must() if rv.results[k]["app"] == "billing-service" and rv.results[k]["state"] in RV.GAP]
        for k in gaps[:2]:
            rv.record({"key": k, "outcome": "disputed", "reason": "client_fact"})
        for k in gaps[2:]:
            rv.record({"key": k, "outcome": "cannot_confirm"})
        confirm_all(rv)
        m = CF.model(rv)
        self.assertEqual([a["app"] for a in m["apps"]], ["orders-service", "billing-service"])
        res = CF.publish(rv)
        self.assertTrue(res["ok"], res)
        self.assertIn("disputes: 2", text_of(res["path"]))

    def test_an_unconfirmed_remedy_is_suggested_not_reviewed(self):
        rv = self.review(apps=["orders-service"])
        k = self.key(rv, "orders-service", "delivery.deploy")
        rv.record({"key": k, "outcome": "confirmed", "remedy_confirmed": False})
        k2 = self.key(rv, "orders-service", "delivery.version_tagging")
        rv.record({"key": k2, "outcome": "confirmed", "remedy_confirmed": True})
        confirm_all(rv)
        m = CF.model(rv)
        d = {x["key"]: x for a in m["apps"] for asp in a["aspects"] for x in asp["results"]}
        self.assertTrue(d[k]["remedies"])
        self.assertEqual((d[k]["remedy_label"], d[k2]["remedy_label"]), ("suggested, not reviewed", None))
        self.assertFalse([x for x in d.values() if x["remedies"] and x["outcome"] in ("none", "disputed", "cannot_confirm")])
        res = CF.publish(rv)
        self.assertIn("(suggested, not reviewed)", text_of(res["path"]))

    def test_an_unreviewed_result_shows_only_not_reviewed(self):
        rv = self.review(apps=["billing-service"])
        confirm_all(rv)
        k = next(k for k, o in rv.doc["outcomes"].items() if o["mode"] == "aspect")
        del rv.doc["outcomes"][k]
        rv.save()
        res = CF.publish(rv)
        self.assertTrue(res["ok"], res)
        html = open(res["path"]).read()
        i = html.find('data-key="%s"' % k)
        self.assertIn('data-outcome="none"', html[i:i + 80])
        self.assertIn("Not reviewed</span></li>", html[i:i + 400])


class RecordCliTest(Base):
    def test_record_and_publish_through_the_command_line(self):
        run = copies(self.base, "20261101-000000")[0]
        rv = RV.Review(run, ["billing-service"], "consultant", "Rev One", budget=500)
        must, screens = rv.must(), rv.bulk_screens()
        rv.close()
        outs = [{"app": "billing-service", "control": k.split("::")[1], "outcome": "confirmed", "seconds": 12} for k in must] + \
               [{"bulk": s["aspect"], "app": s["app"], "seconds": 8} for s in screens]
        f = os.path.join(tempfile.mkdtemp(), "outcomes.json")
        json.dump(outs, open(f, "w"))
        rc, out = quiet(cli.main, ["review", run, "--reviewer", "Rev One", "--record", f, "--publish"])
        self.assertEqual(rc, 0, out)
        self.assertIn("━━ APP-INSIGHT-REVIEW ━━", out)
        self.assertTrue(os.path.isfile(os.path.join(run, CF.NAME)))
        self.assertFalse(os.path.exists(os.path.join(run, RV.LOCK)))
        doc = json.load(open(os.path.join(run, "review.json")))
        self.assertEqual(len(doc["log"]), len(must) + len(screens))


class ReviewPageTest(Base):
    """The local review page: 127.0.0.1 only, a token on every request, the Host checked."""

    def setUp(self):
        self.rv = self.review(apps=["billing-service"])
        self.srv = RP.Server(self.rv)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def req(self, method, path, token=True, host=None, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=10)
        h = {"Host": host or "127.0.0.1:%d" % self.srv.server_port}
        if token:
            h["X-Review-Token"] = self.srv.token
        if body is not None:
            h["Content-Type"] = "application/json"
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, data

    def test_binds_to_127_0_0_1_only(self):
        self.assertEqual(self.srv.server_address[0], "127.0.0.1")
        self.assertNotEqual(self.srv.server_port, 0)

    def test_a_request_without_the_token_is_refused(self):
        self.assertEqual(self.req("GET", "/api/state", token=False)[0], 403)
        self.assertEqual(self.req("GET", "/", token=False)[0], 403)
        self.assertEqual(self.req("GET", "/?t=wrong", token=False)[0], 403)
        k = self.rv.must()[0]
        self.assertEqual(self.req("POST", "/api/outcome", token=False, body={"key": k, "outcome": "confirmed"})[0], 403)
        self.assertNotIn(k, self.rv.doc["outcomes"])

    def test_a_wrong_host_is_refused(self):
        self.assertEqual(self.req("GET", "/api/state", host="evil.example:80")[0], 421)
        self.assertEqual(self.req("GET", "/api/state", host="127.0.0.1:1")[0], 421)

    def test_the_page_drives_the_same_functions_and_measures_time(self):
        st, page = self.req("GET", "/?t=" + self.srv.token, token=False)
        self.assertEqual(st, 200)
        self.assertIn(b"Consultant review", page)
        k = self.rv.must()[0]
        self.assertEqual(self.req("GET", "/api/item?key=" + k)[0], 200)
        st, data = self.req("POST", "/api/outcome", body={"key": k, "outcome": "corrected"})
        self.assertEqual(st, 409)  # a correction needs a state and a reason: refused by Review.record
        st, data = self.req("POST", "/api/outcome", body={"key": k, "outcome": "confirmed"})
        self.assertEqual(st, 200, data)
        self.assertEqual(self.rv.doc["outcomes"][k]["mode"], "individual")
        self.assertIn(k, json.load(open(self.rv.path))["outcomes"])
        s = self.rv.bulk_screens()[0]
        self.assertEqual(self.req("POST", "/api/bulk", body={"app": s["app"], "aspect": s["aspect"]})[0], 200)
        self.assertEqual(self.req("POST", "/api/outcome", body={"key": "x::y", "outcome": "confirmed"})[0], 409)


class SanitiseTest(Base):
    """Disputes become synthetic fixtures, never client code."""

    def test_a_fixture_containing_a_client_package_name_fails(self):
        ws = os.path.dirname(os.path.dirname(self.base))
        found = SAN.names(ws)
        self.assertIn("com.shop.orders", found["packages"])
        self.assertIn("orders-service", found["applications"])
        d = tempfile.mkdtemp()
        bad, good = os.path.join(d, "bad.java"), os.path.join(d, "good.java")
        open(bad, "w").write("package com.shop.orders.web;\nclass A {}\n")
        open(good, "w").write("package com.example.fixture;\n// a deploy step run by a shared library, as seen in a dispute\nclass A { String url = \"http://localhost:8080\"; }\n")
        hits, _ = SAN.check_file(bad, ws)
        self.assertEqual([(k, n) for _, k, n in hits], [("package prefix", 1)])
        self.assertEqual(SAN.check_file(good, ws)[0], [])
        self.assertEqual([k for k, _ in SAN.check("calls orders-service at api.shop-internal.example.net", found)], ["application name"])
        rc, out = quiet(cli.main, ["fixture-check", bad, "--workspace", ws])
        self.assertEqual(rc, 1)
        self.assertIn("cannot leave the workspace", out)
        self.assertEqual(quiet(cli.main, ["fixture-check", good, "--workspace", ws])[0], 0)

    def test_hostnames_from_the_workspace_are_caught(self):
        found = {"applications": [], "packages": [], "hostnames": ["git.acme-corp.invalid"]}
        self.assertEqual(SAN.check("clone from https://git.acme-corp.invalid/a.git", found), [("hostname", 1)])
        self.assertEqual(SAN.check("clone from https://git.acme-corp.invalid.example/a.git", found), [])


if __name__ == "__main__":
    unittest.main()
