from __future__ import annotations

import os
import re
import unicodedata

from avior_dedup import config


def normalize_film_name(
    name: str,
    semantic_prefixes: list[str],
    remove_episode_nos: bool,
) -> str:
    """Normalize a film filename for semantic duplicate detection."""
    # Normalize Unicode representation first and use casefold for robust case-insensitive matching.
    base = unicodedata.normalize("NFKC", name).casefold().strip()
    candidate_suffixes = config.candidate_suffixes()

    matched_suffix = ""
    ext = ""
    stem = base

    # Strip known suffix
    for suf in candidate_suffixes:
        if base.endswith(suf.lower()):
            matched_suffix = suf
            stem = base[:-len(suf)]
            break
    else:
        stem, ext = os.path.splitext(base)

    # Strip semantic prefixes
    for pattern in semantic_prefixes:
        stem = re.sub(pattern, "", stem, flags=re.IGNORECASE)

    # Split into first block / rest on " - "
    parts = stem.split(" - ")
    rest = parts[-1].strip() if len(parts) > 1 else ""

    # Determine whether to apply episode number removal
    apply_regex = remove_episode_nos

    if apply_regex:
        for kw in config.series_keep_episode_nos():
            if kw in base:
                apply_regex = False
                break

    if apply_regex and rest:
        for kw in config.episode_keep_keywords():
            if kw in rest:
                apply_regex = False
                break

    if apply_regex and len(parts) > 2:
        for kw in config.episode_keep_keywords_years():
            if kw in parts[-1]:
                apply_regex = False
                break

    # Remove numeric parentheses like (1), (2_3) — but only if more text follows
    if apply_regex:
        stem = re.sub(r"\(\d+(_\d+)?\)(?=.*\S)", "", stem)

    base = stem

    # Normalize punctuation and whitespace
    base = re.sub(r"[^\w\s]", " ", base)
    base = re.sub(r"\s+", " ", base).strip()

    # Re-attach suffix
    if matched_suffix:
        base = f"{base}{matched_suffix}".strip()
    elif ext:
        base = f"{base}{ext}".strip()

    return base
