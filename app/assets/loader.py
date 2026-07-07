import json
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@lru_cache
def load_yaml_asset(relative_path: str) -> Any:
    """读取机器可读 YAML 资产。

    MVP 为了减少依赖，YAML 文件采用 JSON 兼容写法；后续接入 PyYAML 时可平滑替换。
    """

    asset_path = PROJECT_ROOT / relative_path
    return json.loads(asset_path.read_text(encoding="utf-8"))
