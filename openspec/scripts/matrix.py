#!/usr/bin/env python3
"""Recount and check the AS-IS coverage matrix (tasks.md T-1.2, T-1.3; rule R-20).

Reads openspec/changes/asis-baseline/coverage-matrix.md: item rows
`| item | method | STATUS | where |` under `## A<n>` headings, and the `## Counts` table at the bottom.

  --check  recompute the counts and compare them with the table (exit 1 on a mismatch); also fail when a
           BUILT row cites no test (`path::Test.method` or `path::method`) or cites one that does not exist.
  --write  rewrite the counts table with the recomputed numbers (labels and layout kept).

Python 3.9, standard library only.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEFAULT = os.path.join(REPO, "openspec", "changes", "asis-baseline", "coverage-matrix.md")

STATUSES = ["BUILT", "PARTIAL", "PLANNED", "NOT_ASSESSED", "OUT"]
AREA = re.compile(r"^## (A\d+)\b")
TEST_REF = re.compile(r"((?:[\w.-]+/)*test[\w-]*\.py)::([A-Za-z_]\w*)(?:\.([A-Za-z_]\w*))?")
TOTAL = re.compile(r"\*\*(\d+) items in (\d+) areas \((A\d+)-(A\d+)\)\*\*")


def cells(line):
    parts = re.split(r"(?<!\\)\|", line.strip())
    return [p.strip() for p in parts[1:-1]]


def is_separator(row):
    return all(re.fullmatch(r":?-{3,}:?", c) for c in row)


def parse(lines):
    """Return (rows, counts_table) where rows are (line_no, area, cells) and counts_table maps
    status -> (line_no, cells)."""
    rows, counts, area, in_counts, seen_header = [], {}, None, False, False
    for no, line in enumerate(lines):
        if line.startswith("## "):
            m = AREA.match(line)
            area = m.group(1) if m else None
            in_counts = line.strip() == "## Counts"
            seen_header = False
            continue
        if not line.lstrip().startswith("|"):
            continue
        row = cells(line)
        if is_separator(row):
            continue
        if area:
            if not seen_header:
                seen_header = True  # the `| Item | How | Status | ... |` header
                continue
            rows.append((no, area, row))
        elif in_counts:
            if not seen_header:
                seen_header = True
                continue
            label = row[0]
            key = next((s for s in STATUSES if label.split(" ")[0] == s), None)
            if key:
                counts[key] = (no, row)
            elif TOTAL.search(label) or TOTAL.search(" ".join(row)):
                counts["TOTAL"] = (no, row)
    return rows, counts


def recount(rows):
    n = {s: 0 for s in STATUSES}
    for _, _, row in rows:
        n[row[2]] += 1
    areas = sorted({a for _, a, _ in rows}, key=lambda a: int(a[1:]))
    return n, areas


def test_ref_problems(text):
    """Every test reference in text must name an existing file and a def (and class) in it."""
    refs = TEST_REF.findall(text)
    problems = []
    for path, first, second in refs:
        full = os.path.join(REPO, path)
        if not os.path.isfile(full):
            problems.append("%s: no such file" % path)
            continue
        with open(full, encoding="utf-8") as f:
            src = f.read()
        if second:
            if not re.search(r"^class %s\b" % re.escape(first), src, re.M):
                problems.append("%s::%s: no such class" % (path, first))
            if not re.search(r"^\s+def %s\(" % re.escape(second), src, re.M):
                problems.append("%s::%s.%s: no such test" % (path, first, second))
        elif not re.search(r"^\s*(?:def %s\(|class %s\b)" % (re.escape(first), re.escape(first)), src, re.M):
            problems.append("%s::%s: no such test" % (path, first))
    return refs, problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    ap.add_argument("--file", default=DEFAULT)
    args = ap.parse_args(argv)

    with open(args.file, encoding="utf-8") as f:
        lines = f.read().split("\n")
    rows, counts = parse(lines)
    errors = []
    for no, area, row in rows:
        if len(row) < 4:
            errors.append("line %d (%s): expected 4 columns, got %d" % (no + 1, area, len(row)))
        elif row[2] not in STATUSES:
            errors.append("line %d (%s): unknown status %r" % (no + 1, area, row[2]))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    n, areas = recount(rows)
    total = sum(n.values())
    missing = [s for s in STATUSES + ["TOTAL"] if s not in counts]
    if missing:
        print("counts table lacks rows: %s" % ", ".join(missing), file=sys.stderr)
        return 1

    if args.write:
        for s in STATUSES:
            no, row = counts[s]
            row = row[:1] + [str(n[s])] + row[2:]
            lines[no] = "| " + " | ".join(row) + " |"
        no, row = counts["TOTAL"]
        label = "**%d items in %d areas (%s-%s)**" % (total, len(areas), areas[0], areas[-1])
        lines[no] = "| " + " | ".join([TOTAL.sub(lambda _: label, row[0])] + row[1:]) + " |"
        with open(args.file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print("written: %s, total %d in %d areas" % (", ".join("%s %d" % (s, n[s]) for s in STATUSES), total, len(areas)))
        return 0

    for s in STATUSES:
        shown = counts[s][1][1]
        if shown != str(n[s]):
            errors.append("count %s: table says %s, rows give %d" % (s, shown, n[s]))
    m = TOTAL.search(" ".join(counts["TOTAL"][1]))
    expected = (str(total), str(len(areas)), areas[0], areas[-1])
    if not m or m.groups() != expected:
        errors.append("total: table says %s, rows give %s items in %s areas (%s-%s)"
                      % (m.group(0) if m else "nothing", *expected))
    for no, area, row in rows:
        refs, problems = test_ref_problems(row[3])
        for p in problems:
            errors.append("line %d (%s): %s" % (no + 1, area, p))
        if row[2] == "BUILT" and not refs:
            errors.append("line %d (%s): BUILT with no test reference: %s" % (no + 1, area, row[0]))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("ok: %s, total %d in %d areas; every BUILT row cites a test"
          % (", ".join("%s %d" % (s, n[s]) for s in STATUSES), total, len(areas)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
