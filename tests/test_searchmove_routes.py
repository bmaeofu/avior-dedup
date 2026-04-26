from __future__ import annotations

from pathlib import Path

from avior_dedup.server.searchmove_routes import _get_searchmove_output_paths


def test_searchmove_output_paths_skip_existing_log_and_results(tmp_path: Path):
    dest = tmp_path
    (dest / "searchmove_log.txt").write_text("existing log", encoding="utf-8")
    (dest / "results.txt").write_text("existing results", encoding="utf-8")

    log_path, output_path = _get_searchmove_output_paths(str(dest), "searchmove_log.txt")

    assert Path(log_path).name == "searchmove_log_001.txt"
    assert Path(output_path).name == "results_001.txt"