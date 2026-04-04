"""Tests for the searchmove module.

Uses the test-data/search-and-move/ positive/negative NFO files
with the criteria: rating:>5.4 & nfostatus:!exists (OR two alternatives).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from avior_dedup.searchmove.models import ActivityMode
from avior_dedup.searchmove.parser import parse_condition, parse_search_expression
from avior_dedup.searchmove.runner import run_search_move_job
from avior_dedup.searchmove.searcher import search_xml_file

# Resolve test-data paths relative to repo root
_REPO = Path(__file__).resolve().parent.parent
_TEST_DATA = _REPO / "test-data" / "search-and-move"
_POSITIVE_DIR = _TEST_DATA / "positive"
_NEGATIVE_DIR = _TEST_DATA / "negative"

# The search expressions from the original CLI usage
_SEARCH_EXPRESSIONS = [
    "rating:>5.4&nfostatus:!exists",
    "rating:>5.4&nfostatus:",
    "rating:>5.4&nfostatus:nfo file ok",
]


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class TestParseSearchExpression:
    def test_single_and(self):
        result = parse_search_expression(["a&b"])
        assert result == [[["a", "b"]]]

    def test_single_or(self):
        result = parse_search_expression(["a|b"])
        assert result == [[["a"], ["b"]]]

    def test_and_or_combined(self):
        result = parse_search_expression(["a&b|c"])
        assert result == [[["a", "b"], ["c"]]]

    def test_multiple_expressions(self):
        result = parse_search_expression(["a&b", "c&d"])
        assert result == [[["a", "b"]], [["c", "d"]]]

    def test_empty_input(self):
        assert parse_search_expression(None) == []
        assert parse_search_expression([]) == []
        assert parse_search_expression([""]) == []

    def test_real_criteria(self):
        result = parse_search_expression(_SEARCH_EXPRESSIONS)
        assert len(result) == 3
        # First: (rating:>5.4 AND nfostatus:!exists)
        assert result[0] == [["rating:>5.4", "nfostatus:!exists"]]
        # Second: (rating:>5.4 AND nfostatus:)
        assert result[1] == [["rating:>5.4", "nfostatus:"]]
        # Third: (rating:>5.4 AND nfostatus:nfo file ok)
        assert result[2] == [["rating:>5.4", "nfostatus:nfo file ok"]]


class TestParseCondition:
    def test_greater_than(self):
        pred = parse_condition(">5.4")
        assert pred is not None
        assert pred(5.5) is True
        assert pred(5.4) is False
        assert pred(5.3) is False

    def test_less_than(self):
        pred = parse_condition("<5")
        assert pred is not None
        assert pred(4.9) is True
        assert pred(5.0) is False

    def test_range(self):
        pred = parse_condition("4-6")
        assert pred is not None
        assert pred(5.0) is True
        assert pred(4.0) is True
        assert pred(6.0) is True
        assert pred(3.9) is False
        assert pred(6.1) is False

    def test_compound(self):
        pred = parse_condition(">4<6")
        assert pred is not None
        assert pred(5.0) is True
        assert pred(4.0) is False
        assert pred(6.0) is False

    def test_equals(self):
        pred = parse_condition("7")
        assert pred is not None
        assert pred(7.0) is True
        assert pred(7.1) is False

    def test_empty(self):
        assert parse_condition("") is None
        assert parse_condition(None) is None

    def test_non_numeric(self):
        assert parse_condition("hello") is None


# ---------------------------------------------------------------------------
# Searcher tests — using real test-data NFO files
# ---------------------------------------------------------------------------

class TestSearchXmlFile:
    """Test search_xml_file against the actual test data."""

    @pytest.fixture
    def search_groups(self):
        return parse_search_expression(_SEARCH_EXPRESSIONS)

    def _nfo_files(self, directory: Path) -> list[str]:
        return sorted(str(p) for p in directory.glob("*.nfo"))

    def test_positive_files_match(self, search_groups):
        """All positive NFO files should match the search criteria."""
        nfo_files = self._nfo_files(_POSITIVE_DIR)
        assert len(nfo_files) > 0, "No positive test NFO files found"

        for nfo_path in nfo_files:
            result = search_xml_file(nfo_path, search_groups)
            assert result is not None, f"Expected match for {os.path.basename(nfo_path)}"

    def test_negative_files_no_match(self, search_groups):
        """No negative NFO files should match the search criteria."""
        nfo_files = self._nfo_files(_NEGATIVE_DIR)
        assert len(nfo_files) > 0, "No negative test NFO files found"

        for nfo_path in nfo_files:
            result = search_xml_file(nfo_path, search_groups)
            assert result is None, f"Expected no match for {os.path.basename(nfo_path)}"

    def test_positive_match_details(self, search_groups):
        """Positive matches should report rating and !exists."""
        nfo_files = self._nfo_files(_POSITIVE_DIR)
        for nfo_path in nfo_files:
            result = search_xml_file(nfo_path, search_groups)
            assert result is not None
            assert "rating:>5.4" in result.matched_expression
            assert "nfostatus:!exists" in result.matched_expression


# ---------------------------------------------------------------------------
# Integration test — full pipeline in test mode
# ---------------------------------------------------------------------------

class TestRunSearchMoveJob:
    def test_positive_found_negative_skipped(self):
        """Run the job against the combined test-data directory in test mode."""
        with tempfile.TemporaryDirectory() as tmp_dest:
            result = run_search_move_job(
                source=str(_TEST_DATA),
                dest=tmp_dest,
                mode=ActivityMode.TEST,
                extensions=[".nfo"],
                search_expressions=_SEARCH_EXPRESSIONS,
                recursive=True,
            )
            # 5 positive + 2 negative = 7 NFO files scanned
            assert result.files_scanned == 7
            # Only the 5 positive should match
            assert result.files_matched == 5

    def test_move_mode_moves_related_files(self):
        """In move mode, matched files and their related files are moved."""
        with tempfile.TemporaryDirectory() as tmp_src, \
             tempfile.TemporaryDirectory() as tmp_dest:
            # Copy one positive movie set to the temp source
            for f in _POSITIVE_DIR.iterdir():
                if f.name.startswith("Blinde Weide"):
                    shutil.copy2(str(f), os.path.join(tmp_src, f.name))

            result = run_search_move_job(
                source=tmp_src,
                dest=tmp_dest,
                mode=ActivityMode.MOVE,
                extensions=[".nfo"],
                search_expressions=_SEARCH_EXPRESSIONS,
                recursive=False,
            )

            assert result.files_matched == 1
            # Related files should have been moved to dest
            dest_files = os.listdir(tmp_dest)
            assert any("Blinde Weide" in f for f in dest_files)
            # Source should be empty (files moved out)
            src_remaining = [f for f in os.listdir(tmp_src) if "Blinde Weide" in f]
            assert len(src_remaining) == 0
