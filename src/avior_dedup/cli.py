from __future__ import annotations

import argparse
import os
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

    parser = argparse.ArgumentParser(description="Duplicate film files finder/mover")
    parser.add_argument("mode", choices=["m", "f"], help="m = move, f = find only")
    parser.add_argument("source", help="source directory")
    parser.add_argument("target", help="target directory")
    parser.add_argument("logname", help="log file name")
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
        default=[r"terra\s*x\s*-\s*"],
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
        "--normalize-episode-nos",
        action="store_true",
        help="Normalize episode tokens like (1_5) or (S01_E05) to standard form (s01e05) instead of removing them",
    )

    args = parser.parse_args()

    source_root = os.path.abspath(args.source)
    target_root = os.path.abspath(args.target)
    error_target = os.path.abspath(args.error_target) if args.error_target else os.path.join(target_root, "errors")
    novideo_target = os.path.abspath(args.novideo_target) if args.novideo_target else os.path.join(target_root, "no_video")

    os.makedirs(target_root, exist_ok=True)
    os.makedirs(error_target, exist_ok=True)
    os.makedirs(novideo_target, exist_ok=True)
    ensure_output_permissions(target_root, is_dir=True)
    ensure_output_permissions(error_target, is_dir=True)
    ensure_output_permissions(novideo_target, is_dir=True)

    log_path = get_numbered_log_file(os.path.join(target_root, args.logname))
    log_handle = open(log_path, "w", encoding="utf-8")
    ensure_output_permissions(log_path, is_dir=False)

    def log_fn(msg: str) -> None:
        print(msg)
        log_handle.write(msg + "\n")

    groups, file_to_groupkey = find_duplicates(
        source_root,
        args.duptype,
        args.remove_episode_nos,
        args.semantic_prefixes,
        args.remove_spaces,
        args.remove_non_episode_parens,
    )

    print(f"\nDuplicate groups found: {len(groups)}")
    print(f"Duplicate type: {args.duptype}")
    print(f"Mode: {'MOVE' if args.mode == 'm' else 'FIND ONLY'}\n")

    selection_prios = [SelectionPriority(v) for v in args.selection_priorities]

    files_to_move, action_counter, size_counter, resolution_by_action_build, resolution_size_by_action_build, attr_matrix_build, attrs_by_file = build_move_plan(
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
    )

    # Write merge diagnostic: capture pre-merge counts for quick inspection
    try:
        merge_diag_path = get_numbered_log_file(os.path.join(target_root, args.logname + ".diag_merge.txt"))
        with open(merge_diag_path, "w", encoding="utf-8") as md:
            md.write("Pre-merge resolution_by_action_build DUPLICATE 720:\n")
            dup_actions_build = [a for a in resolution_by_action_build.keys() if a.startswith("DUPLICATE")]
            md.write(str({a: resolution_by_action_build[a].get(720, 0) for a in dup_actions_build}) + "\n")
            md.write("Pre-merge attr_matrix_build 720->DUPLICATE:\n")
            md.write(str(attr_matrix_build.get("720", Counter()).get("DUPLICATE", 0)) + "\n")
            md.write("Move-phase resolution_by_action_move DUPLICATE 720:\n")
            dup_actions_move = [a for a in resolution_by_action_move.keys() if a.startswith("DUPLICATE")]
            md.write(str({a: resolution_by_action_move[a].get(720, 0) for a in dup_actions_move}) + "\n")
            md.write("Move-phase attr_matrix_move 720->DUPLICATE:\n")
            md.write(str(attr_matrix_move.get("720", Counter()).get("DUPLICATE", 0)) + "\n")
        print(f"Wrote merge diagnostic: {merge_diag_path}")
    except Exception:
        pass

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
