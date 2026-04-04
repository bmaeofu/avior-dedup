"""Domain types for the Search & Move feature."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class ActivityMode(enum.Enum):
    """What to do with matched files."""

    COPY = "copy"
    MOVE = "move"
    DELETE = "delete"
    TEST = "test"


@dataclass
class SearchMatch:
    """A single file that matched a search expression."""

    file_path: str
    matched_expression: str  # e.g. "rating:>5.4 & nfostatus:!exists"
    found_values: str  # e.g. "6.0 | !exists"


@dataclass
class MoveRecord:
    """Result of a single file action (move/copy/delete)."""

    src: str
    dst: str
    status: str  # "moved", "copied", "deleted", "test run", "error", "already exists"


@dataclass
class SearchMoveJobResult:
    """Aggregated result of a complete search-move job."""

    files_scanned: int = 0
    files_matched: int = 0
    action_counts: dict[str, int] = field(default_factory=dict)
    matches: list[SearchMatch] = field(default_factory=list)
    log_path: str | None = None


# File suffixes considered part of the same media set.
# Ordered longest-first so greedy matching strips the right suffix.
RELATED_SUFFIXES: list[str] = sorted(
    [
        ".txt", ".log", ".mp2", ".mp4", ".mkv", ".ts", ".nfo",
        ".mp2.log", ".mpg.log", ".mkv.log", ".plot.txt",
        "-fanart.jpg", "-poster.jpg", "-landscape.jpg", "-thumb.jpg", "-keyart.jpg",
        ".mp4.INFO.log", ".mp2.INFO.log", ".ts.INFO.log", ".mkv.INFO.log",
    ],
    key=len,
    reverse=True,
)

# Extensions that should be stripped repeatedly from the stem
# (e.g. "movie.mkv.INFO" -> "movie")
STRIP_EXTENSIONS: frozenset[str] = frozenset(
    {".info", ".mkv", ".ts", ".mpg", ".mp2", ".nfo"}
)
