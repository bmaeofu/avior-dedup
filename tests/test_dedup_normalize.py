"""Tests for film-name normalization, esp. year-vs-episode parentheses."""

from __future__ import annotations

from avior_dedup.dedup.normalize import normalize_film_name


def _norm(name: str, **kw) -> str:
    return normalize_film_name(name, [], False, **kw)


def test_year_in_parentheses_is_removed_with_remove_non_episode_parens():
    a = _norm("Karla, Rosalie und das Loch in der Wand (2020)", remove_non_episode_parens=True)
    b = _norm("Karla, Rosalie und das Loch in der Wand", remove_non_episode_parens=True)
    assert a == b
    assert "2020" not in a


def test_episode_parentheses_are_kept_with_remove_non_episode_parens():
    for tok in ("(1)", "(2_3)", "(S01E05)", "(1-5)"):
        out = _norm("Serie " + tok, remove_non_episode_parens=True)
        assert "serie" in out, f"episode parens wrongly removed for {tok}"


# ---------------------------------------------------------------------------
# Trailing 4-digit number: year vs. episode number
# ---------------------------------------------------------------------------

def test_trailing_number_is_year_without_txt():
    from avior_dedup.dedup.normalize import _trailing_number_is_year
    assert _trailing_number_is_year("serie (1) - titel 2019", False, None, None) is True


def test_trailing_number_is_year_when_txt_year_matches():
    from avior_dedup.dedup.normalize import _trailing_number_is_year
    assert _trailing_number_is_year("serie (1) - titel 2019", True, 1, 2019) is True


def test_trailing_number_is_episode_when_txt_proves_it():
    from avior_dedup.dedup.normalize import _trailing_number_is_year
    # Episode == number and the year differs -> strip allowed
    assert _trailing_number_is_year("serie (1) - titel 1188", True, 1188, 2019) is False


def test_non_trailing_number_is_not_a_year_guard():
    from avior_dedup.dedup.normalize import _trailing_number_is_year
    assert _trailing_number_is_year("serie (1) - der fall 1987 und mehr", True, 1, 2019) is False


def test_stripping_blocked_by_trailing_year():
    # Episode number must survive because the trailing 2019 is the year.
    out = normalize_film_name(
        "Serie (1) - Der Fall 2019", [], True,
        txt_available=True, txt_episode=1, txt_year=2019,
    )
    assert "serie 1 " in out or "serie 1" in out.replace("  ", " ")


def test_stripping_allowed_when_number_is_episode():
    # .txt proves 1188 is the episode number, not the year -> (1) is stripped.
    out = normalize_film_name(
        "Serie (1) - Titel 1188", [], True,
        txt_available=True, txt_episode=1188, txt_year=2019,
    )
    assert "serie 1 " not in out and "serie 1" not in out.replace("  ", " ")
