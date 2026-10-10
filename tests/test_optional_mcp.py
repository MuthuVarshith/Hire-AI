"""The MCP server is an optional extra (requirements-mcp.txt): the app and agent run without mcp."""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_app_and_agent_import_without_mcp(tmp_path):
    code = ("import sys; sys.modules['mcp'] = None  # any 'import mcp...' now raises ImportError\n"
            "import legacy_flask_app, agent, agent_api, agent_tools, agent_llm")
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{(tmp_path / 'm.db').as_posix()}", "HF_HUB_OFFLINE": "1",
           "GOOGLE_API_KEY": "", "AGENT_CHECKPOINT_DB": str(tmp_path / "cp.db")}
    result = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[-2000:]


def test_core_requirements_do_not_install_mcp():
    core = (REPO / "requirements.txt").read_text(encoding="utf-8").splitlines()
    assert not any(line.strip().startswith("mcp") for line in core)
    assert any(line.strip().startswith("mcp") for line in (REPO / "requirements-mcp.txt").read_text().splitlines())
