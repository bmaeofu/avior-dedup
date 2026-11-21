from __future__ import annotations
def _series_marker_completeness(path: str) -> int:
    """Return the highest configured episode-marker score in a filename."""
    stem = os.path.splitext(os.path.basename(path))[0]
def _series_marker_completeness(path: str) -> int:
    """Return the highest configured episode-marker score in a filename."""
    stem = os.path.splitext(os.path.basename(path))[0]
    best = 0
    for item in config.series_marker_scores():
        pattern = str(item["pattern"])
        try:
            matched = re.search(pattern, stem, flags=re.IGNORECASE) is not None
        except re.error as exc:
            raise ValueError(f"Invalid series marker pattern {pattern!r}: {exc}") from exc
        if matched:
            best = max(best, int(item["points"]))
    return best


def _series_marker_completeness(path: str) -> int:
    """Return the highest configured episode-marker score in a filename."""
    stem = os.path.splitext(os.path.basename(path))[0]
    best = 0
    for item in config.series_marker_scores():
        pattern = str(item["pattern"])
        try:
            matched = re.search(pattern, stem, flags=re.IGNORECASE) is not None
        except re.error as exc:
            raise ValueError(f"Invalid series marker pattern {pattern!r}: {exc}") from exc
        if matched:
            best = max(best, int(item["points"]))
    return best


def _series_marker_completeness(path: str) -> int:
    """Return the highest configured episode-marker score in a filename."""
    stem = os.path.splitext(os.path.basename(path))[0]
    best = 0
    for item in config.series_marker_scores():
        pattern = str(item["pattern"])
        try:
            matched = re.search(pattern, stem, flags=re.IGNORECASE) is not None
        except re.error as exc:
            raise ValueError(f"Invalid series marker pattern {pattern!r}: {exc}") from exc
        if matched:
            best = max(best, int(item["points"]))
    return best


def _sort_key(
    r: FileRecord,
    priorities: list[SelectionPriority],
    max_errors_when_mc: int | None = None,
    max_duration_diff_longer: int = 600,
    max_duration_diff_shorter: int = 240,
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
            # Prefer the recording whose duration is closest to the EPG duration.
            if r.video_duration is not None and r.rec_duration is not None:
                key.append(abs(r.video_duration - r.rec_duration))
            else:
                key.append(10**9)
        elif p == SelectionPriority.RECORDING_DATE:
            # newer should be better -> smaller sort key -> use negative ordinal
            key.append(-_recording_ordinal(r))
        elif p == SelectionPriority.YEAR_MATCH:
            # Prefer records where the .nfo year matches the .txt year.
            key.append(0 if _year_matches(r) else 1)
        elif p == SelectionPriority.SERIES_MARKER_COMPLETENESS:
            # Higher marker completeness should sort first.
            key.append(-_series_marker_completeness(r.file))

        elif p == SelectionPriority.CLEAN_NAME:
            # Prefer the cleaner name, i.e. the fewest repeated tokens.
            key.append(_name_redundancy(r.file))
        elif p == SelectionPriority.LOG_INCLUDE:
            # Prefer the copy that avior-go did not mark as replaceable.
            # Unknown (no log) ranks with the marked copies.
            key.append(0 if r.log_include_match is False else 1)
    return tuple(key)


def select_best_film(
    valid_records: list[FileRecord],
    max_duration_diff_longer: int = 600,
    max_duration_diff_shorter: int = 240,
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


def _year_matches(r: FileRecord) -> bool:
    """Return True when the record's .nfo year matches its .txt year."""
    return (
        r.nfo_year is not None
        and r.txt_year is not None
        and r.nfo_year == r.txt_year
    )


def _recording_ordinal(r: FileRecord) -> float:
    """Return a comparable recording date, preserving mtime precision."""
    if getattr(r, "rec_date", None):
        try:
            matched = re.search(pattern, stem, flags=re.IGNORECASE) is not None
        except re.error as exc:
            raise ValueError(f"Invalid series marker pattern {pattern!r}: {exc}") from exc
        if matched:
            best = max(best, int(item["points"]))
    return best


def _reason_for_priority(
    priority: SelectionPriority,
    best: FileRecord,
    others: list[FileRecord],
    max_errors_when_mc: int | None,
    max_duration_diff_longer: int = 600,
    max_duration_diff_shorter: int = 240,
) -> str | None:
    """Return the reason label when *priority* separates `best` from `others`."""
    try:
        if priority == SelectionPriority.MULTICHANNEL:
            if best.multichannel:
                for o in others:
                    if not o.multichannel:
                        # If best has acceptable errors when MC is considered
                        if max_errors_when_mc is None or (best.error_count or 0) <= max_errors_when_mc:
                            return "multichannel"
        elif priority == SelectionPriority.RESOLUTION:
            best_res = best.resolution or 0
            if any((o.resolution or 0) < best_res for o in others):
                return "higher_resolution"
        elif priority == SelectionPriority.FEWER_ERRORS:
            best_err = best.error_count if best.error_count is not None else 10**9
            if any(((o.error_count if o.error_count is not None else 10**9) > best_err) for o in others):
                return "fewer_errors"
        elif priority == SelectionPriority.SERIES_MARKER_COMPLETENESS:
            best_score = _series_marker_completeness(best.file)
            if any(_series_marker_completeness(o.file) < best_score for o in others):
                return "series_marker_completeness"
        elif priority == SelectionPriority.CLEAN_NAME:
            best_redundancy = _name_redundancy(best.file)
            if any(_name_redundancy(o.file) > best_redundancy for o in others):
                return "cleaner_name"
        elif priority == SelectionPriority.LOG_INCLUDE:
            if best.log_include_match is False and any(o.log_include_match is not False for o in others):
                return "no_include_match"
        elif priority == SelectionPriority.RECORDING_DATE:
            if any(_recording_ordinal(o) < _recording_ordinal(best) for o in others):
                return "newer"
        elif priority == SelectionPriority.YEAR_MATCH:
            if _year_matches(best) and any(not _year_matches(o) for o in others):
                return "year_match"
        elif priority == SelectionPriority.CLOSEST_DURATION:
            def distance(r: FileRecord) -> float:
                if r.video_duration is None or r.rec_duration is None:
                    return 10**9
                return abs(r.video_duration - r.rec_duration)

        try:
            matched = re.search(pattern, stem, flags=re.IGNORECASE) is not None
        except re.error as exc:
            raise ValueError(f"Invalid series marker pattern {pattern!r}: {exc}") from exc
        if matched:
            best = max(best, int(item["points"]))
    return best


        elif p == SelectionPriority.SERIES_MARKER_COMPLETENESS:
            # Higher marker completeness should sort first.
            key.append(-_series_marker_completeness(r.file))
        elif priority == SelectionPriority.SERIES_MARKER_COMPLETENESS:
            best_score = _series_marker_completeness(best.file)
            if any(_series_marker_completeness(o.file) < best_score for o in others):
                return "series_marker_completeness"

        try:
            for rec in get_video_md(global_uncached, log_fn=log_fn, progress_cb=_probe_cb):
                film_info_cache[rec.file] = rec
        except Exception:
            # Keep going even if metadata probing fails for some files
            pass
        t_fetch = time.perf_counter() - t_fetch_start
        film_info_accumulator += t_fetch
        try:
            log_fn(f"TIMING prefetch: {t_fetch:.3f}s for {len(global_uncached)} files")
        except Exception:
            pass

    # Build a stem -> representative FileRecord map from the probed files
    # so we can apply full metadata to unprobed siblings sharing the same stem.
    stem_prefetched: dict[str, FileRecord] = {}
    try:
        for rec in list(film_info_cache.values()):
            stem = match_suffix(os.path.basename(rec.file))[0]
            # Prefer entries that actually have useful media metadata
            if rec.video_exists and (rec.resolution is not None or rec.video_duration is not None or rec.multichannel is not None):
                if stem not in stem_prefetched:
                    stem_prefetched[stem] = rec
    except Exception:
        stem_prefetched = {}
    # Build a map of the originally prefetched paths -> FileRecord so we can
    # directly lookup by the exact paths that were passed into build_move_plan.
    prefetch_by_path: dict[str, FileRecord] = {rec.file: rec for rec in film_info_cache.values() if rec.file in input_files}

    for group_idx, group in enumerate(groups):
        # Build FileRecords for this group (with caching)
        records: list[FileRecord] = []
        # At this point `film_info_cache` already contains metadata for all
        # uncached paths (fetched once above). Build `records` from the cache.
        for f in group:
            # Use cached metadata when available. If the (expanded) sibling
            # wasn't part of the original input set, create a lightweight
            # placeholder FileRecord so planning can continue without probing.
            rec = film_info_cache.get(f)
            if rec is None:
                # First try direct lookup by expected .log path (same dir, stem + '.log')
                stem = stem_map.get(f, match_suffix(os.path.basename(f))[0])
                dirpath = dir_map.get(f, os.path.dirname(f))
                candidates: list[str] = []
                try:
                    candidates.append(os.path.join(dirpath, stem + ".log"))
                except Exception:
                    pass
                # Also consider any originally prefetched input files that share the same stem
                for p in input_files:
                    if match_suffix(os.path.basename(p))[0] == stem:
                        candidates.append(p)

                rep: FileRecord | None = None
                for cand in candidates:
                    rep = prefetch_by_path.get(cand) or film_info_cache.get(cand)
                    if rep is not None:
                        break

                if rep is not None:
                    # Carry over *every* field from the stem's representative so
                    # a newly added FileRecord field cannot silently be forgotten
                    # here (that is how log_include_match ended up as None).
                    rec = dataclasses.replace(rep, file=f)
                else:
                    exists = os.path.exists(f)
                    mod_date = None
                    try:
                        if exists:
                            mod_date = os.path.getmtime(f)
                    except Exception:
                        mod_date = None
                    rec = FileRecord(file=f, video_exists=exists, mod_date=mod_date)
                film_info_cache[f] = rec
            records.append(rec)

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
            # Decide KEEP only for files that are in the same directory as
            # the selected representative (`best_film`). Files with the same
            # stem but in other directories are considered duplicates.
            best_stem = stem_map.get(best_film.file, match_suffix(os.path.basename(best_film.file))[0])
            src_stem = stem_map.get(src, match_suffix(os.path.basename(src))[0])
            best_dir = os.path.dirname(best_film.file)
            src_dir = dir_map.get(src, os.path.dirname(src))

            # KEEP only the exact selected representative file and its siblings
            # in the same directory. Files in other directories with the same
            # stem are treated as DUPLICATE.
            if src_stem == best_stem and src_dir == best_dir:
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

                    # For KEEP lines include a reason in the found_path column
                    reason = determine_keep_reason(
                        rep,
                        [r for r in valid_records if r.file != rep.file],
                        selection_priorities or DEFAULT_SELECTION_PRIORITIES,
                        max_errors_when_mc,
                        max_duration_diff_longer,
                        max_duration_diff_shorter,
                    )
                    log_fn(f"[{action}]\t{group_name}\t{src}\t{reason}\t{res_str}\t{audio_str}\t{length_flag}\t{err_count}")
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
        log_fn(f"TIMING probes_total: {film_info_accumulator:.3f}s build_total: {t_total:.3f}s")
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
        log_fn(f"[{move.action}]\t{move.group_name}\t{file_path}\t{dst}\t{res_str}\t{audio_str}\t{length_flag}\t{err_count}")
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
            # Attempt to copy permissions from the source directory to the
            # newly created destination directory so mirrored structure keeps
            # the same POSIX mode/ownership when possible.
            try:
                from avior_dedup.permissions import copy_dir_permissions

                src_dir_perm = os.path.dirname(src_to_move)
                copy_dir_permissions(src_dir_perm, dst_dir)
            except Exception:
                pass
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
                                log_fn(f"[CHECK_RESOLVE]\t{move.group_name}\t{file_path}\tresolved_to={candidate}")
                                src_to_move = candidate
                                exists = True
                                break
                    except Exception as e:
                        log_fn(f"[CHECK_RESOLVE_FAIL]\t{move.group_name}\t{file_path}\t{e}")

                if not os.path.exists(dst):
                    try:
                        if not os.path.exists(src_to_move):
                            # Source still missing — log and continue
                            log_fn(f"[ERROR_MOVE]\t{move.group_name}\t{src_to_move}\t{dst}\t[WinError 2] The system cannot find the file specified")
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
                        log_fn(f"[ERROR_MOVE]\t{move.group_name}\t{src_to_move}\t{dst}\t{e}")
                        action_counter["ERROR_MOVE"] += 1
                else:
                    log_fn(f"[SKIP_EXISTS]\t{move.group_name}\t{dst}")
                    action_counter["SKIP_EXISTS"] += 1
            except Exception as e:
                # Catch-all to prevent aborting the run; log and continue
                log_fn(f"[ERROR_MOVE]\t{move.group_name}\t{file_path}\t{dst}\t{e}")
                action_counter["ERROR_MOVE"] += 1
    return resolution_by_action, resolution_size_by_action, attr_matrix
