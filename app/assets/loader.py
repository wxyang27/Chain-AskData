import json
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@lru_cache
def load_yaml_asset(relative_path: str) -> Any:
    """Load a JSON-compatible or standard YAML asset."""

    asset_path = PROJECT_ROOT / relative_path
    content = asset_path.read_text(encoding="utf-8")
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError(
                f"{relative_path} is not JSON-compatible and PyYAML is not installed"
            ) from exc
        return yaml.safe_load(content)
