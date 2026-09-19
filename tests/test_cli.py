from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from aoae.cli import main
from aoae.contracts import load_spec
from aoae.experiment import canonical_json, run_experiment, write_record


ROOT = Path(__file__).parents[1]
SPEC_PATH = ROOT / "research" / "experiments" / "0001-synthetic-mean-reversion" / "spec.json"


class CliFailClosedTests(unittest.TestCase):
    def test_verify_rejects_a_tampered_record(self) -> None:
        spec = load_spec(SPEC_PATH)
        record_text = canonical_json(run_experiment(spec))
        tampered = record_text.replace("infrastructure_validated", "alpha_validated", 1)
        with patch("aoae.cli.load_spec", return_value=spec), patch.object(
            Path, "read_text", return_value=tampered
        ):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                exit_code = main(["verify", "--spec", str(SPEC_PATH), "--expected", "tampered.json"])
        self.assertEqual(exit_code, 1)

    def test_run_refuses_to_overwrite_research_history(self) -> None:
        output = Mock(spec=Path)
        output.exists.return_value = True
        with self.assertRaises(FileExistsError):
            write_record(output, run_experiment(load_spec(SPEC_PATH)))
        output.write_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
