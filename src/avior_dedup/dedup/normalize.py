from __future__ import annotations

import os
import re
import unicodedata

from avior_dedup import config


_TRAILING_YEAR_RE = re.compile(r"(?:\((\d{4})\)|(\d{4}))\s*$")


def _trailing_year_value(stem: str) -> int | None:
    """Return the 4-digit number that ends *stem* (in parentheses or bare)."""
    m = _TRAILING_YEAR_RE.search(stem)
    if not m:
        return None
    return int(m.group(1) or m.group(2))


def _trailing_number_is_year(
    stem: str,
    txt_available: bool,
    txt_episode: int | None,
    txt_year: int | None,
) -> bool:
    """Decide whether the trailing 4-digit number of *stem* denotes a year.

    A trailing 4-digit number is only stripped as an episode number when the
    sibling .txt proves it (``Episode == number`` and ``year != number``).
    Anything unproven — no number at all, no .txt, or differing data — counts
    as a year, so episode numbers are not stripped.
    """
    value = _trailing_year_value(stem)
    if value is None:
        return False
    if not txt_available:
        return True
    if txt_year is not None and txt_year == value:
        return True
    if txt_episode is not None and txt_episode == value:
        return False
    return True


def normalize_film_name(
    name: str,
    semantic_prefixes: list[str],
    remove_episode_nos: bool,
    remove_spaces: bool = False,
    remove_non_episode_parens: bool = False,
    replace_underscores: bool = False,
    ignore_keep_keywords: bool = False,
    txt_available: bool = False,
    txt_episode: int | None = None,
    txt_year: int | None = None,
) -> str:
    """Normalize a film filename for semantic duplicate detection."""
    # Normalize Unicode representation first and use casefold for robust case-insensitive matching.
    base = unicodedata.normalize("NFKC", name).casefold().strip()
    # Optionally replace underscores with spaces before further normalization.
    # Do NOT replace underscores that appear inside episode-like parentheses
    # such as "(2_2)" or "(S01_E05)" which represent episode tokens.
    if replace_underscores:
        # Pattern: either an episode-like parenthetical (capture group 1)
        # or a run of underscores. We preserve the parenthetical unchanged
        # and replace underscores with a single space.
        pat = re.compile(r"(\(\s*[sS]?\d{1,2}(?:[ _\-]?[eE]?\d{1,2}|[ _\-]\d{1,2})?\s*\))|_+", flags=re.IGNORECASE)

        def _repl(m: re.Match) -> str:
            if m.group(1):
                return m.group(1)
            return " "

        base = pat.sub(_repl, base)
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
        # Do not fallback to os.path.splitext here. We only want to strip
        # suffixes that are declared in the candidate suffix list; names
        # without a known candidate suffix should be treated as-is.
        stem = base
        ext = ''

    # Strip semantic prefixes
    for pattern in semantic_prefixes:
        stem = re.sub(pattern, "", stem, flags=re.IGNORECASE)

    # Broadcasters also write the episode as "(Staffel 4, Folge 6)". Normalise it
    # to the SxxEyy form the rest of the pipeline already understands, so the
    # marker counts as an episode number instead of being dropped as noise.
    stem = re.sub(
        r"\(\s*staffel\s*(\d{1,3})\s*,?\s*folge\s*(\d{1,3})\s*\)",
        lambda m: f"(s{int(m.group(1)):02d}e{int(m.group(2)):02d})",
        stem,
        flags=re.IGNORECASE,
    )

    # Split into first block / rest on " - "
    parts = stem.split(" - ")
    rest = parts[-1].strip() if len(parts) > 1 else ""

    # Determine whether to apply episode number removal
    apply_regex = remove_episode_nos

    # The keyword lists exist to *prevent* stripping for series whose episode
    # titles are not unique. When the data-driven episode check is enabled they
    # are bypassed, so stripping applies uniformly and the .txt metadata decides
    # which groups are genuine duplicates.
    if apply_regex and not ignore_keep_keywords:
        for kw in config.series_keep_episode_nos():
            if kw in base:
                apply_regex = False
                break
    if apply_regex and not ignore_keep_keywords:
        # A trailing 4-digit number counts as a year (and blocks stripping)
        # unless the sibling .txt proves it is the episode number.
        if _trailing_number_is_year(stem, txt_available, txt_episode, txt_year):
            apply_regex = False
    if apply_regex and rest and not ignore_keep_keywords:
        for kw in config.episode_keep_keywords():
            if kw in rest:
                apply_regex = False
                break

    if apply_regex and len(parts) > 2 and not ignore_keep_keywords:
        for kw in config.episode_keep_keywords_years():
            if kw in parts[-1]:
                apply_regex = False
                break

    # Snapshot before stripping: the non-episode cleanup needs to know which
    # episode identities the name carried, even the ones stripped below.
    pre_strip_stem = stem

    # Remove or normalize episode parentheses like (1), (2_3) or (S01_E05)
    if apply_regex:
        # Recognize simple numbers with optional separator (1_5, 1-5, 1 5, 01_05)
        # and season/episode forms like S01E05, S01_E05, S01 E05
        # The same token grammar the non-episode cleanup uses: 1_5, 01-05,
        # 27 - 28, 19+20, 17 und 18, 10-11_13, 7+8_18 and S01E05. Four plain
        # digits stay out of it so a release year is never stripped.
        _EP_TOKEN = r"(?:\d{1,3}(?:\s*(?:[+\-/_]|und|&)\s*\d{1,4})*|[sS]\d{1,2}\s*[ _\-]?\s*[eE]?\d{1,2})"
        episode_re = re.compile(r"\(\s*(" + _EP_TOKEN + r")\s*\)(?=.*\S)")

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
        def _is_basic_episode_token(tok: str) -> bool:
            tok = tok.strip()
            # A plausible release year (e.g. (2020)) is not an episode token —
            # so remove_non_episode_parens removes it. A 4-digit number outside
            # that range is an episode number: long-running series reach
            # (1045) and must keep their marker.
            if re.fullmatch(r"(?:19|20|21)\d{2}", tok):
                return False
            # matches: numeric-only tokens and every episode-group notation the
            # broadcasters use: 1_5, 01-05, 1 5, 27 - 28, 19+20, 17 und 18,
            # 10-11_13, 7+8_18. All of them mark one or more episodes and must
            # survive the non-episode cleanup.
            if re.fullmatch(r"\d{1,4}(?:\s*(?:[+\-/_]|und|&)\s*\d{1,4})*", tok, re.IGNORECASE):
                return True
            # matches: S01E05, S01_E05, S01 E05, s1e5, s01-e05
            if re.fullmatch(r"[sS]\d{1,2}\s*[ _-]?\s*[eE]?\d{1,2}", tok):
                return True
            # matches: roman numerals marking a part, e.g. (I), (II), (III), (IV)
            # - the broadcaster's way of splitting a double episode.
            if re.fullmatch(r"(?i:i{1,4}|iv|vi{0,4}|ix|x{1,4})", tok):
                return True
            return False

        # "Teil 2" and "Folge 6" are two different things:
        #   * "Teil"/"Part" mark a *part* of a work. They never repeat an
        #     episode number, so they are always an identity of their own -
        #     otherwise Teil 1 and Teil 2 collapse.
        #   * "Folge"/"Episode"/"Kapitel" restate the episode number. Next to a
        #     real marker like "(6_8)" they are redundant and go with the noise.
        _part_re = re.compile(r"(?:teil|part)\s*\.?\s*\d{1,3}", re.IGNORECASE)
        _repeat_re = re.compile(r"(?:folge|episode|kapitel)\s*\.?\s*\d{1,3}", re.IGNORECASE)
        _inner_tokens = [
            m.group(1).strip() for m in re.finditer(r"\(([^)]*)\)", pre_strip_stem)
        ]
        _other_episode_identity = any(
            t and not _part_re.fullmatch(t) and not _repeat_re.fullmatch(t) and _is_basic_episode_token(t)
            for t in _inner_tokens
        )
        # Only the first episode identity counts. A second one is the same
        # episode written twice, e.g.
        # "(4_5) - … bekam (Staffel 1, Folge 4)"; it goes with the noise so the
        # name still meets its counterpart without the repetition.
        _identities = [t for t in _inner_tokens if t and _is_basic_episode_token(t)]
        _redundant_tokens = set(_identities[1:])

        def _is_episode_token(tok: str) -> bool:
            tok = tok.strip()
            if tok in _redundant_tokens:
                return False
            if _part_re.fullmatch(tok):
                return True          # a part is never a repetition
            if _repeat_re.fullmatch(tok):
                return not _other_episode_identity
            return _is_basic_episode_token(tok)

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
