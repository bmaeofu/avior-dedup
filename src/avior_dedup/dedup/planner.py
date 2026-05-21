from __future__ import annotations

import os
import shutil
from collections import Counter, defaultdict
from typing import Callable
import datetime
import time

from avior_dedup.dedup.models import (
    DEFAULT_SELECTION_PRIORITIES,
    FileRecord,
    GroupKeys,
    MoveAction,
    SelectionPriority,
)
from avior_dedup.dedup.scanner import get_film_error_count
from avior_dedup import config
from avior_dedup.dedup.suffix import match_suffix
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
) -> tuple[dict[str, MoveAction], Counter, Counter, dict[str, Counter], dict[str, Counter]]:
    """Decide what to do with each file.

    Returns (files_to_move, action_counter, size_counter, resolution_by_action, resolution_size_by_action).
    """
    film_info_cache: dict[str, FileRecord] = {}
    files_to_move: dict[str, MoveAction] = {}
    already_logged: set[tuple[str, str]] = set()
    action_counter: Counter = Counter()
    size_counter: Counter = Counter()
    # Per-action resolution counters for KEEP (since kept files are not in files_to_move)
    resolution_by_action: dict[str, Counter] = defaultdict(Counter)
    resolution_size_by_action: dict[str, Counter] = defaultdict(Counter)
    # Cross-tab attribute matrix: attr -> Counter(attr->count) (KEEP entries only)
    attr_matrix: dict[str, Counter] = defaultdict(Counter)
    # Per-file attribute list for files that will be moved (counted later in execute)
    attrs_by_file: dict[str, list[str]] = {}
    errors_by_file: dict[str, int] = {}
    
    total_groups = len(groups)
    # For finer-grained planning progress, count total files to be processed
    # (after potential expansion) and report progress per file.
    total_files_to_plan = sum(len(g) for g in groups)
    files_processed = 0
    # Limit progress updates to a configurable number of steps to avoid UI/request overhead.
    # Controlled by environment variable `AVIOR_DEDUP_PROGRESS_UPDATES` (default 20).
    try:
        target_updates = int(os.getenv("AVIOR_DEDUP_PROGRESS_UPDATES", "100"))
    except Exception:
        target_updates = 100
    progress_interval = max(1, total_files_to_plan // max(1, target_updates))

    # Expand groups: if caller supplied groups consisting of .log files only
    # (scanner now groups by .log stems), expand each log-file entry into the
    # full set of sibling files that share the same stem in the same
    # directory according to configured `candidate_suffixes`.
    t_build_start = time.perf_counter()
    film_info_accumulator = 0.0
    t_expand_start = time.perf_counter()
    expanded_groups: list[list[str]] = []
    suffixes = config.candidate_suffixes()
    # Cache directory listings to avoid repeated os.path.exists calls
    dir_listing_cache: dict[str, set[str]] = {}
    for group in groups:
        collected: set[str] = set()
        for f in group:
            stem, _ = match_suffix(os.path.basename(f))
            dirpath = os.path.dirname(f)
            if dirpath not in dir_listing_cache:
                try:
                    dir_listing_cache[dirpath] = set(os.listdir(dirpath))
                except OSError:
                    dir_listing_cache[dirpath] = set()
            files_in_dir = dir_listing_cache[dirpath]
            for suf in suffixes:
                candidate_name = stem + suf
                if candidate_name in files_in_dir:
                    collected.add(os.path.join(dirpath, candidate_name))
        if collected:
            expanded_groups.append(sorted(collected))
    # Use expanded groups if expansion produced anything, otherwise keep original
    if expanded_groups:
        groups = expanded_groups
        total_groups = len(groups)
    t_expand = time.perf_counter() - t_expand_start
    try:
        log_fn(f"TIMING expansion: {t_expand:.3f}s, groups_after={total_groups}")
    except Exception:
        pass

    # Precompute basename/stem/dir for all files in the (possibly expanded) groups
    all_files = [f for g in groups for f in g]
    basename_map: dict[str, str] = {f: os.path.basename(f) for f in all_files}
    stem_map: dict[str, str] = {f: match_suffix(basename_map[f])[0] for f in all_files}
    dir_map: dict[str, str] = {f: os.path.dirname(f) for f in all_files}

    for group_idx, group in enumerate(groups):
        # Build FileRecords for this group (with caching)
        records: list[FileRecord] = []
        uncached = [f for f in group if f not in film_info_cache]
        if uncached:
            # Only probe one representative per video-set (prefer video file,
            # then plain .log, then any .log, else first uncached). This avoids
            # repeated ffprobe/log parsing for sidecar files.
            rep = None
            video_exts = {e.lower() for e in config.video_suffixes()}
            # prefer an uncached video file
            for f in uncached:
                suf = match_suffix(os.path.basename(f))[1] or ""
                if suf.lower() in video_exts:
                    rep = f
                    break
            # prefer plain .log (not .mkv.log) if no video
            if rep is None:
                for f in uncached:
                    bn = os.path.basename(f).lower()
                    if bn.endswith('.log') and not bn.endswith('.mkv.log'):
                        rep = f
                        break
            # fallback: any .log
            if rep is None:
                for f in uncached:
                    if os.path.basename(f).lower().endswith('.log'):
                        rep = f
                        break
            # last resort: first uncached
            if rep is None:
                rep = uncached[0]

            t_fetch_start = time.perf_counter()
            reps = [rep]
            for rec in get_film_error_count(reps, log_fn=log_fn):
                # store the record for the representative path
                film_info_cache[rec.file] = rec
                # clone the record for all other files in the same group
                for sibling in group:
                    if sibling not in film_info_cache:
                        film_info_cache[sibling] = FileRecord(
                            file=sibling,
                            video_exists=rec.video_exists,
                            error_count=rec.error_count,
                            mod_date=rec.mod_date,
                            multichannel=rec.multichannel,
                            resolution=rec.resolution,
                            video_duration=rec.video_duration,
                            rec_duration=rec.rec_duration,
                            rec_date=rec.rec_date,
                        )
            t_fetch = time.perf_counter() - t_fetch_start
            film_info_accumulator += t_fetch
            try:
                log_fn(f"TIMING get_film_error_count: {t_fetch:.3f}s for rep={os.path.basename(rep)} (expanded to {len(group)} files)")
            except Exception:
                pass
        for f in group:
            records.append(film_info_cache[f])

        valid_records = [r for r in records if r.video_exists]

        # Also update progress at group boundary in case some groups had no
        # uncached files (ensures steady progress even when cached entries are used).
        if progress_cb is not None:
            # Report planning progress as groups processed / total groups.
            progress_cb(group_idx + 1, total_groups)

        # Case: no video exists for any file in the group
        if not valid_records:
            for r in records:
                group_name = get_group_name(r.file, duptype, file_to_groupkey)
                files_to_move[r.file] = MoveAction(novideo_target, "NO_VIDEO", group_name, resolution=r.resolution)
            continue

        best_film = select_best_film(
            valid_records,
            max_duration_diff_longer=max_duration_diff_longer,
            max_duration_diff_shorter=max_duration_diff_shorter,
            selection_priorities=selection_priorities,
            max_errors_when_mc=max_errors_when_mc,
        )
        for r in records:
            src = r.file
            group_name = get_group_name(src, duptype, file_to_groupkey)
            # Decide KEEP for the whole stem chosen by select_best_film.
            best_stem = stem_map.get(best_film.file, match_suffix(os.path.basename(best_film.file))[0])
            src_stem = stem_map.get(src, match_suffix(os.path.basename(src))[0])

            if src_stem == best_stem:
                # Use attributes from the best_film as representative for the whole set
                rep = best_film
                base_action = "KEEP_MC" if getattr(rep, "multichannel", False) else "KEEP"
                has_errors = getattr(rep, "error_count", None) is not None and getattr(rep, "error_count", 0) > 0
                has_duration_values = getattr(rep, "video_duration", None) is not None and getattr(rep, "rec_duration", None) is not None
                is_too_long = has_duration_values and (rep.video_duration - rep.rec_duration) > max_duration_diff_longer
                is_too_short = has_duration_values and (rep.video_duration - rep.rec_duration) < -max_duration_diff_shorter

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
                    file_size = _get_file_size(src)

                    # Representative resolution/audio/length/errors come from rep
                    if getattr(rep, "resolution", None) is not None:
                        if rep.resolution >= 1080:
                            res_str = "1080"
                        elif rep.resolution >= 720:
                            res_str = "720"
                        else:
                            res_str = "unknown"
                    else:
                        res_str = "unknown"

                    if getattr(rep, "multichannel", None) is True:
                        audio_str = "MC"
                    elif getattr(rep, "multichannel", None) is False:
                        audio_str = "Stereo"
                    else:
                        audio_str = "unknown"

                    length_flag = ""
                    if has_duration_values:
                        if is_too_long:
                            length_flag = "longer"
                        elif is_too_short:
                            length_flag = "shorter"
                        else:
                            length_flag = "ok"

                    err_count = rep.error_count if getattr(rep, "error_count", None) is not None else 0

                    # For KEEP lines include an empty found_path column so columns align with DUPLICATE lines
                    log_fn(f"{group_name}\t[{action}]\t{src}\t\t{res_str}\t{audio_str}\t{length_flag}\t{err_count}")
                    action_counter[action] += 1
                    size_counter[action] += file_size
                    # record resolution counters for kept files
                    res = rep.resolution if getattr(rep, "resolution", None) is not None else 0
                    resolution_by_action[action][res] += 1
                    resolution_size_by_action[action][res] += file_size
                    # record attribute flags for this file
                    attrs: list[str] = []
                    if rep.multichannel:
                        attrs.append("MC")
                    if rep.error_count is not None and rep.error_count > 0:
                        attrs.append("ERRORS")
                    if has_duration_values and is_too_long:
                        attrs.append("LONGER")
                    if has_duration_values and is_too_short:
                        attrs.append("SHORTER")
                    if rep.resolution is not None:
                        if rep.resolution >= 1080:
                            attrs.append("1080")
                        elif rep.resolution >= 720:
                            attrs.append("720")
                    # mark as KEEP so we get cross-counts with other attributes
                    attrs.append("KEEP")
                    # ensure attributes are unique to avoid double-counting
                    attrs = list(dict.fromkeys(attrs))
                    for a in attrs:
                        for b in attrs:
                            attr_matrix[a][b] += 1
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

            files_to_move[src] = MoveAction(dst_root, action, group_name, resolution=r.resolution)
            # Collect attributes for moved files to be counted in execute_move_plan
            attrs_move: list[str] = []
            if r.multichannel:
                attrs_move.append("MC")
            if r.error_count is not None and r.error_count > 0:
                attrs_move.append("ERRORS")
            if has_duration_values and is_too_long:
                attrs_move.append("LONGER")
            if has_duration_values and is_too_short:
                attrs_move.append("SHORTER")
            # mark presence of duration values and OK state for files within bounds
            if has_duration_values and not is_too_long and not is_too_short:
                attrs_move.append("OK")
            if r.resolution is not None:
                if r.resolution >= 1080:
                    attrs_move.append("1080")
                elif r.resolution >= 720:
                    attrs_move.append("720")
            attrs_move.append("DUPLICATE")
            # ensure attributes are unique before storing to avoid duplicates
            attrs_move = list(dict.fromkeys(attrs_move))
            attrs_by_file[src] = attrs_move
            # record numeric error count for this file to be used during execute
            errors_by_file[src] = r.error_count if r.error_count is not None else 0

    t_total = time.perf_counter() - t_build_start
    try:
        log_fn(f"TIMING build_move_plan total: {t_total:.3f}s (film_info={film_info_accumulator:.3f}s)")
    except Exception:
        pass
    return (
        files_to_move,
        action_counter,
        size_counter,
        resolution_by_action,
        resolution_size_by_action,
        attr_matrix,
        attrs_by_file,
        errors_by_file,
    )


def execute_move_plan(
    files_to_move: dict[str, MoveAction],
    source_root: str,
    mode: str,
    action_counter: Counter,
    log_fn: Callable[[str], None],
    progress_cb: Callable[[int, int], None] | None = None,
    size_counter: Counter | None = None,
    attrs_by_file: dict[str, list[str]] | None = None,
    errors_by_file: dict[str, int] | None = None,
) -> tuple[dict[str, Counter], dict[str, Counter], dict[str, Counter]]:
    """Execute or dry-run the move plan."""
    if size_counter is None:
        size_counter = Counter()
    # Per-action resolution counters: action -> Counter(resolution->count)
    from collections import defaultdict

    resolution_by_action: dict[str, Counter] = defaultdict(Counter)
    resolution_size_by_action: dict[str, Counter] = defaultdict(Counter)
    attr_matrix: dict[str, Counter] = defaultdict(Counter)
    sorted_items = sorted(files_to_move.items())
    total = len(sorted_items)
    for idx, (file_path, move) in enumerate(sorted_items):
        rel = os.path.relpath(file_path, source_root)
        dst = os.path.join(move.dst_root, rel)

        file_size = _get_file_size(file_path)
        # Append error count for moves when available
        err_count = errors_by_file.get(file_path, 0) if errors_by_file is not None else 0
        # Build appended attribute columns for moved files: resolution, audio, length_flag, errors
        # Start with attrs coming from attrs_by_file (if provided)
        attrs_move = []
        if attrs_by_file and file_path in attrs_by_file:
            attrs_move.extend(attrs_by_file[file_path])
        # Normalize resolution
        if getattr(move, "resolution", None) is not None:
            if move.resolution >= 1080:
                res_str = "1080"
            elif move.resolution >= 720:
                res_str = "720"
            else:
                res_str = "unknown"
        else:
            res_str = "unknown"

        audio_str = "MC" if "MC" in attrs_move else ("Stereo" if "MC" not in attrs_move and attrs_move else "unknown")

        length_flag = ""
        if "LONGER" in attrs_move:
            length_flag = "longer"
        elif "SHORTER" in attrs_move:
            length_flag = "shorter"
        elif "OK" in attrs_move:
            length_flag = "ok"

        # err_count is numeric
        # Log with destination and appended attributes
        log_fn(f"{move.group_name}\t[{move.action}]\t{file_path}\t{dst}\t{res_str}\t{audio_str}\t{length_flag}\t{err_count}")
        action_counter[move.action] += 1
        size_counter[move.action] += file_size
        # Only count resolution and attributes for actual video files (e.g., .mkv)
        if str(file_path).lower().endswith(".mkv"):
            # Track resolution distribution per action (use 0 for unknown)
            res = move.resolution if getattr(move, "resolution", None) is not None else 0
            resolution_by_action[move.action][res] += 1
            resolution_size_by_action[move.action][res] += file_size
        # attributes for moved file: prefer attrs_by_file from build, but ensure resolution/DUPLICATE tags present
        attrs_move = []
        if attrs_by_file and file_path in attrs_by_file:
            attrs_move.extend(attrs_by_file[file_path])
            # If move.resolution is not available, don't trust resolution tags coming
            # from attrs_by_file (these can be sidecar/meta files). Remove them so
            # resolution counts come only from `move.resolution`.
            if getattr(move, "resolution", None) is None:
                attrs_move = [a for a in attrs_move if a not in ("720", "1080")]
        # normalize resolution tag: remove any existing resolution tags
        # then append the correct tag from move.resolution (if available).
        attrs_move = [a for a in attrs_move if a not in ("720", "1080")]
        if move.resolution is not None:
            if move.resolution >= 1080:
                attrs_move.append("1080")
            elif move.resolution >= 720:
                attrs_move.append("720")
        # ensure DUPLICATE tag
        if "DUPLICATE" not in attrs_move and move.action.startswith("DUPLICATE"):
            attrs_move.append("DUPLICATE")
        # ensure uniqueness before counting to avoid accidental duplicates
        attrs_move = list(dict.fromkeys(attrs_move))
        # Only include attribute counts for actual video files
        if str(file_path).lower().endswith(".mkv"):
            for a in attrs_move:
                for b in attrs_move:
                    attr_matrix[a][b] += 1

        if progress_cb is not None:
            progress_cb(idx + 1, total)

        if mode == "m":
            dst_dir = os.path.dirname(dst)
            os.makedirs(dst_dir, exist_ok=True)
            ensure_output_permissions(dst_dir, is_dir=True)
            try:
                # Diagnostic existence check before attempting move — helps
                # determine whether WinError 2 is caused by missing source.
                exists = os.path.exists(file_path)

                src_to_move = file_path
                # If source doesn't exist, attempt a case-insensitive resolution
                # in the parent directory (handles Windows/Samba case mismatches).
                if not exists:
                    parent = os.path.dirname(file_path) or os.path.sep
                    base = os.path.basename(file_path)
                    try:
                        for entry in os.listdir(parent):
                            if entry.lower() == base.lower():
                                candidate = os.path.join(parent, entry)
                                log_fn(f"{move.group_name}\t[CHECK_RESOLVE]\t{file_path}\tresolved_to={candidate}")
                                src_to_move = candidate
                                exists = True
                                break
                    except Exception as e:
                        log_fn(f"{move.group_name}\t[CHECK_RESOLVE_FAIL]\t{file_path}\t{e}")

                if not os.path.exists(dst):
                    try:
                        if not os.path.exists(src_to_move):
                            # Source still missing — log and continue
                            log_fn(f"{move.group_name}\t[ERROR_MOVE]\t{src_to_move}\t{dst}\t[WinError 2] The system cannot find the file specified")
                            action_counter["ERROR_MOVE"] += 1
                        else:
                            # If resolution changed, adjust size counters to reflect actual file
                            actual_size = _get_file_size(src_to_move)
                            if actual_size != file_size:
                                delta = actual_size - file_size
                                size_counter[move.action] += delta
                                # also adjust resolution_size_by_action if applicable
                                if str(src_to_move).lower().endswith(".mkv"):
                                    res = move.resolution if getattr(move, "resolution", None) is not None else 0
                                    resolution_size_by_action[move.action][res] += delta

                            shutil.move(src_to_move, dst)
                            ensure_output_permissions(dst, is_dir=False)
                    except OSError as e:
                        # OS errors (permissions, etc.) — log and continue
                        log_fn(f"{move.group_name}\t[ERROR_MOVE]\t{src_to_move}\t{dst}\t{e}")
                        action_counter["ERROR_MOVE"] += 1
                else:
                    log_fn(f"{move.group_name}\t[SKIP_EXISTS]\t{dst}")
                    action_counter["SKIP_EXISTS"] += 1
            except Exception as e:
                # Catch-all to prevent aborting the run; log and continue
                log_fn(f"{move.group_name}\t[ERROR_MOVE]\t{file_path}\t{dst}\t{e}")
                action_counter["ERROR_MOVE"] += 1
    return resolution_by_action, resolution_size_by_action, attr_matrix
