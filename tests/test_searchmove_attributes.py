"""Tests for XML attribute matching in search expressions (``path@selector:cond``).

Covers the ``@`` syntax added for NFO attribute matching:
  - exact / wildcard / exists / !exists / numeric conditions
  - attribute vs. child-element selector resolution
  - recursive search for bare tag paths, path-based search for nested paths
  - malformed terms never raise and never match
"""

from __future__ import annotations

from pathlib import Path

import pytest

from avior_dedup.searchmove.parser import parse_search_expression
from avior_dedup.searchmove.searcher import search_text_file, search_xml_file

_NFO = """<?xml version='1.0' encoding='utf-8'?>
<movie>
    <title>Wild Christmas</title>
    <originaltitle>Reindeer Games</originaltitle>
    <ratings>
        <rating name="themoviedb" max="10">
            <value>5.705000</value>
            <votes>719</votes>
        </rating>
        <rating name="imdb" max="10" default="true">
            <value>5.800000</value>
            <votes>43965</votes>
        </rating>
    </ratings>
    <userrating>0</userrating>
    <top250>0</top250>
</movie>
"""


@pytest.fixture(scope="module")
def nfo_path(tmp_path_factory) -> str:
    """Fixture NFO with nested <ratings><rating name=...> elements."""
    p = tmp_path_factory.mktemp("attr") / "Wild Christmas.nfo"
    p.write_text(_NFO, encoding="utf-8")
    return str(p)


def _match(nfo_path: str, expr: str):
    return search_xml_file(nfo_path, parse_search_expression([expr]))


def test_exact_attribute_match_recursive(nfo_path):
    """Bare tag paths search the whole tree (rating is nested under ratings)."""
    m = _match(nfo_path, "rating@name:themoviedb")
    assert m is not None
    assert "themoviedb" in m.found_values


def test_exact_attribute_match_nested_path(nfo_path):
    m = _match(nfo_path, "ratings/rating@name:themoviedb")
    assert m is not None


def test_exact_attribute_match_explicit_recursive_path(nfo_path):
    m = _match(nfo_path, ".//rating@name:themoviedb")
    assert m is not None


def test_attribute_no_match_for_wrong_value(nfo_path):
    assert _match(nfo_path, "rating@name:tmdb") is None


def test_attribute_wildcard(nfo_path):
    m = _match(nfo_path, "rating@name:*imdb*")
    assert m is not None


def test_attribute_exists_bare(nfo_path):
    m = _match(nfo_path, "rating@name")
    assert m is not None
    assert "exists" in m.found_values


def test_attribute_exists_explicit(nfo_path):
    m = _match(nfo_path, "rating@name:exists")
    assert m is not None


def test_attribute_absent_existence_no_match(nfo_path):
    """Both ratings have <votes> children, so !exists cannot match."""
    assert _match(nfo_path, "rating@votes:!exists") is None


def test_attribute_absent_existence_match(nfo_path):
    """None of the ratings has a 'lang' attribute."""
    m = _match(nfo_path, "rating@lang:!exists")
    assert m is not None
    assert "!exists" in m.found_values


def test_numeric_condition_on_attribute(nfo_path):
    m = _match(nfo_path, "rating@max:10")
    assert m is not None


def test_numeric_condition_on_child_scoped(nfo_path):
    m = _match(nfo_path, "ratings/rating@name:themoviedb@value:>5.4")
    assert m is not None
    assert "5.705000" in m.found_values


def test_numeric_condition_on_child_scoped_negative(nfo_path):
    assert _match(nfo_path, "ratings/rating@name:themoviedb@value:>6") is None


def test_multiple_specs_same_element(nfo_path):
    m = _match(nfo_path, "ratings/rating@name:themoviedb@max:10")
    assert m is not None


def test_multiple_specs_cross_element_no_match(nfo_path):
    """name:themoviedb and default:true live on DIFFERENT rating elements."""
    assert _match(nfo_path, "ratings/rating@name:themoviedb@default:true") is None


def test_case_insensitive_selector_and_value(nfo_path):
    m = _match(nfo_path, "rating@Name:THEMOVIEDB")
    assert m is not None


def test_combine_with_existing_syntax(nfo_path):
    m = _match(nfo_path, "rating@name:themoviedb&rating:>0")
    assert m is not None


def test_empty_cond_is_existence(nfo_path):
    m = _match(nfo_path, "rating@name:")
    assert m is not None


@pytest.mark.parametrize(
    "expr",
    [
        "@name:themoviedb",          # empty path
        "rating@",                   # empty spec
        "rating@:themoviedb",        # empty selector
        "rating@name:themoviedb@",   # trailing @ -> empty spec
        # The malformed XPath cases below pin every arm of the findall
        # guard in _xml_attr_match (SyntaxError, TypeError, KeyError).
        "rating[0@name:themoviedb",  # TypeError arm (unbalanced [)
        "rating]@name:themoviedb",   # KeyError arm (unbalanced ])
        "rating[]@name:themoviedb",  # SyntaxError arm (empty predicate)
        "rating[0@name:themoviedb@default:true",  # TypeError arm, multi-spec
    ],
)
def test_malformed_terms_no_crash_no_match(nfo_path, expr):
    m = _match(nfo_path, expr)
    assert m is None


def test_legacy_tag_value_with_at_in_value(tmp_path: Path):
    """@ inside a tag:value term's VALUE must not route to attribute matching."""
    p = tmp_path / "legacy at.nfo"
    p.write_text(
        "<?xml version='1.0' encoding='utf-8'?>\n"
        "<movie><title>user@host</title></movie>\n",
        encoding="utf-8",
    )
    m = search_xml_file(str(p), parse_search_expression(["title:user@host"]))
    assert m is not None
    assert "user@host" in m.found_values


def test_text_search_treats_at_literally(tmp_path: Path):
    """Plain-text search must NOT route @ terms through XML attribute logic."""
    txt = tmp_path / "notes.txt"
    txt.write_text("contact: dev@example.com\n", encoding="utf-8")
    m = search_text_file(str(txt), parse_search_expression(["dev@example.com"]))
    assert m is not None


def test_negated_value_document_level(nfo_path):
    """thumb@aspect:!poster matches only when NO thumb has aspect=poster."""
    from pathlib import Path
    import tempfile
    # Build a temp NFO with only a fanart thumb -> should match (no poster)
    with tempfile.TemporaryDirectory() as tmp:
        nfo = Path(tmp) / "x.nfo"
        nfo.write_text(
            "<movie><thumb aspect='fanart'>https://f.jpg</thumb></movie>",
            encoding="utf-8",
        )
        m = search_xml_file(str(nfo), parse_search_expression(["thumb@aspect:!poster"]))
        assert m is not None

    with tempfile.TemporaryDirectory() as tmp:
        nfo = Path(tmp) / "y.nfo"
        nfo.write_text(
            "<movie><thumb aspect='poster'>https://p.jpg</thumb></movie>",
            encoding="utf-8",
        )
        m = search_xml_file(str(nfo), parse_search_expression(["thumb@aspect:!poster"]))
        assert m is None

    with tempfile.TemporaryDirectory() as tmp:
        # No thumb at all -> poster absent -> matches
        nfo = Path(tmp) / "z.nfo"
        nfo.write_text("<movie><title>A</title></movie>", encoding="utf-8")
        m = search_xml_file(str(nfo), parse_search_expression(["thumb@aspect:!poster"]))
        assert m is not None
