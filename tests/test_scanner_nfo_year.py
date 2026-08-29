"""Tests for the nfo_year duplicate-grouping rule in find_duplicates.

Rule: two recordings are semantic duplicates only if BOTH have an nfo_year
and they are identical. Different or missing nfo_year -> not duplicates.
"""

from __future__ import annotations

from pathlib import Path

from avior_dedup.dedup.scanner import find_duplicates


def _make(path: Path, name: str, year: int | None = None) -> None:
    Path(path, name + ".log").write_text("x", encoding="utf-8")
    if year is not None:
        Path(path, name + ".nfo").write_text(
            f"<movie><year>{year}</year></movie>", encoding="utf-8"
        )


def _groups(path: Path) -> list:
    groups, _ = find_duplicates(
        str(path),
        duptype="semantic",
        remove_episode_nos=False,
        remove_non_episode_parens=True,
        semantic_prefixes=[],
    )
    return groups


def test_same_year_groups_as_duplicates(tmp_path):
    _make(tmp_path, "Film (2020)", year=2020)
    _make(tmp_path, "Film", year=2020)
    assert len(_groups(tmp_path)) == 1


def test_different_year_not_duplicates(tmp_path):
    _make(tmp_path, "Film (2020)", year=2020)
    _make(tmp_path, "Film (2019)", year=2019)
    assert _groups(tmp_path) == []


def test_missing_year_not_duplicates(tmp_path):
    _make(tmp_path, "Film (2020)", year=2020)
    _make(tmp_path, "Film")  # no .nfo -> no nfo_year
    assert _groups(tmp_path) == []
