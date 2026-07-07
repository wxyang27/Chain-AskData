from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImportResult:
    """Result summary for a primary knowledge import run."""

    output_dir: Path
    counts: dict[str, int]
    files: dict[str, Path]

