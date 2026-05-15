"""Standalone CLI for Search & Move.

Registered as ``avior-searchmove`` entry point.
"""

from __future__ import annotations

import argparse
import os

from avior_dedup.cli import get_numbered_log_file
from avior_dedup.permissions import ensure_output_permissions
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
        "--logname",
        default="searchmove_log.txt",
        help="Log file name to write job log into destination (numbered if exists)",
    )
    parser.add_argument(
        "--recursive", "-r",
        action="store_true",
        help="Search subdirectories recursively",
    )
    parser.add_argument(
        "--preserve-dirs",
        action="store_true",
        help="When used with --recursive, recreate source directory structure under the destination",
    )

    args = parser.parse_args()

    mode = _MODE_MAP[args.mode]
    source = os.path.abspath(args.source_dir)
    dest = os.path.abspath(args.dest_dir)

    # Open a log file in the destination
    os.makedirs(dest, exist_ok=True)
    ensure_output_permissions(dest, is_dir=True)
    log_path = get_numbered_log_file(os.path.join(dest, args.logname))
    # ensure permissions and create
    ensure_output_permissions(log_path, is_dir=False)
    log_handle = open(log_path, "a", encoding="utf-8")

    # Write header with job parameters for debugging/auditability.
    try:
        log_handle.write(f"Timestamp:\t{time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_handle.write(f"Source:\t{source}\n")
        log_handle.write(f"Dest:\t{dest}\n")
        log_handle.write(f"Mode:\t{args.mode}\n")
        log_handle.write(f"Extensions:\t{','.join(args.extensions or [])}\n")
        log_handle.write(f"Recursive:\t{bool(args.recursive)}\n")
        log_handle.write(f"Preserve_Dirs:\t{getattr(args, 'preserve_dirs', False)}\n")
        log_handle.write(f"Search_Expressions:\t{','.join(args.search_strings or [])}\n")
        log_handle.write(f"Output_File:\t{args.output_file}\n")
        log_handle.write("---\n")
    except Exception:
        pass

    def log_fn(msg: str) -> None:
        log_handle.write(msg + "\n")

    last_dir: str | None = None
    last_phase: str | None = None

    def progress_cb(**kw: object) -> None:
        nonlocal last_dir
        nonlocal last_phase
        phase = kw.get("phase", "")
        if phase == "scanning":
            current_dir = kw.get("current_dir", "")
            if current_dir and current_dir != last_dir:
                print(f"Entering directory: {current_dir}")
                last_dir = current_dir
        elif phase == "searching":
            scanned = kw.get("files_scanned", 0)
            total = kw.get("dirs_total", 0)
            if total:
                print(f"\rSearching: {scanned}/{total}", end="", flush=True)
        elif phase == "executing":
            moved = kw.get("files_moved", 0)
            total = kw.get("total_files_to_move", 0)
            if total:
                # When entering the executing phase, ensure the previous
                # searching line is terminated so leftover characters
                # from a longer 'Searching:' line are not left behind.
                if last_phase != "executing":
                    print()
                print(f"\rExecuting: {moved}/{total}", end="", flush=True)

        # Track last seen phase so we can detect phase transitions
        last_phase = phase

    try:
        result = run_search_move_job(
            source=source,
            dest=dest,
            mode=mode,
            extensions=args.extensions or [],
            search_expressions=args.search_strings or [],
            recursive=args.recursive,
            preserve_dirs=getattr(args, "preserve_dirs", False),
            progress_cb=progress_cb,
            log_fn=log_fn,
            output_path=args.output_file,
            log_path=log_path,
        )
        # Append concise statistics to the log for quick inspection.
        try:
            log_handle.write("--- STATS ---\n")
            log_handle.write(f"SCAN_SECONDS:\t{result.scan_seconds:.3f}\n")
            log_handle.write(f"SEARCH_SECONDS:\t{result.search_seconds:.3f}\n")
            log_handle.write(f"EXECUTE_SECONDS:\t{result.execute_seconds:.3f}\n")
            log_handle.write(f"TOTAL_SECONDS:\t{result.total_seconds:.3f}\n")
            log_handle.write(f"Files_Scanned:\t{result.files_scanned}\n")
            log_handle.write(f"Files_Matched:\t{result.files_matched}\n")
            log_handle.write(f"Action_Counts:\t{result.action_counts}\n")
            for k, v in (result.action_counts or {}).items():
                log_handle.write(f"Action_{k}:\t{v}\n")
            log_handle.write("--- END STATS ---\n")
        except Exception:
            pass
    finally:
        log_handle.close()

    print(f"\n\nDone. Files scanned: {result.files_scanned}, "
          f"Matches: {result.files_matched}, "
          f"Actions: {result.action_counts}")

    # Also print the same STATS block to the terminal
    try:
        print("\n--- STATS ---")
        print(f"SCAN_SECONDS:\t{result.scan_seconds:.3f}")
        print(f"SEARCH_SECONDS:\t{result.search_seconds:.3f}")
        print(f"EXECUTE_SECONDS:\t{result.execute_seconds:.3f}")
        print(f"TOTAL_SECONDS:\t{result.total_seconds:.3f}")
        print(f"Files_Scanned:\t{result.files_scanned}")
        print(f"Files_Matched:\t{result.files_matched}")
        print(f"Action_Counts:\t{result.action_counts}")
        for k, v in (result.action_counts or {}).items():
            print(f"Action_{k}:\t{v}")
        print("--- END STATS ---")
    except Exception:
        pass


if __name__ == "__main__":
    main()
