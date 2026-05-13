from __future__ import annotations

import argparse
import os
from collections import Counter
from datetime import datetime
from typing import IO, Optional

from avior_dedup.dedup.io_utils import read_text


def _format_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / 1024 ** 2:.1f} MB"
    else:
        return f"{size_bytes / 1024 ** 3:.2f} GB"


def write_summary(
    log_handle: Optional[IO[str]],
    action_counter: Counter,
    args: argparse.Namespace,
    size_counter: Optional[Counter] = None,
    decision_counter: Optional[Counter] = None,
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
        f"  Max errors (MC):       {args.max_errors_when_mc}",
        f"  Max duration +diff:    {args.max_duration_diff_longer}",
        f"  Max duration -diff:    {args.max_duration_diff_shorter}",
        f"  Selection priorities:  {', '.join(p.value if hasattr(p, 'value') else str(p) for p in args.selection_priorities)}",
        f"  Semantic prefixes:     {', '.join(args.semantic_prefixes)}",
        f"  Remove episode nos:    {'yes' if args.remove_episode_nos else 'no'}",
        f"  Ignored directories:   {', '.join(getattr(args, 'ignored_directories')) if getattr(args, 'ignored_directories', None) else 'none'}",
    ]

    summary_lines.append("\nACTION STATISTICS:")
    if action_counter:
        total_files = sum(action_counter.values())
        total_size = sum(size_counter.values()) if size_counter else 0
        has_sizes = size_counter and total_size > 0
        for action, count in sorted(action_counter.items()):
            pct = (count / total_files * 100) if total_files > 0 else 0
            size_str = f"  [{_format_size(size_counter[action]):>10}]" if has_sizes else ""
            summary_lines.append(f"  {action:.<40} {count:>6} files ({pct:>5.1f}%){size_str}")
        summary_lines.append(f"  {'-' * (70 if has_sizes else 58)}")
        total_size_str = f"  [{_format_size(total_size):>10}]" if has_sizes else ""
        summary_lines.append(f"  {'TOTAL':.<40} {total_files:>6} files{total_size_str}")
    else:
        summary_lines.append("  No actions performed")

    # Optional: include decision statistics (what priority decided between top two candidates)
    if decision_counter:
        summary_lines.append("\nDECISION STATISTICS:")
        for key, cnt in sorted(decision_counter.items()):
            summary_lines.append(f"  {key.replace('_', ' ').upper():.<40} {cnt:>6} groups")

    summary_lines.append(f"\nExecution date: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    summary_lines.append("=" * 80)

    for line in summary_lines:
        print(line)
        if log_handle:
            log_handle.write(line + "\n")


def sort_and_finalize_log(
    log_path: str,
    action_counter: Counter,
    args: argparse.Namespace,
    size_counter: Counter | None = None,
    decision_counter: Counter | None = None,
) -> None:
    """Sort the log file by group name and action, then append summary."""
    if not log_path or not os.path.exists(log_path):
        return

    content = read_text(log_path)
    if content is None:
        return
    lines = content.splitlines()

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
        write_summary(f, action_counter, args, size_counter, decision_counter)
