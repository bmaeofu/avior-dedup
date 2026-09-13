from __future__ import annotations

import shutil
from pathlib import Path

from avior_dedup.searchmove import mover
from avior_dedup.searchmove.models import ActivityMode


def test_find_related_files_reuses_directory_cache(monkeypatch, tmp_path: Path):
    directory = tmp_path
    (directory / "Movie.nfo").write_text("", encoding="utf-8")
    (directory / "Movie.mkv").write_text("", encoding="utf-8")
    (directory / "Movie.plot.txt").write_text("", encoding="utf-8")

    mover._DIRECTORY_FILE_INDEX_CACHE.clear()
    scandir_calls = 0
    real_scandir = mover.os.scandir

    def counting_scandir(path: str):
        nonlocal scandir_calls
        scandir_calls += 1
        return real_scandir(path)

    monkeypatch.setattr(mover.os, "scandir", counting_scandir)

    first = mover.find_related_files(str(directory / "Movie.nfo"))
    second = mover.find_related_files(str(directory / "Movie.plot.txt"))

    assert scandir_calls == 1
    assert any(Path(path).name == "Movie.mkv" for path in first)
    assert any(Path(path).name == "Movie.nfo" for path in second)


def test_process_match_skips_existing_dest_via_cached_directory_index(tmp_path: Path):
    src_dir = tmp_path / "src"
    dest_dir = tmp_path / "dest"
    src_dir.mkdir()
    dest_dir.mkdir()

    matched = src_dir / "Movie.nfo"
    matched.write_text("", encoding="utf-8")
    (src_dir / "Movie.mkv").write_text("", encoding="utf-8")
    (dest_dir / "Movie.nfo").write_text("already here", encoding="utf-8")

    mover._DIRECTORY_FILE_INDEX_CACHE.clear()
    records = mover.process_match(str(matched), str(dest_dir), ActivityMode.COPY, lambda _msg: None)

    assert any(record.status == "already exists" for record in records)

def test_ensure_dest_dir_recreates_removed_directory(tmp_path: Path):
    dest = tmp_path / "dest"
    mover._ENSURED_DEST_DIRS.clear()

    mover._ensure_dest_dir(str(dest))
    assert dest.is_dir()

    # Verzeichnis verschwindet zwischen zwei Jobs im selben Prozess.
    shutil.rmtree(dest)
    mover._ensure_dest_dir(str(dest))
    assert dest.is_dir()


def test_process_match_survives_dest_dir_removed_between_jobs(tmp_path: Path):
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    src.mkdir()
    matched = src / "Movie.nfo"
    matched.write_text("", encoding="utf-8")

    mover._DIRECTORY_FILE_INDEX_CACHE.clear()
    mover._ENSURED_DEST_DIRS.clear()

    first = mover.process_match(str(matched), str(dest), ActivityMode.COPY, lambda _msg: None)
    assert [record.status for record in first] == ["copied"]

    shutil.rmtree(dest)
    second = mover.process_match(str(matched), str(dest), ActivityMode.COPY, lambda _msg: None)
    assert [record.status for record in second] == ["copied"]


def test_execute_file_action_reports_missing_source(tmp_path: Path):
    dest = tmp_path / "dest"
    dest.mkdir()
    lines: list[str] = []

    record = mover.execute_file_action(
        str(tmp_path / "gone.nfo"), str(dest / "gone.nfo"), ActivityMode.MOVE, lines.append
    )

    assert record.status == "error: source not found"
    assert lines[-1].endswith("source not found")


def test_execute_file_action_reports_missing_destination_dir(tmp_path: Path):
    src = tmp_path / "Movie.nfo"
    src.write_text("", encoding="utf-8")
    lines: list[str] = []

    record = mover.execute_file_action(
        str(src), str(tmp_path / "missing" / "Movie.nfo"), ActivityMode.MOVE, lines.append
    )

    assert record.status == "error: destination directory missing"
    assert lines[-1].endswith("destination directory missing")
