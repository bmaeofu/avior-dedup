from __future__ import annotations

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