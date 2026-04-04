"""Content matching logic for text and XML files.

Functions return ``SearchMatch`` on success, ``None`` on no match.
Side-effect-free — callers decide what to do with matches.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Callable

from avior_dedup.searchmove.models import SearchMatch
from avior_dedup.searchmove.parser import parse_condition


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def match_and_or(
    groups: list[list[list[str]]],
    match_func: Callable[[str], str | None],
) -> tuple[list[str], list[str]] | None:
    """Evaluate OR-of-AND groups using *match_func*.

    Returns ``(matched_terms, found_values)`` for the first matching
    AND-group, or ``None`` if nothing matches.
    """
    for group in groups:  # OR across groups
        for and_group in group:  # OR within group
            values = [match_func(term) for term in and_group]
            if all(v is not None for v in values):
                return and_group, [v for v in values if v is not None]
    return None


# ---------------------------------------------------------------------------
# Plain-text file search
# ---------------------------------------------------------------------------

def search_text_file(
    path: str,
    search_groups: list[list[list[str]]],
) -> SearchMatch | None:
    """Search a plain-text file for matching terms.

    Each term is matched as a case-insensitive regex against the full
    file contents.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
            contents = f.read()
    except IOError:
        return None

    def _match_val(term: str) -> str | None:
        term = term.strip()
        if not term:
            return None
        pattern = re.escape(term)
        m = re.search(pattern, contents, flags=re.IGNORECASE)
        return m.group(0) if m else None

    result = match_and_or(search_groups, _match_val)
    if result is None:
        return None

    terms, values = result
    return SearchMatch(
        file_path=path,
        matched_expression=" & ".join(terms),
        found_values=" | ".join(values),
    )


# ---------------------------------------------------------------------------
# XML (.nfo) file search
# ---------------------------------------------------------------------------

def _select_rating(root: ET.Element) -> float | None:
    """Pick the best rating from an NFO XML tree.

    Priority:
    1. IMDB rating if it has >= 10 votes
    2. Rating with the most votes
    3. ``<userrating>`` element as fallback
    """
    ratings: list[dict] = []
    for rating_elem in root.findall(".//ratings/rating"):
        name = (rating_elem.get("name") or "").strip().lower()
        value_text = rating_elem.findtext("value") or ""
        votes_text = rating_elem.findtext("votes") or ""
        try:
            value = float(value_text) if value_text.strip() else None
        except ValueError:
            value = None
        try:
            votes = int(votes_text) if votes_text.strip() else 0
        except ValueError:
            votes = 0
        if value is not None:
            ratings.append({"name": name, "value": value, "votes": votes})

    selected: float | None = None
    if ratings:
        imdb = next((r for r in ratings if r["name"] == "imdb"), None)
        if imdb and imdb["votes"] >= 10:
            selected = imdb["value"]
        else:
            ratings_sorted = sorted(ratings, key=lambda r: r["votes"], reverse=True)
            selected = ratings_sorted[0]["value"]

    if selected is None:
        userrating_text = root.findtext(".//userrating") or ""
        try:
            selected = float(userrating_text) if userrating_text.strip() else None
        except ValueError:
            selected = None

    return selected


def _xml_tag_match(
    root: ET.Element,
    tag: str,
    attrib: str,
    selected_rating: float | None,
) -> str | None:
    """Match a single ``tag:attrib`` expression against an XML tree.

    Returns the matched value as a string, or ``None`` if no match.
    """
    # Rating has its own dedicated selection logic
    if tag == "rating":
        pred = parse_condition(attrib)
        if pred and selected_rating is not None and pred(selected_rating):
            return str(selected_rating)
        return None

    tag_nodes = root.findall(tag)

    # Numeric comparison for generic tags (e.g. plot_sim_score:>0.9)
    pred = parse_condition(attrib)
    if pred:
        for node in tag_nodes:
            txt = (node.text or "").strip()
            if not txt:
                continue
            try:
                value = float(txt)
            except ValueError:
                continue
            if pred(value):
                return txt
        return None

    # Existence checks
    if attrib == "exists":
        return "exists" if tag_nodes else None
    if attrib == "!exists":
        return "!exists" if not tag_nodes else None

    # Wildcard matching
    has_wildcard_start = attrib.startswith("*")
    has_wildcard_end = attrib.endswith("*")

    if has_wildcard_start or has_wildcard_end:
        search_term = attrib.strip("*")
        for node in tag_nodes:
            txt = (node.text or "").strip()
            txt_lower = txt.lower()
            if has_wildcard_start and has_wildcard_end:
                if search_term in txt_lower:
                    return txt
            elif has_wildcard_start:
                if txt_lower.endswith(search_term):
                    return txt
            elif has_wildcard_end:
                if txt_lower.startswith(search_term):
                    return txt
    else:
        # Exact match (case-insensitive)
        for node in tag_nodes:
            txt = (node.text or "").strip()
            if txt.lower() == attrib:
                return txt

    return None


def search_xml_file(
    path: str,
    search_groups: list[list[list[str]]],
) -> SearchMatch | None:
    """Search an XML/NFO file for matching tag:value expressions."""
    try:
        tree = ET.parse(path)  # noqa: S314
        root = tree.getroot()
    except (ET.ParseError, IOError) as e:
        print(f"XML parse error for {path}: {e}")
        return None

    selected_rating = _select_rating(root)

    def _xml_match(search_string: str) -> str | None:
        try:
            tag, attrib = search_string.strip().split(":", 1)
        except ValueError:
            return None
        return _xml_tag_match(root, tag.strip().lower(), attrib.strip().lower(), selected_rating)

    result = match_and_or(search_groups, _xml_match)
    if result is None:
        return None

    terms, values = result
    return SearchMatch(
        file_path=path,
        matched_expression=" & ".join(terms),
        found_values=" | ".join(values),
    )
