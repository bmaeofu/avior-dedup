from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class FileRecord:
    file: str
    video_exists: bool
    error_count: Optional[int] = None
    mod_date: Optional[float] = None
    multichannel: Optional[bool] = None


@dataclass
class MoveAction:
    dst_root: str
    action: str
    group_name: str
