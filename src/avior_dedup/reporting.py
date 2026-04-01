from __future__ import annotations

import argparse
import os
from collections import Counter
from datetime import datetime
from typing import IO, Optional


def write_summary(
    log_handle: Optional[IO[str]],
    action_counter: Counter,
    args: argparse.Namespace,
) -> None:
    """Write execution summary to log file and stdout."""
    summary_lines = [
        "",
        "=" * 80,
        "SUMMARY",
        "=" * 80,
        "",
        "PARAMETERS:",
        f"  Mode:                   {args.mode} ({'MOVE' if args.mode == 'm' else 'FIND ONLY'})",
        f"  Source:                 {args.source}",
        f"  Target:                {args.target}",
        f"  Error target:          {args.error_target or 'default'}",
        f"  No-video target:       {args.novideo_target or 'default'}",
        f"  Duplicate type:        {args.duptype}",
        f"  Prefer errors:         {'yes' if args.prefer_errors else 'no'}",
        f"  Max errors (MC):       {args.max_errors_when_mc}",
        f"  Semantic prefixes:     {', '.join(args.semantic_prefixes)}",
        f"  Remove episode nos:    {'yes' if args.remove_episode_nos else 'no'}",
    ]

    summary_lines.append("\nACTION STATISTICS:")
    if action_counter:
        total_files = sum(action_counter.values())
        for action, count in sorted(action_counter.items()):
            pct = (count / total_files * 100) if total_files > 0 else 0
            summary_lines.append(f"  {action:.<40} {count:>6} files ({pct:>5.1f}%)")
        summary_lines.append(f"  {'-' * 58}")
        summary_lines.append(f"  {'TOTAL':.<40} {total_files:>6} files")
    else:
        summary_lines.append("  No actions performed")

    summary_lines.append(f"\nExecution date: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    summary_lines.append("=" * 80)

    for line in summary_lines:
        print(line)
        if log_handle:
            log_handle.write(line + "\n")


def sort_and_finalize_log(log_path: str, action_counter: Counter, args: argparse.Namespace) -> None:
    """Sort the log file by group name and action, then append summary."""
    if not log_path or not os.path.exists(log_path):
        return

    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    sorted_lines = sorted(
        set(line.rstrip("\n") for line in lines if line.strip()),
        key=lambda line: (
            line.split("\t")[0] if line.split("\t") else "",
            line.split("\t")[1] if len(line.split("\t")) > 1 else "",
        ),
    )

    with open(log_path, "w", encoding="utf-8") as f:
        for line in sorted_lines:
            f.write(line + "\n")
        write_summary(f, action_counter, args)
