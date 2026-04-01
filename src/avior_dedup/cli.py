from __future__ import annotations

import argparse
import os

from avior_dedup.planner import build_move_plan, execute_move_plan
from avior_dedup.reporting import sort_and_finalize_log
from avior_dedup.scanner import find_duplicates


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
    parser.add_argument("--prefer-errors", action="store_true", help="Keep film with fewer errors according to .log")
    parser.add_argument("--error-target", help="Directory where worse recordings are moved")
    parser.add_argument("--novideo-target", help="Directory where metadata with no video are moved")
    parser.add_argument("--max-errors-when-mc", type=int, default=0, help="Max allowed errors for multichannel to be considered good")
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

    args = parser.parse_args()

    source_root = os.path.abspath(args.source)
    target_root = os.path.abspath(args.target)
    error_target = os.path.abspath(args.error_target) if args.error_target else os.path.join(target_root, "errors")
    novideo_target = os.path.abspath(args.novideo_target) if args.novideo_target else os.path.join(target_root, "no_video")

    os.makedirs(target_root, exist_ok=True)
    os.makedirs(error_target, exist_ok=True)
    os.makedirs(novideo_target, exist_ok=True)

    log_path = get_numbered_log_file(os.path.join(target_root, args.logname))
    log_handle = open(log_path, "w", encoding="utf-8")

    def log_fn(msg: str) -> None:
        print(msg)
        log_handle.write(msg + "\n")

    groups, file_to_groupkey = find_duplicates(source_root, args.duptype, args.remove_episode_nos, args.semantic_prefixes)

    print(f"\nDuplicate groups found: {len(groups)}")
    print(f"Duplicate type: {args.duptype}")
    print(f"Prefer errors: {args.prefer_errors}")
    print(f"Mode: {'MOVE' if args.mode == 'm' else 'FIND ONLY'}\n")

    files_to_move, action_counter = build_move_plan(
        groups=groups,
        target_root=target_root,
        error_target=error_target,
        novideo_target=novideo_target,
        prefer_errors=args.prefer_errors,
        max_errors_when_mc=args.max_errors_when_mc,
        duptype=args.duptype,
        file_to_groupkey=file_to_groupkey,
        log_fn=log_fn,
    )

    execute_move_plan(files_to_move, source_root, args.mode, action_counter, log_fn)

    log_handle.close()
    sort_and_finalize_log(log_path, action_counter, args)
