from __future__ import annotations

import os
import re
from typing import Callable

from avior_dedup import config
from avior_dedup.models import FileRecord
from avior_dedup.normalize import normalize_film_name
from avior_dedup.suffix import match_suffix


def count_errors(lines: list[str]) -> int:
    """Count encoding errors from log lines containing 'MB) Errors:'."""
    error_count = 0
    for line in lines:
        if "MB) Errors:" in line:
            try:
                parts = line.split("MB) Errors:")
                if len(parts) > 1:
                    error_count += int(parts[1].strip().split()[0])
            except ValueError:
                continue
    return error_count


def is_multichannel_from_log(lines: list[str], max_seconds: int = 20) -> bool:
    """Check if AC3 5.x multichannel audio appears within the first max_seconds of the recording log."""
    time_re = re.compile(r"/\s*(\d+):(\d+):(\d+)")
    recording_started = False

    for line in lines:
        if not recording_started:
            if line.strip().endswith("Start") or "Start Recording" in line:
                recording_started = True
            continue

        m = time_re.search(line)
        if not m:
            continue

        h, mi, s = map(int, m.groups())
        seconds = h * 3600 + mi * 60 + s
        if seconds > max_seconds:
            break

        if "AC3 Audio 5." in line:
            return True

    return False


def get_film_error_count(
    file_list: list[str],
    progress_cb: Callable[[str, int], None] | None = None,
) -> list[FileRecord]:
    """Analyze a list of file paths and return FileRecord for each, including error counts from logs."""
    video_suffixes = config.video_suffixes()
    results: list[FileRecord] = []

    for idx, file_path in enumerate(file_list):
        film_dir = os.path.dirname(file_path)
        film_base, _ = match_suffix(os.path.basename(file_path))

        # Check if a video file exists for this base name
        video_exists = False
        for ext in video_suffixes:
            if os.path.exists(os.path.join(film_dir, film_base + ext)):
                video_exists = True
                break

        error_count = None
        mod_date = None
        multichannel = None

        if video_exists:
            main_log = os.path.join(film_dir, film_base + ".log")
            if not os.path.exists(main_log):
                main_log = os.path.join(film_dir, film_base + "mkv.log")
            if os.path.exists(main_log):
                try:
                    mod_date = os.path.getmtime(main_log)
                    with open(main_log, "r", encoding="utf-8", errors="ignore") as fh:
                        lines = fh.readlines()
                        error_count = count_errors(lines)
                        multichannel = is_multichannel_from_log(lines)
                except (OSError, UnicodeDecodeError, ValueError):
                    error_count = None
                    mod_date = None
                    multichannel = None

        results.append(FileRecord(
            file=file_path,
            video_exists=video_exists,
            error_count=error_count,
            mod_date=mod_date,
            multichannel=multichannel,
        ))
        if progress_cb is not None:
            progress_cb(file_path, idx + 1)

    return results


def find_duplicates(
    source_root: str,
    duptype: str,
    remove_episode_nos: bool,
    semantic_prefixes: list[str],
    progress_cb: Callable[..., None] | None = None,
) -> tuple[list[list[str]], dict[str, dict[str, str]]]:
    """Walk source_root and group files into duplicate sets based on duptype.

    progress_cb signature: (current_dir, dirs_completed, dirs_total, files_scanned)
    """
    ignored_dirs_lower = {x.lower() for x in config.ignored_dirs()}
    ignored_files_lower = {x.lower() for x in config.ignored_files()}

    files_by_lower: dict[str, list[str]] = {}
    files_by_exact: dict[str, list[str]] = {}
    files_by_semantic: dict[str, list[str]] = {}
    file_to_groupkey: dict[str, dict[str, str]] = {}
    files_scanned = 0

    # Enumerate top-level entries to provide directory-level progress
    try:
        top_entries = sorted(os.listdir(source_root))
    except OSError as e:
        print(f"[avior-dedup] Cannot list source directory: {e}")
        top_entries = []

    # Separate into: subdirectories to walk + files in the root itself
    top_dirs = []
    root_files = []
    for entry in top_entries:
        full = os.path.join(source_root, entry)
        if os.path.isdir(full):
            if entry.lower() not in ignored_dirs_lower:
                top_dirs.append(entry)
        else:
            root_files.append(entry)

    # We treat root files + each top-level subdir as a "unit" of work
    total_units = len(top_dirs) + (1 if root_files else 0)
    units_done = 0

    def _process_file(name: str, dir_path: str) -> None:
        nonlocal files_scanned
        if name.lower() in ignored_files_lower:
            return
        full_path = os.path.join(dir_path, name)
        files_scanned += 1

        files_by_exact.setdefault(name, []).append(full_path)
        file_to_groupkey[full_path] = {"exact": name}

        lower_name = name.lower()
        files_by_lower.setdefault(lower_name, []).append(full_path)
        file_to_groupkey[full_path]["case"] = lower_name

        semantic_name = normalize_film_name(name, semantic_prefixes, remove_episode_nos)
        files_by_semantic.setdefault(semantic_name, []).append(full_path)
        file_to_groupkey[full_path]["semantic"] = semantic_name

    def _scan_dir(dir_path: str) -> None:
        """Recursively scan a directory using scandir, reporting after each subdir."""
        nonlocal files_scanned
        try:
            entries = list(os.scandir(dir_path))
        except OSError as e:
            print(f"[avior-dedup] Cannot read directory: {e}")
            return

        # Process files in this directory
        for entry in entries:
            if entry.is_file(follow_symlinks=False):
                _process_file(entry.name, dir_path)

        # Report progress once per directory
        if progress_cb is not None:
            progress_cb(dir_path, units_done, total_units, files_scanned)

        # Then recurse into subdirectories
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                if entry.name.lower() not in ignored_dirs_lower:
                    _scan_dir(entry.path)

    # Process files in the source root itself
    if root_files:
        print(f"[avior-dedup] Scanning: {source_root} ({len(root_files)} root files)")
        if progress_cb is not None:
            progress_cb(source_root, units_done, total_units, files_scanned)
        for name in root_files:
            _process_file(name, source_root)
        units_done += 1

    # Scan each top-level subdirectory
    for top_dir_name in top_dirs:
        top_dir_path = os.path.join(source_root, top_dir_name)
        print(f"[avior-dedup] Scanning: {top_dir_path}")
        if progress_cb is not None:
            progress_cb(top_dir_path, units_done, total_units, files_scanned)

        _scan_dir(top_dir_path)

        units_done += 1
        if progress_cb is not None:
            progress_cb(top_dir_path, units_done, total_units, files_scanned)
        print(f"[avior-dedup] Completed: {top_dir_path} ({files_scanned} files total so far)")

    groups: list[list[str]] = []
    if duptype in ("case", "both", "all"):
        for paths in files_by_lower.values():
            if len(paths) > 1:
                groups.append(paths)
    if duptype in ("exact", "both", "all"):
        for paths in files_by_exact.values():
            if len(paths) > 1:
                groups.append(paths)
    if duptype in ("semantic", "all"):
        for paths in files_by_semantic.values():
            if len(paths) > 1:
                groups.append(paths)

    return groups, file_to_groupkey
