"""ragas and langfuse are optional extras (requirements-eval.txt): the FastAPI app imports without them.

Needs app/main.py (Agent A's FastAPI migration) to pass.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_app_imports_without_ragas_or_langfuse(tmp_path: Path) -> None:
    code = ("import sys\n"
            "for name in ('ragas', 'langfuse'):\n"
            "    sys.modules[name] = None  # any 'import ragas...' or 'import langfuse...' now raises ImportError\n"
            "import app.main\n"
            "assert 'ragas' not in [m for m in sys.modules if sys.modules[m] is not None]\n")
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{(tmp_path / 'e.db').as_posix()}", "HF_HUB_OFFLINE": "1",
           "GOOGLE_API_KEY": "", "AGENT_CHECKPOINT_DB": str(tmp_path / "cp.db"), "LANGFUSE_ENABLED": "false"}
    result = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[-2000:]
