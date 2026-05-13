from __future__ import annotations

from avior_dedup.dedup.scanner import (
    _truncate_log,
    get_recording_resolution_from_log,
    is_multichannel_from_log,
)


def test_detects_multichannel_in_format1_plain_timestamp_log() -> None:
    lines = [
        "ZDF HD 20.03.2011",
        "15:00:02 Start",
        "15:00:04 Video: 16:9 / 1280x720 @1,2 MB",
        "15:00:04 Audio: AC3 Audio 5.1 / 448 kbps / 48 khz @1,2 MB",
    ]
    assert is_multichannel_from_log(lines) is True


def test_detects_multichannel_in_format2_elapsed_timestamp_log() -> None:
    lines = [
        "23:30:38 / 00:00:00 (~ 0,00 MB) Start Recording",
        "23:30:39 / 00:00:01 (~ 1,75 MB) PID 5316: AC3 Audio 5.1, 48 khz, 384 kbps",
    ]
    assert is_multichannel_from_log(lines) is True


def test_detects_multichannel_from_ac3_channel_pair_notation() -> None:
    lines = [
        "15:00:02 Start",
        "15:00:04 Audio: AC3 3/2 / 448 kbps / 48 khz @1,2 MB",
    ]
    assert is_multichannel_from_log(lines) is True


def test_stereo_ac3_is_not_marked_as_multichannel() -> None:
    lines = [
        "15:00:02 Start",
        "15:00:04 Audio: AC3 2/0 / 448 kbps / 48 khz @1,2 MB",
    ]
    assert is_multichannel_from_log(lines) is False


def test_last_audio_state_in_start_window_decides_result_format1() -> None:
    lines = [
        "20:13:02 / 00:00:00 (~ 0,00 MB) Start EPG Monitoring",
        "20:16:02 / 00:00:00 (~ 0,00 MB) Start Recording",
        "20:16:04 / 00:00:02 (~ 1,69 MB) PID 5106: AC3 Audio Stereo, 48 khz, 448 kbps",
        "20:16:10 / 00:00:08 (~ 8,95 MB) PID 5106: AC3 Audio 5.1, 48 khz, 448 kbps",
        "21:44:15 / 01:28:13 (~ 7348,51 MB) PID 5106: AC3 Audio Stereo, 48 khz, 448 kbps",
    ]
    assert is_multichannel_from_log(lines) is True


def test_format3_uses_last_audio_state_within_first_15_seconds() -> None:
    lines = [
        "13:55:00 Start",
        "13:55:02 Audio: AC3 Audio Stereo / 448 kbps / 48 khz @1,2 MB",
        "13:55:10 Audio: AC3 Audio 5.1 / 448 kbps / 48 khz @1,2 MB",
        "15:06:59 Stop",
    ]
    assert is_multichannel_from_log(lines) is True


def test_late_audio_changes_do_not_override_start_window_state() -> None:
    lines = [
        "14:11:23 / 00:00:00 (~ 0,00 MB) Start",
        "14:11:24 / 00:00:01 (~ 0,46 MB) PID 5116: AC3 Audio 5.1, 48 khz, 448 kbps",
        "17:02:40 / 02:51:17 (~ 8340,00 MB) PID 5116: AC3 Audio Stereo, 48 khz, 448 kbps",
        "17:02:45 / 02:51:22 (~ 8341,72 MB) Stop",
    ]
    assert is_multichannel_from_log(lines) is True


def test_error_lines_do_not_change_multichannel_detection() -> None:
    lines = [
        "22:25:00 / 00:00:00 (~ 0,00 MB) Start Recording",
        "22:25:01 / 00:00:00 (~ 0,00 MB) PID 4924: AC3 Audio 5.1, 48 khz, 384 kbps",
        "22:58:07 / 00:33:06 (~ 2014,65 MB) Errors: 1",
        "00:50:00 / 02:24:59 (~ 9157,45 MB) Stop",
    ]
    assert is_multichannel_from_log(lines) is True


def test_truncate_log_excludes_avior_go_tail() -> None:
    content = (
        "14:11:23 / 00:00:00 (~ 0,00 MB) Start\n"
        "14:11:24 / 00:00:01 (~ 0,46 MB) PID 5116: AC3 Audio 5.1, 48 khz, 448 kbps\n"
        "avior-go info\n"
        "14:11:25 / 00:00:02 (~ 0,80 MB) PID 5116: AC3 Audio Stereo, 48 khz, 448 kbps\n"
    )
    truncated = _truncate_log(content)
    assert "avior-go info" not in truncated
    assert "14:11:25 / 00:00:02" not in truncated


def test_resolution_detects_1080_from_1920x1080() -> None:
    lines = [
        "01:32:08 / 00:00:00 (~ 0,00 MB) Start Recording",
        "01:32:17 / 00:00:08 (~ 0,58 MB) PID 4920: H.264 Video, 16:9, 1920x1080, 25 fps",
    ]
    assert get_recording_resolution_from_log(lines) == 1080


def test_resolution_normalizes_1088_to_1080() -> None:
    lines = [
        "01:32:08 / 00:00:00 (~ 0,00 MB) Start Recording",
        "01:32:17 / 00:00:08 (~ 0,58 MB) PID 4920: H.264 Video, 16:9, 1920x1088, 25 fps",
    ]
    assert get_recording_resolution_from_log(lines) == 1080


def test_resolution_detects_720_from_1280x720() -> None:
    lines = [
        "23:10:26 / 00:00:00 (~ 0,00 MB) Start Recording",
        "23:10:27 / 00:00:01 (~ 0,09 MB) PID 5331: H.264 Video, 16:9, 1280x720, 50 fps",
    ]
    assert get_recording_resolution_from_log(lines) == 720
