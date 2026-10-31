"""The relationship benchmark is a gate: every hand-labelled case must pass (no forbidden edge, no unlabelled edge, integrity, determinism)."""
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(HERE, "..", "benchmark", "relationship_benchmark.py")


class RelationshipBenchmarkGate(unittest.TestCase):
    def test_all_labelled_cases_pass(self):
        r = subprocess.run([sys.executable, RUNNER], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-500:])
        self.assertIn("false positives 0", r.stdout)


if __name__ == "__main__":
    unittest.main()
