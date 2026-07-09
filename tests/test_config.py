import json
import os
from pathlib import Path
import subprocess
import sys


def test_settings_load_llm_values_from_dotenv(tmp_path):
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "LLM_ENABLED=true",
                "LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1",
                "LLM_API_KEY=test-key",
                "LLM_COT_MODEL=qwen3.7-plus",
            ]
        ),
        encoding="utf-8",
    )
    repo_root = Path(__file__).resolve().parents[1]
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("LLM_")
    }
    env["PYTHONPATH"] = str(repo_root)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; "
                "from app.core.config import settings; "
                "print(json.dumps({"
                "'enabled': settings.llm_enabled, "
                "'base_url': settings.llm_base_url, "
                "'model': settings.llm_cot_model"
                "}))"
            ),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert json.loads(result.stdout) == {
        "enabled": True,
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3.7-plus",
    }
