"""File operations — move, copy, delete matched file sets."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable

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
    lower_stem = stem.lower()

    lower_candidates = sorted((s.lower() for s in RELATED_SUFFIXES), key=len, reverse=True)
    related: list[str] = []

    try:
        with os.scandir(search_dir) as it:
            for entry in it:
                if not entry.is_file():
                    continue
                ename_low = entry.name.lower()
                for suf in lower_candidates:
                    if ename_low == lower_stem + suf:
                        related.append(entry.path)
                        break
    except OSError as e:
        print(f"Error scanning directory {search_dir}: {e}")

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
        else:  # TEST
            log_fn(f"{src}\t{dst}\ttest run")
            return MoveRecord(src=src, dst=dst, status="test run")
    except IOError as e:
        log_fn(f"{src}\t{dst}\t{e}")
        return MoveRecord(src=src, dst=dst, status=f"error: {e}")


def process_match(
    matched_path: str,
    dest_dir: str,
    mode: ActivityMode,
    log_fn: Callable[[str], None],
) -> list[MoveRecord]:
    """Move/copy/delete all files related to a matched file.

    Skips the operation if source and destination directories are the same.
    """
    src_dir = os.path.dirname(os.path.abspath(matched_path))
    abs_dest = os.path.abspath(dest_dir)

    if src_dir == abs_dest:
        return []

    os.makedirs(dest_dir, exist_ok=True)

    related = find_related_files(matched_path)
    records: list[MoveRecord] = []

    for src in related:
        dst = os.path.join(dest_dir, os.path.basename(src))
        record = execute_file_action(src, dst, mode, log_fn)
        records.append(record)

    return records
