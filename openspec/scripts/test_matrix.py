"""Tests for openspec/scripts/matrix.py (tasks.md T-1.2, T-1.3; rule R-20). Run: python3 -m unittest openspec/scripts/test_matrix.py"""
import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matrix  # noqa: E402

REF = "`openspec/scripts/test_matrix.py::MatrixTest.test_check_passes_on_a_consistent_file`"
DOC = """# m

## A0. One

| Item | How | Status | Where today / note |
|---|---|---|---|
| a | F | BUILT | `x.y`; test %s |
| b | F | PLANNED | |

## A1. Two

| Item | How | Status | Where today / note |
|---|---|---|---|
| c | F | PARTIAL | built, no test |

## Counts

| Status | Items |
|---|---|
| BUILT (implemented, not validated) | 1 |
| PARTIAL | 1 |
| PLANNED | 1 |
| NOT_ASSESSED (a control exists, no detector yet) | 0 |
| OUT | 0 |
| **Total** | **3 items in 2 areas (A0-A1)** |
""" % REF


def run(text, *args):
    p = os.path.join(tempfile.mkdtemp(), "m.md")
    with open(p, "w") as fh:
        fh.write(text)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
        rc = matrix.main(list(args) + ["--file", p])
    with open(p) as fh:
        return rc, fh.read(), err.getvalue()


class MatrixTest(unittest.TestCase):
    def test_check_passes_on_a_consistent_file(self):
        self.assertEqual(run(DOC, "--check")[0], 0)

    def test_check_fails_when_a_count_drifts(self):
        rc, _, err = run(DOC.replace("| PLANNED | 1 |", "| PLANNED | 4 |"), "--check")
        self.assertEqual(rc, 1)
        self.assertIn("count PLANNED", err)

    def test_check_fails_on_a_built_row_without_a_test(self):
        rc, _, err = run(DOC.replace("`x.y`; test " + REF, "`x.y`"), "--check")
        self.assertEqual(rc, 1)
        self.assertIn("BUILT with no test reference: a", err)

    def test_check_fails_on_a_test_that_does_not_exist(self):
        rc, _, err = run(DOC.replace("test_check_passes_on_a_consistent_file`", "test_never_written`"), "--check")
        self.assertEqual(rc, 1)
        self.assertIn("no such test", err)

    def test_write_recounts_and_keeps_the_table_format(self):
        moved = DOC.replace("| c | F | PARTIAL |", "| c | F | OUT |")
        rc, text, _ = run(moved, "--write")
        self.assertEqual(rc, 0)
        self.assertIn("| PARTIAL | 0 |", text)
        self.assertIn("| OUT | 1 |", text)
        self.assertIn("| **Total** | **3 items in 2 areas (A0-A1)** |", text)
        self.assertEqual(run(text, "--check")[0], 0)

    def test_an_unknown_status_is_refused(self):
        self.assertEqual(run(DOC.replace("| b | F | PLANNED |", "| b | F | DONE |"), "--check")[0], 1)


if __name__ == "__main__":
    unittest.main()
