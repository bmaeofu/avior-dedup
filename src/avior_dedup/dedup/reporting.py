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
    resolution_by_action: Optional[dict[str, Counter]] = None,
    resolution_size_by_action: Optional[dict[str, Counter]] = None,
    attr_matrix: Optional[dict[str, Counter]] = None,
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
        f"  Remove spaces:         {'yes' if getattr(args, 'remove_spaces', False) else 'no'}",
        f"  Remove non-episode parentheses: {'yes' if getattr(args, 'remove_non_episode_parens', False) else 'no'}",
        f"  Ignored directories:   {', '.join(getattr(args, 'ignored_directories')) if getattr(args, 'ignored_directories', None) else 'none'}",
    ]

    summary_lines.append("\nACTION STATISTICS:")
    if action_counter:
        total_files = sum(action_counter.values())
        total_size = sum(size_counter.values()) if size_counter else 0
        has_sizes = size_counter and total_size > 0
        # Preferred display order for action statistics
        preferred_order = [
            "DUPLICATE",
            "DUPLICATE_WITH_ERRORS",
            "DUPLICATE_WITH_ERRORS_MC",
            "DUPLICATE_WITH_LONGER_DURATION",
            "DUPLICATE_WITH_SHORTER_DURATION",
            "KEEP",
            "KEEP_MC",
            "KEEP_WITH_SHORTER_DURATION",
            "KEEP_MC_WITH_ERRORS",
            "KEEP_MC_WITH_SHORTER_DURATION",
            "NO_VIDEO",
        ]

        # Print preferred items first in that order, then any remaining actions sorted
        printed = set()
        for action in preferred_order:
            if action in action_counter:
                count = action_counter[action]
                pct = (count / total_files * 100) if total_files > 0 else 0
                size_str = f"  [{_format_size(size_counter[action]):>10}]" if has_sizes else ""
                summary_lines.append(f"  {action:.<40} {count:>6} files ({pct:>5.1f}%){size_str}")
                printed.add(action)

        for action, count in sorted(action_counter.items()):
            if action in printed:
                continue
            pct = (count / total_files * 100) if total_files > 0 else 0
            size_str = f"  [{_format_size(size_counter[action]):>10}]" if has_sizes else ""
            summary_lines.append(f"  {action:.<40} {count:>6} files ({pct:>5.1f}%){size_str}")
        summary_lines.append(f"  {'-' * (70 if has_sizes else 58)}")
        total_size_str = f"  [{_format_size(total_size):>10}]" if has_sizes else ""
        summary_lines.append(f"  {'TOTAL':.<40} {total_files:>6} files{total_size_str}")
    else:
        summary_lines.append("  No actions performed")

    # Optional: include per-action resolution breakdown
    if resolution_by_action:
        summary_lines.append("\nRESOLUTION BY ACTION:")
        # iterate actions in the same displayed order where possible
        actions_order = [
            "DUPLICATE",
            "DUPLICATE_WITH_ERRORS",
            "DUPLICATE_WITH_ERRORS_MC",
            "DUPLICATE_WITH_LONGER_DURATION",
            "DUPLICATE_WITH_SHORTER_DURATION",
            "KEEP",
            "KEEP_MC",
            "KEEP_WITH_SHORTER_DURATION",
            "KEEP_MC_WITH_ERRORS",
            "KEEP_MC_WITH_SHORTER_DURATION",
            "NO_VIDEO",
        ]
        # ensure we include any other actions too
        remaining_actions = [a for a in sorted(resolution_by_action.keys()) if a not in actions_order]
        full_actions = [a for a in actions_order if a in resolution_by_action] + remaining_actions

        for action in full_actions:
            res_counter = resolution_by_action.get(action, {})
            if not res_counter:
                continue
            total_res_files = sum(res_counter.values())
            size_counter_for_action = resolution_size_by_action.get(action) if resolution_size_by_action else None
            has_res_sizes = size_counter_for_action and sum(size_counter_for_action.values()) > 0
            summary_lines.append(f"  {action}:")
            # sort resolutions numeric descending, put 0 (unknown) last
            res_keys = sorted([k for k in res_counter.keys() if k != 0], reverse=True) + ([0] if 0 in res_counter else [])
            for res in res_keys:
                cnt = res_counter[res]
                pct = (cnt / total_res_files * 100) if total_res_files > 0 else 0
                size_str = (
                    f"  [{_format_size(size_counter_for_action[res]):>10}]" if has_res_sizes and size_counter_for_action and res in size_counter_for_action else ""
                )
                label = f"{res}p" if res and res != 0 else "unknown"
                summary_lines.append(f"    {label:<8} {cnt:>6} files ({pct:>5.1f}%){size_str}")

    # Optional: print attribute cross-tab matrix (e.g., MC/ERRORS/LONGER/SHORTER/1080/720)
    if attr_matrix:
        summary_lines.append("\nATTRIBUTE MATRIX:")
        # preferred attribute order
        preferred = ["MC", "ERRORS", "LONGER", "SHORTER", "1080", "720"]
        others = [a for a in sorted(attr_matrix.keys()) if a not in preferred]
        attrs = [a for a in preferred if a in attr_matrix] + others
        if attrs:
            # compute dynamic column widths so headers and numbers align
            # row label width should fit the longest attribute name
            row_label_width = max(7, max(len(r) for r in attrs) + 1)
            # compute per-column width based on header and largest value in that column
            col_widths: list[int] = []
            for col in attrs:
                max_val_len = max(len(str(attr_matrix.get(row, {}).get(col, 0))) for row in attrs)
                col_w = max(len(col), max_val_len) + 2
                col_widths.append(col_w)
            # header
            header = " " * row_label_width + "".join(f"{a:>{w}}" for a, w in zip(attrs, col_widths))
            summary_lines.append(header)
            for row in attrs:
                row_vals = [str(attr_matrix.get(row, {}).get(col, 0)) for col in attrs]
                line = f"{row:<{row_label_width}}" + "".join(f"{v:>{w}}" for v, w in zip(row_vals, col_widths))
                summary_lines.append(line)

    # Allow caller to provide an explicit execution date (e.g. job end time).
    exec_date = getattr(args, "execution_date", None)
    start_time = getattr(args, "start_time", None)
    if not exec_date:
        exec_date = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

    # If we have both start and end, compute duration
    duration_str = None
    if start_time:
        try:
            fmt = "%d.%m.%Y %H:%M:%S"
            sd = datetime.strptime(start_time, fmt)
            ed = datetime.strptime(exec_date, fmt)
            delta = ed - sd
            total = int(delta.total_seconds())
            hrs = total // 3600
            mins = (total % 3600) // 60
            secs = total % 60
            duration_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"
        except Exception:
            duration_str = None

    summary_lines.append("")
    summary_lines.append(f"  Start time: {start_time or 'unknown'}")
    summary_lines.append(f"  End time:   {exec_date}")
    if duration_str:
        summary_lines.append(f"  Duration:   {duration_str}")
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
    resolution_counter: Counter | None = None,
    resolution_size_counter: Counter | None = None,
    attr_matrix: dict[str, Counter] | None = None,
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
        write_summary(f, action_counter, args, size_counter, resolution_counter, resolution_size_counter, attr_matrix)
