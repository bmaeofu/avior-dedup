from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_CONFIG_DIR = Path(__file__).parent
_cache: dict[str, Any] = {}


def _load_yaml(filename: str) -> Any:
    if filename not in _cache:
        with open(_CONFIG_DIR / filename, "r", encoding="utf-8") as f:
            _cache[filename] = yaml.safe_load(f)
    return _cache[filename]


def reload() -> None:
    """Clear cached config so next access re-reads from disk."""
    _cache.clear()


def ignored_files() -> set[str]:
    return set(_load_yaml("ignored_files.yaml"))


def ignored_dirs() -> set[str]:
    return set(_load_yaml("ignored_dirs.yaml"))


def candidate_suffixes() -> list[str]:
    return _load_yaml("suffixes.yaml")["candidate_suffixes"]


def video_suffixes() -> list[str]:
    return _load_yaml("suffixes.yaml")["video_suffixes"]


def series_keep_episode_nos() -> list[str]:
    data = _load_yaml("episode_keywords.yaml")
    return data["series_keep_episode_nos"]


def episode_keep_keywords() -> list[str]:
    data = _load_yaml("episode_keywords.yaml")
    return data["episode_keep_keywords"]


def episode_keep_keywords_years() -> list[str]:
    data = _load_yaml("episode_keywords.yaml")
    return data["episode_keep_keywords_years"]


def config_dir() -> Path:
    """Return the directory containing the YAML config files."""
    return _CONFIG_DIR


def config_files() -> dict[str, str]:
    """Return a mapping of config name to YAML filename."""
    return {
        "ignored_files": "ignored_files.yaml",
        "ignored_dirs": "ignored_dirs.yaml",
        "suffixes": "suffixes.yaml",
        "episode_keywords": "episode_keywords.yaml",
        "path_suggestions": "path_suggestions.yaml",
    }
