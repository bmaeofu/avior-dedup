from __future__ import annotations

from pathlib import Path

from avior_dedup.dedup.scanner import find_duplicates


def test_case_duplicate_detection_uses_unicode_casefold(tmp_path: Path) -> None:
    """Case-insensitive matching should treat STRASSE and Straße as equal."""
    d1 = tmp_path / "a"
    d2 = tmp_path / "b"
    d1.mkdir()
    d2.mkdir()

    (d1 / "Der Weg in die Straße.nfo").write_text("", encoding="utf-8")
    (d2 / "Der Weg in die STRASSE.nfo").write_text("", encoding="utf-8")

    groups, _ = find_duplicates(str(tmp_path), "case", False, [])

    assert len(groups) == 1
    assert len(groups[0]) == 2


def test_semantic_duplicate_detection_matches_simple_case_difference(tmp_path: Path) -> None:
    """Semantic matching should group plain case differences reliably."""
    d1 = tmp_path / "a"
    d2 = tmp_path / "b"
    d1.mkdir()
    d2.mkdir()

    (d1 / "Aus lauter Liebe zu Dir.nfo").write_text("", encoding="utf-8")
    (d2 / "Aus lauter Liebe zu dir.nfo").write_text("", encoding="utf-8")

    groups, _ = find_duplicates(str(tmp_path), "semantic", False, [])

    assert len(groups) == 1
    assert len(groups[0]) == 2
