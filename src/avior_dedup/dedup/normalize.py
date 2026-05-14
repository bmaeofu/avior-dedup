from __future__ import annotations

import os
import re
import unicodedata

from avior_dedup import config


def normalize_film_name(
    name: str,
    semantic_prefixes: list[str],
    remove_episode_nos: bool,
    remove_spaces: bool = False,
    remove_non_episode_parens: bool = False,
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

    # Remove or normalize episode parentheses like (1), (2_3) or (S01_E05)
    if apply_regex:
        # Recognize simple numbers with optional separator (1_5, 1-5, 1 5, 01_05)
        # and season/episode forms like S01E05, S01_E05, S01 E05
        episode_re = re.compile(r"\(\s*([sS]?\d{1,2}(?:[ _\-]?[eE]?\d{1,2}|[ _\-]\d{1,2})?)\s*\)(?=.*\S)")

        def _parse_season_episode(token: str):
            t = token.strip()
            # SxxEyy or Sxx_Eyy or Sxx Eyy or s1e5 etc.
            m = re.fullmatch(r"([sS])(\d{1,2})[ _\-]?[eE]?(\d{1,2})", t)
            if m:
                season = int(m.group(2))
                episode = int(m.group(3))
                return season, episode
            # numeric pair like 1_5, 01_05, 1-5, 1 5
            m2 = re.fullmatch(r"(\d{1,2})[ _\-](\d{1,2})", t)
            if m2:
                season = int(m2.group(1))
                episode = int(m2.group(2))
                return season, episode
            # single number - treat as episode only (no season)
            m3 = re.fullmatch(r"(\d{1,3})", t)
            if m3:
                # indicate episode-only by returning (None, episode)
                return None, int(m3.group(1))
            return None

        def _ep_repl(m: re.Match) -> str:
            # For matched episode-like parentheses, remove them when applying regex
            return ""

        stem = episode_re.sub(_ep_repl, stem)

    base = stem

    # Optionally remove parenthetical expressions that are NOT episode numbers
    if remove_non_episode_parens:
        def _is_episode_token(tok: str) -> bool:
            tok = tok.strip()
            # matches: numeric-only tokens (years, single numbers) and numeric pairs like 1_5, 01-05, 1 5
            if re.fullmatch(r"\d+(?:[ _\-]\d+)?", tok):
                return True
            # matches: S01E05, S01_E05, S01 E05, s1e5, s01-e05
            if re.fullmatch(r"[sS]\d{1,2}[ _-]?[eE]?\d{1,2}", tok):
                return True
            return False

        def _paren_repl(m: re.Match) -> str:
            inner = m.group(1)
            return m.group(0) if _is_episode_token(inner) else ""

        base = re.sub(r"\(([^)]*)\)", _paren_repl, base)

    # Normalize punctuation and whitespace
    base = re.sub(r"[^\w\s]", " ", base)
    base = re.sub(r"\s+", " ", base).strip()

    # Optional: produce a space-insensitive form
    nospace = re.sub(r"\s+", "", base)
    if remove_spaces:
        base = nospace

    # Re-attach suffix
    if matched_suffix:
        base = f"{base}{matched_suffix}".strip()
    elif ext:
        base = f"{base}{ext}".strip()

    return base
