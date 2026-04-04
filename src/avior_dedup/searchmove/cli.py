"""Standalone CLI for Search & Move.

Registered as ``avior-searchmove`` entry point.
"""

from __future__ import annotations

import argparse
import os

from avior_dedup.searchmove.models import ActivityMode
from avior_dedup.searchmove.runner import run_search_move_job


_MODE_MAP: dict[str, ActivityMode] = {
    "copy": ActivityMode.COPY,
    "move": ActivityMode.MOVE,
    "delete": ActivityMode.DELETE,
    "test": ActivityMode.TEST,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Search files by content and move/copy/delete matching file sets.\n"
            "\n"
            "Search expressions support boolean logic:\n"
            "  &  = AND  (all terms must match)\n"
            "  |  = OR   (any group may match)\n"
            "\n"
            "Examples:\n"
            '  "action&thriller"\n'
            '  "action&thriller|comedy"\n'
            '  "rating:>7&year:2020|rating:>8"\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "mode",
        choices=list(_MODE_MAP.keys()),
        help="Action mode: copy, move, delete, or test (dry run)",
    )
    parser.add_argument(
        "source_dir",
        help="Path to the directory or single file to search",
    )
    parser.add_argument(
        "dest_dir",
        help="Destination directory for moved/copied files",
    )
    parser.add_argument(
        "--extensions", "-e",
        nargs="+",
        help="File extensions to search for (e.g. .txt .nfo .log)",
    )
    parser.add_argument(
        "--search_strings", "-s",
        nargs="+",
        help=(
            "Search expressions with boolean logic.\n"
            "  &  AND  |  OR\n"
            '  Text: "action&thriller|comedy"\n'
            '  XML:  "genre:Action&rating:>7"\n'
            '  Wildcards: genre:*Action*\n'
            '  Existence: nfostatus:exists / nfostatus:!exists\n'
            '  Ranges: rating:>4<6, rating:4-6\n'
        ),
    )
    parser.add_argument(
        "--output_file", "-o",
        default="result.txt",
        help="File to write match results to (default: result.txt)",
    )
    parser.add_argument(
        "--recursive", "-r",
        action="store_true",
        help="Search subdirectories recursively",
    )

    args = parser.parse_args()

    mode = _MODE_MAP[args.mode]
    source = os.path.abspath(args.source_dir)
    dest = os.path.abspath(args.dest_dir)

    # Open a log file in the destination
    os.makedirs(dest, exist_ok=True)
    log_path = os.path.join(dest, "log.txt")
    log_handle = open(log_path, "a", encoding="utf-8")

    def log_fn(msg: str) -> None:
        log_handle.write(msg + "\n")

    def progress_cb(**kw: object) -> None:
        phase = kw.get("phase", "")
        if phase == "scanning":
            current_dir = kw.get("current_dir", "")
            if current_dir:
                print(f"Entering directory: {current_dir}")
        elif phase == "searching":
            scanned = kw.get("files_scanned", 0)
            total = kw.get("dirs_total", 0)
            if total:
                print(f"\rSearching: {scanned}/{total}", end="", flush=True)
        elif phase == "executing":
            moved = kw.get("files_moved", 0)
            total = kw.get("total_files_to_move", 0)
            if total:
                print(f"\rExecuting: {moved}/{total}", end="", flush=True)

    try:
        result = run_search_move_job(
            source=source,
            dest=dest,
            mode=mode,
            extensions=args.extensions or [],
            search_expressions=args.search_strings or [],
            recursive=args.recursive,
            progress_cb=progress_cb,
            log_fn=log_fn,
            output_path=args.output_file,
        )
    finally:
        log_handle.close()

    print(f"\n\nDone. Files scanned: {result.files_scanned}, "
          f"Matches: {result.files_matched}, "
          f"Actions: {result.action_counts}")


if __name__ == "__main__":
    main()
