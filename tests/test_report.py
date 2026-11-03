"""End-to-end report: analysis -> aspects -> HTML. Self-contained, no unfilled placeholders, and every view renders in a real
browser without a script error or a leaked undefined/NaN/null. Moved from the engine's test_platform when the report became
part of the product."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(1, os.path.join(HERE, "..", "engine", "tests"))
os.environ["DISCOVERY_FIXED_TIME"] = "2026-10-29T00:00:00Z"

from app_insight import aspects as A  # noqa: E402
from app_insight import report as R  # noqa: E402
import graph_fixtures as F  # noqa: E402
import relate  # noqa: E402

CHROME = next((p for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", shutil.which("google-chrome") or "", shutil.which("chromium") or "") if p and os.path.exists(p)), None)


class ReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.repos = F.make_portfolio()
        repos = cls.repos
        cls.out = tempfile.mkdtemp(prefix="rep-")
        assert relate.main(["analyse"] + sorted(repos.values()) + ["--out", cls.out]) == 0
        for sc in (["--scenario", "java_runtime", "--to", "17"], ["--scenario", "messaging_schema", "--topic", "orders.created"]):
            assert relate.main(["impact", "--out", cls.out] + sc) == 0
        cat, packs = A.load_catalogue(), A.load_remedy_packs(["modernise-plugin", "generic"])
        cls.docs = A.build(cls.out, cat, packs)
        cls.html = os.path.join(cls.out, "report.html")
        src = [{"path": cls.repos["orders-service"], "criticality": "tier-1", "team": "payments", "status": "local"}]  # criticality from a list file
        R.build(cls.out, cls.html, cat, packs, src, client="test-client")

    def test_report_has_no_unfilled_placeholders_and_is_self_contained(self):
        text = open(self.html).read()
        for ph in ("/*__DATA__*/", "/*__C4STYLE__*/", "/*__CSS__*/", "//__JS__"):
            self.assertNotIn(ph, text)
        self.assertIsNone(re.search(r"""(?:src|href)=["']https?://""", text))  # no network resources
        self.assertNotIn("fetch(", text)

    @unittest.skipUnless(CHROME, "Chrome/Chromium not installed")
    def test_report_renders_every_view_in_a_browser_without_errors(self):
        text = open(self.html).read()
        probe = "<script>window.__errs=[];window.addEventListener('error',function(e){__errs.push(String(e.message))});</script>"
        tail = "<script>document.documentElement.setAttribute('data-errs',JSON.stringify(window.__errs));</script>"
        page = os.path.join(self.out, "probe.html")
        open(page, "w").write(text.replace("<script>\n\"use strict\"", probe + "<script>\n\"use strict\"", 1).replace("</body>", tail + "</body>"))
        app = "orders-service"
        finding = self.docs[app]["findings"][0]
        views = ["portfolio", "apps", "apps?f=unmatched,tests", "apps?f=crit:tier-1", "map", "gaps", "gaps?v=app", "roadmap", "impact", "about", "finding/" + finding,
                 "assessment/" + app, "assessment/%s/runtime" % app, "assessment/notifier-a"] + ["app/%s/%s" % (a, t) for a in (app, "notifier-a") for t in ("overview", "components", "dependencies", "configuration", "findings", "evidence")]
        for v in views:
            dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--virtual-time-budget=4000", "--dump-dom", "file://%s#/%s" % (page, v)],
                                 capture_output=True, text=True, timeout=90).stdout
            self.assertIn("data-errs", dom, v)
            self.assertEqual(re.search(r'data-errs="([^"]*)"', dom).group(1), "[]", v)
            visible = re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", "", dom, flags=re.S))
            for bad in ("undefined", "NaN", "[object", "null"):
                self.assertNotIn(bad, visible, "%s shows %s" % (v, bad))
            self.assertGreater(len(visible.strip()), 300, v)
        dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--virtual-time-budget=4000", "--dump-dom", "file://%s#/assessment/%s" % (page, app)], capture_output=True, text=True, timeout=90).stdout
        self.assertIn("Controls by aspect", dom)
        self.assertIn("Aspect scorecard", dom)
        self.assertIn("criticality: tier-1", dom)  # T-1.18: the list file's criticality is shown
        self.assertIn("Internal: not validated", dom)  # T-1.19: every page says it is not for client use
        self.assertIn("Verify: not run", dom)
        dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--virtual-time-budget=4000", "--dump-dom", "file://%s#/apps?f=crit:tier-1" % page], capture_output=True, text=True, timeout=90).stdout
        rows = re.findall(r'<tr tabindex="0" data-go="#/app/([^/"]+)/overview"', dom)
        self.assertEqual(rows, ["orders-service"])  # filterable by criticality
        self.assertNotIn(">Maturity<", dom)  # T-1.13: no maturity percentage tile


if __name__ == "__main__":
    unittest.main()
