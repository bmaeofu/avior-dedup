from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SelectionPriority(str, Enum):
    """Criteria for selecting the best film, applied in list order."""
    MULTICHANNEL = "multichannel"
    FEWER_ERRORS = "fewer_errors"
    CLOSEST_DURATION = "closest_duration"


DEFAULT_SELECTION_PRIORITIES = [
    SelectionPriority.MULTICHANNEL,
    SelectionPriority.FEWER_ERRORS,
    SelectionPriority.CLOSEST_DURATION,
]


@dataclass
class GroupKeys:
    """Grouping keys for a single file, used to determine display names."""
    exact: str
    lower: str = ""
    semantic: str = ""


@dataclass
class FileRecord:
    file: str
    video_exists: bool
    error_count: Optional[int] = None
    mod_date: Optional[float] = None
    multichannel: Optional[bool] = None
    video_duration: Optional[float] = None
    rec_duration: Optional[int] = None


@dataclass
class MoveAction:
    dst_root: str
    action: str
    group_name: str
