"""Runs submission/execution_script.py inside the test suite, so CI checks it in Docker on every push."""
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "submission" / "execution_script.py"


@pytest.mark.parametrize("sample", ["sample_ai_output", "sample_ai_output1", "sample_ai_output2"])
def test_execution_script_passes_on_every_sample_file(sample):
    result = subprocess.run([sys.executable, str(SCRIPT), sample], capture_output=True, text=True, timeout=300)
    # on failure, show the script's report so the failing check is visible in the CI log
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]
    assert "checks passed." in result.stdout
