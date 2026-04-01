from __future__ import annotations

import os

from avior_dedup import config


def match_suffix(name: str) -> tuple[str, str]:
    """Return (stem, matched_suffix) for a filename.

    Tries each candidate suffix longest-first. If none match, falls back to os.path.splitext.
    """
    lower = name.lower()
    for suf in config.candidate_suffixes():
        if lower.endswith(suf.lower()):
            return name[:-len(suf)], suf
    stem, ext = os.path.splitext(name)
    return stem, ext
