"""Tests for the strict duplicate-grouping options (txt year, video duration)."""

from __future__ import annotations

from pathlib import Path

from avior_dedup.dedup import scanner
from avior_dedup.dedup.scanner import _cluster_by_duration, find_duplicates


def _base(path: Path, name: str, txt_year: int | None = None) -> None:
    Path(path, name + ".log").write_text("x", encoding="utf-8")
    if txt_year is not None:
        Path(path, name + ".txt").write_text(
            f"Info=Spielfilm Deutschland {txt_year}\n", encoding="utf-8"
        )


def _groups(path: Path, **opts) -> list:
    groups, _ = find_duplicates(
        str(path),
        duptype="semantic",
        remove_episode_nos=False,
        remove_non_episode_parens=True,
        semantic_prefixes=[],
        **opts,
    )
    return groups


# ---------------------------------------------------------------------------
# _cluster_by_duration
# ---------------------------------------------------------------------------

def test_cluster_within_tolerance():
    clusters = _cluster_by_duration([("/a", 100.0), ("/b", 103.0), ("/c", 105.0)], 0.05)
    assert len(clusters) == 1
    assert sorted(clusters[0]) == ["/a", "/b", "/c"]


def test_cluster_outside_tolerance_splits():
    clusters = _cluster_by_duration([("/a", 100.0), ("/b", 103.0), ("/d", 200.0)], 0.05)
    assert len(clusters) == 2
    assert sorted(clusters[0]) == ["/a", "/b"]
    assert clusters[1] == ["/d"]


def test_cluster_drops_missing_duration():
    clusters = _cluster_by_duration([("/a", 100.0), ("/b", None), ("/c", 103.0)], 0.05)
    assert len(clusters) == 1
    assert sorted(clusters[0]) == ["/a", "/c"]


# ---------------------------------------------------------------------------
# require_identical_txt_year
# ---------------------------------------------------------------------------

def test_txt_year_different_not_duplicates(tmp_path):
    _base(tmp_path, "Film (2019)", txt_year=2019)
    _base(tmp_path, "Film", txt_year=2020)
    assert _groups(tmp_path, require_identical_txt_year=True) == []


def test_txt_year_identical_groups(tmp_path):
    _base(tmp_path, "Film (2019)", txt_year=2019)
    _base(tmp_path, "Film", txt_year=2019)
    assert len(_groups(tmp_path, require_identical_txt_year=True)) == 1


def test_txt_year_missing_excluded(tmp_path):
    _base(tmp_path, "Film (2019)", txt_year=2019)
    _base(tmp_path, "Film")  # no .txt -> no txt_year
    assert _groups(tmp_path, require_identical_txt_year=True) == []


# ---------------------------------------------------------------------------
# require_videoduration_match
# ---------------------------------------------------------------------------

def test_videoduration_match_groups_within_5_percent(tmp_path, monkeypatch):
    # Both stems normalize to "film"; durations differ by 2.8% -> duplicates.
    monkeypatch.setattr(scanner, "_video_duration_for", lambda d, s: 3600.0 if "(" in s else 3700.0)
    _base(tmp_path, "Film (2019)")
    _base(tmp_path, "Film")
    assert len(_groups(tmp_path, require_videoduration_match=True)) == 1


def test_videoduration_mismatch_not_duplicates(tmp_path, monkeypatch):
    # 3600 vs 5000 -> ~28% -> not duplicates.
    monkeypatch.setattr(scanner, "_video_duration_for", lambda d, s: 3600.0 if "(" in s else 5000.0)
    _base(tmp_path, "Film (2019)")
    _base(tmp_path, "Film")
    assert _groups(tmp_path, require_videoduration_match=True) == []
