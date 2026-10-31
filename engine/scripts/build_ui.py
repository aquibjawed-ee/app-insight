#!/usr/bin/env python3
"""Embed N discovery.json files into one self-contained HTML page (no server, no network).

  build_ui.py PATH [PATH ...] --out portfolio.html
PATH is a discovery.json file or a directory searched recursively for discovery.json.
Every input is schema-validated first; an invalid file aborts the build (exit 1).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import validate  # noqa: E402

TEMPLATE = os.path.join(HERE, "..", "assets", "ui_template.html")


def collect(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, names in os.walk(p):
                dirs.sort()
                out += [os.path.join(root, n) for n in sorted(names) if n == "discovery.json"]
        else:
            out.append(p)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    files = collect(a.paths)
    if not files:
        print("no discovery.json found", file=sys.stderr)
        return 1
    apps = []
    for f in files:
        doc = json.load(open(f, encoding="utf-8"))
        errs = validate.validate(doc)
        if errs:
            print("%s invalid: %s" % (f, errs[0]), file=sys.stderr)
            return 1
        apps.append(doc)
    apps.sort(key=lambda d: d["identity"]["app_id"]["value"] or "")
    data = json.dumps(apps, sort_keys=True).replace("</", "<\\/")
    html = open(TEMPLATE, encoding="utf-8").read().replace("/*__DATA__*/[]", data)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("wrote %s (%d app%s)" % (a.out, len(apps), "" if len(apps) == 1 else "s"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
