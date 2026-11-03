"""Phase 1 of the AS-IS baseline (client safety and correctness), product side. Each test pins one defect from the red-team reviews
(openspec/changes/asis-baseline/reviews) and fails on the code before its fix. Fixture secrets are obviously fake."""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(1, os.path.join(HERE, "..", "engine", "tests"))
os.environ["DISCOVERY_FIXED_TIME"] = "2026-10-29T00:00:00Z"

from app_insight import aspects as A  # noqa: E402
from app_insight import cli  # noqa: E402
from app_insight import report as R  # noqa: E402
from app_insight import sources as SRC  # noqa: E402
from app_insight import verify as V  # noqa: E402
import graph_fixtures as F  # noqa: E402
import discover  # noqa: E402

CAT = A.load_catalogue()
CTL = {c["id"]: c for c in CAT["controls"]}
FAKE = "Fake-Pass-0000-xyz"  # an obviously fake value, planted only in throwaway fixture repositories
NOWHERE = {"nodes": [], "edges": []}


def cx(disc, res=None, sn=None, dims=None):
    return A.Context("x", disc, None, res, sn, dims, NOWHERE)


def quiet(fn, *a):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*a)


def spot(sid="build.parent_pom", area="build", what="a parent POM from outside this repository (com.acme:parent)"):
    return {"value": [{"id": sid, "area": area, "what": what, "at": ["pom.xml:5"]}], "status": "CONFIRMED",
            "evidence": [{"kind": "file", "path": "pom.xml", "line_start": 5, "snippet": "<groupId>com.acme</groupId>"}]}


READ = {"value": {a: {"count": 1, "files": ["f"]} for a in ("build", "ci", "config", "deploy", "main_source", "test_source", "docs")}}


class ScanTest(unittest.TestCase):
    """T-1.1, T-1.4, T-1.6, T-1.7, T-1.19 through the command line, on a small portfolio."""

    @classmethod
    def setUpClass(cls):
        cls.root, repos = F.make_portfolio(names=["orders-service", "notifier-a"])
        cls.repos = sorted(repos.values())
        cfg = os.path.join(repos["orders-service"], "src", "main", "resources", "secret.properties")
        os.makedirs(os.path.dirname(cfg), exist_ok=True)
        with open(cfg, "w") as fh:
            fh.write("vault.password=%s\n" % FAKE)
        cls.ws = tempfile.mkdtemp(prefix="ws-")

    def scan(self, client, *extra):
        return quiet(cli.main, ["scan", "--client", client, "--workspace", self.ws, "--json"] + self.repos + list(extra))

    def test_verify_runs_before_the_report_and_latest_and_its_result_is_in_the_summary_and_header(self):
        self.assertEqual(self.scan("ok"), 0)
        ws = os.path.join(self.ws, "ok")
        run = cli.resolve_run(ws)  # latest was written: the run passed
        s = cli.summarise(run)
        self.assertEqual((s["verify"]["ok"], s["verify"]["state"], s["gate"]), (True, "passed", "Internal: not validated"))
        data = V._report_data(os.path.join(run, V.REPORT))
        self.assertEqual((data["verify"]["state"], data["gate"]), ("passed", "Internal: not validated"))
        self.assertFalse(os.path.exists(os.path.join(run, "report.pending.html")))

    def test_a_failed_verify_is_never_the_latest_says_failed_and_rebuilds_exit_non_zero(self):
        fail = {"ok": False, "checked": {"applications": 0, "controls": 0, "lines_reread": 0}, "rules": V.RULES,
                "problems": [{"rule": "ACC-1", "app": "x", "control": "y", "detail": "z"}]}
        self.assertEqual(self.scan("good"), 0)
        before = open(os.path.join(self.ws, "good", "latest")).read()
        with mock.patch.object(V, "check", return_value=fail):
            self.assertEqual(self.scan("good"), 1)
            self.assertEqual(open(os.path.join(self.ws, "good", "latest")).read(), before)  # the failed run did not become the latest
            runs = sorted(os.listdir(os.path.join(self.ws, "good", "runs")))
            bad = os.path.join(self.ws, "good", "runs", runs[-1]) if runs[-1] != before else os.path.join(self.ws, "good", "runs", runs[0])
            self.assertEqual(V._report_data(os.path.join(bad, V.REPORT))["verify"]["state"], "FAILED")
            self.assertEqual(cli.summarise(bad)["verify"]["failed_rules"]["ACC-1"]["count"], 1)
            self.assertEqual(quiet(cli.main, ["report", bad]), 1)
            self.assertEqual(quiet(cli.main, ["aspects", bad]), 1)

    def test_a_credentialed_url_is_refused_and_never_stored(self):
        url = "https://ci-bot:FAKE-TOKEN-0000@git.example.invalid/acme/svc.git"
        self.assertEqual(self.scan("creds", url), 0)
        ws = os.path.join(self.ws, "creds")
        run = cli.resolve_run(ws)
        text = open(os.path.join(run, "run.json")).read()
        self.assertNotIn("FAKE-TOKEN-0000", text)  # neither in inputs nor in sources[].spec
        src = next(s for s in json.loads(text)["sources"] if s["remote"])
        self.assertEqual((src["status"], src["error"]), ("failed", SRC.REFUSED))
        self.assertFalse(os.path.isdir(os.path.join(ws, "repos")))  # nothing cloned, so no .git/config holds it

    def test_a_token_as_user_name_or_in_the_query_is_a_credential_too(self):
        for u in ("https://FAKE-TOKEN-0000@github.com/acme/a.git", "https://h.example.invalid/a.git?private_token=FAKE-TOKEN-0000",
                  "ssh://git:FAKE-TOKEN-0000@h.example.invalid/a.git"):
            s = SRC.Source(u)
            self.assertEqual(s.status, "failed", u)
            self.assertNotIn("FAKE-TOKEN-0000", json.dumps(s.as_dict()))
        self.assertNotEqual(SRC.Source("ssh://git@h.example.invalid/a.git").status, "failed")  # a user name alone over SSH is the user's own setup

    def test_two_remotes_with_the_same_last_segments_get_different_clone_folders(self):
        a, b = SRC.expand(["https://git.example.invalid/teamA/payments/api.git", "https://git.example.invalid/teamB/payments/api.git"])
        self.assertNotEqual(a.slug(), b.slug())  # both were payments__api before
        lst = os.path.join(tempfile.mkdtemp(), "estate.csv")
        with open(lst, "w") as fh:  # the same name given twice in a list
            fh.write("url,name\nhttps://h.example.invalid/x/a.git,api\nhttps://h.example.invalid/y/a.git,api\n")
        n1, n2 = SRC.expand([lst])
        self.assertNotEqual(n1.slug(), n2.slug())

    def test_the_leak_check_compares_literal_values_on_scan_rebuild_and_verify(self):
        self.assertEqual(self.scan("leak"), 0)
        run = cli.resolve_run(os.path.join(self.ws, "leak"))
        planted = os.path.join(run, "analysis", "portfolio", "notes.json")
        with open(planted, "w") as fh:  # a value no redaction rule masks: only the literal-value comparison can see it
            json.dump({"note": "copied: " + FAKE.replace("Pass", "Pass")}, fh)
        try:
            self.assertEqual(V.evidence.redact(FAKE), FAKE)  # redaction alone does not know it
            res = V.check(run)
            hit = [p for p in res["problems"] if p["rule"] == "ACC-11"]
            self.assertEqual([p["app"] for p in hit], ["analysis/portfolio/notes.json"])
            self.assertNotIn(FAKE, json.dumps(res))  # the location only, never the value
            self.assertEqual(quiet(cli.main, ["verify", run]), 1)
            self.assertEqual(quiet(cli.main, ["report", run]), 1)  # a rebuild re-locates the values in memory too
        finally:
            os.remove(planted)

    def test_a_credential_shape_redaction_does_not_use_is_caught_by_the_second_pattern_set(self):
        self.assertEqual(self.scan("broad"), 0)
        run = cli.resolve_run(os.path.join(self.ws, "broad"))
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmYWtlLXVzZXIifQ.ZmFrZS1zaWduYXR1cmUtMDAw"  # a fake token: header, payload, signature
        planted = os.path.join(run, "analysis", "portfolio", "notes.txt")
        with open(planted, "w") as fh:
            fh.write("seen " + jwt + "\n")
        try:
            self.assertEqual(V.evidence.redact(jwt), jwt)
            self.assertIn("ACC-12", {p["rule"] for p in V.check(run)["problems"]})
        finally:
            os.remove(planted)

    def test_a_detector_failure_is_in_the_summary(self):
        real = discover.build

        def broken(r):
            with mock.patch("detectors.runtime.detect", side_effect=ValueError("fake failure")):
                return real(r)
        with mock.patch.object(discover, "build", side_effect=broken):
            self.assertEqual(self.scan("crash"), 0)
        s = cli.summarise(cli.resolve_run(os.path.join(self.ws, "crash")))
        self.assertTrue(s["detector_failures"])
        self.assertTrue(all("runtime: ValueError" in f["failed"] for f in s["detector_failures"]))


class FailureTest(unittest.TestCase):
    """T-1.4: a control fed by a failed detector is NOT_ASSESSED with that reason, never ABSENT, N/A or 'scan again'."""

    def setUp(self):
        self.disc = {"run_meta": {"failures": ["runtime: ValueError: boom", "stack: KeyError: 'x'"]}, "runtime": {}, "stack": {},
                     "scope": {"files_read": READ}}

    def test_every_control_reading_a_failed_detector_is_not_assessed(self):
        c = cx(self.disc)
        for cid in ("runtime.http_timeouts", "runtime.graceful_shutdown", "observability.health", "observability.metrics", "data.migrations",
                    "platform.framework_support", "architecture.calls_matched"):
            r = A.evaluate(CTL[cid], c)
            self.assertEqual(r["state"], "NOT_ASSESSED", cid)
            self.assertIn("detector failed on this repository", r["summary"], cid)

    def test_the_check_controls_no_longer_say_scan_again_after_a_crash(self):
        r = A.eval_check("runtime.db_timeouts", cx({"run_meta": {"failures": ["runtime: ValueError: boom"]}, "runtime": {}}))
        self.assertEqual(r["summary"], "Not assessed: the runtime detector failed on this repository")
        self.assertIn("scan again", A.eval_check("runtime.db_timeouts", cx({}))["summary"])  # an old analysis still says so

    def test_a_scope_failure_leaves_no_absence_standing(self):
        disc = {"run_meta": {"failures": ["scope: OSError: x"]}, "maturity": {"criteria": [{"id": "sast", "result": "NO_EVIDENCE", "facts": ["security.sast"]}]}}
        self.assertEqual(A.evaluate(CTL["security.sast"], cx(disc))["state"], "NOT_ASSESSED")


class AbsenceGuardTest(unittest.TestCase):
    """T-1.8: every verdict derived from not finding something is guarded and carries a search record."""

    def dw(self, deps=(), extra=None):
        disc = {"stack": {"app_framework": {"value": {"name": "dropwizard", "label": "Dropwizard"}}, "external_dependencies": {"value": list(deps)}},
                "scope": {"files_read": READ}, "maturity": {"criteria": []}}
        disc.update(extra or {})
        c = cx(disc)
        c.kind = "service"
        return c

    def test_need_based_not_applicable_is_not_recognised_for_every_need(self):
        for cid in ("runtime.messaging_errors", "runtime.db_timeouts", "api.openapi", "runtime.http_timeouts"):
            r = A.evaluate(CTL[cid], self.dw())
            self.assertEqual(r["state"], "UNKNOWN", cid)
            self.assertIn("Not recognised for Dropwizard", r["summary"])

    def test_need_based_not_applicable_carries_a_search_record_and_a_blind_spot_makes_it_undecided(self):
        sb = {"stack": {"app_framework": {"value": {"name": "spring_boot", "label": "Spring Boot"}}, "spring_boot_version": {"value": "3.4.1"}, "external_dependencies": {"value": []}},
              "scope": {"files_read": READ}}
        r = A.evaluate(CTL["data.migrations"], cx(sb))
        self.assertEqual(r["state"], "NOT_APPLICABLE")
        self.assertEqual((r["searched"]["for"], [w["area"] for w in r["searched"]["in"]]), (A.NEED_SEARCH["sql_database"]["for"], ["build", "config", "main_source"]))
        sb["scope"]["blind_spots"] = spot()
        r = A.evaluate(CTL["data.migrations"], cx(sb))
        self.assertEqual(r["state"], "UNKNOWN")
        self.assertIn("pom.xml:5", r["summary"])

    def test_partial_keeps_its_state_with_a_note_and_a_search_record(self):
        disc = {"maturity": {"criteria": [{"id": "sast", "result": "PARTIAL", "facts": ["security.sast"]}]},
                "security": {"sast": {"value": True, "status": "CONFIRMED", "evidence": [{"kind": "file", "path": "pom.xml", "line_start": 9, "snippet": "spotbugs"}]}},
                "scope": {"files_read": READ, "blind_spots": spot()}}
        r = A.evaluate(CTL["security.sast"], cx(disc))
        self.assertEqual(r["state"], "PARTIAL")
        self.assertIn("may complete it", r["summary"])
        self.assertTrue(r["searched"]["in"])

    def test_an_issue_read_from_a_default_is_undecided_when_something_outside_may_set_it(self):
        disc = {"runtime": {"graceful_shutdown": {"value": {"state": "ISSUE", "summary": "default is immediate", "level": "configured", "by_default": True},
                                                  "status": "CONFIRMED", "evidence": [{"kind": "file", "path": "build.gradle", "line_start": 1, "snippet": "x"}]}},
                "stack": {"spring_boot_version": {"value": "2.7.0"}}, "scope": {"files_read": READ, "blind_spots": spot("config.external", "config", "settings read at run time from a Spring Cloud Config server")}}
        c = cx(disc)
        c.kind = "service"
        self.assertEqual(A.evaluate(CTL["runtime.graceful_shutdown"], c)["state"], "UNKNOWN")
        disc["scope"]["blind_spots"] = {"value": []}
        self.assertEqual(A.evaluate(CTL["runtime.graceful_shutdown"], cx(disc))["state"], "ISSUE")

    def test_the_repo_search_area_names_what_it_checked(self):
        r = A.evaluate(CTL["security.dependency_updates"], cx({"maturity": {"criteria": [{"id": "dependency_updates", "result": "NO_EVIDENCE", "facts": ["security.dependency_updates"]}]},
                                                             "scope": {"files_read": READ}}))
        where = r["searched"]["in"][0]
        self.assertEqual((where["area"], where["count"]), ("repo", 8))
        self.assertIn(".github/dependabot.yml", where["files"])


class VerifyRulesTest(unittest.TestCase):
    """T-1.8 and T-1.13 verify rules: a tampered result is caught by its rule."""

    @classmethod
    def setUpClass(cls):
        _, repos = F.make_portfolio(names=["orders-service", "notifier-a"])
        cls.run_dir = tempfile.mkdtemp(prefix="v1-")
        out = os.path.join(cls.run_dir, "analysis")
        import relate
        assert quiet(relate.main, ["analyse"] + sorted(repos.values()) + ["--out", out]) == 0
        packs = A.load_remedy_packs(["generic"])
        cls.docs = A.build(out, CAT, packs)
        R.build(out, os.path.join(cls.run_dir, V.REPORT), CAT, packs, [], "t")
        cls.app = "orders-service"
        cls.path = os.path.join(out, cls.app, "aspects.json")
        cls.clean = json.load(open(cls.path))

    def tearDown(self):
        json.dump(self.clean, open(self.path, "w"))

    def tamper(self, fn):
        d = copy.deepcopy(self.clean)
        fn({c["id"]: c for a in d["aspects"] for c in a["controls"]}, d)
        json.dump(d, open(self.path, "w"))
        return {p["rule"] for p in V.check(self.run_dir)["problems"] if p["app"] == self.app}

    def test_the_clean_run_passes(self):
        self.assertTrue(V.check(self.run_dir)["ok"], V.check(self.run_dir)["problems"][:3])

    def test_partial_and_issue_must_cite_a_line(self):
        def f(cs, d):
            c = next(c for c in cs.values() if c["state"] in ("PARTIAL", "ISSUE"))
            c["evidence"] = []
        self.assertIn("ACC-2", self.tamper(f))

    def test_a_framework_the_check_does_not_read_cannot_give_not_found_or_does_not_apply(self):
        def f(cs, d):
            d["profile"]["framework"] = "dropwizard"
            cs["runtime.http_timeouts"].update(state="ABSENT", searched={"for": "x", "in": [{"area": "config", "count": 1, "files": []}]}, severity="high",
                                               finding="runtime.http_timeouts@" + self.app)
            d["findings"].append("runtime.http_timeouts@" + self.app)
        self.assertIn("CON-9", self.tamper(f))

    def test_does_not_apply_by_need_without_a_search_record_or_in_a_blind_area_is_caught(self):
        def f(cs, d):
            cs["data.migrations"].update(state="NOT_APPLICABLE", summary=A.NEED_TEXT["sql_database"], searched=None, severity=None, finding=None, remedies=[])
            d["findings"] = [x for x in d["findings"] if not x.startswith("data.migrations@")]
            d["scope"]["blind_spots"] = [{"id": "build.parent_pom", "area": "build", "what": "a parent POM", "at": ["pom.xml:3"]}]
        got = self.tamper(f)
        self.assertTrue({"ACC-10", "CON-8"} <= got, got)

    def test_a_coupling_headline_that_hides_an_incomplete_map_is_caught(self):
        def f(cs, d):
            cs["architecture.calls_matched"].update(state="UNKNOWN", summary="An HTTP client is used but no call target was traced", evidence=[],
                                                    severity=None, finding=None, remedies=[])
            d["findings"] = [x for x in d["findings"] if not x.startswith("architecture.calls_matched@")]
        self.assertIn("CON-10", self.tamper(f))

    def test_evidence_from_an_example_or_build_output_is_caught(self):
        def f(cs, d):
            c = next(c for c in cs.values() if c["evidence"] and c["evidence"][0].get("kind") == "file")
            c["evidence"][0] = dict(c["evidence"][0], path="examples/demo/" + c["evidence"][0]["path"])
        self.assertIn("ACC-4", self.tamper(f))


class OutsideTest(unittest.TestCase):
    """T-1.9: controls usually set outside the repository."""

    def crit(self, cid, result="NO_EVIDENCE", extra=None):
        disc = {"maturity": {"criteria": [{"id": cid, "result": result, "facts": ["build_ci.deploy_step"]}]}, "scope": {"files_read": READ}}
        disc.update(extra or {})
        c = cx(disc)
        c.kind = "service"
        return c

    def test_platform_settings_not_seen_are_confirm_with_the_team(self):
        r = A.evaluate(CTL["security.secret_scanning"], self.crit("secret_scanning"))
        self.assertEqual(r["state"], "UNKNOWN")
        self.assertTrue(r["summary"].startswith("Not seen in the repository; confirm with the team"))
        self.assertTrue(r["searched"]["in"])  # where it looked is still said

    def test_deploy_is_a_gap_unless_the_repository_hands_it_to_gitops(self):
        self.assertEqual(A.evaluate(CTL["delivery.deploy"], self.crit("automated_deploy"))["state"], "ABSENT")
        gitops = {"scope": {"files_read": READ, "blind_spots": spot("deploy.gitops", "deploy", "deployment handed to Argo CD, whose target manifests this scan cannot see")}}
        r = A.evaluate(CTL["delivery.deploy"], self.crit("automated_deploy", extra=gitops))
        self.assertEqual(r["state"], "UNKNOWN")
        self.assertIn("Argo CD", r["summary"])

    def test_a_documented_manual_deploy_stays_a_gap_even_with_a_marker(self):
        man = {"build_ci": {"manual_deploy_documented": {"value": True, "evidence": [{"kind": "file", "path": "README.md", "line_start": 3, "snippet": "ansible-playbook x"}]}},
               "scope": {"files_read": READ, "blind_spots": spot("deploy.gitops", "deploy", "deployment handed to Flux")}}
        self.assertEqual(A.evaluate(CTL["delivery.deploy"], self.crit("automated_deploy", extra=man))["state"], "ABSENT")

    def test_the_usually_outside_controls_are_the_agreed_ones(self):
        self.assertEqual(sorted(c["id"] for c in CAT["controls"] if c.get("usually_outside")),
                         ["availability.backup_dr", "data.backups", "delivery.deploy", "observability.alerts_slos", "security.dependency_updates", "security.secret_scanning"])
        self.assertEqual(CTL["delivery.deploy"]["usually_outside"]["marker"], "deploy.gitops")


class CatalogueTest(unittest.TestCase):
    """T-1.10, T-1.14, T-1.15."""

    def test_named_file_searches_match_what_the_detectors_read(self):
        from detectors import identity, security
        self.assertEqual(CTL["knowledge.owners"]["search"]["names"], list(identity.CODEOWNERS))
        self.assertEqual(CTL["knowledge.owners"]["search"]["for"], "a CODEOWNERS file")  # not README or build, which it does not read
        self.assertEqual(CTL["security.dependency_updates"]["search"]["names"], list(security.UPDATE_FILES))

    def test_every_remedy_requirement_uses_the_declared_vocabulary(self):
        packs = A.load_remedy_packs(["modernise-plugin", "generic"])
        self.assertEqual([e for p in packs for e in A.vocabulary_errors(p)], [])
        with self.assertRaises(ValueError):
            path = os.path.join(tempfile.mkdtemp(), "bad.json")
            json.dump({"id": "bad", "version": "1", "remedies": {"r": {"title": "t", "requires": {"ci_system": ["gitlab"]}}}}, open(path, "w"))
            A.load_remedy_packs([path])

    def test_critical_sorts_before_high(self):
        self.assertLess(A.SEVERITY_ORDER["critical"], A.SEVERITY_ORDER["high"])


class DeclaredOnlyTest(unittest.TestCase):
    """T-1.12, narrowed by review round 3 (F3-1): only declared dependencies and inferred facts become PARTIAL."""

    def test_a_declared_dependency_with_no_configuration_is_partial(self):
        disc = {"stack": {"external_dependencies": {"value": [{"kind": "Observability", "technology": "OpenTelemetry", "at": ["build.gradle:3"]}],
                                                    "evidence": [{"kind": "file", "path": "build.gradle", "line_start": 3, "snippet": "opentelemetry"}]}}}
        c = cx(disc)
        c.kind = "service"
        r = A.evaluate(CTL["observability.tracing"], c)
        self.assertEqual((r["state"], r["level"]), ("PARTIAL", "declared"))
        self.assertIn("Declared only", r["summary"])

    def test_an_inferred_fact_is_partial_declared_only(self):
        r = A.eval_fact("identity.owners", cx({"identity": {"owners": {"value": ["@team"], "status": "INFERRED", "evidence": [{"kind": "file", "path": "x", "line_start": 1, "snippet": "x"}]}}}))
        self.assertEqual((r["state"], r["level"]), ("PARTIAL", "declared"))

    def boot34(self):
        r = F.make_repo(tempfile.mkdtemp(), "svc", {"build.gradle": "plugins {\n  id 'org.springframework.boot' version '3.4.1'\n}\n",
                                                    "src/main/resources/application.yml": "server:\n  port: 8080\n"})
        c = cx(discover.build(r))
        c.kind = "service"
        return c

    def test_no_secret_found_in_code_stays_present(self):
        self.assertEqual(A.evaluate(CTL["security.secrets_in_code"], self.boot34())["state"], "PRESENT")

    def test_no_literal_in_configuration_stays_present(self):
        self.assertEqual(A.evaluate(CTL["config.secrets_externalised"], self.boot34())["state"], "PRESENT")

    def test_graceful_shutdown_by_default_on_boot_34_stays_present(self):
        r = A.evaluate(CTL["runtime.graceful_shutdown"], self.boot34())
        self.assertEqual(r["state"], "PRESENT", r["summary"])


class ReportTest(unittest.TestCase):
    """T-1.13 and T-1.18 in the report data; the browser test renders them."""

    def test_the_report_carries_no_maturity_score_or_band(self):
        _, repos = F.make_portfolio(names=["orders-service"])
        out = tempfile.mkdtemp(prefix="r1-")
        import relate
        assert quiet(relate.main, ["analyse"] + list(repos.values()) + ["--out", out]) == 0
        A.build(out, CAT, [])
        data = R.collect(out, CAT, [], [{"path": repos["orders-service"], "criticality": "tier-1"}])
        app = data["apps"][0]
        self.assertNotIn("maturity", app["discovery"])
        em = app["dimensions"]["dimensions"]["engineering_maturity"]
        self.assertNotRegex(em["headline"], r"%|Low|Medium|High")
        self.assertFalse({"score", "band"} & set(em["values"]))
        self.assertEqual(app["source"]["criticality"], "tier-1")
        self.assertNotIn("Maturity", open(os.path.join(R.UI, "core.js")).read().split("/* ---------- drawer")[0])


class Audit6Test(unittest.TestCase):
    """T-1.20: the audit-6 minor items (design section 15)."""

    def test_a_scanner_the_pipeline_runs_on_part_of_the_code_is_enforced(self):
        ev = [{"kind": "file", "path": "build.gradle", "line_start": 18, "snippet": "apply from: 'quality.gradle'"},
              {"kind": "file", "path": "deploy/Jenkinsfile", "line_start": 20, "snippet": "sh './gradlew build'"}]
        disc = {"maturity": {"criteria": [{"id": "sast", "result": "PARTIAL", "facts": ["security.sast_root_only", "security.sast_in_pipeline"]}]},
                "security": {"sast_root_only": {"value": True, "status": "CONFIRMED", "evidence": ev[:1], "note": "applied to the root project only"},
                             "sast_in_pipeline": {"value": True, "status": "INFERRED", "evidence": ev[1:]}}}
        r = A.eval_criterion("sast", cx(disc))
        self.assertEqual((r["state"], r["level"]), ("PARTIAL", "enforced"))

    def test_the_unit_test_uplift_is_not_offered_to_a_cobertura_project(self):
        packs = A.load_remedy_packs(["modernise-plugin", "generic"])
        c = cx({"tests": {"coverage_tool_configured": {"value": "cobertura"}}})
        self.assertNotIn("unit", [r["key"] for r in A.remedies_for(CTL["testing.coverage_gate"], packs, c)])  # a JaCoCo uplift for a Cobertura build
        c = cx({"tests": {"coverage_tool_configured": {"value": "jacoco"}}})
        self.assertEqual(A.remedies_for(CTL["testing.coverage_gate"], packs, c)[0]["key"], "unit")

    def test_a_missing_health_endpoint_gets_a_health_remedy_not_a_configuration_change(self):
        self.assertEqual([r["key"] for r in A.remedies_for(CTL["observability.health"], A.load_remedy_packs(["generic"]), cx({}))], ["health_endpoint"])

    def test_no_resilience_library_stays_not_found_outside_spring(self):
        disc = {"stack": {"app_framework": {"value": {"name": "dropwizard", "label": "Dropwizard"}}, "http_client_libraries": {"value": ["Jersey"]}},
                "runtime": {"retries_breakers": {"value": {"state": "ABSENT", "summary": "No retry or circuit breaker found in code or configuration",
                                                           "framework_neutral": "no retry or circuit-breaker library is declared in the build, and none is used in code"},
                                                 "status": "NOT_FOUND", "evidence": []}}, "scope": {"files_read": READ}}
        c = cx(disc)
        c.kind = "service"
        r = A.evaluate(CTL["runtime.retries_breakers"], c)
        self.assertEqual(r["state"], "ABSENT")
        self.assertIn("Dropwizard's own client settings are not read", r["summary"])
        self.assertTrue(r["framework_neutral"])  # verify CON-9 accepts it

    def test_context_load_only_classes_are_said_in_the_summary(self):
        disc = {"maturity": {"criteria": [{"id": "unit_tests_exist", "result": "MET", "facts": ["tests.unit_tests"]}]},
                "tests": {"unit_tests": {"value": {"test_classes": 3, "context_load_only": 1}, "status": "CONFIRMED",
                                         "evidence": [{"kind": "file", "path": "src/test/java/ATest.java", "line_start": 5, "snippet": "@Test"}]}}}
        self.assertEqual(A.eval_criterion("unit_tests_exist", cx(disc))["summary"],
                         "Found: 3 test classes; 1 more only checks that the application context starts and is not counted")


if __name__ == "__main__":
    unittest.main()


class Phase1FinishTest(unittest.TestCase):
    """T-1.25 to T-1.29: reference-data status, verify at the run's own source state, an independent status recomputation, the
    internal report name, and runs that are never rebuilt in place once reviewed."""

    @classmethod
    def setUpClass(cls):
        cls.root, repos = F.make_portfolio(names=["orders-service", "notifier-a"])
        cls.repos = sorted(repos.values())
        cls.ws = tempfile.mkdtemp(prefix="ws-")
        assert quiet(cli.main, ["scan", "--client", "c", "--workspace", cls.ws, "--json"] + cls.repos) == 0
        cls.rd = cli.resolve_run(os.path.join(cls.ws, "c"))

    def aspects(self, app="orders-service"):
        return json.load(open(os.path.join(self.rd, "analysis", app, "aspects.json")))

    def test_support_dates_carry_their_source_and_review_status(self):
        cs = [c for a in self.aspects()["aspects"] for c in a["controls"] if c["id"].startswith("platform.") and c["id"] != "platform.libraries_current"]
        self.assertTrue(cs)
        for c in cs:
            self.assertEqual((c["reference"]["source"], c["reference"]["status"]), ("engine/rules/lifecycle.v1.json", "unreviewed"))
            if c["state"] != "UNKNOWN":
                self.assertIn("reference data unreviewed", c["summary"])

    def test_a_support_result_without_its_review_status_is_caught(self):
        p = os.path.join(self.rd, "analysis", "orders-service", "aspects.json")
        clean = open(p).read()
        try:
            doc = json.loads(clean)
            c = next(c for a in doc["aspects"] for c in a["controls"] if c["id"] == "platform.java_support")
            c["reference"] = None
            json.dump(doc, open(p, "w"))
            self.assertIn("ACC-13", {x["rule"] for x in V.check(self.rd)["problems"]})
        finally:
            open(p, "w").write(clean)

    def test_verify_recomputes_status_without_the_writers_rollup(self):
        # a writer whose rollup says "in place" for everything is caught, because verify does not ask that function
        out = os.path.join(self.rd, "analysis")
        real = A.rollup
        try:
            with mock.patch.object(A, "rollup", side_effect=lambda cs: ("in_place",) + real(cs)[1:]):
                A.build(out, CAT, A.load_remedy_packs(["generic"]))
            self.assertIn("CON-2", {x["rule"] for x in V.check(self.rd)["problems"]})
        finally:
            A.build(out, CAT, A.load_remedy_packs(["generic"]))
        for a in self.aspects()["aspects"]:  # and on a correct build both agree
            self.assertEqual(V.recompute(a["controls"]), (a["status"], a["coverage"]))

    def git_repo(self, body):
        d = tempfile.mkdtemp(prefix="src-")
        with open(os.path.join(d, "a.txt"), "w") as fh:
            fh.write(body)
        for args in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "c"]):
            SRC._git(args, cwd=d)
        return d

    def test_verify_reads_a_changed_repository_at_the_recorded_commit(self):
        import evidence  # engine
        d = self.git_repo("one\n")
        fp, sha = evidence.inventory_fingerprint(d, evidence.walk(d)), SRC._head(d)
        with open(os.path.join(d, "a.txt"), "w") as fh:
            fh.write("two\n")
        view, tmp, why = V.source_view(d, fp, {"commit": sha, "changed_files": 0})
        try:
            self.assertIsNone(why)
            self.assertEqual(open(os.path.join(view, "a.txt")).read(), "one\n")  # the run's content, not today's
            self.assertEqual(open(os.path.join(d, "a.txt")).read(), "two\n")     # and the repository was not touched
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_verify_refuses_when_the_state_at_the_run_cannot_be_rebuilt(self):
        import evidence  # engine
        d = self.git_repo("one\n")
        fp = evidence.inventory_fingerprint(d, evidence.walk(d))
        with open(os.path.join(d, "a.txt"), "w") as fh:
            fh.write("two\n")
        _, _, why = V.source_view(d, fp, {"commit": SRC._head(d), "changed_files": 3})
        self.assertIn("uncommitted", why)
        _, _, why = V.source_view(d, fp, {"commit": "0" * 40, "changed_files": 0})
        self.assertIn("no longer in it", why)
        _, _, why = V.source_view(d, fp, {})
        self.assertIn("no commit to rebuild", why)
        view, _, why = V.source_view(d, evidence.inventory_fingerprint(d, evidence.walk(d)), {})
        self.assertEqual((view, why), (d, None))  # unchanged: the working tree is read

    def test_the_report_file_name_says_internal(self):
        self.assertTrue(os.path.isfile(os.path.join(self.rd, "report-internal.html")))
        self.assertFalse(os.path.exists(os.path.join(self.rd, "report.html")))
        self.assertEqual(cli.summarise(self.rd)["report"], os.path.join(self.rd, "report-internal.html"))

    def test_report_rebuilds_the_html_only(self):
        p = os.path.join(self.rd, "analysis", "orders-service", "aspects.json")
        before = open(p).read()
        with mock.patch.object(A, "build", side_effect=AssertionError("report must not rebuild the trace")):
            self.assertEqual(quiet(cli.main, ["report", self.rd]), 0)
        self.assertEqual(open(p).read(), before)

    def test_a_reviewed_run_is_never_rebuilt_in_place(self):
        review = os.path.join(self.rd, "review.json")
        p = os.path.join(self.rd, "analysis", "orders-service", "aspects.json")
        before, runs = open(p).read(), set(os.listdir(os.path.dirname(self.rd)))
        open(review, "w").write("{}")
        try:
            self.assertEqual(quiet(cli.main, ["aspects", self.rd, "--remedies", "generic"]), 0)
            new = set(os.listdir(os.path.dirname(self.rd))) - runs
            self.assertEqual(len(new), 1)
            self.assertTrue(next(iter(new)).endswith("-rebuild"))
            self.assertEqual(open(p).read(), before)
            self.assertFalse(os.path.exists(os.path.join(os.path.dirname(self.rd), next(iter(new)), "review.json")))
        finally:
            os.remove(review)

    def test_each_runs_commit_is_pinned_in_our_own_clones_only(self):
        d = self.git_repo("x\n")
        repos_dir = os.path.dirname(d)
        s = SRC.Source("https://git.example.invalid/a/b.git") if hasattr(SRC, "Source") else None
        if s is None:
            self.skipTest("no Source class")
        s.remote, s.path, s.commit = True, d, SRC._head(d)
        cli.pin([s], repos_dir, "20990101-000000")
        self.assertEqual(SRC._git(["rev-parse", "refs/app-insight/runs/20990101-000000"], cwd=d).stdout.strip(), s.commit)
        local = self.git_repo("y\n")
        s2 = SRC.Source(local)
        s2.remote, s2.path, s2.commit = False, local, SRC._head(local)
        cli.pin([s2], tempfile.mkdtemp(), "20990101-000000")
        self.assertNotEqual(SRC._git(["rev-parse", "-q", "--verify", "refs/app-insight/runs/20990101-000000"], cwd=local).returncode, 0)
