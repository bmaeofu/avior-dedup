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
    selected_combos: Optional[list[tuple]] = None,
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
        f"  Log file:               {getattr(args, 'logname', 'unknown')}",
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

    # Optional: include per-action resolution breakdown (counts only real video files)
    if resolution_by_action:
        summary_lines.append("\nRESOLUTION BY ACTION (video files only):")
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

    # Optional: print attribute cross-tab matrix (counts only real video files)
    if attr_matrix:
        summary_lines.append("\nATTRIBUTE MATRIX (video files only):")
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

    # Optional: include a compact list of selected attribute combinations (top combos)
    if selected_combos:
        summary_lines.append("")
        summary_lines.append("SELECTED ATTRIBUTE COMBINATIONS SUMMARY (video files only):")
        for combo, total, keep_cnt, dup_cnt in selected_combos:
            res, audio, length, err_bucket = combo
            summary_lines.append(f"('{res}', '{audio}', '{length}', '{err_bucket}'): total={total}  KEEP={keep_cnt}  DUPLICATE={dup_cnt}")

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
        # Compute selected attribute combinations from sorted_lines
        from collections import Counter, defaultdict

        def _normalize_resolution(s: str) -> str:
            s = (s or "").lower()
            if "1080" in s:
                return "1080"
            if "720" in s:
                return "720"
            return "unknown"

        def _normalize_audio(s: str) -> str:
            s = (s or "").lower()
            if "mc" in s or "5.1" in s or "5/1" in s:
                return "MC"
            if "stereo" in s or "2/0" in s:
                return "Stereo"
            return "unknown"

        def _normalize_length(s: str) -> str:
            s = (s or "").lower()
            if "longer" in s:
                return "longer"
            if "shorter" in s:
                return "shorter"
            if "ok" in s:
                return "ok"
            return "ok"

        combo_counter: Counter[tuple] = Counter()
        combo_keep: defaultdict = defaultdict(int)
        combo_dup: defaultdict = defaultdict(int)

        for line in sorted_lines:
            if not line.strip() or line.startswith("[DEBUG]"):
                continue
            parts = line.split("\t")
            # expect last 4 columns: resolution, audio, length, errors
            if len(parts) < 4:
                continue
            # Only count statistics for real video source files (.mkv)
            src_path = parts[2] if len(parts) > 2 else ""
            if not src_path.lower().endswith(".mkv"):
                continue
            res_raw = parts[-4]
            audio_raw = parts[-3]
            length_raw = parts[-2]
            errors_raw = parts[-1]

            res = _normalize_resolution(res_raw)
            audio = _normalize_audio(audio_raw)
            length = _normalize_length(length_raw)
            try:
                errors = int(errors_raw) if errors_raw.strip() else 0
            except Exception:
                errors = 0
            err_bucket = "0" if errors == 0 else ">0"

            combo = (res, audio, length, err_bucket)
            combo_counter[combo] += 1

            # determine keep vs duplicate by looking at action token (second column)
            action_token = parts[1] if len(parts) > 1 else ""
            if "KEEP" in action_token:
                combo_keep[combo] += 1
            elif "DUPLICATE" in action_token:
                combo_dup[combo] += 1

        # select top 7 combos by total count
        top = combo_counter.most_common(7)
        selected_combos = []
        for combo, total in top:
            selected_combos.append((combo, total, combo_keep.get(combo, 0), combo_dup.get(combo, 0)))

        # Keep ACTION STATISTICS as provided (file-based). Build filtered structures
        # for RESOLUTION BY ACTION, ATTRIBUTE MATRIX and SELECTED COMBOS that count only .mkv files.
        video_resolution_by_action: dict[str, Counter] = {}
        video_resolution_size_by_action: dict[str, Counter] = {}
        video_attr_matrix: dict[str, Counter] = {}

        def _res_key_numeric(s: str) -> int:
            s = (s or "").lower()
            if "1080" in s:
                return 1080
            if "720" in s:
                return 720
            return 0

        from collections import defaultdict

        # Track observed resolutions per action to filter size map later
        observed_res_for_action: dict[str, set] = defaultdict(set)

        for line in sorted_lines:
            if not line.strip() or line.startswith("[DEBUG]"):
                continue
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            src_path = parts[2] if len(parts) > 2 else ""
            if not src_path.lower().endswith(".mkv"):
                continue
            action_token = parts[1] if len(parts) > 1 else ""
            res_raw = parts[-4]
            audio_raw = parts[-3]
            length_raw = parts[-2]
            errors_raw = parts[-1]

            res_num = _res_key_numeric(res_raw)
            # update resolution by action
            video_resolution_by_action.setdefault(action_token, Counter())[res_num] += 1
            observed_res_for_action[action_token].add(res_num)

            # build attribute list for this file and update attribute cross-tab
            attrs = []
            # audio
            a = (audio_raw or "").lower()
            if "mc" in a or "5.1" in a or "5/1" in a:
                attrs.append("MC")
            elif "stereo" in a or "2/0" in a:
                attrs.append("Stereo")
            else:
                attrs.append("unknown")
            # errors / ok
            try:
                errors = int(errors_raw) if errors_raw.strip() else 0
            except Exception:
                errors = 0
            if errors > 0:
                attrs.append("ERRORS")
            else:
                attrs.append("OK")
            # length
            l = (length_raw or "").lower()
            if "longer" in l:
                attrs.append("LONGER")
            elif "shorter" in l:
                attrs.append("SHORTER")
            else:
                attrs.append("OK")
            # resolution flag
            if res_num == 1080:
                attrs.append("1080")
            elif res_num == 720:
                attrs.append("720")
            else:
                attrs.append("unknown")
            # action flag
            if "KEEP" in action_token:
                attrs.append("KEEP")
            elif "DUPLICATE" in action_token:
                attrs.append("DUPLICATE")

            # update matrix: for each pair of attrs increment row->col
            for row in attrs:
                video_attr_matrix.setdefault(row, Counter())
                for col in attrs:
                    video_attr_matrix[row][col] += 1

        # Filter resolution_size_counter to only include observed resolutions for each action
        if resolution_size_counter:
            for action, res_map in resolution_size_counter.items():
                obs = observed_res_for_action.get(action, set())
                if not obs:
                    continue
                # keep only resolutions we saw in .mkv lines
                filtered = {res: size for res, size in res_map.items() if res in obs}
                if filtered:
                    video_resolution_size_by_action[action] = Counter(filtered)

        # Write summary: pass original action_counter (file-based), but filtered resolution and attr matrices
        write_summary(f, action_counter, args, size_counter, video_resolution_by_action or None, video_resolution_size_by_action or None, video_attr_matrix or None, selected_combos)

        # --- Generate Keep.txt: list all KEEP .mkv video files with full path, reason and attributes
        keep_entries = []
        for idx, line in enumerate(sorted_lines, start=1):
            if not line.strip() or line.startswith("[DEBUG]"):
                continue
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            action_token = parts[1] if len(parts) > 1 else ""
            src_path = parts[2] if len(parts) > 2 else ""
            if "KEEP" not in action_token:
                continue
            if not src_path.lower().endswith(".mkv"):
                continue
            # For KEEP lines the expected columns are:
            # group_name, [ACTION], src_path, reason, resolution, audio, length, errors
            # last 4 columns are resolution, audio, length, errors — reason is at index 3
            reason = parts[3] if len(parts) > 3 else ""
            res = parts[-4] if len(parts) >= 4 else "unknown"
            audio = parts[-3] if len(parts) >= 3 else "unknown"
            length_flag = parts[-2] if len(parts) >= 2 else "ok"
            errors_raw = parts[-1] if parts else "0"
            try:
                errors = int(errors_raw) if errors_raw.strip() else 0
            except Exception:
                errors = 0
            keep_entries.append((idx, src_path, reason, res, audio, length_flag, errors))

        # sort by audio format (lexicographically) then by error count (ascending)
        # tuple format: (idx, path, reason, res, audio, length_flag, errors)
        keep_entries.sort(key=lambda e: (str(e[4]).lower(), e[6]))

        # write Keep file next to log_path using the same numbering as the dedup log
        try:
            import re

            log_base = os.path.basename(log_path)
            base_no_ext, _ext = os.path.splitext(log_base)
            m = re.match(r"(?i)dedup_log_(.+)$", base_no_ext)
            if m:
                suffix = m.group(1)
                keep_name = f"keep_{suffix}.txt"
            else:
                # If the basename ends with an underscore+number (e.g.
                # duplicate_case_files_found_002), extract that numeric
                # suffix so the keep file becomes `keep_002` as expected.
                m2 = re.search(r"_(\d+)$", base_no_ext)
                if m2:
                    suffix = m2.group(1)
                    keep_name = f"keep_{suffix}.txt"
                else:
                    # Fall back to keeping a related name without extension
                    keep_name = f"keep_{base_no_ext}.txt"

            keep_path = os.path.join(os.path.dirname(log_path), keep_name)
            with open(keep_path, "w", encoding="utf-8") as kf:
                kf.write("# Keep report generated by avior-dedup\n")
                kf.write("# format: index\tfull_path\treason\tresolution\taudio\tlength\terrors\n")
                for idx, path, reason, res, audio, length_flag, errors in keep_entries:
                    kf.write(f"{idx}\t{path}\t{reason}\t{res}\t{audio}\t{length_flag}\t{errors}\n")
        except Exception:
            # never fail the finalizer if keep file cannot be written
            pass
