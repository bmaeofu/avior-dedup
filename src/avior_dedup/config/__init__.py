from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import yaml

_BUNDLED_DIR = Path(__file__).parent
_CONFIG_DIR: Path | None = None
_cache: dict[str, Any] = {}

# Cache key for the log_include term list read from MongoDB.
_LOG_INCLUDE_CACHE_KEY = "__log_include_terms__"

# avior-go MongoDB instance. Override with AVIOR_GO_MONGO_URL.
DEFAULT_AVIOR_GO_MONGO_URL = "mongodb://192.168.178.75:27017"


def _resolve_config_dir() -> Path:
    """Return the active config directory, initialising from defaults if needed."""
    global _CONFIG_DIR
    if _CONFIG_DIR is not None:
        return _CONFIG_DIR

    env = os.getenv("AVIOR_DEDUP_CONFIG_DIR")
    if env:
        target = Path(env)
        target.mkdir(parents=True, exist_ok=True)
        # Seed with bundled defaults if the directory is empty
        for yaml_file in _BUNDLED_DIR.glob("*.yaml"):
            dest = target / yaml_file.name
            if not dest.exists():
                shutil.copy2(yaml_file, dest)
        _CONFIG_DIR = target
    else:
        _CONFIG_DIR = _BUNDLED_DIR

    return _CONFIG_DIR


def _load_yaml(filename: str) -> Any:
    if filename not in _cache:
        with open(_resolve_config_dir() / filename, "r", encoding="utf-8") as f:
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
    return _resolve_config_dir()


def config_files() -> dict[str, str]:
    """Return a mapping of config name to YAML filename."""
    return {
        "ignored_files": "ignored_files.yaml",
        "ignored_dirs": "ignored_dirs.yaml",
        "semantic_prefixes": "semantic_prefixes.yaml",
        "suffixes": "suffixes.yaml",
        "episode_keywords": "episode_keywords.yaml",
        "path_suggestions": "path_suggestions.yaml",
        "searchmove_paths": "searchmove_paths.yaml",
        "searchmove_templates": "searchmove_templates.yaml",
        "searchmove_ignored_dirs": "searchmove_ignored_dirs.yaml",
    }


def log_include_terms() -> list[str]:
    """Return the log_include terms from avior-go's MongoDB collection.

    The collection ``Avior.log_include`` (field ``Name``) is the single source of
    truth. The avior-go MongoDB instance defaults to
    :data:`DEFAULT_AVIOR_GO_MONGO_URL` and can be overridden with
    ``AVIOR_GO_MONGO_URL``. When the instance is unreachable the list is empty and
    the `log_include` selection priority is inert.
    """
    cached = _cache.get(_LOG_INCLUDE_CACHE_KEY)
    if cached is not None:
        return list(cached)

    terms = _log_include_from_mongo() or []
    _cache[_LOG_INCLUDE_CACHE_KEY] = list(terms)
    return terms


def invalidate_log_include() -> None:
    """Drop the cached log_include list so the next access re-reads MongoDB."""
    _cache.pop(_LOG_INCLUDE_CACHE_KEY, None)


def _log_include_from_mongo() -> list[str] | None:
    """Read avior-go's log_include collection; ``None`` when unavailable."""
    url = (os.getenv("AVIOR_GO_MONGO_URL") or "").strip() or DEFAULT_AVIOR_GO_MONGO_URL
    try:
        from pymongo import MongoClient
    except ImportError:
        return None
    client = None
    try:
        client = MongoClient(url, serverSelectionTimeoutMS=3000)
        # "Avior" is avior-go's database (consts.DB_NAME).
        docs = client["Avior"]["log_include"].find({}, {"Name": 1})
        terms = [str(doc.get("Name") or "").strip() for doc in docs]
    except Exception:
        print(f"[avior-dedup] log_include: avior-go MongoDB unreachable ({url})")
        return None
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
    return [term for term in terms if term]


def semantic_prefixes() -> list[str]:
    """Return configured semantic prefix regex patterns."""
    data = _load_yaml("semantic_prefixes.yaml")
    # Expecting a YAML list
    return list(data) if data else []
