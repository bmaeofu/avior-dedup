from __future__ import annotations

import os

from avior_dedup.permissions import _parse_octal_env


def test_parse_octal_env_default_on_missing(monkeypatch) -> None:
    monkeypatch.delenv("AVIOR_DEDUP_OUTPUT_DIR_MODE", raising=False)
    assert _parse_octal_env("AVIOR_DEDUP_OUTPUT_DIR_MODE", 0o2775) == 0o2775


def test_parse_octal_env_default_on_invalid(monkeypatch) -> None:
    monkeypatch.setenv("AVIOR_DEDUP_OUTPUT_DIR_MODE", "not-octal")
    assert _parse_octal_env("AVIOR_DEDUP_OUTPUT_DIR_MODE", 0o2775) == 0o2775


def test_parse_octal_env_valid_value(monkeypatch) -> None:
    monkeypatch.setenv("AVIOR_DEDUP_OUTPUT_DIR_MODE", "2770")
    assert _parse_octal_env("AVIOR_DEDUP_OUTPUT_DIR_MODE", 0o2775) == int("2770", 8)
