"""Tests for the log_include selection priority and its term matching."""

from __future__ import annotations

from avior_dedup.dedup.models import DEFAULT_SELECTION_PRIORITIES, FileRecord, SelectionPriority
from avior_dedup.dedup.planner import determine_keep_reason, select_best_film
from avior_dedup.dedup.scanner import log_matches_include_terms

TERMS = ["-tune hq", "Lost Data:"]


def _rec(name: str, include_match: bool | None) -> FileRecord:
    return FileRecord(
        file=name,
        video_exists=True,
        error_count=0,
        mod_date=1000.0,
        multichannel=False,
        resolution=720,
        video_duration=3600.0,
        rec_duration=3600,
        log_include_match=include_match,
    )


def test_term_match_is_case_insensitive_substring():
    assert log_matches_include_terms("Encoder: ffmpeg -TUNE HQ ...", TERMS)
    assert log_matches_include_terms("... 12:00:00 Lost data: 5", TERMS)
    assert not log_matches_include_terms("PID 5311: H.264 Video, 16:9", TERMS)


def test_empty_term_list_never_matches():
    assert not log_matches_include_terms("Lost Data: 5", [])


def test_prefers_copy_without_include_match():
    plain = _rec("plain.mkv", False)
    marked = _rec("marked.mkv", True)  # e.g. newer, but avior-go marks it replaceable
    marked.mod_date = 99_999_999.0
    best = select_best_film([marked, plain])
    assert best.file == "plain.mkv"
    assert determine_keep_reason(best, [marked], DEFAULT_SELECTION_PRIORITIES) == "no_include_match"


def test_unknown_log_ranks_with_marked_copy():
    unknown = _rec("unknown.mkv", None)
    clean = _rec("clean.mkv", False)
    assert select_best_film([unknown, clean]).file == "clean.mkv"


def test_criterion_is_inert_when_not_configured():
    marked = _rec("marked.mkv", True)
    marked.mod_date = 99_999_999.0
    plain = _rec("plain.mkv", False)
    prios = [p for p in DEFAULT_SELECTION_PRIORITIES if p != SelectionPriority.LOG_INCLUDE]
    assert select_best_film([marked, plain], selection_priorities=prios).file == "marked.mkv"


def test_terms_come_from_mongo_only(monkeypatch):
    from avior_dedup import config

    monkeypatch.setattr(config, "_log_include_from_mongo", lambda: ["from-mongo"])
    config.reload()
    assert config.log_include_terms() == ["from-mongo"]


def test_no_mongo_url_means_no_terms(monkeypatch):
    from avior_dedup import config

    monkeypatch.delenv("AVIOR_DEDUP_MONGO_URL", raising=False)
    config.reload()
    assert config._log_include_from_mongo() is None
    assert config.log_include_terms() == []


def test_terms_are_cached_until_invalidated(monkeypatch):
    from avior_dedup import config

    calls = []

    def fake() -> list[str]:
        calls.append(1)
        return [f"term-{len(calls)}"]

    monkeypatch.setattr(config, "_log_include_from_mongo", fake)
    config.reload()
    assert config.log_include_terms() == ["term-1"]
    assert config.log_include_terms() == ["term-1"]
    config.invalidate_log_include()
    assert config.log_include_terms() == ["term-2"]
    assert len(calls) == 2
