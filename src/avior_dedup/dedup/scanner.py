from __future__ import annotations

import os
import re
import subprocess
import unicodedata
import datetime
import logging
from typing import Callable, Optional, Tuple

from avior_dedup import config
from avior_dedup.dedup.io_utils import read_text
from avior_dedup.dedup.models import FileRecord, GroupKeys
from avior_dedup.dedup.normalize import normalize_film_name
from avior_dedup.dedup.suffix import match_suffix


def _canonical_case_key(name: str) -> str:
    """Return a Unicode-normalized key for case-insensitive filename grouping."""
    return unicodedata.normalize("NFKC", name).casefold()

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
    """Count encoding errors from log lines.

    Historically we looked for lines containing 'MB) Errors:', but some
    log formats use 'Errors: N' (e.g. '02:18:00 Errors: 1 @5889,6 MB').
    This function now recognizes both variants.
    """
    error_count = 0
    for line in lines:
        try:
            # Preferred pattern: 'Errors: <num>' anywhere in the line
            m = re.search(r'Errors:\s*(\d+)', line)
            if m:
                error_count += int(m.group(1))
                continue

            # Backwards-compatible: '...MB) Errors: <num>'
            if "MB) Errors:" in line:
                parts = line.split("MB) Errors:")
                if len(parts) > 1:
                    error_count += int(parts[1].strip().split()[0])
        except ValueError:
            continue
    return error_count


def _ac3_audio_state_from_line(line: str) -> Optional[bool]:
    """Return AC3 channel state from a recording line: True=MC, False=stereo, None=not an AC3 audio-state line."""
    lower = line.lower()
    if "ac3" not in lower:
        return None

    # Ignore non-audio AC3 mentions (e.g. channel/program headers)
    if "audio" not in lower and not re.search(r"\bac3\s+\d\s*/\s*\d\b", lower):
        return None

    if "stereo" in lower:
        return False

    # Common notation in VDR logs (e.g. "AC3 Audio 5.1")
    if re.search(r"\b([5-9])\.[01]\b", lower):
        return True

    # Channel pair notation (e.g. "AC3 3/2" -> 5 channels, "AC3 2/0" -> stereo)
    m = re.search(r"\bac3(?:\s+audio)?\s+(\d)\s*/\s*(\d)\b", lower)
    if m:
        front = int(m.group(1))
        rear = int(m.group(2))
        return (front + rear) > 2

    if re.search(r"\b([12])\.[01]\b", lower):
        return False

    return None


def _recording_elapsed_seconds_from_line(line: str, plain_start_seconds: int | None) -> Optional[int]:
    """Extract seconds elapsed since recording start for a log line."""
    slash_time_re = re.compile(r"/\s*(\d+):(\d+):(\d+)")
    plain_time_re = re.compile(r"^\s*(\d+):(\d+):(\d+)\b")
    m = slash_time_re.search(line)
    if m:
        h, mi, s = map(int, m.groups())
        return h * 3600 + mi * 60 + s

    m = plain_time_re.search(line)
    if not m:
        return None
    h, mi, s = map(int, m.groups())
    current_seconds = h * 3600 + mi * 60 + s
    if plain_start_seconds is None:
        return current_seconds
    seconds = current_seconds - plain_start_seconds
    if seconds < 0:
        seconds += 86400
    return seconds


def _recording_start_window_lines(lines: list[str], max_seconds: int = 25) -> list[str]:
    """Return lines in the first max_seconds after Start/Start Recording."""
    plain_time_re = re.compile(r"^\s*(\d+):(\d+):(\d+)\b")
    recording_started = False
    plain_start_seconds: int | None = None
    window_lines: list[str] = []

    for line in lines:
        if not recording_started:
            if line.strip().endswith("Start") or "Start Recording" in line:
                recording_started = True
                m_start = plain_time_re.search(line)
                if m_start:
                    h, mi, s = map(int, m_start.groups())
                    plain_start_seconds = h * 3600 + mi * 60 + s
            continue

        seconds = _recording_elapsed_seconds_from_line(line, plain_start_seconds)
        if seconds is None:
            continue
        if seconds > max_seconds:
            break
        window_lines.append(line)

    return window_lines


def _recording_lines(lines: list[str]) -> list[str]:
    """Return all lines from the first recording Start until the corresponding Stop.

    This extracts the full recording block (used for video resolution detection),
    not just the initial start window.
    """
    plain_time_re = re.compile(r"^\s*(\d+):(\d+):(\d+)\b")
    recording_started = False
    block_lines: list[str] = []

    for line in lines:
        if not recording_started:
            if line.strip().endswith("Start") or "Start Recording" in line:
                recording_started = True
                block_lines.append(line)
            continue

        block_lines.append(line)
        if line.strip().endswith("Stop") or re.search(r"\bStop\b", line):
            break

    return block_lines


def is_multichannel_from_log(lines: list[str], max_seconds: int = 25) -> bool:
    """Determine AC3 channel mode from the recording start window.

    The decisive signal is the *last* AC3 audio state line found within the
    first ``max_seconds`` after recording start.
    """
    last_audio_state: Optional[bool] = None
    for line in _recording_start_window_lines(lines, max_seconds=max_seconds):
        ac3_state = _ac3_audio_state_from_line(line)
        if ac3_state is not None:
            last_audio_state = ac3_state
    return bool(last_audio_state)


def _video_resolution_from_line(line: str) -> Optional[int]:
    """Extract normalized vertical resolution from a video line (e.g. 1080, 720)."""
    if "video" not in line.lower():
        return None
    m = re.search(r"\b(\d{3,5})x(\d{3,5})\b", line)
    if not m:
        return None
    height = int(m.group(2))
    if height == 1088:
        return 1080
    return height


def get_recording_resolution_from_log(lines: list[str], max_seconds: int = 15) -> Optional[int]:
    """Return the last detected video resolution from the full recording block.

    Video resolution detection uses the entire recording block (from Start to
    Stop) rather than the short start window. The start window remains the
    authoritative source for audio/multichannel detection.
    """
    recording_block = _recording_lines(lines)
    last_resolution: Optional[int] = None
    for line in recording_block:
        res = _video_resolution_from_line(line)
        if res is not None:
            last_resolution = res
    return last_resolution

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
    """Entfernt den Statistik-/Nachlaufteil, inkl. avior-go Zusatzdaten."""
    cut_markers = ("Removed Filler Data", "Total Size", "avior-go info", "avior-go")
    cut_idx = len(content)
    found = False
    for marker in cut_markers:
        idx = content.find(marker)
        if idx != -1 and idx < cut_idx:
            cut_idx = idx
            found = True
    if found:
        return content[:cut_idx]
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
    log_fn: Callable[[str], None] | None = None,
) -> list[FileRecord]:
    """Analyze a list of file paths and return FileRecord for each, including error counts from logs."""
    video_suffixes = config.video_suffixes()
    results: list[FileRecord] = []
    # cache directory listings to reduce IO
    dir_files_cache: dict[str, set[str]] = {}

    for idx, file_path in enumerate(file_list):
        film_dir = os.path.dirname(file_path)
        film_base, _ = match_suffix(os.path.basename(file_path))

        if film_dir not in dir_files_cache:
            try:
                dir_files_cache[film_dir] = set(os.listdir(film_dir))
            except OSError:
                dir_files_cache[film_dir] = set()
        files_in_dir = dir_files_cache[film_dir]

        # Check if a video file exists for this base name using cached listing
        video_exists = any((film_base + ext) in files_in_dir for ext in video_suffixes)
        video_filepath = None
        if video_exists:
            for ext in video_suffixes:
                candidate = film_base + ext
                if candidate in files_in_dir:
                    video_filepath = os.path.join(film_dir, candidate)
                    break

        if not video_exists:
            tried = [os.path.join(film_dir, film_base + ext) for ext in video_suffixes]
            # logging.debug("No video found for base '%s' in '%s'. Tried: %s", film_base, film_dir, tried)

        video_duration=None
        rec_duration=None
        if video_exists:
            ok, msg, video_duration, rec_duration = get_video_length(video_filepath, use_epg=True)

        error_count = None
        mod_date = None
        multichannel = None
        resolution = None
        rec_date = None

        if video_exists:
            # Determine main_log using cached directory listing when possible
            main_log = None
            if (film_base + ".log") in files_in_dir:
                main_log = os.path.join(film_dir, film_base + ".log")
            elif (film_base + "mkv.log") in files_in_dir:
                main_log = os.path.join(film_dir, film_base + "mkv.log")
            if main_log and os.path.exists(main_log):
                try:
                    mod_date = os.path.getmtime(main_log)
                    content = read_text(main_log)
                    if content is not None:
                        content = _truncate_log(content)
                    lines = content.splitlines() if content is not None else []
                    if not lines:
                        raise ValueError("log file could not be read")

                    # Parse recording date from first line (formats: dd.mm.yyyy or dd/mm/yyyy)
                    first_line = lines[0]
                    m = re.search(r"(\b\d{1,2}[./]\d{1,2}[./]\d{4}\b)", first_line)
                    if m:
                        date_str = m.group(1)
                        sep = '.' if '.' in date_str else '/'
                        d, mo, y = date_str.split(sep)
                        try:
                            dt = datetime.date(int(y), int(mo), int(d))
                            rec_date = dt.isoformat()
                        except ValueError:
                            rec_date = None

                    error_count = count_errors(lines)
                    multichannel = is_multichannel_from_log(lines)
                    resolution = get_recording_resolution_from_log(lines)
                except (OSError, UnicodeDecodeError, ValueError):
                    error_count = None
                    mod_date = None
                    multichannel = None
                    resolution = None
                    rec_date = None

        results.append(FileRecord(
            file=file_path,
            video_exists=video_exists,
            error_count=error_count,
            mod_date=mod_date,
            multichannel=multichannel,
            resolution=resolution,
            video_duration=video_duration,
            rec_duration=rec_duration,
            rec_date=rec_date,
        ))
        if progress_cb is not None:
            progress_cb(file_path, idx + 1)

    return results


def find_duplicates(
    source_root: str,
    duptype: str,
    remove_episode_nos: bool,
    semantic_prefixes: list[str],
    remove_spaces: bool = False,
    remove_non_episode_parens: bool = False,
    ignored_directories: list[str] | None = None,
    progress_cb: Callable[..., None] | None = None,
) -> tuple[list[list[str]], dict[str, dict[str, str]]]:
    """Walk source_root and group files into duplicate sets based on duptype.

    progress_cb signature: (current_dir, dirs_completed, dirs_total, files_scanned)
    """
    ignored_dirs_lower = {_canonical_case_key(x) for x in config.ignored_dirs()}
    ignored_dir_paths_lower: set[str] = set()
    for raw in ignored_directories or []:
        val = (raw or "").strip()
        if not val:
            continue
        ignored_dirs_lower.add(_canonical_case_key(os.path.basename(val)))
        ignored_dir_paths_lower.add(_canonical_case_key(os.path.abspath(val)))

    ignored_files_lower = {_canonical_case_key(x) for x in config.ignored_files()}

    # Map stem (base name without known suffix) -> list of files with that stem
    stems_to_files: dict[str, list[str]] = {}
    # Stems for which we found a log-like file (defines a video set)
    stems_with_log: set[str] = set()
    file_to_groupkey: dict[str, GroupKeys] = {}
    files_scanned = 0

    def _is_ignored_dir(name: str, full_path: str) -> bool:
        return (
            _canonical_case_key(name) in ignored_dirs_lower
            or _canonical_case_key(os.path.abspath(full_path)) in ignored_dir_paths_lower
        )

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
            if not _is_ignored_dir(entry, full):
                top_dirs.append(entry)
        else:
            root_files.append(entry)

    # We treat root files + each top-level subdir as a "unit" of work
    total_units = len(top_dirs) + (1 if root_files else 0)
    units_done = 0

    def _process_file(name: str, dir_path: str) -> None:
        nonlocal files_scanned
        if _canonical_case_key(name) in ignored_files_lower:
            return
        full_path = os.path.join(dir_path, name)
        files_scanned += 1

        # Determine canonical stem and matched suffix using the suffix matcher
        stem, suf = match_suffix(name)
        stems_to_files.setdefault(stem, []).append(full_path)

        # If the matched suffix is a log variant, mark this stem as a defined video-set
        if suf and suf.lower().endswith(".log"):
            stems_with_log.add(stem)

        # Build group keys based on the stem so the whole set is identified by the stem
        lower_name = _canonical_case_key(stem)
        semantic_name = normalize_film_name(
            stem,
            semantic_prefixes,
            remove_episode_nos,
            remove_spaces,
            remove_non_episode_parens,
        )
        file_to_groupkey[full_path] = GroupKeys(
            exact=stem,
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
                if not _is_ignored_dir(entry.name, entry.path):
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

    # If both '<stem>.log' and '<stem>.<something>.log' (e.g. '.mkv.log') exist,
    # prefer the plain '<stem>.log' and remove the other log-variants from the
    # stem->files mapping so they are not considered as separate log entries.
    for stem, fps in list(stems_to_files.items()):
        log_variants = [fp for fp in fps if match_suffix(os.path.basename(fp))[1] and match_suffix(os.path.basename(fp))[1].lower().endswith('.log')]
        # if a plain '.log' exists, drop other '.<ext>.log' variants
        plain_log = None
        for lp in log_variants:
            if os.path.basename(lp).lower().endswith('.log') and not os.path.basename(lp).lower().endswith('.mkv.log') and not os.path.basename(lp).lower().endswith('.mp4.log') and not os.path.basename(lp).lower().endswith('.ts.log'):
                plain_log = lp
                break
        if plain_log:
            new_fps = [fp for fp in fps if not (match_suffix(os.path.basename(fp))[1] and match_suffix(os.path.basename(fp))[1].lower().endswith('.log') and fp != plain_log)]
            stems_to_files[stem] = new_fps

    # Build groups based on stems that have a log file. Stems represent full
    # video-sets; group together stems that match under the requested duptype,
    # then expand those stems into the actual file paths that belong to each set.
    # Prepare mappings: key -> list[stem]
    if stems_with_log:
        lower_to_stems: dict[str, list[str]] = {}
        exact_to_stems: dict[str, list[str]] = {}
        semantic_to_stems: dict[str, list[str]] = {}

        for stem in stems_with_log:
            lower = _canonical_case_key(stem)
            lower_to_stems.setdefault(lower, []).append(stem)

            exact_to_stems.setdefault(stem, []).append(stem)

            sem = normalize_film_name(
                stem,
                semantic_prefixes,
                remove_episode_nos,
                remove_spaces,
                remove_non_episode_parens,
            )
            semantic_to_stems.setdefault(sem, []).append(stem)

        if duptype in ("case", "both", "all"):
            for stems in lower_to_stems.values():
                if len(stems) > 1:
                    # expand stems into .log file paths only
                    group_paths: list[str] = []
                    for s in stems:
                        for fp in stems_to_files.get(s, []):
                            suf = match_suffix(os.path.basename(fp))[1]
                            if suf and suf.lower().endswith('.log'):
                                group_paths.append(fp)
                    if len(group_paths) > 1:
                        groups.append(group_paths)

        if duptype in ("exact", "both", "all"):
            for stems in exact_to_stems.values():
                if len(stems) > 1:
                    group_paths = []
                    for s in stems:
                        for fp in stems_to_files.get(s, []):
                            suf = match_suffix(os.path.basename(fp))[1]
                            if suf and suf.lower().endswith('.log'):
                                group_paths.append(fp)
                    if len(group_paths) > 1:
                        groups.append(group_paths)

        if duptype in ("semantic", "all"):
            for stems in semantic_to_stems.values():
                if len(stems) > 1:
                    group_paths = []
                    for s in stems:
                        for fp in stems_to_files.get(s, []):
                            suf = match_suffix(os.path.basename(fp))[1]
                            if suf and suf.lower().endswith('.log'):
                                group_paths.append(fp)
                    if len(group_paths) > 1:
                        groups.append(group_paths)

    return groups, file_to_groupkey
