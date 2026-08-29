"""Tests for the ``year_match`` selection priority in dedup best-film selection."""

from __future__ import annotations

from avior_dedup.dedup.models import FileRecord, SelectionPriority
from avior_dedup.dedup.planner import determine_keep_reason, select_best_film


def _rec(name: str, nfo_year=None, txt_year=None, **kw) -> FileRecord:
    return FileRecord(
        file=name,
        video_exists=True,
        nfo_year=nfo_year,
        txt_year=txt_year,
        **kw,
    )


def test_select_best_film_prefers_year_match():
    good = _rec("good.mkv", nfo_year=1989, txt_year=1989)
    bad = _rec("bad.mkv", nfo_year=2000, txt_year=1990)
    best = select_best_film(
        [good, bad],
        selection_priorities=[SelectionPriority.YEAR_MATCH],
    )
    assert best.file == "good.mkv"


def test_select_best_film_prefers_year_match_over_missing():
    good = _rec("good.mkv", nfo_year=1989, txt_year=1989)
    missing = _rec("missing.mkv")
    best = select_best_film(
        [good, missing],
        selection_priorities=[SelectionPriority.YEAR_MATCH],
    )
    assert best.file == "good.mkv"


def test_select_best_film_year_match_last_tiebreak():
    """year_match is a tiebreaker: higher priorities decide first."""
    # Same resolution (720), but one has matching years.
    good = _rec("good.mkv", nfo_year=1989, txt_year=1989, resolution=720)
    bad = _rec("bad.mkv", nfo_year=2000, txt_year=1990, resolution=720)
    best = select_best_film(
        [good, bad],
        selection_priorities=[
            SelectionPriority.RESOLUTION,
            SelectionPriority.YEAR_MATCH,
        ],
    )
    assert best.file == "good.mkv"


def test_determine_keep_reason_year_match():
    good = _rec("good.mkv", nfo_year=1989, txt_year=1989)
    bad = _rec("bad.mkv", nfo_year=2000, txt_year=1990)
    reason = determine_keep_reason(
        good,
        [bad],
        [SelectionPriority.YEAR_MATCH],
    )
    assert reason == "year_match"


def test_determine_keep_reason_no_match_falls_back():
    a = _rec("a.mkv", nfo_year=2000, txt_year=2000)
    b = _rec("b.mkv", nfo_year=2000, txt_year=2000)
    reason = determine_keep_reason(
        a,
        [b],
        [SelectionPriority.YEAR_MATCH],
    )
    assert reason == "selected"
