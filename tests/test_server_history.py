"""Tests for the persistent run history store (server/history.py)."""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def history(tmp_path, monkeypatch):
    """Fresh history module bound to a temporary config dir."""
    monkeypatch.setenv("AVIOR_DEDUP_CONFIG_DIR", str(tmp_path))
    from avior_dedup import config
    config.reload()
    config._CONFIG_DIR = None  # force re-resolution to the temp dir
    from avior_dedup.server import history as history_module
    importlib.reload(history_module)
    history_module.init_db()
    yield history_module
    config.reload()
    config._CONFIG_DIR = None


def test_record_and_list_runs(history):
    rid = history.record_run("dedup", "m", {"mode": "m", "source": "/s", "target": "/t"})
    assert rid > 0
    runs = history.list_runs()
    assert len(runs) == 1
    assert runs[0]["module"] == "dedup"
    assert runs[0]["mode"] == "m"
    assert runs[0]["status"] == "running"
    assert runs[0]["params"]["source"] == "/s"


def test_finish_run_sets_status_and_summary(history):
    rid = history.record_run("searchmove", "test", {"mode": "test", "source": "/s", "dest": "/d"})
    history.finish_run(rid, "completed", {"files_matched": 5})
    run = history.get_run(rid)
    assert run["status"] == "completed"
    assert run["summary"]["files_matched"] == 5
    assert run["finished_at"] is not None


def test_list_runs_filters_by_module(history):
    history.record_run("dedup", "m", {})
    history.record_run("searchmove", "test", {})
    assert [r["module"] for r in history.list_runs("dedup")] == ["dedup"]
    assert [r["module"] for r in history.list_runs("searchmove")] == ["searchmove"]
    assert len(history.list_runs()) == 2


def test_newest_first(history):
    first = history.record_run("dedup", "m", {"n": 1})
    second = history.record_run("dedup", "m", {"n": 2})
    runs = history.list_runs()
    assert runs[0]["id"] == second
    assert runs[1]["id"] == first


def test_init_marks_stale_running_as_failed(history):
    rid = history.record_run("dedup", "m", {})
    assert history.get_run(rid)["status"] == "running"
    history.init_db()
    assert history.get_run(rid)["status"] == "failed"


def test_delete_run(history):
    rid = history.record_run("dedup", "m", {})
    assert history.delete_run(rid) is True
    assert history.get_run(rid) is None
    assert history.delete_run(rid) is False


def test_clear_runs_by_module(history):
    history.record_run("dedup", "m", {})
    history.record_run("dedup", "f", {})
    history.record_run("searchmove", "test", {})
    assert history.clear_runs("dedup") == 2
    assert [r["module"] for r in history.list_runs()] == ["searchmove"]
    assert history.clear_runs() == 1
    assert history.list_runs() == []
