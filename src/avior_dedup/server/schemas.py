from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from avior_dedup.dedup.models import SelectionPriority


class JobRequest(BaseModel):
    mode: Literal["m", "f"]
    source: str
    target: str
    ignored_directories: list[str] = Field(default_factory=list)
    logname: str = "dedup_log.txt"
    duptype: Literal["case", "exact", "semantic", "both", "all"] = "case"
    error_target: str | None = None
    novideo_target: str | None = None
    max_errors_when_mc: int = 0
    max_duration_diff_longer: int = 600
    max_duration_diff_shorter: int = 120
    selection_priorities: list[SelectionPriority] = Field(
        default_factory=lambda: [
            SelectionPriority.MULTICHANNEL,
            SelectionPriority.RESOLUTION,
            SelectionPriority.FEWER_ERRORS,
            SelectionPriority.RECORDING_DATE,
            SelectionPriority.CLOSEST_DURATION,
        ]
    )
    semantic_prefixes: list[str] = Field(default_factory=lambda: [r"terra\s*x\s*-\s*"])
    remove_episode_nos: bool = False
    remove_spaces: bool = False
    remove_non_episode_parens: bool = False
    replace_underscores: bool = False


class ProgressSnapshot(BaseModel):
    phase: str = ""
    current_file: str | None = None
    current_dir: str | None = None
    dirs_completed: int = 0
    dirs_total: int = 0
    files_scanned: int = 0
    groups_found: int = 0
    files_planned: int = 0
    files_moved: int = 0
    total_files_to_move: int = 0


class JobResult(BaseModel):
    files_scanned: int
    groups_found: int
    action_counts: dict[str, int]
    action_sizes: dict[str, int] = {}
    log_path: str | None
    timing_path: str | None = None


# ---------------------------------------------------------------------------
# Search & Move schemas
# ---------------------------------------------------------------------------

class SearchMoveRequest(BaseModel):
    mode: Literal["copy", "move", "delete", "test"]
    source: str
    dest: str
    ignored_directories: list[str] = Field(default_factory=list)
    extensions: list[str] = Field(default_factory=lambda: [".nfo"])
    search_expressions: list[str]
    recursive: bool = False
    preserve_dirs: bool = False
    logname: str = "searchmove_log.txt"


class SearchMoveMatchEntry(BaseModel):
    file_path: str
    matched_expression: str
    found_values: str


class SearchMoveResult(BaseModel):
    files_scanned: int
    files_matched: int
    action_counts: dict[str, int]
    matches: list[SearchMoveMatchEntry] = []
    log_path: str | None
    timing_path: str | None = None


# ---------------------------------------------------------------------------
# Shared schemas
# ---------------------------------------------------------------------------

class JobStatus(BaseModel):
    job_id: str
    state: str
    progress: ProgressSnapshot | None = None
    result: JobResult | SearchMoveResult | None = None
    error: str | None = None


class ConfigUpdate(BaseModel):
    content: Any
