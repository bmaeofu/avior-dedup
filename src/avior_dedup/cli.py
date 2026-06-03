from __future__ import annotations

import argparse
import os
from datetime import datetime
from collections import Counter

from avior_dedup.dedup.models import SelectionPriority
from avior_dedup.dedup.planner import build_move_plan, execute_move_plan
from avior_dedup.dedup.reporting import sort_and_finalize_log
from avior_dedup.dedup.scanner import find_duplicates
from avior_dedup.permissions import apply_runtime_umask, ensure_output_permissions


def get_numbered_log_file(path: str) -> str:
    """Return a non-conflicting log file path by appending a number if needed."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    counter = 1
    while True:
        candidate = f"{base}_{counter:03d}{ext}"
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def main() -> None:
    apply_runtime_umask()

    class ArgParseError(Exception):
        pass

    class NoExitArgumentParser(argparse.ArgumentParser):
        def error(self, message: str) -> None:  # raise instead of exiting
            raise ArgParseError(message)

    parser = NoExitArgumentParser(description="Duplicate film files finder/mover")
    parser.add_argument("mode", choices=["m", "f"], help="m = move, f = find only")
    parser.add_argument("source", help="source directory")
    parser.add_argument("target", help="target directory")
    parser.add_argument("logname", nargs="?", default="dedup_log_cli.txt", help="log file name (default: dedup_log_cli.txt)")
    parser.add_argument(
        "--duptype",
        choices=["case", "exact", "semantic", "both", "all"],
        default="case",
        help="case = case-insensitive, exact = exact name, semantic = normalized name, both = case+exact, all = all types",
    )
    parser.add_argument("--error-target", help="Directory where worse recordings are moved")
    parser.add_argument("--novideo-target", help="Directory where metadata with no video are moved")
    parser.add_argument("--max-errors-when-mc", type=int, default=0, help="Max allowed errors for multichannel to be considered good")
    parser.add_argument(
        "--max-duration-diff-longer",
        type=int,
        default=600,
        help="Max allowed positive difference (video_duration - rec_duration) in seconds",
    )
    parser.add_argument(
        "--max-duration-diff-shorter",
        type=int,
        default=180,
        help="Maxallowed negative difference (rec_duration - video_duration) in seconds",
    )
    parser.add_argument(
        "--selection-priorities",
        nargs="+",
        default=["multichannel", "resolution", "fewer_errors", "recording_date", "closest_duration"],
        choices=[p.value for p in SelectionPriority],
        help="Ordered priority list for best-film selection (default: multichannel resolution fewer_errors recording_date closest_duration)",
    )
    parser.add_argument(
        "--semantic-prefixes",
        nargs="+",
        default=None,
        help="List of regex prefixes to strip for semantic duplicate detection",
    )
    parser.add_argument(
        "--remove-episode-nos",
        action="store_true",
        help="Remove episode numbers like (1_2), (2) for semantic matching (skipped if certain keywords are present)",
    )
    parser.add_argument(
        "--remove-spaces",
        action="store_true",
        help="Also remove all spaces when computing semantic normalization (space-insensitive matching)",
    )
    parser.add_argument(
        "--remove-non-episode-parens",
        action="store_true",
        help="Remove parenthetical expressions that are not episode numbers when computing semantic normalization",
    )
    parser.add_argument(
        "--replace-underscores",
        action="store_true",
        help="Replace underscores with spaces before semantic normalization (useful for filenames with _ separators)",
    )
    parser.add_argument(
        "--ignored-directories",
        nargs="+",
        help="List of directories to ignore for this run (full paths or directory names)",
    )
    parser.add_argument(
        "--normalize-episode-nos",
        action="store_true",
        help="Normalize episode tokens like (1_5) or (S01_E05) to standard form (s01e05) instead of removing them",
    )

    try:
        args = parser.parse_args()
    except ArgParseError as e:
        print("Argument parsing failed:", e)
        parser.print_usage()
        raise SystemExit(2)

    # Record run start time so final SUMMARY shows a meaningful Start time
    try:
        args.start_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        args.start_time = None

    # If no semantic prefixes were provided, normalize to an empty list so
    # downstream code can always iterate over it.
    if args.semantic_prefixes is None:
        args.semantic_prefixes = []

    source_root = os.path.abspath(args.source)
    target_root = os.path.abspath(args.target)
    error_target = os.path.abspath(args.error_target) if args.error_target else os.path.join(target_root, "errors")
    novideo_target = os.path.abspath(args.novideo_target) if args.novideo_target else os.path.join(target_root, "no_video")

    # Print parsed PARAMETERS immediately so the CLI shows the exact selections
    print("\nPARAMETERS:")
    print(f"  Mode:                   {args.mode} ({'MOVE' if args.mode == 'm' else 'FIND ONLY'})")
    print(f"  Source:                 {args.source}")
    print(f"  Target:                {args.target}")
    print(f"  Error target:          {args.error_target or 'default'}")
    print(f"  Duplicate type:        {args.duptype}")
    print(f"  Max errors (MC):       {args.max_errors_when_mc}")
    print(f"  Max duration +diff:    {args.max_duration_diff_longer}")
    print(f"  Max duration -diff:    {args.max_duration_diff_shorter}")
    print(f"  Selection priorities:  {', '.join(p.value if hasattr(p, 'value') else str(p) for p in args.selection_priorities)}")
    print(f"  Semantic prefixes:     {', '.join(args.semantic_prefixes) if args.semantic_prefixes else 'none'}")
    print(f"  Remove episode nos:    {'yes' if args.remove_episode_nos else 'no'}")
    print(f"  Remove spaces:         {'yes' if getattr(args, 'remove_spaces', False) else 'no'}")
    print(f"  Remove non-episode parentheses: {'yes' if getattr(args, 'remove_non_episode_parens', False) else 'no'}")
    print(f"  Ignored directories:   {', '.join(getattr(args, 'ignored_directories')) if getattr(args, 'ignored_directories', None) else 'none'}")

    os.makedirs(target_root, exist_ok=True)
    os.makedirs(error_target, exist_ok=True)
    os.makedirs(novideo_target, exist_ok=True)
    ensure_output_permissions(target_root, is_dir=True)
    ensure_output_permissions(error_target, is_dir=True)
    ensure_output_permissions(novideo_target, is_dir=True)

    log_path = get_numbered_log_file(os.path.join(target_root, args.logname))
    log_handle = open(log_path, "w", encoding="utf-8")
    ensure_output_permissions(log_path, is_dir=False)

    # Create a corresponding timing log next to the main log with the
    # same numbering as the dedup log and keep files. If the numbered
    # dedup log follows the pattern 'dedup_log_<suffix>' we create
    # 'dedup_timing_<suffix>' so numbering matches exactly.
    import re

    orig_name = os.path.basename(log_path)
    base, ext = os.path.splitext(orig_name)
    # Name timing files as `timing_{logbasename_no_ext}{ext}` so the
    # timing file clearly relates to the original log file.
    timing_name = f"timing_{base}{ext}"

    timing_path = os.path.join(os.path.dirname(log_path), timing_name)
    timing_handle = open(timing_path, "w", encoding="utf-8")
    ensure_output_permissions(timing_path, is_dir=False)

    def log_fn(msg: str) -> None:
        # TIMING lines go only to the timing diagnostic log (and not to
        # the user-facing main log). Other messages go to stdout + main log.
        try:
            if isinstance(msg, str) and msg.startswith("TIMING"):
                timing_handle.write(msg + "\n")
            else:
                print(msg)
                log_handle.write(msg + "\n")
        except Exception:
            # Best-effort logging; ignore failures to avoid aborting run
            pass

    groups, file_to_groupkey = find_duplicates(
        source_root,
        args.duptype,
        args.remove_episode_nos,
        args.semantic_prefixes or [],
        args.remove_spaces,
        args.remove_non_episode_parens,
        args.replace_underscores,
        args.ignored_directories,
    )

    print(f"\nDuplicate groups found: {len(groups)}")
    print(f"Duplicate type: {args.duptype}")
    print(f"Mode: {'MOVE' if args.mode == 'm' else 'FIND ONLY'}\n")

    selection_prios = [SelectionPriority(v) for v in args.selection_priorities]

    files_to_move, action_counter, size_counter, resolution_by_action_build, resolution_size_by_action_build, attr_matrix_build, attrs_by_file, errors_by_file = build_move_plan(
        groups=groups,
        target_root=target_root,
        error_target=error_target,
        novideo_target=novideo_target,
        max_errors_when_mc=args.max_errors_when_mc,
        duptype=args.duptype,
        file_to_groupkey=file_to_groupkey,
        log_fn=log_fn,
        max_duration_diff_longer=args.max_duration_diff_longer,
        max_duration_diff_shorter=args.max_duration_diff_shorter,
        selection_priorities=selection_prios,
    )

    resolution_by_action_move, resolution_size_by_action_move, attr_matrix_move = execute_move_plan(
        files_to_move,
        source_root,
        args.mode,
        action_counter,
        log_fn,
        size_counter=size_counter,
        attrs_by_file=attrs_by_file,
        errors_by_file=errors_by_file,
    )

    # Merge diagnostic generation disabled: diag_merge file no longer produced

    # Merge resolution counters from move-phase (duplicates) with build-phase (KEEP entries)
    for action, ctr in resolution_by_action_move.items():
        if action not in resolution_by_action_build:
            resolution_by_action_build[action] = Counter()
        resolution_by_action_build[action].update(ctr)
    for action, sz in resolution_size_by_action_move.items():
        if action not in resolution_size_by_action_build:
            resolution_size_by_action_build[action] = Counter()
        for res_val, v in sz.items():
            resolution_size_by_action_build[action][res_val] += v
    # Merge attribute matrices
    for a, ctr in attr_matrix_move.items():
        if a not in attr_matrix_build:
            attr_matrix_build[a] = Counter()
        attr_matrix_build[a].update(ctr)

    log_handle.close()
    try:
        timing_handle.close()
    except Exception:
        pass
    # Expose the actual log path for reporting so the SUMMARY shows the real file
    args.logname = log_path
    # Diagnostic: verify 720p DUPLICATE counts match between resolution counters and attribute matrix
    try:
        dup_actions = [a for a in resolution_by_action_build.keys() if a.startswith("DUPLICATE")]
        sum_dup_720 = sum(resolution_by_action_build[a].get(720, 0) for a in dup_actions)
        matrix_dup_720 = attr_matrix_build.get("720", Counter()).get("DUPLICATE", 0)
        if sum_dup_720 != matrix_dup_720:
            print(f"DIAGNOSTIC: mismatch DUPLICATE 720: actions_sum={sum_dup_720} matrix={matrix_dup_720}")
            diag_path = get_numbered_log_file(os.path.join(target_root, args.logname + ".diag.txt"))
            # Files that contributed to resolution counts (move.resolution == 720)
            res_files = [fp for fp, mv in files_to_move.items() if mv.action.startswith("DUPLICATE") and getattr(mv, "resolution", None) == 720]
            # Files that have attrs_by_file marking 720 & DUPLICATE
            attrs_files = [fp for fp, attrs in (attrs_by_file or {}).items() if "720" in attrs and "DUPLICATE" in attrs]
            only_in_attrs = sorted(set(attrs_files) - set(res_files))
            only_in_resolution = sorted(set(res_files) - set(attrs_files))
            with open(diag_path, "w", encoding="utf-8") as df:
                df.write(f"Mismatch DUPLICATE 720: actions_sum={sum_dup_720} matrix={matrix_dup_720}\n")
                df.write("\nFiles counted by resolution (move.resolution==720):\n")
                for fp in sorted(res_files):
                    df.write(fp + "\n")
                df.write("\nFiles with attrs_by_file marking 720 & DUPLICATE:\n")
                for fp in sorted(attrs_files):
                    df.write(fp + "\n")
                df.write("\nOnly in attrs_by_file (not in resolution list):\n")
                for fp in only_in_attrs:
                    df.write(fp + "\n")
                df.write("\nOnly in resolution list (not in attrs_by_file):\n")
                for fp in only_in_resolution:
                    df.write(fp + "\n")
            print(f"Wrote diagnostic file: {diag_path}")
    except Exception:
        pass
    sort_and_finalize_log(log_path, action_counter, args, size_counter, resolution_by_action_build, resolution_size_by_action_build, attr_matrix_build)
