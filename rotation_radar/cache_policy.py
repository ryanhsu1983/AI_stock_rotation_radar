from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def is_fresh(path: str | Path, max_age_days: float) -> bool:
    file_path = Path(path)
    if not file_path.exists():
        return False
    modified = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
    age = datetime.now(timezone.utc) - modified
    return age.total_seconds() <= max_age_days * 24 * 60 * 60
