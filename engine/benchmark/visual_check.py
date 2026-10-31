#!/usr/bin/env python3
"""Visual regression check for the multi-application HTML view. Stdlib only; needs Chrome or Chromium installed.

  visual_check.py --out DIR [--width 1440] [--screenshots]

Builds one portfolio from benchmark fixtures that exercise the UI (gate wired, partial-run coverage, multi-module, external suites,
remote includes, library, empty), then opens every application x tab in headless Chrome and asserts, on the rendered DOM:
the requested tab is the selected one; the tab is not empty; no `undefined`, `NaN`, `null` or `[object` in visible text; no
uncaught script error; every row of the main table has exactly as many cells as the header has leaf columns. With --screenshots
it also saves PNGs of the collapsed table and every tab so a person can look at them (pixel baselines are not kept: font
rendering differs per machine). Exit codes: 0 pass, 1 a check failed, 2 could not run.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_benchmark as rb  # noqa: E402
import build_ui  # noqa: E402

CASES = ["maven_jacoco_gate_reached_by_ci", "gradle_kotlin_kover_gate_wired", "kover_report_from_partial_run", "gradle_multimodule_settings",
         "gitlab_external_suites_triggered", "gitlab_remote_include_hides_pipeline", "java_library_published_no_http", "empty_repository",
         "deps_spring_boot_postgres_redis_kafka", "modules_maven_named_with_roles", "container_dockerfile_base_images",
         "container_jib_maven_configured", "container_spring_boot_maven_build_image_configured", "container_quarkus_container_image_enabled_in_config"]
TABS = ["about", "stack", "tests", "build", "operations", "security", "notes"]
FORBIDDEN = ("undefined", "NaN", "null", "[object")
CHROMES = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome", "chromium", "chromium-browser"]


def find_chrome():
    for c in CHROMES:
        if os.path.isabs(c) and os.path.exists(c):
            return c
        if not os.path.isabs(c) and shutil.which(c):
            return shutil.which(c)
    return None


def run_chrome(chrome, args):
    """One throwaway profile per call: concurrent headless instances sharing a profile lock each other and hang."""
    prof = tempfile.mkdtemp(prefix="chrome-profile-")
    try:
        return subprocess.run([chrome, "--headless", "--disable-gpu", "--no-first-run", "--user-data-dir=" + prof, "--virtual-time-budget=2500"] + args,
                              capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 1, "", "timeout")
    finally:
        shutil.rmtree(prof, ignore_errors=True)


def dump(chrome, url, width):
    return run_chrome(chrome, ["--window-size=%d,1200" % width, "--dump-dom", url]).stdout


def visible_text(dom):
    dom = re.sub(r"<script\b.*?</script>", " ", dom, flags=re.S)
    dom = re.sub(r"<style\b.*?</style>", " ", dom, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", dom))


def leaf_columns(dom):
    head = re.search(r"<thead[^>]*>(.*?)</thead>", dom, re.S)
    rows = re.findall(r"<tr>(.*?)</tr>", head.group(1), re.S) if head else []
    if len(rows) < 2:
        return None
    return len(re.findall(r'<th[^>]*rowspan="2"', rows[0])) + len(re.findall(r"<th\b", rows[1]))


def check_page(dom, app, tab, n_apps):
    errs = []
    if "Uncaught" in dom:
        errs.append("uncaught script error")
    sel = re.findall(r'<button[^>]*aria-selected="true"[^>]*data-id="([^"]+)"|<button[^>]*data-id="([^"]+)"[^>]*aria-selected="true"', dom)
    got = [a or b for a, b in sel]
    if got != [tab]:
        errs.append("selected tab is %s, expected %s" % (got, tab))
    if not re.search(r'<table class="dt ct"|class="about"|class="empty"|<div class="kv">', dom):
        errs.append("tab rendered no table or text")
    text = visible_text(dom)
    for tok in FORBIDDEN:
        if re.search(r"(?<![\w-])" + re.escape(tok) + r"(?![\w-])", text):
            errs.append("visible text contains %r" % tok)
    if 'data-fit="overflows"' in dom:
        errs.append("the main table is wider than the viewport (horizontal scroll)")
    leaf = leaf_columns(dom)
    rows = re.findall(r'<tr class="row [^"]*">(.*?)</tr>', dom, re.S)
    if len(rows) != n_apps:
        errs.append("main table has %d rows, expected %d" % (len(rows), n_apps))
    for r in rows:
        n = len(re.findall(r"<td\b", r))
        if leaf is None or n != leaf:
            errs.append("a main-table row has %s cells, header has %s leaf columns" % (n, leaf))
            break
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--screenshots", action="store_true")
    a = ap.parse_args(argv)
    chrome = find_chrome()
    if not chrome:
        print("Chrome or Chromium not found", file=sys.stderr)
        return 2
    os.makedirs(a.out, exist_ok=True)
    dirs, apps = [], []
    for n in CASES:
        case_dir = os.path.join(HERE, "fixtures", n)
        case = json.load(open(os.path.join(case_dir, "case.json")))
        doc, _ = rb.run_engine(case_dir, case.get("setup") or {})
        d = os.path.join(a.out, "data", n)
        os.makedirs(d, exist_ok=True)
        json.dump(doc, open(os.path.join(d, "discovery.json"), "w"), indent=2, sort_keys=True)
        dirs.append(d)
        apps.append(doc["identity"]["app_id"]["value"])
    portfolio = os.path.join(a.out, "portfolio.html")
    if build_ui.main(dirs + ["--out", portfolio]) != 0:
        print("build_ui failed", file=sys.stderr)
        return 2
    url = "file://" + portfolio
    jobs = [(app, tab) for app in apps for tab in TABS]
    with ThreadPoolExecutor(max_workers=4) as ex:
        doms = list(ex.map(lambda j: dump(chrome, "%s#app=%s&tab=%s" % (url, j[0], j[1]), a.width), jobs))
    failures = []
    for (app, tab), dom in zip(jobs, doms):
        for e in check_page(dom, app, tab, len(apps)):
            failures.append("%s/%s: %s" % (app, tab, e))
    shots = []
    if a.screenshots:
        def shot(j):
            app, tab = j
            out = os.path.join(a.out, "shots", "%s_%s.png" % (app, tab or "collapsed"))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            frag = "#app=%s&tab=%s" % (app, tab) if tab else ""
            run_chrome(chrome, ["--window-size=%d,1300" % a.width, "--screenshot=" + out, url + frag])
            return out
        with ThreadPoolExecutor(max_workers=4) as ex:
            shots = list(ex.map(shot, [(apps[0], None)] + [(ap_, t) for ap_ in apps for t in TABS]))
    report = {"apps": apps, "tabs": TABS, "pages_checked": len(jobs), "failures": failures, "screenshots": shots, "passed": not failures}
    json.dump(report, open(os.path.join(a.out, "visual_report.json"), "w"), indent=2)
    print("visual check: %d pages (%d apps x %d tabs), %d failures" % (len(jobs), len(apps), len(TABS), len(failures)))
    for f in failures:
        print("  FAIL " + f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
