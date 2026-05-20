"""Generate statistics for appended attributes in dedup log lines.

Usage: python scripts/generate_attr_stats.py [path/to/dedup_log.txt]

It computes counts for all combinations of:
 - resolution: 1080, 720, unknown
 - audio: MC, Stereo, unknown
 - length: longer, shorter, unknown
 - errors: integer (kept as exact count)

Output: list of combinations sorted by count, and aggregated matrix for res x audio x length.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from typing import Tuple

LOG_PATH_DEFAULT = "test-data/dedupe/Dup_test/dedup_log_cli.txt"


def normalize_resolution(s: str) -> str:
    s = (s or "").lower()
    if "1080" in s:
        return "1080"
    if "720" in s:
        return "720"
    return "unknown"


def normalize_audio(s: str) -> str:
    s = (s or "").lower()
    if "mc" in s or "5.1" in s or "5/1" in s:
        return "MC"
    if "stereo" in s or "2/0" in s:
        return "Stereo"
    return "unknown"


def normalize_length(s: str) -> str:
    s = (s or "").lower()
    if "longer" in s:
        return "longer"
    if "shorter" in s:
        return "shorter"
    if "ok" in s:
        return "ok"
    # Treat empty/unknown as within bounds (ok)
    return "ok"


def parse_line_fields(line: str) -> Tuple[str, str, str, int]:
    """Return (resolution, audio, length, errors) parsed from a log line."""
    parts = line.rstrip("\n").split("\t")
    # ignore debug lines
    if not parts or parts[0].startswith("[DEBUG]"):
        return None

    # take last 4 columns as resolution, audio, length, errors
    tail = parts[-4:] if len(parts) >= 4 else ([""] * (4 - len(parts))) + parts
    res_raw, audio_raw, length_raw, errors_raw = tail[-4], tail[-3], tail[-2], tail[-1]

    res = normalize_resolution(res_raw)
    audio = normalize_audio(audio_raw)
    length = normalize_length(length_raw)
    try:
        errors = int(errors_raw) if errors_raw.strip() else 0
    except Exception:
        # sometimes there is an ERRORS:N token elsewhere, but last column should be numeric
        # fallback: try to extract digits
        import re

        m = re.search(r"(\d+)", errors_raw or "")
        errors = int(m.group(1)) if m else 0

    return res, audio, length, errors


def main(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [l for l in f.readlines() if l.strip()]
    except FileNotFoundError:
        print(f"Log file not found: {path}")
        sys.exit(2)

    # errors will be bucketed as 0 or '>0'
    combo_counter: Counter[Tuple[str, str, str, str]] = Counter()
    combo_errors_sum: defaultdict[Tuple[str, str, str], int] = defaultdict(int)
    combo_files_sum: Counter[Tuple[str, str, str]] = Counter()

    for l in lines:
        if l.startswith("[DEBUG]"):
            continue
        parsed = parse_line_fields(l)
        if parsed is None:
            continue
        res, audio, length, errors = parsed
        err_bucket = "0" if errors == 0 else ">0"
        combo_counter[(res, audio, length, err_bucket)] += 1
        combo_errors_sum[(res, audio, length)] += errors
        combo_files_sum[(res, audio, length)] += 1

    # print top combinations including errors
    print("Combinations (resolution, audio, length, errors>0 flag) - count")
    for combo, cnt in combo_counter.most_common():
        print(f"{combo}: {cnt}")

    print("\nAggregated by (resolution, audio, length): files / total_errors / avg_errors")
    rows = sorted(combo_files_sum.keys(), key=lambda x: (-combo_files_sum[x], x))
    for key in rows:
        files = combo_files_sum[key]
        errs = combo_errors_sum[key]
        avg = errs / files if files else 0
        print(f"{key}: {files} files, {errs} errors, avg {avg:.2f}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else LOG_PATH_DEFAULT
    main(path)
