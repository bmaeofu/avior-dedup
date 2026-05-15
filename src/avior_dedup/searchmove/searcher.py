"""Content matching logic for text and XML files.

Functions return ``SearchMatch`` on success, ``None`` on no match.
Side-effect-free — callers decide what to do with matches.

Supports both content-based terms (rating:, genre:, etc.) and metadata terms:
  - sibling:.nfo:exists|!exists — check if a file with same stem and .nfo exists
  - fileext:.mkv — check file extension (useful for binary files)
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from functools import lru_cache

from avior_dedup.searchmove.models import RELATED_SUFFIXES, STRIP_EXTENSIONS, SearchMatch
from avior_dedup.searchmove.parser import parse_condition

# reuse log-parsing helpers from dedup scanner
from avior_dedup.dedup.scanner import count_errors, _truncate_log  # noqa: E402
from avior_dedup.dedup.io_utils import read_text  # noqa: E402


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

_KNOWN_SUFFIXES_LOWER_SORTED: tuple[str, ...] = tuple(
    sorted((s.lower() for s in RELATED_SUFFIXES), key=len, reverse=True)
)

_REPEATED_KNOWN_EXTENSIONS = frozenset(e.lower() for e in STRIP_EXTENSIONS)


@lru_cache(maxsize=4096)
def _directory_entries_lower(directory: str) -> frozenset[str]:
    """Return case-normalized directory entries for fast sibling lookups."""
    return frozenset(entry.lower() for entry in os.listdir(directory))

def _strip_to_stem(filename: str) -> str:
    """Extract base stem from a filename, stripping known suffixes.
    
    Removes compound suffixes (e.g. .mkv.INFO.log), then repeatedly strips
    known extensions until only the base name remains.
    """
    lower = filename.lower()
    
    stem = filename
    for suffix in _KNOWN_SUFFIXES_LOWER_SORTED:
        if lower.endswith(suffix):
            stem = filename[:-len(suffix)]
            break
    else:
        stem = os.path.splitext(filename)[0]
    
    # Strip repeated known extensions
    while True:
        ext = os.path.splitext(stem)[1].lower()
        if ext in _REPEATED_KNOWN_EXTENSIONS:
            stem = os.path.splitext(stem)[0]
        else:
            break
    
    return stem


def _has_sibling(path: str, suffix: str) -> bool:
    """Check if a file with same stem and given suffix exists in same directory.
    
    Case-insensitive match for robustness on SMB/Windows.
    """
    directory = os.path.dirname(path) or "."
    filename = os.path.basename(path)
    stem = _strip_to_stem(filename)
    candidate = os.path.join(directory, stem + suffix)
    wanted_name = stem.lower() + suffix.lower()

    # Fast path: direct lookup is much cheaper than listing large SMB dirs.
    if os.path.exists(candidate):
        return True

    # On Windows/SMB, the lookup above is already case-insensitive.
    if os.name == "nt":
        return False
    
    try:
        entries = _directory_entries_lower(directory)
        return wanted_name in entries
    except OSError:
        return False


def _match_metadata(path: str, term: str) -> str | None:
    """Match metadata terms (fileext, sibling) without reading file contents.
    
    Returns matched value string or None.
    Metadata terms: fileext:.mkv, sibling:.nfo:exists, sibling:.nfo:!exists
    """
    term_lower = term.lower()
    
    # fileext:.mkv
    if term_lower.startswith("fileext:"):
        requested_ext = term[8:].strip()  # After "fileext:"
        _, file_ext = os.path.splitext(path)
        if file_ext.lower() == requested_ext.lower():
            return file_ext
        return None
    
    # sibling:.nfo:exists or sibling:.nfo:!exists
    if term_lower.startswith("sibling:"):
        try:
            _, rest = term.split(":", 1)
            suffix, op = rest.rsplit(":", 1)
            suffix = suffix.strip()
            op = op.strip().lower()
        except ValueError:
            return None
        
        if not suffix.startswith("."):
            suffix = "." + suffix
        
        has_sibling = _has_sibling(path, suffix)
        
        if op == "exists":
            return "exists" if has_sibling else None
        elif op == "!exists":
            return "!exists" if not has_sibling else None

    # errors:<cond> -> parse numeric condition against encoding error count in associated .log
    if term_lower.startswith("errors:"):
        _, cond = term.split(":", 1)
        cond = cond.strip()

        # existence checks: errors:exists or errors:!exists
        if cond.lower() in ("exists", "!exists"):
            directory = os.path.dirname(path) or "."
            filename = os.path.basename(path)
            stem = _strip_to_stem(filename)
            main_log = os.path.join(directory, stem + ".log")
            alt_log = os.path.join(directory, stem + ".mkv.log")
            if cond.lower() == "exists":
                return "exists" if os.path.exists(main_log) or os.path.exists(alt_log) else None
            else:
                return "!exists" if not (os.path.exists(main_log) or os.path.exists(alt_log)) else None

        # numeric condition: parse predicate
        pred = parse_condition(cond)
        if pred is None:
            return None

        # determine stem and candidate log files; prefer .log then .mkv.log
        directory = os.path.dirname(path) or "."
        filename = os.path.basename(path)
        stem = _strip_to_stem(filename)
        candidates = [os.path.join(directory, stem + ".log"), os.path.join(directory, stem + ".mkv.log")]

        for c in candidates:
            if os.path.exists(c):
                content = read_text(c)
                if content is None:
                    continue
                content = _truncate_log(content)
                lines = content.splitlines() if content is not None else []
                ec = count_errors(lines)
                if pred(ec):
                    return str(ec)
                return None

        # no log found -> no match (use errors:!exists explicitly to find missing logs)
        return None
    
    return None


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
    file contents, or as a metadata term (fileext, sibling) if applicable.
    """
    contents_cache: str | None = None
    content_read_failed = False

    def _match_val(term: str) -> str | None:
        nonlocal contents_cache, content_read_failed
        term = term.strip()
        if not term:
            return None
        
        # Check if it's a metadata term (fileext, sibling, errors)
        if term.lower().startswith(("fileext:", "sibling:", "errors:")):
            return _match_metadata(path, term)
        
        # Fall back to content-based matching. Read file only once per path.
        if contents_cache is None and not content_read_failed:
            try:
                with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
                    contents_cache = f.read()
            except IOError:
                content_read_failed = True
                return None

        if contents_cache is None:
            return None
        
        pattern = re.escape(term)
        m = re.search(pattern, contents_cache, flags=re.IGNORECASE)
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
    """Search an XML/NFO file for matching tag:value expressions or metadata terms."""
    parsed_root: ET.Element | None = None
    selected_rating: float | None = None
    parse_attempted = False
    parse_failed = False

    def _xml_match(search_string: str) -> str | None:
        nonlocal parsed_root, selected_rating, parse_attempted, parse_failed
        search_string = search_string.strip()
        
        # Check if it's a metadata term (fileext, sibling, errors)
        if search_string.lower().startswith(("fileext:", "sibling:", "errors:")):
            return _match_metadata(path, search_string)
        
        # Fall back to XML content matching. Parse XML only once per path.
        if not parse_attempted:
            parse_attempted = True
            try:
                tree = ET.parse(path)  # noqa: S314
                parsed_root = tree.getroot()
                selected_rating = _select_rating(parsed_root)
            except (ET.ParseError, IOError):
                parse_failed = True
                return None

        if parse_failed or parsed_root is None:
            return None
        
        try:
            tag, attrib = search_string.split(":", 1)
        except ValueError:
            return None
        return _xml_tag_match(parsed_root, tag.strip().lower(), attrib.strip().lower(), selected_rating)

    result = match_and_or(search_groups, _xml_match)
    if result is None:
        return None

    terms, values = result
    return SearchMatch(
        file_path=path,
        matched_expression=" & ".join(terms),
        found_values=" | ".join(values),
    )
