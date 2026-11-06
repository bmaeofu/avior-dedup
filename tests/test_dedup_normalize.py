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


def test_trailing_year_in_parentheses_or_bare():
    from avior_dedup.dedup.normalize import _trailing_year_value
    assert _trailing_year_value("titel (2019)") == 2019
    assert _trailing_year_value("titel 2019") == 2019
    assert _trailing_year_value("serie (3) - episodentitel") is None


def test_parenthesised_year_blocks_stripping():
    out = normalize_film_name(
        "Serie (3) - Episodentitel (2019)", [], True,
        txt_available=True, txt_episode=3, txt_year=2019,
    )
    # The episode number 3 must survive: (2019) is the year.
    assert "serie 3" in out


def test_spaced_episode_range_is_an_episode_token():
    """(27 - 28) marks a double episode and must survive the non-episode cleanup."""
    for stem in ["Babylon Berlin (27 - 28)", "Babylon Berlin (4 - 6)", "Babylon Berlin (20 - 22)"]:
        kept = normalize_film_name(stem, [], False, remove_non_episode_parens=True)
        assert kept == normalize_film_name(stem, [], False), stem
        assert "berlin" in kept and kept.split()[-1].isdigit(), kept


def test_non_episode_parentheses_are_still_removed():
    assert "omu" not in normalize_film_name(
        "Babylon Berlin (OmU)", [], False, remove_non_episode_parens=True
    )
    assert "2020" not in normalize_film_name(
        "Babylon Berlin (2020)", [], False, remove_non_episode_parens=True
    )


def test_roman_numeral_parts_are_episode_tokens():
    """(I)/(II) split a double episode, so the non-episode cleanup must keep them."""
    stems = [
        "Candice Renoir - Was Frau will (I)",
        "Candice Renoir - Was Frau will (II)",
        "Candice Renoir - Was Frau will (IV)",
    ]
    keys = [normalize_film_name(stem, [], False, remove_non_episode_parens=True) for stem in stems]

    assert len(set(keys)) == 3
    assert keys[0].endswith(" i") and keys[1].endswith(" ii") and keys[2].endswith(" iv")
    # A bare name without a part marker stays a separate key, as before.
    assert normalize_film_name(
        "Candice Renoir - Was Frau will", [], False, remove_non_episode_parens=True
    ) not in keys


def test_long_running_episode_numbers_are_not_treated_as_years():
    """(1045) is an episode of a long-running series, not a release year."""
    kept = normalize_film_name(
        "Sturm der Liebe (1045)", [], False, remove_non_episode_parens=True
    )
    assert kept == "sturm der liebe 1045"

    # A plausible release year is still removed.
    assert normalize_film_name(
        "Ein Film (2020)", [], False, remove_non_episode_parens=True
    ) == "ein film"


def test_episode_group_notations_survive_the_cleanup():
    """(19+20), (17 und 18), (21 + 22), (10-11_13) all mark episodes."""
    for token in ["(19+20)", "(17 und 18)", "(21 + 22)", "(10-11_13)", "(7+8_18)", "(3_6)"]:
        stem = f"Weissensee {token} - Titel"
        assert normalize_film_name(stem, [], False, remove_non_episode_parens=True) == \
            normalize_film_name(stem, [], False), token


def test_spelled_out_episode_marker_maps_to_season_episode():
    """(Staffel 4, Folge 1) is the episode marker S04E01, not noise."""
    on = normalize_film_name(
        "Weissensee - Am Ende des Tages (Staffel 4, Folge 6)", [], False,
        remove_non_episode_parens=True,
    )
    assert "s04e06" in on

    # Same treatment as the short notation: stripping removes it as an episode.
    stripped = normalize_film_name(
        "Little Britain - (Staffel 2, Folge 1) - Titel", [], True,
        remove_non_episode_parens=True,
    )
    assert stripped == normalize_film_name("Little Britain - Titel", [], True)


def test_every_episode_notation_is_stripped_when_a_title_follows():
    """The strip understands the same token grammar as the non-episode cleanup."""
    cases = [
        ("Die Märchenbraut (8-9_13) - Hänsel und Gretel", "8 9_13"),
        ("Oktoberfest 1900 (1+2_6) - Titel", "1 2_6"),
        ("Serie (17 und 18) - Titel", "17 und 18"),
        ("Serie (S01 - E05) - Titel", "s01 e05"),
    ]
    for stem, marker in cases:
        key = normalize_film_name(stem, [], True, remove_non_episode_parens=True)
        assert marker not in key, (stem, key)


def test_written_out_part_marker_is_an_episode_identity():
    """(Teil 1) and (Teil 2) are different episodes, not noise."""
    one = normalize_film_name(
        "Die Bergretter - Die Hoffnung stirbt zuletzt (Teil 1)", [], True,
        remove_non_episode_parens=True,
    )
    two = normalize_film_name(
        "Die Bergretter - Die Hoffnung stirbt zuletzt (Teil 2)", [], True,
        remove_non_episode_parens=True,
    )
    assert one != two
    assert one.endswith("teil 1") and two.endswith("teil 2")


def test_redundant_part_marker_goes_with_the_noise():
    """Next to a real episode marker, "(Folge 6)" only repeats it."""
    plain = normalize_film_name("Tokyo Vice (6_8) - Die Lieferung", [], True, remove_non_episode_parens=True)
    marked = normalize_film_name(
        "Tokyo Vice (6_8) - Die Lieferung (Folge 6)", [], True, remove_non_episode_parens=True
    )
    assert plain == marked
