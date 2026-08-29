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
