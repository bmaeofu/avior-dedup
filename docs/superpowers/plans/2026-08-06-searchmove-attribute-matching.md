# Searchmove XML Attribute Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add XML attribute matching (`path@selector:cond[...]`) to the searchmove expression language so `.nfo`-based searches can match element attributes like `<rating name="themoviedb">` and element-scoped value conditions.

**Architecture:** Extends only the XML search path in `avior_dedup/searchmove/searcher.py`. Terms containing `@` are routed to a new `_xml_attr_match` helper; terms without `@` (including the `rating:` special case and the `&`/`|` parser) are untouched. Bare tag paths search recursively (`.//tag`), path-based expressions (`ratings/rating`) keep exact `findall` semantics. A shared `_match_value` helper replaces the duplicated comparison chain in the generic tag branch (behavior-preserving refactor).

**Tech Stack:** Python 3.12, ElementTree (`xml.etree.ElementTree`), pytest, PyYAML (config), Vue 3 (frontend placeholder only).

## Global Constraints

- Python 3.12 venv: `.venv/Scripts/python.exe` (Windows). Run tests with `.venv/Scripts/python.exe -m pytest`.
- No new dependencies. No changes to `parse_search_expression`, `parse_condition`, `_select_rating`, `search_text_file`, or `match_and_or`.
- Terms without `@` must behave exactly as before (existing tests are the gate).
- Malformed `@` terms must NEVER raise — they return no match.
- `@` is a spec separator; it must NOT appear inside a condition value (documented limitation).
- Style: 4-space indent, single quotes, docstrings in the existing file style.
- Spec: `docs/superpowers/specs/2026-08-06-searchmove-attribute-matching-design.md` (committed).

---

### Task 1: Attribute matching core (searcher.py + tests)

**Files:**
- Create: `tests/test_searchmove_attributes.py`
- Modify: `src/avior_dedup/searchmove/searcher.py` (`_xml_match` routing in `search_xml_file`, generic branch of `_xml_tag_match`, three new module functions after `_xml_tag_match`)

**Interfaces:**
- Consumes: existing `parse_condition` (unchanged), existing `ET` import.
- Produces:
  - `_match_value(text: str | None, cond: str) -> str | None` — comparison chain (numeric/wildcard/exact) on a text value.
  - `_match_attr_or_child(node: ET.Element, selector: str, cond: str) -> str | None` — one `selector:cond` spec against one element; attribute first (case-insensitive), then child element; existence on presence.
  - `_xml_attr_match(root: ET.Element, search_string: str) -> str | None` — full `path@selector:cond[...]` evaluation; returns `" | ".join(values)` or `None`.
  - `search_xml_file` routes terms containing `@` to `_xml_attr_match`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_searchmove_attributes.py`:

```python
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
    ],
)
def test_malformed_terms_no_crash_no_match(nfo_path, expr):
    m = _match(nfo_path, expr)
    assert m is None


def test_text_search_treats_at_literally(tmp_path: Path):
    """Plain-text search must NOT route @ terms through XML attribute logic."""
    txt = tmp_path / "notes.txt"
    txt.write_text("contact: dev@example.com\n", encoding="utf-8")
    m = search_text_file(str(txt), parse_search_expression(["dev@example.com"]))
    assert m is not None
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_searchmove_attributes.py -v`
Expected: FAIL/ERROR on every `@` test (currently `findall("@name")` raises `KeyError: '@'` inside `_xml_tag_match`, or assertions fail); `test_text_search_treats_at_literally` PASSES (text search is unaffected). Do not proceed until the `@` tests are red.

- [ ] **Step 3: Implement the matcher in searcher.py**

Edit `src/avior_dedup/searchmove/searcher.py`:

**(3a)** Add `@` routing in `search_xml_file._xml_match`. Replace:

```python
        if parse_failed or parsed_root is None:
            return None
        
        try:
            tag, attrib = search_string.split(":", 1)
        except ValueError:
            return None
        return _xml_tag_match(parsed_root, tag.strip().lower(), attrib.strip().lower(), selected_rating)
```

with:

```python
        if parse_failed or parsed_root is None:
            return None

        # Attribute matching: path@selector:cond[@selector:cond...]
        if "@" in search_string:
            return _xml_attr_match(parsed_root, search_string)

        try:
            tag, attrib = search_string.split(":", 1)
        except ValueError:
            return None
        return _xml_tag_match(parsed_root, tag.strip().lower(), attrib.strip().lower(), selected_rating)
```

**(3b)** Refactor the generic branch of `_xml_tag_match` to use `_match_value`. Replace everything from `tag_nodes = root.findall(tag)` to the final `return None` (keeping the `rating` special case above untouched):

```python
    tag_nodes = root.findall(tag)

    # Node-level existence checks
    if attrib == "exists":
        return "exists" if tag_nodes else None
    if attrib == "!exists":
        return "!exists" if not tag_nodes else None

    # Empty condition matches a node with empty text (e.g. "nfostatus:")
    if not attrib:
        for node in tag_nodes:
            if not (node.text or "").strip():
                return ""
        return None

    # Value comparison chain (numeric, wildcard, exact)
    for node in tag_nodes:
        matched = _match_value(node.text, attrib)
        if matched is not None:
            return matched
    return None
```

**(3c)** Add three new module-level functions directly after `_xml_tag_match` (before `search_xml_file`):

```python
def _match_value(text: str | None, cond: str) -> str | None:
    """Apply the value comparison chain (numeric, wildcard, exact) to text.

    Returns the matched value or ``None``. Existence of the *container*
    (attribute present, child element present, tag node set) is decided by
    the callers; this only compares text content.
    """
    txt = (text or "").strip()

    # Numeric comparison (e.g. >5.4, 4-6, ==7)
    pred = parse_condition(cond)
    if pred:
        if not txt:
            return None
        try:
            value = float(txt)
        except ValueError:
            return None
        return txt if pred(value) else None

    # Wildcard matching
    has_wildcard_start = cond.startswith("*")
    has_wildcard_end = cond.endswith("*")
    if has_wildcard_start or has_wildcard_end:
        search_term = cond.strip("*")
        txt_lower = txt.lower()
        if has_wildcard_start and has_wildcard_end:
            return txt if search_term in txt_lower else None
        if has_wildcard_start:
            return txt if txt_lower.endswith(search_term) else None
        return txt if txt_lower.startswith(search_term) else None

    # Exact match (case-insensitive)
    return txt if txt.lower() == cond else None


def _match_attr_or_child(node: ET.Element, selector: str, cond: str) -> str | None:
    """Evaluate one ``selector:cond`` spec against a single element.

    ``selector`` resolves to an XML attribute first (case-insensitive), then
    to a child element (case-insensitive). Existence semantics operate on the
    *presence* of the attribute/element, not on value non-emptiness.
    """
    # Attribute lookup (case-insensitive)
    attr_value = None
    for key, value in node.attrib.items():
        if key.lower() == selector:
            attr_value = value
            break

    if attr_value is not None:
        if not cond or cond == "exists":
            return "exists"
        if cond == "!exists":
            return None
        return _match_value(attr_value, cond)

    # Child element lookup (case-insensitive)
    child = None
    for cand in node:
        if (cand.tag or "").lower() == selector:
            child = cand
            break

    if child is not None:
        if not cond or cond == "exists":
            return "exists"
        if cond == "!exists":
            return None
        return _match_value(child.text, cond)

    # Selector absent: only !exists matches
    if cond == "!exists":
        return "!exists"
    return None


def _xml_attr_match(root: ET.Element, search_string: str) -> str | None:
    """Match a ``path@selector:cond[@selector:cond...]`` expression.

    ``path`` resolves via ``findall``; bare paths (no ``/``) search the whole
    tree recursively (``.//path``) so nested elements like
    ``<ratings><rating>`` match without knowing the path. Every
    ``@selector:cond`` spec must be satisfied by the *same* element.
    """
    path, spec_str = search_string.split("@", 1)
    path = path.strip()
    if not path:
        return None

    specs = [s.strip() for s in spec_str.split("@")]
    if not specs or any(not s for s in specs):
        return None

    if "/" in path:
        nodes = root.findall(path)
    else:
        nodes = root.findall(".//" + path)

    for node in nodes:
        values: list[str] = []
        ok = True
        for spec in specs:
            selector, _, cond = spec.partition(":")
            selector = selector.strip().lower()
            if not selector:
                ok = False
                break
            cond = cond.strip().lower()
            value = _match_attr_or_child(node, selector, cond)
            if value is None:
                ok = False
                break
            values.append(value)
        if ok:
            return " | ".join(values)
    return None
```

- [ ] **Step 4: Run the full searchmove test suite**

Run: `.venv/Scripts/python.exe -m pytest tests/test_searchmove.py tests/test_searchmove_mover.py tests/test_searchmove_attributes.py -v`
Expected: ALL PASS — the new attribute tests plus every pre-existing searchmove test (the refactored generic branch must be behavior-preserving; in particular `rating:>5.4&nfostatus:!exists`, `nfostatus:`, `genre:*Action*`, `plot_sim_score:>0.9` from the templates/tests must still match exactly as before).

- [ ] **Step 5: Commit**

```bash
git add src/avior_dedup/searchmove/searcher.py tests/test_searchmove_attributes.py
git commit -m "feat(searchmove): XML attribute matching in search expressions"
```

---

### Task 2: Document the `@` syntax (CLI help, templates, UI placeholder) + end-to-end smoke

**Files:**
- Modify: `src/avior_dedup/searchmove/cli.py` (help text only)
- Modify: `src/avior_dedup/config/searchmove_templates.yaml`
- Modify: `frontend/src/components/SearchMoveForm.vue` (placeholder only)

**Interfaces:**
- Consumes: Task 1's `_xml_attr_match` (no direct import — exercised via the CLI smoke test).
- Produces: discoverable examples of the new syntax (CLI `--help`, template dropdown in the UI).

- [ ] **Step 1: Extend the CLI help text**

In `src/avior_dedup/searchmove/cli.py`, inside the `--search_strings` argument's `help=` string, after the `'  Ranges: rating:>4<6, rating:4-6\n'` line add:

```python
            '  XML attributes: rating@name:themoviedb\n'
            '  Scoped value: ratings/rating@name:themoviedb@value:>5.4\n'
```

- [ ] **Step 2: Add templates**

Append to `src/avior_dedup/config/searchmove_templates.yaml`:

```yaml
- extensions:
  - .nfo
  name: Has themoviedb rating
  search_expressions:
  - rating@name:themoviedb
- extensions:
  - .nfo
  name: themoviedb rating above 5.4
  search_expressions:
  - ratings/rating@name:themoviedb@value:>5.4
```

- [ ] **Step 3: Extend the UI placeholder**

In `frontend/src/components/SearchMoveForm.vue`, in the raw-mode `<v-textarea>`, change the placeholder to include an `@` example (keep the existing two lines):

```html
          placeholder="sibling:.nfo:exists&fileext:.mkv&#10;rating:>5.4&nfostatus:!exists&#10;rating@name:themoviedb"
```

- [ ] **Step 4: Verify — config loads, CLI smoke test end-to-end, full suite**

Run: `.venv/Scripts/python.exe -c "import yaml; d=yaml.safe_load(open('src/avior_dedup/config/searchmove_templates.yaml', encoding='utf-8')); names=[t['name'] for t in d]; assert 'Has themoviedb rating' in names and 'themoviedb rating above 5.4' in names, names; print('templates ok:', names)"`
Expected: prints `templates ok:` followed by the list including both new names.

Create a temp source dir with the fixture NFO (copy `Wild Christmas.nfo` content from `tests/test_searchmove_attributes.py` `_NFO` into `tmp_smoke_src/Wild Christmas.nfo`), then run the CLI in test mode:

```
.venv/Scripts/python.exe -m avior_dedup.searchmove.cli test tmp_smoke_src tmp_smoke_dest -e .nfo -s "rating@name:themoviedb"
```

Expected: `Done. Files scanned: 1, Matches: 1`; `tmp_smoke_dest/result.txt` contains a line with `rating@name:themoviedb`.

Second smoke (scoped value condition): `-s "ratings/rating@name:themoviedb@value:>6"` → Expected: `Files scanned: 1, Matches: 0`.

Final regression: `.venv/Scripts/python.exe -m pytest tests/test_searchmove.py tests/test_searchmove_mover.py tests/test_searchmove_attributes.py -q`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add src/avior_dedup/searchmove/cli.py src/avior_dedup/config/searchmove_templates.yaml frontend/src/components/SearchMoveForm.vue
git commit -m "feat(searchmove): document @ attribute syntax (CLI help, templates, UI placeholder)"
```

---

## Self-Review Checklist (run before handoff)

1. **Spec coverage:** routing (Task 1, 3a) ✓; recursion bare-tag + path semantics (Task 1, `_xml_attr_match`) ✓; selector attr→child resolution (Task 1, `_match_attr_or_child`) ✓; comparison chain incl. numeric/exists/!exists/wildcard/exact (Task 1, `_match_value` + caller presence handling) ✓; empty cond = existence ✓; malformed terms never raise (parametrized test) ✓; backward compat (existing tests as gate, Step 4) ✓; CLI help / templates / UI placeholder (Task 2) ✓; `@`-in-cond limitation (spec correction, not tested — documented only) ✓.
2. **Placeholder scan:** every code step contains full code; no TBD/TODO.
3. **Type consistency:** `_match_value(text: str | None, cond: str)`, `_match_attr_or_child(node, selector, cond)`, `_xml_attr_match(root, search_string)` — names and signatures identical in Step 3 and referenced in Task 2 smoke; `search_xml_file`/`search_text_file`/`parse_search_expression` imported in tests exactly as in `tests/test_searchmove.py`.
