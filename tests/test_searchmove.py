"""Tests for the searchmove module.

Uses the test-data/search-and-move/ positive/negative NFO files
with the criteria: rating:>5.4 & nfostatus:!exists (OR two alternatives).

Also tests metadata-based matching (fileext, sibling) for binary files.
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
from avior_dedup.searchmove.searcher import search_xml_file, search_text_file

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

    def test_txt_match_moves_mpg_sibling(self):
        """A .txt match should also move .mpg sibling files with same stem."""
        with tempfile.TemporaryDirectory() as tmp_src, \
             tempfile.TemporaryDirectory() as tmp_dest:
            src = Path(tmp_src)
            (src / "Europe.plot.txt").write_text("MATCH_TOKEN")
            (src / "Europe.mpg").touch()

            result = run_search_move_job(
                source=tmp_src,
                dest=tmp_dest,
                mode=ActivityMode.MOVE,
                extensions=[".txt"],
                search_expressions=["MATCH_TOKEN"],
                recursive=False,
            )

            assert result.files_matched == 1
            assert (Path(tmp_dest) / "Europe.plot.txt").exists()
            assert (Path(tmp_dest) / "Europe.mpg").exists()

    def test_txt_match_moves_configured_md_candidates(self):
        """A .txt match should move sibling files resolved via base+candidate suffixes."""
        with tempfile.TemporaryDirectory() as tmp_src, \
             tempfile.TemporaryDirectory() as tmp_dest:
            src = Path(tmp_src)
            (src / "Europe.txt").write_text("MATCH_EUROPE")
            (src / "Europe.nfo").write_text("<?xml version='1.0'?><movie></movie>")
            (src / "Europe.mkv").touch()
            (src / "Europe.mpg.log").write_text("log")
            (src / "Europe-fanart.jpg").touch()

            result = run_search_move_job(
                source=tmp_src,
                dest=tmp_dest,
                mode=ActivityMode.MOVE,
                extensions=[".txt"],
                search_expressions=["MATCH_EUROPE"],
                recursive=False,
            )

            assert result.files_matched == 1
            assert (Path(tmp_dest) / "Europe.txt").exists()
            assert (Path(tmp_dest) / "Europe.nfo").exists()
            assert (Path(tmp_dest) / "Europe.mkv").exists()
            assert (Path(tmp_dest) / "Europe.mpg.log").exists()
            assert (Path(tmp_dest) / "Europe-fanart.jpg").exists()


# ---------------------------------------------------------------------------
# Metadata-based matching tests (fileext:, sibling:)
# ---------------------------------------------------------------------------

class TestMetadataMatching:
    """Test metadata-based search terms for binary file matching."""

    def test_search_text_file_with_fileext(self):
        """Test fileext: metadata term for .txt files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a dummy .txt file
            txt_file = Path(tmp_dir) / "test.txt"
            txt_file.write_text("Some text content")

            # Search for .txt files
            search_groups = parse_search_expression(["fileext:.txt"])
            result = search_text_file(str(txt_file), search_groups)
            assert result is not None, "Should match fileext:.txt"

            # Search for .mkv files (should not match)
            search_groups = parse_search_expression(["fileext:.mkv"])
            result = search_text_file(str(txt_file), search_groups)
            assert result is None, "Should not match fileext:.mkv"

    def test_search_text_file_with_sibling_exists(self):
        """Test sibling: metadata term when sibling file exists."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            # Create .mkv and .nfo files
            mkv_file = tmp_path / "movie.mkv"
            nfo_file = tmp_path / "movie.nfo"
            mkv_file.touch()
            nfo_file.write_text("<movie></movie>")

            # Search for .mkv with .nfo sibling
            search_groups = parse_search_expression(["sibling:.nfo:exists"])
            result = search_text_file(str(mkv_file), search_groups)
            assert result is not None, "Should match sibling:.nfo:exists when .nfo exists"

    def test_search_text_file_with_sibling_not_exists(self):
        """Test sibling: metadata term when sibling file does not exist."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            # Create .mkv file without .nfo
            mkv_file = tmp_path / "orphan.mkv"
            mkv_file.touch()

            # Search for .mkv without .nfo sibling
            search_groups = parse_search_expression(["sibling:.nfo:!exists"])
            result = search_text_file(str(mkv_file), search_groups)
            assert result is not None, "Should match sibling:.nfo:!exists when .nfo does NOT exist"

    def test_search_text_file_with_sibling_exists_negative(self):
        """Test that missing sibling doesn't match :exists."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            # Create .mkv without .nfo
            mkv_file = tmp_path / "orphan.mkv"
            mkv_file.touch()

            # Search for .nfo sibling (should NOT match)
            search_groups = parse_search_expression(["sibling:.nfo:exists"])
            result = search_text_file(str(mkv_file), search_groups)
            assert result is None, "Should NOT match sibling:.nfo:exists when .nfo missing"

    def test_search_text_file_with_sibling_not_exists_negative(self):
        """Test that existing sibling doesn't match :!exists."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            # Create both .mkv and .nfo
            mkv_file = tmp_path / "movie.mkv"
            nfo_file = tmp_path / "movie.nfo"
            mkv_file.touch()
            nfo_file.write_text("<movie></movie>")

            # Search for missing .nfo sibling (should NOT match)
            search_groups = parse_search_expression(["sibling:.nfo:!exists"])
            result = search_text_file(str(mkv_file), search_groups)
            assert result is None, "Should NOT match sibling:.nfo:!exists when .nfo exists"

    def test_search_xml_file_with_fileext(self):
        """Test fileext: metadata term for .nfo XML files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a dummy .nfo file with XML
            nfo_file = Path(tmp_dir) / "movie.nfo"
            nfo_file.write_text("<?xml version='1.0'?><movie></movie>")

            # Search for .nfo files
            search_groups = parse_search_expression(["fileext:.nfo"])
            result = search_xml_file(str(nfo_file), search_groups)
            assert result is not None, "Should match fileext:.nfo"

            # Search for .mkv files (should not match)
            search_groups = parse_search_expression(["fileext:.mkv"])
            result = search_xml_file(str(nfo_file), search_groups)
            assert result is None, "Should not match fileext:.mkv"

    def test_combined_metadata_and_content_matching(self):
        """Test combining metadata terms (fileext:) with content terms (rating:)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a .nfo file that matches rating criteria with proper structure
            nfo_file = Path(tmp_dir) / "good_movie.nfo"
            nfo_file.write_text(
                "<?xml version='1.0'?><movie>"
                "<ratings><rating><value>8.0</value><votes>50</votes></rating></ratings>"
                "</movie>"
            )

            # Search for .nfo files with rating > 7.0
            search_groups = parse_search_expression(["fileext:.nfo&rating:>7.0"])
            result = search_xml_file(str(nfo_file), search_groups)
            assert result is not None, "Should match both fileext:.nfo and rating:>7.0"

    def test_mkv_nfo_workflow_positive(self):
        """Integration test: MKV+NFO workflow using new templates."""
        with tempfile.TemporaryDirectory() as tmp_src, \
             tempfile.TemporaryDirectory() as tmp_dest:
            tmp_src_path = Path(tmp_src)

            # Create test files: 2 MKV with NFO, 1 MKV without NFO
            (tmp_src_path / "movie1.mkv").touch()
            (tmp_src_path / "movie1.nfo").write_text("<movie></movie>")

            (tmp_src_path / "movie2.mkv").touch()
            (tmp_src_path / "movie2.nfo").write_text("<movie></movie>")

            (tmp_src_path / "orphan.mkv").touch()

            # Search in test mode for MKV with NFO
            result = run_search_move_job(
                source=tmp_src,
                dest=tmp_dest,
                mode=ActivityMode.TEST,
                extensions=[".mkv"],
                search_expressions=["sibling:.nfo:exists"],
                recursive=False,
            )
            # Should find 2 MKV files with NFO siblings
            assert result.files_scanned == 3, f"Expected 3 MKV files scanned, got {result.files_scanned}"
            assert result.files_matched == 2, f"Expected 2 MKV with NFO to match, got {result.files_matched}"

    def test_mkv_nfo_workflow_negative(self):
        """Integration test: MKV without NFO workflow."""
        with tempfile.TemporaryDirectory() as tmp_src, \
             tempfile.TemporaryDirectory() as tmp_dest:
            tmp_src_path = Path(tmp_src)

            # Create test files: 2 MKV with NFO, 1 MKV without NFO
            (tmp_src_path / "movie1.mkv").touch()
            (tmp_src_path / "movie1.nfo").write_text("<movie></movie>")

            (tmp_src_path / "movie2.mkv").touch()
            (tmp_src_path / "movie2.nfo").write_text("<movie></movie>")

            (tmp_src_path / "orphan.mkv").touch()

            # Search in test mode for MKV without NFO
            result = run_search_move_job(
                source=tmp_src,
                dest=tmp_dest,
                mode=ActivityMode.TEST,
                extensions=[".mkv"],
                search_expressions=["sibling:.nfo:!exists"],
                recursive=False,
            )
            # Should find 1 orphan MKV without NFO
            assert result.files_scanned == 3, f"Expected 3 MKV files scanned, got {result.files_scanned}"
            assert result.files_matched == 1, f"Expected 1 MKV without NFO to match, got {result.files_matched}"
