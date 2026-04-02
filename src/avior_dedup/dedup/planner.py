from __future__ import annotations

import os
import shutil
from collections import Counter
from typing import Callable, Optional

from avior_dedup.dedup.models import FileRecord, MoveAction
from avior_dedup.dedup.scanner import get_film_error_count


def get_group_name(file_path: str, duptype: str, file_to_groupkey: dict[str, dict[str, str]]) -> str:
    """Return the grouping name relevant for the given duptype."""
    basename = os.path.basename(file_path)
    if duptype == "exact":
        return basename
    elif duptype == "case":
        return basename.lower()
    elif duptype in ("semantic", "all"):
        return file_to_groupkey.get(file_path, {}).get("semantic", basename)
    elif duptype == "both":
        return basename.lower()
    return basename


def select_best_film(
    valid_records: list[FileRecord],
    prefer_errors: bool,
    max_errors_when_mc: Optional[int],
    max_duration_diff: int = 600,
) -> FileRecord:
    """Select the best recording to keep from a list of valid (video exists) records."""
    # Hard exclusion criterion (highest priority):
    # keep-candidates must have both durations and may not be more than 10 min longer than rec_duration.
    keep_candidates = [
        r
        for r in valid_records
        if r.video_duration is not None
        and r.rec_duration is not None
        and (r.video_duration - r.rec_duration) <= max_duration_diff
    ]

    # Exception: allow a too-long recording if otherwise no error-free candidate exists.
    too_long_error_free = [
        r
        for r in valid_records
        if r.video_duration is not None
        and r.rec_duration is not None
        and (r.video_duration - r.rec_duration) > max_duration_diff
        and r.error_count == 0
    ]
    keep_has_error_free = any(r.error_count == 0 for r in keep_candidates)

    if too_long_error_free and not keep_has_error_free:
        pool = too_long_error_free
    else:
        pool = keep_candidates if keep_candidates else valid_records

    if len(pool) == 1:
        return pool[0]

    mc = [r for r in pool if r.multichannel]
    mc_good = mc
    if max_errors_when_mc is not None:
        mc_good = [
            r for r in mc
            if r.error_count is not None and r.error_count <= max_errors_when_mc
        ]

    if not prefer_errors:
        if mc_good:
            return max(mc_good, key=lambda r: r.mod_date or 0)
        return max(pool, key=lambda r: r.mod_date or 0)

    # prefer_errors: pick fewest errors, then newest
    if mc_good:
        return min(mc_good, key=lambda r: (r.error_count, -(r.mod_date or 0)))
    return min(
        pool,
        key=lambda r: (
            r.error_count if r.error_count is not None else 10**9,
            -(r.mod_date or 0),
        ),
    )


def build_move_plan(
    groups: list[list[str]],
    target_root: str,
    error_target: str,
    novideo_target: str,
    prefer_errors: bool,
    max_errors_when_mc: int,
    duptype: str,
    file_to_groupkey: dict[str, dict[str, str]],
    log_fn: Callable[[str], None],
    progress_cb: Callable[[int, int], None] | None = None,
    max_duration_diff: int = 600,
) -> tuple[dict[str, MoveAction], Counter]:
    """Decide what to do with each file. Returns (files_to_move, action_counter)."""
    film_info_cache: dict[str, FileRecord] = {}
    files_to_move: dict[str, MoveAction] = {}
    already_logged: set[tuple[str, str]] = set()
    action_counter: Counter = Counter()
    total_groups = len(groups)

    for group_idx, group in enumerate(groups):
        # Build FileRecords for this group (with caching)
        records: list[FileRecord] = []
        uncached = [f for f in group if f not in film_info_cache]
        if uncached:
            for rec in get_film_error_count(uncached):
                film_info_cache[rec.file] = rec
        for f in group:
            records.append(film_info_cache[f])

        valid_records = [r for r in records if r.video_exists]

        if progress_cb is not None:
            progress_cb(group_idx + 1, total_groups)

        # Case: no video exists for any file in the group
        if not valid_records:
            for r in records:
                group_name = get_group_name(r.file, duptype, file_to_groupkey)
                files_to_move[r.file] = MoveAction(novideo_target, "NO_VIDEO", group_name)
            continue

        best_film = select_best_film(
            valid_records,
            prefer_errors,
            max_errors_when_mc,
            max_duration_diff=max_duration_diff,
        )

        for r in records:
            src = r.file
            group_name = get_group_name(src, duptype, file_to_groupkey)

            if src == best_film.file:
                action = "KEEP_MC" if r.multichannel else "KEEP"
                key = (action, src)
                if key not in already_logged:
                    log_fn(f"{group_name}\t[{action}]\t{src}")
                    action_counter[action] += 1
                    already_logged.add(key)
                continue

            # Determine move destination
            has_errors = r.error_count is not None and r.error_count > 0
            has_duration_values = r.video_duration is not None and r.rec_duration is not None
            is_too_long = has_duration_values and (r.video_duration - r.rec_duration) > max_duration_diff

            if not r.video_exists:
                dst_root = novideo_target
                action = "NO_VIDEO"
            elif is_too_long:
                dst_root = error_target
                action = "DUPLICATE_WITH_LONGER_DURATION"
            elif prefer_errors and not r.multichannel and has_errors:
                dst_root = error_target
                action = "DUPLICATE_WITH_ERRORS"
            elif r.multichannel and has_errors:
                dst_root = error_target
                action = "DUPLICATE_WITH_ERRORS_MC"
            else:
                dst_root = target_root
                action = "DUPLICATE"

            files_to_move[src] = MoveAction(dst_root, action, group_name)

    return files_to_move, action_counter


def execute_move_plan(
    files_to_move: dict[str, MoveAction],
    source_root: str,
    mode: str,
    action_counter: Counter,
    log_fn: Callable[[str], None],
    progress_cb: Callable[[int, int], None] | None = None,
) -> None:
    """Execute or dry-run the move plan."""
    sorted_items = sorted(files_to_move.items())
    total = len(sorted_items)
    for idx, (file_path, move) in enumerate(sorted_items):
        rel = os.path.relpath(file_path, source_root)
        dst = os.path.join(move.dst_root, rel)

        log_fn(f"{move.group_name}\t[{move.action}]\t{file_path}\t{dst}")
        action_counter[move.action] += 1

        if progress_cb is not None:
            progress_cb(idx + 1, total)

        if mode == "m":
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not os.path.exists(dst):
                shutil.move(file_path, dst)
            else:
                log_fn(f"{move.group_name}\t[SKIP_EXISTS]\t{dst}")
                action_counter["SKIP_EXISTS"] += 1
