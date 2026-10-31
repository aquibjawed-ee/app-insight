"""The report must stay usable with hundreds of applications: dense table, filters, sorting, pagination, deep links, no global hairball."""
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
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


def clone_apps(data, n):
    """Grow a real analysis to n applications by renaming copies of its applications (analysis data only; graph left as is)."""
    base = data["apps"]
    out = []
    for i in range(n):
        a = copy.deepcopy(base[i % len(base)])
        a["name"] = "%s-%03d" % (a["name"], i)
        out.append(a)
    d = copy.deepcopy(data)
    d["apps"] = out
    return d


class ScaleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root, repos = F.make_portfolio()
        cls.out = tempfile.mkdtemp(prefix="scale-")
        assert relate.main(["analyse"] + sorted(repos.values()) + ["--out", cls.out]) == 0
        cat, packs = A.load_catalogue(), A.load_remedy_packs(["generic"])
        A.build(cls.out, cat, packs)
        cls.data = R.collect(cls.out, cat, packs)

    def page(self, data, route, js=""):
        html = R.render(data)
        probe = "<script>window.__errs=[];window.addEventListener('error',function(e){__errs.push(String(e.message))});</script>"
        tail = "<script>%s;document.documentElement.setAttribute('data-errs',JSON.stringify(window.__errs));</script>" % js
        html = html.replace("<script>\n\"use strict\"", probe + "<script>\n\"use strict\"", 1).replace("</body>", tail + "</body>")
        path = os.path.join(self.out, "scale.html")
        open(path, "w").write(html)
        t = time.time()
        r = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--virtual-time-budget=6000", "--dump-dom", "file://%s#/%s" % (path, route)], capture_output=True, text=True, timeout=120)
        return r.stdout, time.time() - t

    def text(self, dom):
        body = re.sub(r"<script.*?</script>|<style.*?</style>", "", dom, flags=re.S)
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))

    def test_the_generated_page_carries_no_full_diagram_above_the_threshold(self):
        big = clone_apps(self.data, 40)
        self.assertEqual(self.data["portfolio"]["views"]["context"] is not None, len(self.data["apps"]) <= R.FULL_MAP_MAX)
        self.assertEqual(R.FULL_MAP_MAX, 12)
        self.assertEqual(len(big["apps"]), 40)

    @unittest.skipUnless(CHROME, "Chrome/Chromium not installed")
    def test_two_hundred_applications_render_as_a_paginated_table_without_errors(self):
        data = clone_apps(self.data, 200)
        dom, secs = self.page(data, "apps")
        self.assertEqual(re.search(r'data-errs="([^"]*)"', dom).group(1), "[]")
        self.assertEqual(len(re.findall(r"<tr tabindex", re.sub(r"<script.*?</script>", "", dom, flags=re.S))), 50)                      # one page, not 200 rows
        t = self.text(dom)
        self.assertIn("Showing 200 of 200 applications", t)
        self.assertIn("Page 1 / 4", t)
        self.assertLess(secs, 60)

    @unittest.skipUnless(CHROME, "Chrome/Chromium not installed")
    def test_deep_links_filter_the_table_and_say_so(self):
        data = clone_apps(self.data, 200)
        dom, _ = self.page(data, "apps?f=ended")
        t = self.text(dom)
        m = re.search(r"Showing (\d+) of 200 applications", t)
        self.assertTrue(m and 0 < int(m.group(1)) < 200, t[:300])
        self.assertIn("Vendor support ended ✕", t)
        self.assertIn("Clear filters", t)

    @unittest.skipUnless(CHROME, "Chrome/Chromium not installed")
    def test_default_order_puts_the_worst_applications_first(self):
        data = clone_apps(self.data, 30)
        dom, _ = self.page(data, "apps")
        first = re.search(r"<tbody>.*?<tr tabindex.*?</tr>", re.sub(r"<script.*?</script>", "", dom, flags=re.S), re.S).group(0)
        self.assertRegex(first, r"cell (?:bad|warn)")

    @unittest.skipUnless(CHROME, "Chrome/Chromium not installed")
    def test_portfolio_answers_questions_in_plain_language_and_drops_the_hairball(self):
        data = clone_apps(self.data, 60)
        dom, _ = self.page(data, "portfolio")
        t = self.text(dom)
        self.assertIn("What stands out", t)
        self.assertRegex(t, r"\d+ of 60 applications use a Java or Spring Boot version whose vendor support has ended")
        self.assertNotIn("Links", t)                          # renamed: it was not self-explanatory
        self.assertIn("Unmatched calls", t)
        self.assertNotIn("Health at a glance", t)             # replaced by the filterable table
        self.assertEqual(re.search(r'data-errs="([^"]*)"', dom).group(1), "[]")
        dom, _ = self.page(data, "map")
        t = self.text(dom)
        self.assertIn("Most connected applications", t)
        self.assertIn("would be unreadable", t)
        self.assertNotIn("<svg class=\"c4\"", dom.split("</main>")[0] if "</main>" in dom else dom)


if __name__ == "__main__":
    unittest.main()
