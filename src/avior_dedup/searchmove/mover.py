"""File operations — move, copy, delete matched file sets."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from functools import lru_cache

from avior_dedup.searchmove.models import (
    ActivityMode,
    MoveRecord,
    RELATED_SUFFIXES,
    STRIP_EXTENSIONS,
)


def _strip_to_stem(filename: str) -> str:
    """Extract the base stem from a media filename.

    Strips known compound suffixes (e.g. ``.mkv.INFO.log``) and then
    repeatedly removes known extensions from the stem so that
    ``movie.mkv.INFO`` becomes ``movie``.
    """
    lower = filename.lower()
    lower_candidates = sorted((s.lower() for s in RELATED_SUFFIXES), key=len, reverse=True)

    stem = filename
    for suffix in lower_candidates:
        if lower.endswith(suffix):
            stem = filename[: -len(suffix)]
            break
    else:
        stem = os.path.splitext(filename)[0]

    # Strip repeated known extensions from the stem
    while True:
        ext = os.path.splitext(stem)[1].lower()
        if ext in STRIP_EXTENSIONS:
            stem = os.path.splitext(stem)[0]
        else:
            break

    return stem


def find_related_files(path: str) -> list[str]:
    """Find all files sharing the same base stem in the same directory.

    Given ``/media/movie.nfo``, returns paths like ``movie.mkv``,
    ``movie.txt``, ``movie-fanart.jpg``, etc.
    """
    directory, filename = os.path.split(path)
    search_dir = directory or "."
    stem = _strip_to_stem(filename)

    try:
        with os.scandir(search_dir) as it:
            entries = {entry.name.lower(): entry.path for entry in it if entry.is_file()}
    except OSError as e:
        print(f"Error scanning directory {search_dir}: {e}")
        return []

    lower_stem = stem.lower()
    lower_candidates = sorted((s.lower() for s in RELATED_SUFFIXES), key=len, reverse=True)

    related: list[str] = []
    seen: set[str] = set()
    for suffix in lower_candidates:
        wanted = lower_stem + suffix
        found = entries.get(wanted)
        if found and found not in seen:
            related.append(found)
            seen.add(found)

    return related


def execute_file_action(
    src: str,
    dst: str,
    mode: ActivityMode,
    log_fn: Callable[[str], None],
) -> MoveRecord:
    """Perform a single file action (copy/move/delete/test).

    Returns a ``MoveRecord`` describing what happened.
    """
    # TEST mode should avoid expensive SMB stat/exists checks.
    if mode == ActivityMode.TEST:
        log_fn(f"{src}\t{dst}\ttest run")
        return MoveRecord(src=src, dst=dst, status="test run")

    if not os.path.isfile(src):
        return MoveRecord(src=src, dst=dst, status="error: source not found")

    if mode != ActivityMode.DELETE and os.path.isfile(dst):
        log_fn(f"{src}\t{dst}\tDestination already exists")
        return MoveRecord(src=src, dst=dst, status="already exists")

    try:
        if mode == ActivityMode.COPY:
            shutil.copy2(src, dst)
            log_fn(f"{src}\t{dst}\tcopied")
            return MoveRecord(src=src, dst=dst, status="copied")
        elif mode == ActivityMode.MOVE:
            shutil.move(src, dst)
            log_fn(f"{src}\t{dst}\tmoved")
            return MoveRecord(src=src, dst=dst, status="moved")
        elif mode == ActivityMode.DELETE:
            os.remove(src)
            log_fn(f"{src}\t\tdeleted")
            return MoveRecord(src=src, dst="", status="deleted")
        else:  # defensive fallback
            log_fn(f"{src}\t{dst}\ttest run")
            return MoveRecord(src=src, dst=dst, status="test run")
    except IOError as e:
        log_fn(f"{src}\t{dst}\t{e}")
        return MoveRecord(src=src, dst=dst, status=f"error: {e}")


@lru_cache(maxsize=512)
def _resolve_case_insensitive(path: str) -> str:
    """Resolve a path to use the actual on-disk casing of each component.

    Walks the path from root, and for each component looks up the real
    directory name on disk (case-insensitive match). This prevents creating
    ``tobescraped`` when ``ToBeScraped`` already exists, even on systems
    where ``os.path.exists`` is case-insensitive (Windows/SMB).

    Components that don't exist on disk yet are kept as-is.
    """
    parts = os.path.normpath(path).replace("\\", "/").split("/")
    # Handle UNC paths (//server/share/...)
    if path.replace("\\", "/").startswith("//"):
        resolved = "//" + parts[2] + "/" + parts[3]
        remaining = parts[4:]
    elif parts[0].endswith(":"):
        resolved = parts[0] + "/"
        remaining = parts[1:]
    else:
        resolved = parts[0] or "/"
        remaining = parts[1:]

    for part in remaining:
        if not part:
            continue
        # Always list the parent to find the real on-disk name
        try:
            existing = os.listdir(resolved)
            match = next((e for e in existing if e.lower() == part.lower()), None)
            if match:
                resolved = os.path.join(resolved, match)
            else:
                # Doesn't exist yet — keep user-provided casing
                resolved = os.path.join(resolved, part)
        except OSError:
            # Parent doesn't exist either — keep as-is
            resolved = os.path.join(resolved, part)

    return resolved


@lru_cache(maxsize=512)
def _ensure_dest_dir(path: str) -> str:
    """Create destination directory once per path and return it."""
    os.makedirs(path, exist_ok=True)
    return path


def process_match(
    matched_path: str,
    dest_dir: str,
    mode: ActivityMode,
    log_fn: Callable[[str], None],
) -> list[MoveRecord]:
    """Move/copy/delete all files related to a matched file.

    Skips the operation if source and destination directories are the same.
    Uses case-insensitive directory resolution to avoid creating duplicate
    directories with different casing.
    """
    src_dir = os.path.dirname(os.path.abspath(matched_path))
    abs_dest = os.path.abspath(dest_dir)

    # Cheap same-dir check first; avoids UNC/listdir work in TEST mode.
    if os.path.normcase(src_dir) == os.path.normcase(abs_dest):
        log_fn(f"{matched_path}\t{abs_dest}\tskipped: source and destination are the same directory")
        return []

    if mode != ActivityMode.TEST:
        dest_dir = _ensure_dest_dir(_resolve_case_insensitive(abs_dest))
    else:
        dest_dir = abs_dest

    related = find_related_files(matched_path)
    if not related and os.path.isfile(matched_path):
        # Fallback: never silently no-op for a confirmed match.
        # If the related-files stem index misses, process the matched file itself.
        related = [matched_path]
        log_fn(f"{matched_path}\t\tfallback: no related files found; processing matched file only")

    records: list[MoveRecord] = []

    for src in related:
        dst = os.path.join(dest_dir, os.path.basename(src))
        record = execute_file_action(src, dst, mode, log_fn)
        records.append(record)

    return records
