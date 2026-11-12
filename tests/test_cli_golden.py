import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "expected_sample_output.txt"


def run_sample():
    return subprocess.run(
        [sys.executable, "-m", "report", "data/sample.csv"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class SampleGolden(unittest.TestCase):
    def test_sample_output_matches_golden(self):
        result = run_sample()
        self.assertEqual(result.returncode, 0)
        expected = GOLDEN.read_text(encoding="utf-8", newline="")
        self.assertEqual(result.stdout, expected)

    def test_sample_run_writes_nothing_to_stderr(self):
        self.assertEqual(run_sample().stderr, "")


if __name__ == "__main__":
    unittest.main()
