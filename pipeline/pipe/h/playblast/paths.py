from __future__ import annotations

from datetime import datetime
from pathlib import Path

from shared.util import get_edit_path


def _build_base_name(shot_code: str, timestamp: datetime) -> str:
    timestamp_str = timestamp.strftime("%Y-%m-%d_%H-%M")
    return f"{shot_code}_{timestamp_str}"


def build_output_base_path(
    department: str,
    shot_code: str,
    timestamp: datetime | None = None,
) -> Path:
    if timestamp is None:
        timestamp = datetime.now()

    date_folder = timestamp.strftime("%Y-%m-%d")
    return (
        get_edit_path()
        / department
        / date_folder
        / _build_base_name(shot_code, timestamp)
    )


def build_custom_output_base_path(
    custom_dir: Path,
    shot_code: str,
    timestamp: datetime | None = None,
) -> Path:
    if timestamp is None:
        timestamp = datetime.now()
    return custom_dir / _build_base_name(shot_code, timestamp)
