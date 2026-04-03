from __future__ import annotations

import os
import re
import subprocess
from typing import Callable, Optional, Tuple

from avior_dedup import config
from avior_dedup.dedup.io_utils import read_text
from avior_dedup.dedup.models import FileRecord, GroupKeys
from avior_dedup.dedup.normalize import normalize_film_name
from avior_dedup.dedup.suffix import match_suffix

def _hms_to_seconds(hms: str) -> int:
    h, m, s = map(int, hms.split(":"))
    return h * 3600 + m * 60 + s


def _hm_to_seconds(hm: str) -> int:
    h, m = map(int, hm.split(":"))
    return h * 3600 + m * 60


def _format_seconds_hhmmss(seconds: float) -> str:
    total = int(round(seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def count_errors(lines: list[str]) -> int:
    """Count encoding errors from log lines containing 'MB) Errors:'."""
    error_count = 0
    for line in lines:
        if "MB) Errors:" in line:
            try:
                parts = line.split("MB) Errors:")
                if len(parts) > 1:
                    error_count += int(parts[1].strip().split()[0])
            except ValueError:
                continue
    return error_count


def is_multichannel_from_log(lines: list[str], max_seconds: int = 20) -> bool:
    """Check if AC3 5.x multichannel audio appears within the first max_seconds of the recording log."""
    time_re = re.compile(r"/\s*(\d+):(\d+):(\d+)")
    recording_started = False

    for line in lines:
        if not recording_started:
            if line.strip().endswith("Start") or "Start Recording" in line:
                recording_started = True
            continue

        m = time_re.search(line)
        if not m:
            continue

        h, mi, s = map(int, m.groups())
        seconds = h * 3600 + mi * 60 + s
        if seconds > max_seconds:
            break

        if "AC3 Audio 5." in line:
            return True

    return False

# -----------------------------
# ffprobe
# -----------------------------

def get_media_duration_ffprobe(path: str) -> Optional[float]:
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        duration_str = (result.stdout or "").strip()

        if not duration_str:
            return None

        return float(duration_str)

    except Exception:
        return None

# -----------------------------
# Log Parsing
# -----------------------------
def _truncate_log(content: str) -> str:
    """Entfernt alles ab 'Removed Filler Data' (Format 2) bzw. 'Total Size' (Format 1)."""
    for marker in ("Removed Filler Data", "Total Size"):
        idx = content.find(marker)
        if idx != -1:
            return content[:idx]
    return content


def get_real_rec_time_from_log(path: str) -> Optional[int]:
    base = os.path.splitext(path)[0]
    candidates = [base + ".log", base + ".mkv.log"]

    content = None
    for c in candidates:
        content = read_text(c)
        if content:
            break

    if not content:
        return None

    content = _truncate_log(content)


    # 1. Format 2 Stop-Zeile  z. B. "23:34:11 / 01:33:27 (~ ...) Stop"
    #    Zweite Gruppe ist die laufende Aufnahmedauer → direkt verwenden
    stop_match = re.findall(
        r'\d{1,2}:\d{2}:\d{2}\s*/\s*(\d{1,2}:\d{2}:\d{2})\s*\(~[^)]*\)\s*Stop',
        content,
        re.IGNORECASE
    )
    if stop_match:
        return _hms_to_seconds(stop_match[-1])

    # 2. Format 1 Start/Stop-Zeilen  z. B. "01:30:02 Start" / "03:29:59 Stop"
    start = re.search(r'^(\d{1,2}:\d{2}:\d{2})\s+Start\s*$', content, re.MULTILINE)
    stops = re.findall(r'^(\d{1,2}:\d{2}:\d{2})\s+Stop\s*$', content, re.MULTILINE)

    if start and stops:
        start_s = _hms_to_seconds(start.group(1))
        stop_s = _hms_to_seconds(stops[-1])
        if stop_s < start_s:
            stop_s += 86400
        return stop_s - start_s

    return None

def get_epg_duration(path: str) -> Optional[int]:
    base = os.path.splitext(path)[0]

    txt_file = base + ".txt"
    if os.path.exists(txt_file):
        txt = read_text(txt_file)
        if txt:
            m = re.search(r'Duration\s*=\s*(\d{1,2}:\d{2}:\d{2})', txt)
            if m:
                return _hms_to_seconds(m.group(1))

    candidates = [base + ".log", base + ".mkv.log"]

    content = None
    for c in candidates:
        content = read_text(c)
        if content:
            break

    if not content:
        return None

    content = _truncate_log(content)

    r"""
    Beispiel Format 1:
    Das Erste HD (AC3,deu) 04.01.2019
    I:\Recording\Afrika ruft nach dir_2019-01-04-03-38-00-Das Erste HD (AC3,deu).ts
    Device: Digital Devices DVB-S/S2 Tuner 2 (2)
    EventID: 45364, PDC: 0x208E8
    Timer Name: Afrika ruft nach Dir - Spielfilm Deutschland/Österreich 2012
    Timer Start: 04.01.2019 03:38:00
    Timer Duration: 01:35:00 (95 min. incl. 2 min. lead time, 0 min. follow-up time)
    Timer Options: Teletext=0, DVB Subtitles=0, All Audio Tracks=0, Adjust PAT/PMT=1, EIT EPG Data=0, Transponder Dump=0
    Timer Source: Webinterface
    Monitoring Mode: Start/stop by running status

    Falls das Wort "Timer Duration: am Anfang der Zeile steht, kann die Dauer direkt aus der Klammer extrahiert werden. Ansonsten muss die EPG-Sendezeit (Format 1 oder 2) geparst werden.
    lead und follow up time mussen abgezogen werden Siehe (95 min. incl. 2 min. lead time, 0 min. follow-up time)
    """
    # 1. EPG-Sendezeit  aus  "Timer Duration: 01:35:00 (95 min. incl. 2 min. lead time, 0 min. follow-up time)"
    m = re.search(r'^\s*Timer Duration:\s*\d{1,2}:\d{2}:\d{2}\s*\((\d+)\s*min\.\s*incl\.\s*(\d+)\s*min\.\s*lead time,\s*(\d+)\s*min\.\s*follow-up time\)', content, re.MULTILINE)
    if m:   
        total_min = int(m.group(1))
        lead_min = int(m.group(2))
        follow_up_min = int(m.group(3))
        return (total_min - lead_min - follow_up_min) * 60  

    r"""
    Beispiel Format 2:
    arte HD 01.08.2011

    Autopiloten
    01:35..03:20

    Spielfilm Deutschland 2007

    Auf den Schnellstraßen des Ruhrgebiets kreuzen sich die Wege von vier Menschen, die versuchen, ihrem längst verlorenen Wunschbild zu entsprechen.

    01:30:02 Start
    01:30:04 Video: 16:9 / 1280x720 @0,7 MB
    01:30:04 Audio: AC3 2/0 / 256 kbps / 48 khz @0,7 MB
    03:29:59 Stop

    Total Size 10642,0 MB (11158992148 Bytes)

    In diesem Fall muss die Dauer aus der Zeile :"01:35..03:20" berechnet werden
    """

    # 1. EPG-Sendezeit  z. B. "01:35..03:20"
    m = re.search(r'^\s*(\d{1,2}:\d{2})\s*\.\.\s*(\d{1,2}:\d{2})\s*$', content, re.MULTILINE)
    if m:
        start_s = _hm_to_seconds(m.group(1))
        stop_s = _hm_to_seconds(m.group(2))
        if stop_s < start_s:
            stop_s += 86400
        total_s = stop_s - start_s
        return total_s


    return None


def get_video_length(path: str, use_epg: bool) -> Tuple[bool, str, Optional[float], Optional[int]]:
    """Get video duration and recording duration from ffprobe and log files."""
    video_duration = get_media_duration_ffprobe(path)

    if video_duration is None:
        return False, "ffprobe failed", None, None

    if use_epg:
        rec_duration = get_epg_duration(path)
    else:
        rec_duration = get_real_rec_time_from_log(path)

    # Fallback: try the other method if primary returned nothing
    if rec_duration is None:
        rec_duration = get_real_rec_time_from_log(path) if use_epg else get_epg_duration(path)

    if rec_duration is None:
        return False, "no reference duration", video_duration, None

    return True, "valid results", video_duration, rec_duration

def get_film_error_count(
    file_list: list[str],
    progress_cb: Callable[[str, int], None] | None = None,
) -> list[FileRecord]:
    """Analyze a list of file paths and return FileRecord for each, including error counts from logs."""
    video_suffixes = config.video_suffixes()
    results: list[FileRecord] = []

    for idx, file_path in enumerate(file_list):
        film_dir = os.path.dirname(file_path)
        film_base, _ = match_suffix(os.path.basename(file_path))

        # Check if a video file exists for this base name
        video_exists = False
        for ext in video_suffixes:
            video_filepath = os.path.join(film_dir, film_base + ext)
            if os.path.exists(video_filepath):
                video_exists = True
                break

        video_duration=None
        rec_duration=None
        if video_exists:
            ok, msg, video_duration, rec_duration = get_video_length(video_filepath, use_epg=True)

        error_count = None
        mod_date = None
        multichannel = None

        if video_exists:
            main_log = os.path.join(film_dir, film_base + ".log")
            if not os.path.exists(main_log):
                main_log = os.path.join(film_dir, film_base + "mkv.log")
            if os.path.exists(main_log):
                try:
                    mod_date = os.path.getmtime(main_log)
                    content = read_text(main_log)
                    lines = content.splitlines() if content is not None else []
                    if not lines:
                        raise ValueError("log file could not be read")
                    error_count = count_errors(lines)
                    multichannel = is_multichannel_from_log(lines)
                except (OSError, UnicodeDecodeError, ValueError):
                    error_count = None
                    mod_date = None
                    multichannel = None

        results.append(FileRecord(
            file=file_path,
            video_exists=video_exists,
            error_count=error_count,
            mod_date=mod_date,
            multichannel=multichannel,
            video_duration=video_duration, 
            rec_duration=rec_duration
        ))
        if progress_cb is not None:
            progress_cb(file_path, idx + 1)

    return results


def find_duplicates(
    source_root: str,
    duptype: str,
    remove_episode_nos: bool,
    semantic_prefixes: list[str],
    progress_cb: Callable[..., None] | None = None,
) -> tuple[list[list[str]], dict[str, dict[str, str]]]:
    """Walk source_root and group files into duplicate sets based on duptype.

    progress_cb signature: (current_dir, dirs_completed, dirs_total, files_scanned)
    """
    ignored_dirs_lower = {x.lower() for x in config.ignored_dirs()}
    ignored_files_lower = {x.lower() for x in config.ignored_files()}

    files_by_lower: dict[str, list[str]] = {}
    files_by_exact: dict[str, list[str]] = {}
    files_by_semantic: dict[str, list[str]] = {}
    file_to_groupkey: dict[str, GroupKeys] = {}
    files_scanned = 0

    # Enumerate top-level entries to provide directory-level progress
    try:
        top_entries = sorted(os.listdir(source_root))
    except OSError as e:
        print(f"[avior-dedup] Cannot list source directory: {e}")
        top_entries = []

    # Separate into: subdirectories to walk + files in the root itself
    top_dirs = []
    root_files = []
    for entry in top_entries:
        full = os.path.join(source_root, entry)
        if os.path.isdir(full):
            if entry.lower() not in ignored_dirs_lower:
                top_dirs.append(entry)
        else:
            root_files.append(entry)

    # We treat root files + each top-level subdir as a "unit" of work
    total_units = len(top_dirs) + (1 if root_files else 0)
    units_done = 0

    def _process_file(name: str, dir_path: str) -> None:
        nonlocal files_scanned
        if name.lower() in ignored_files_lower:
            return
        full_path = os.path.join(dir_path, name)
        files_scanned += 1

        files_by_exact.setdefault(name, []).append(full_path)

        lower_name = name.lower()
        files_by_lower.setdefault(lower_name, []).append(full_path)

        semantic_name = normalize_film_name(name, semantic_prefixes, remove_episode_nos)
        files_by_semantic.setdefault(semantic_name, []).append(full_path)

        file_to_groupkey[full_path] = GroupKeys(
            exact=name,
            lower=lower_name,
            semantic=semantic_name,
        )

    def _scan_dir(dir_path: str) -> None:
        """Recursively scan a directory using scandir, reporting after each subdir."""
        nonlocal files_scanned
        try:
            entries = list(os.scandir(dir_path))
        except OSError as e:
            print(f"[avior-dedup] Cannot read directory: {e}")
            return

        # Process files in this directory
        for entry in entries:
            if entry.is_file(follow_symlinks=False):
                _process_file(entry.name, dir_path)

        # Report progress once per directory
        if progress_cb is not None:
            progress_cb(dir_path, units_done, total_units, files_scanned)

        # Then recurse into subdirectories
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                if entry.name.lower() not in ignored_dirs_lower:
                    _scan_dir(entry.path)

    # Process files in the source root itself
    if root_files:
        print(f"[avior-dedup] Scanning: {source_root} ({len(root_files)} root files)")
        if progress_cb is not None:
            progress_cb(source_root, units_done, total_units, files_scanned)
        for name in root_files:
            _process_file(name, source_root)
        units_done += 1

    # Scan each top-level subdirectory
    for top_dir_name in top_dirs:
        top_dir_path = os.path.join(source_root, top_dir_name)
        print(f"[avior-dedup] Scanning: {top_dir_path}")
        if progress_cb is not None:
            progress_cb(top_dir_path, units_done, total_units, files_scanned)

        _scan_dir(top_dir_path)

        units_done += 1
        if progress_cb is not None:
            progress_cb(top_dir_path, units_done, total_units, files_scanned)
        print(f"[avior-dedup] Completed: {top_dir_path} ({files_scanned} files total so far)")

    groups: list[list[str]] = []
    if duptype in ("case", "both", "all"):
        for paths in files_by_lower.values():
            if len(paths) > 1:
                groups.append(paths)
    if duptype in ("exact", "both", "all"):
        for paths in files_by_exact.values():
            if len(paths) > 1:
                groups.append(paths)
    if duptype in ("semantic", "all"):
        for paths in files_by_semantic.values():
            if len(paths) > 1:
                groups.append(paths)

    return groups, file_to_groupkey
