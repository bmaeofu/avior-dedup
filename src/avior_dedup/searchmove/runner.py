"""Job orchestrator for Search & Move.

Follows the same progress-callback pattern as the dedup feature:
three phases (scanning, searching, executing) with cancellation support.
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Callable
from datetime import datetime

from avior_dedup.searchmove.models import (
    ActivityMode,
    SearchMatch,
    SearchMoveJobResult,
)
from avior_dedup.searchmove.mover import process_match, _resolve_case_insensitive
from avior_dedup.searchmove.parser import parse_search_expression
from avior_dedup.searchmove.searcher import search_text_file, search_xml_file


def run_search_move_job(
    source: str,
    dest: str,
    mode: ActivityMode,
    extensions: list[str],
    search_expressions: list[str],
    recursive: bool = False,
    progress_cb: Callable[..., None] | None = None,
    log_fn: Callable[[str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    output_path: str | None = None,
) -> SearchMoveJobResult:
    """Run the full search-move pipeline.

    Args:
        source: File or directory to search.
        dest: Destination directory for moved/copied files.
        mode: What to do with matched files.
        extensions: File extensions to search (e.g. ``[".nfo", ".txt"]``).
        search_expressions: CLI-style boolean expressions.
        recursive: Whether to search subdirectories.
        progress_cb: Called with keyword arguments for progress updates.
        log_fn: Called with log messages (tab-separated).
        cancel_check: Returns ``True`` if the job should be cancelled.
        output_path: Path to write the match results file.

    Returns:
        Aggregated job result.
    """
    if log_fn is None:
        log_fn = lambda msg: None  # noqa: E731
    if progress_cb is None:
        progress_cb = lambda **kw: None  # noqa: E731
    if cancel_check is None:
        cancel_check = lambda: False  # noqa: E731

    search_groups = parse_search_expression(search_expressions)
    dest = _resolve_case_insensitive(dest)
    os.makedirs(dest, exist_ok=True)

    # Collect files to search
    progress_cb(phase="scanning", current_dir=source)
    files_to_search = _collect_files(source, extensions, recursive, progress_cb, cancel_check)

    # Search phase
    matches: list[SearchMatch] = []
    total = len(files_to_search)
    progress_cb(phase="searching", files_scanned=0, dirs_total=total)

    # Open output file for writing match results
    out_handle = None
    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        out_handle = open(output_path, "a", encoding="utf-8")
        out_handle.write(f"Datum: {datetime.now().strftime('%y-%m-%d %H:%M:%S')}\n")

    log_fn(f"Datum: {datetime.now().strftime('%y-%m-%d %H:%M:%S')}")

    try:
        for i, file_path in enumerate(files_to_search):
            if cancel_check():
                raise _Cancelled

            ext = os.path.splitext(file_path)[1].lower()
            if ext == ".nfo":
                match = search_xml_file(file_path, search_groups)
            else:
                match = search_text_file(file_path, search_groups)

            if match is not None:
                matches.append(match)
                print(f"MATCH FOUND: {match.file_path}  -->  {match.matched_expression}  [Found: {match.found_values}]")
                if out_handle:
                    out_handle.write(f"{match.file_path}\t{match.matched_expression}\t{match.found_values}\n")

            progress_cb(phase="searching", files_scanned=i + 1, dirs_total=total)
    finally:
        if out_handle:
            out_handle.close()

    # Execute phase — move/copy/delete matched file sets
    action_counter: Counter[str] = Counter()
    total_matches = len(matches)
    progress_cb(phase="executing", files_moved=0, total_files_to_move=total_matches)

    for i, match in enumerate(matches):
        if cancel_check():
            raise _Cancelled

        records = process_match(match.file_path, dest, mode, log_fn)
        for rec in records:
            action_counter[rec.status] += 1

        progress_cb(phase="executing", files_moved=i + 1, total_files_to_move=total_matches)

    log_path_out = os.path.join(dest, "log.txt")
    return SearchMoveJobResult(
        files_scanned=total,
        files_matched=len(matches),
        action_counts=dict(action_counter),
        matches=matches,
        log_path=log_path_out,
    )


class _Cancelled(Exception):
    """Internal signal for job cancellation."""


def _collect_files(
    source: str,
    extensions: list[str],
    recursive: bool,
    progress_cb: Callable[..., None],
    cancel_check: Callable[[], bool],
) -> list[str]:
    """Walk the source path and collect files matching the requested extensions."""
    files: list[str] = []

    if os.path.isfile(source):
        ext = os.path.splitext(source)[1]
        if not extensions or ext in extensions:
            files.append(source)
        return files

    if recursive:
        for dirpath, _, filenames in os.walk(source):
            if cancel_check():
                raise _Cancelled
            progress_cb(phase="scanning", current_dir=dirpath)
            for fname in filenames:
                ext = os.path.splitext(fname)[1]
                if not extensions or ext in extensions:
                    files.append(os.path.join(dirpath, fname))
    else:
        progress_cb(phase="scanning", current_dir=source)
        try:
            with os.scandir(source) as entries:
                for entry in entries:
                    if cancel_check():
                        raise _Cancelled
                    if entry.is_file():
                        ext = os.path.splitext(entry.name)[1]
                        if not extensions or ext in extensions:
                            files.append(entry.path)
        except OSError as e:
            print(f"Error scanning directory {source}: {e}")

    return files
