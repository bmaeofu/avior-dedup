"""Job orchestrator for Search & Move.

Follows the same progress-callback pattern as the dedup feature:
three phases (scanning, searching, executing) with cancellation support.
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from time import monotonic

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
    ignored_directories: list[str] | None = None,
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
    started_at = monotonic()

    # Collect files to search
    scan_started_at = monotonic()
    progress_cb(phase="scanning", current_dir=source)
    files_to_search = _collect_files(
        source,
        extensions,
        recursive,
        ignored_directories or [],
        progress_cb,
        cancel_check,
    )

    # Search phase
    search_started_at = monotonic()
    matches: list[SearchMatch] = []
    total = len(files_to_search)
    progress_cb(phase="searching", files_scanned=0, dirs_total=total, groups_found=0)

    # Open output file for writing match results
    out_handle = None
    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        out_handle = open(output_path, "a", encoding="utf-8")
        out_handle.write(f"Datum: {datetime.now().strftime('%y-%m-%d %H:%M:%S')}\n")

    log_fn(f"Datum: {datetime.now().strftime('%y-%m-%d %H:%M:%S')}")

    try:
        log_fn(f"SCAN_SECONDS\t{monotonic() - scan_started_at:.3f}")

        for i, file_path in enumerate(files_to_search):
            if cancel_check():
                raise _Cancelled

            # Heartbeat before expensive matching (XML parse / SMB sibling checks)
            progress_cb(
                phase="searching",
                current_file=file_path,
                files_scanned=i,
                dirs_total=total,
                groups_found=len(matches),
            )

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

            progress_cb(
                phase="searching",
                current_file=file_path,
                files_scanned=i + 1,
                dirs_total=total,
                groups_found=len(matches),
            )
    finally:
        if out_handle:
            out_handle.close()
    log_fn(f"SEARCH_SECONDS\t{monotonic() - search_started_at:.3f}")

    # Execute phase — move/copy/delete matched file sets
    action_counter: Counter[str] = Counter()
    execute_started_at = monotonic()
    total_actions = len(matches)
    files_acted = 0
    progress_cb(phase="executing", files_moved=0, total_files_to_move=total_actions)

    for i, match in enumerate(matches):
        if cancel_check():
            raise _Cancelled

        # Heartbeat before processing this match (video + its siblings = 1 unit).
        progress_cb(
            phase="executing",
            current_file=match.file_path,
            files_moved=files_acted,
            total_files_to_move=total_actions,
        )

        records = process_match(match.file_path, dest, mode, log_fn)
        for rec in records:
            action_counter[rec.status] += 1

        files_acted = i + 1
        progress_cb(
            phase="executing",
            current_file=match.file_path,
            files_moved=files_acted,
            total_files_to_move=total_actions,
        )

    log_fn(f"EXECUTE_SECONDS\t{monotonic() - execute_started_at:.3f}")
    log_fn(f"TOTAL_SECONDS\t{monotonic() - started_at:.3f}")

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
    ignored_directories: list[str] | None,
    progress_cb: Callable[..., None],
    cancel_check: Callable[[], bool],
) -> list[str]:
    """Walk the source path and collect files matching the requested extensions."""
    files: list[str] = []
    scan_count = 0
    update_every = 250
    ignored_names = {os.path.basename(x).strip().lower() for x in (ignored_directories or []) if (x or "").strip()}
    ignored_paths = {os.path.abspath(x).strip().lower() for x in (ignored_directories or []) if (x or "").strip()}

    def _is_ignored_dir(path: str) -> bool:
        abs_path = os.path.abspath(path).lower()
        base = os.path.basename(abs_path).lower()
        return abs_path in ignored_paths or base in ignored_names

    if os.path.isfile(source):
        ext = os.path.splitext(source)[1]
        if not extensions or ext in extensions:
            files.append(source)
            scan_count = 1
        progress_cb(phase="scanning", current_dir=os.path.dirname(source) or source, files_scanned=scan_count)
        return files

    if recursive:
        for dirpath, dirnames, filenames in os.walk(source):
            if cancel_check():
                raise _Cancelled
            dirnames[:] = [d for d in dirnames if not _is_ignored_dir(os.path.join(dirpath, d))]
            progress_cb(phase="scanning", current_dir=dirpath, files_scanned=scan_count)
            for fname in filenames:
                ext = os.path.splitext(fname)[1]
                if not extensions or ext in extensions:
                    files.append(os.path.join(dirpath, fname))
                    scan_count += 1
                    if scan_count % update_every == 0:
                        progress_cb(phase="scanning", current_dir=dirpath, files_scanned=scan_count)
        progress_cb(phase="scanning", current_dir=source, files_scanned=scan_count)
    else:
        progress_cb(phase="scanning", current_dir=source, files_scanned=scan_count)
        try:
            with os.scandir(source) as entries:
                for entry in entries:
                    if cancel_check():
                        raise _Cancelled
                    if entry.is_dir() and _is_ignored_dir(entry.path):
                        continue
                    if entry.is_file():
                        ext = os.path.splitext(entry.name)[1]
                        if not extensions or ext in extensions:
                            files.append(entry.path)
                            scan_count += 1
                            if scan_count % update_every == 0:
                                progress_cb(phase="scanning", current_dir=source, files_scanned=scan_count)
            progress_cb(phase="scanning", current_dir=source, files_scanned=scan_count)
        except OSError as e:
            print(f"Error scanning directory {source}: {e}")

    return files
