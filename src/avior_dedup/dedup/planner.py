from __future__ import annotations

import os
import shutil
from collections import Counter
from typing import Callable
import datetime

from avior_dedup.dedup.models import (
    DEFAULT_SELECTION_PRIORITIES,
    FileRecord,
    GroupKeys,
    MoveAction,
    SelectionPriority,
)
from avior_dedup.dedup.scanner import get_film_error_count
from avior_dedup.permissions import ensure_output_permissions


def get_group_name(file_path: str, duptype: str, file_to_groupkey: dict[str, GroupKeys]) -> str:
    """Return the grouping name relevant for the given duptype."""
    basename = os.path.basename(file_path)
    if duptype == "exact":
        return basename
    elif duptype == "case":
        return basename.lower()
    elif duptype in ("semantic", "all"):
        keys = file_to_groupkey.get(file_path)
        return keys.semantic if keys else basename
    elif duptype == "both":
        return basename.lower()
    return basename


def _sort_key(
    r: FileRecord,
    priorities: list[SelectionPriority],
    max_errors_when_mc: int | None = None,
    max_duration_diff_longer: int = 600,
    max_duration_diff_shorter: int = 120,
) -> tuple:
    """Build a comparable sort key based on the priority list (lower = better).

    For MULTICHANNEL priority: if the record has more errors than
    ``max_errors_when_mc``, its multichannel advantage is ignored (treated as
    non-MC for ranking purposes).
    """
    key: list[float] = []
    for p in priorities:
        if p == SelectionPriority.MULTICHANNEL:
            is_good_mc = bool(r.multichannel)
            if is_good_mc and max_errors_when_mc is not None:
                errors = r.error_count if r.error_count is not None else 0
                if errors > max_errors_when_mc:
                    is_good_mc = False
            key.append(0 if is_good_mc else 1)
        elif p == SelectionPriority.RESOLUTION:
            # Higher resolution should be preferred.
            key.append(-(r.resolution if r.resolution is not None else -10**9))
        elif p == SelectionPriority.FEWER_ERRORS:
            key.append(r.error_count if r.error_count is not None else 10**9)
        elif p == SelectionPriority.CLOSEST_DURATION:
            # Only penalize recordings that deviate more than the configured
            # duration thresholds. If within thresholds, treat as equal (0).
            if r.video_duration is not None and r.rec_duration is not None:
                diff = r.video_duration - r.rec_duration
                if diff > max_duration_diff_longer:
                    # amount exceeding the allowed longer threshold
                    key.append(diff - max_duration_diff_longer)
                elif diff < -max_duration_diff_shorter:
                    # amount exceeding the allowed shorter threshold
                    key.append((-diff) - max_duration_diff_shorter)
                else:
                    key.append(0)
            else:
                key.append(10**9)
        elif p == SelectionPriority.RECORDING_DATE:
            # Prefer newer recordings. If rec_date is not available, fall back to
            # filesystem mod_time. If neither is available use 0.
            rec_ord = 0
            if getattr(r, "rec_date", None):
                try:
                    rec_dt = datetime.date.fromisoformat(r.rec_date)
                    rec_ord = rec_dt.toordinal()
                except Exception:
                    rec_ord = 0
            elif r.mod_date:
                try:
                    rec_ord = datetime.date.fromtimestamp(r.mod_date).toordinal()
                except Exception:
                    rec_ord = 0

            # newer should be better -> smaller sort key -> use negative ordinal
            key.append(-rec_ord)
    # No additional global tiebreaker — mod_date is only considered as fallback
    # inside the RECORDING_DATE priority above.
    return tuple(key)


def select_best_film(
    valid_records: list[FileRecord],
    max_duration_diff_longer: int = 600,
    max_duration_diff_shorter: int = 120,
    selection_priorities: list[SelectionPriority] | None = None,
    max_errors_when_mc: int | None = None,
) -> FileRecord:
    """Select the best recording to keep from a list of valid (video exists) records.

    At least one film is always kept, even if all candidates fall outside the
    duration window.
    """
#    if any("der zuviel" in r.file for r in valid_records):
#        print("debug") 
    if selection_priorities is None:
        selection_priorities = DEFAULT_SELECTION_PRIORITIES

    # Hard exclusion: keep-candidates must have both durations and stay within window.
    keep_candidates = [
        r
        for r in valid_records
        if r.video_duration is not None
        and r.rec_duration is not None
        and (r.video_duration - r.rec_duration) <= max_duration_diff_longer
        and (r.video_duration - r.rec_duration) >= -max_duration_diff_shorter
    ]

    # Guarantee: always keep at least one — fall back to full list if nothing qualifies.
    pool = keep_candidates if keep_candidates else valid_records

    return min(
        pool,
        key=lambda r: _sort_key(
            r,
            selection_priorities,
            max_errors_when_mc,
            max_duration_diff_longer,
            max_duration_diff_shorter,
        ),
    )


def _get_file_size(path: str) -> int:
    """Return the file size in bytes, or 0 if the file cannot be accessed."""
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def build_move_plan(
    groups: list[list[str]],
    target_root: str,
    error_target: str,
    novideo_target: str,
    max_errors_when_mc: int,
    duptype: str,
    file_to_groupkey: dict[str, GroupKeys],
    log_fn: Callable[[str], None],
    progress_cb: Callable[[int, int], None] | None = None,
    max_duration_diff_longer: int = 600,
    max_duration_diff_shorter: int = 120,
    selection_priorities: list[SelectionPriority] | None = None,
) -> tuple[dict[str, MoveAction], Counter, Counter, Counter]:
    """Decide what to do with each file. Returns (files_to_move, action_counter, size_counter, decision_counter)."""
    film_info_cache: dict[str, FileRecord] = {}
    files_to_move: dict[str, MoveAction] = {}
    already_logged: set[tuple[str, str]] = set()
    action_counter: Counter = Counter()
    size_counter: Counter = Counter()
    # Count which priority decided the selection between top candidates
    decision_counter: Counter = Counter()
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
            max_duration_diff_longer=max_duration_diff_longer,
            max_duration_diff_shorter=max_duration_diff_shorter,
            selection_priorities=selection_priorities,
            max_errors_when_mc=max_errors_when_mc,
        )

        # Determine which priority decided between winner and runner-up (if applicable)
        try:
            if len(valid_records) >= 2:
                # compute sort keys for all valid records
                keys = [(r, _sort_key(r, selection_priorities or DEFAULT_SELECTION_PRIORITIES, max_errors_when_mc, max_duration_diff_longer, max_duration_diff_shorter)) for r in valid_records]
                # sort by key (lower is better)
                keys_sorted = sorted(keys, key=lambda t: t[1])
                winner, winner_key = keys_sorted[0]
                runnerup, runner_key = keys_sorted[1]
                # find first differing element in the tuple
                for idx, (wk, rk) in enumerate(zip(winner_key, runner_key)):
                    if wk != rk:
                        # map priority index to name
                        prio = (selection_priorities or DEFAULT_SELECTION_PRIORITIES)[idx]
                        if prio == SelectionPriority.RESOLUTION:
                            decision_counter['RESOLUTION'] += 1
                        elif prio == SelectionPriority.RECORDING_DATE:
                            decision_counter['NEWER_RECDATE'] += 1
                        else:
                            decision_counter[prio.value.upper()] += 1
                        break
        except Exception:
            # non-fatal: don't fail planning if decision counting breaks
            pass

        for r in records:
            src = r.file
            group_name = get_group_name(src, duptype, file_to_groupkey)

            if src == best_film.file:
                base_action = "KEEP_MC" if r.multichannel else "KEEP"
                has_errors = r.error_count is not None and r.error_count > 0
                has_duration_values = r.video_duration is not None and r.rec_duration is not None
                is_too_long = has_duration_values and (r.video_duration - r.rec_duration) > max_duration_diff_longer
                is_too_short = has_duration_values and (r.video_duration - r.rec_duration) < -max_duration_diff_shorter

                if is_too_long:
                    action = f"{base_action}_WITH_LONGER_DURATION"
                elif is_too_short:
                    action = f"{base_action}_WITH_SHORTER_DURATION"
                elif has_errors:
                    action = f"{base_action}_WITH_ERRORS"
                else:
                    action = base_action

                key = (action, src)
                if key not in already_logged:
                    log_fn(f"{group_name}\t[{action}]\t{src}")
                    action_counter[action] += 1
                    size_counter[action] += _get_file_size(src)
                    already_logged.add(key)
                continue

            # Determine move destination
            has_errors = r.error_count is not None and r.error_count > 0
            has_duration_values = r.video_duration is not None and r.rec_duration is not None
            is_too_long = has_duration_values and (r.video_duration - r.rec_duration) > max_duration_diff_longer
            is_too_short = has_duration_values and (r.video_duration - r.rec_duration) < -max_duration_diff_shorter

            if not r.video_exists:
                dst_root = novideo_target
                action = "NO_VIDEO"
            elif is_too_long:
                dst_root = error_target
                action = "DUPLICATE_WITH_LONGER_DURATION"
            elif is_too_short:
                dst_root = error_target
                action = "DUPLICATE_WITH_SHORTER_DURATION"
            elif not r.multichannel and has_errors:
                dst_root = error_target
                action = "DUPLICATE_WITH_ERRORS"
            elif r.multichannel and has_errors:
                dst_root = error_target
                action = "DUPLICATE_WITH_ERRORS_MC"
            else:
                dst_root = target_root
                action = "DUPLICATE"

            files_to_move[src] = MoveAction(dst_root, action, group_name)

    return files_to_move, action_counter, size_counter, decision_counter


def execute_move_plan(
    files_to_move: dict[str, MoveAction],
    source_root: str,
    mode: str,
    action_counter: Counter,
    log_fn: Callable[[str], None],
    progress_cb: Callable[[int, int], None] | None = None,
    size_counter: Counter | None = None,
) -> None:
    """Execute or dry-run the move plan."""
    if size_counter is None:
        size_counter = Counter()
    sorted_items = sorted(files_to_move.items())
    total = len(sorted_items)
    for idx, (file_path, move) in enumerate(sorted_items):
        rel = os.path.relpath(file_path, source_root)
        dst = os.path.join(move.dst_root, rel)

        file_size = _get_file_size(file_path)
        log_fn(f"{move.group_name}\t[{move.action}]\t{file_path}\t{dst}")
        action_counter[move.action] += 1
        size_counter[move.action] += file_size

        if progress_cb is not None:
            progress_cb(idx + 1, total)

        if mode == "m":
            dst_dir = os.path.dirname(dst)
            os.makedirs(dst_dir, exist_ok=True)
            ensure_output_permissions(dst_dir, is_dir=True)
            if not os.path.exists(dst):
                shutil.move(file_path, dst)
                ensure_output_permissions(dst, is_dir=False)
            else:
                log_fn(f"{move.group_name}\t[SKIP_EXISTS]\t{dst}")
                action_counter["SKIP_EXISTS"] += 1
