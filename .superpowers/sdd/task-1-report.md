# Task 1 Report: Attribute matching core (searcher.py + tests)

**Status:** DONE
**Commit:** `2c1251f` — `feat(searchmove): XML attribute matching in search expressions`

## What I implemented

XML attribute matching in the searchmove expression language, per the task brief (`.superpowers/sdd/task-1-brief.md`), all code verbatim from the brief:

1. **`src/avior_dedup/searchmove/searcher.py`**
   - `search_xml_file._xml_match`: added `@` routing — terms containing `@` now go to `_xml_attr_match` (after the metadata-term check and XML parse, before the legacy `tag:attrib` split).
   - `_xml_tag_match`: refactored the generic branch (below the untouched `rating` special case) to a shared comparison chain. The old inline numeric/exists/wildcard/exact logic was replaced with: node-level existence checks (`exists`/`!exists`), empty-condition empty-text semantics (`nfostatus:`), then a per-node `_match_value` loop.
   - Added three new module-level functions directly after `_xml_tag_match` (before `search_xml_file`):
     - `_match_value(text, cond)` — numeric (`parse_condition`), wildcard (`*`-prefix/suffix), then case-insensitive exact comparison.
     - `_match_attr_or_child(node, selector, cond)` — one `selector:cond` spec against one element; case-insensitive attribute lookup first, then case-insensitive child-element lookup; `exists`/`!exists`/empty-cond semantics on presence.
     - `_xml_attr_match(root, search_string)` — full `path@selector:cond[...]` evaluation: bare paths become `.//path` (recursive), `findall` for nested paths, all specs must match the *same* element, returns `" | ".join(values)` or `None`. Malformed terms (empty path, empty spec, empty selector) return `None` without raising.

2. **`tests/test_searchmove_attributes.py`** (new, verbatim from brief) — 22 tests covering exact/wildcard/exists/!exists/numeric conditions, attribute-vs-child selector resolution, recursive vs. path-based search, multi-spec same-element vs. cross-element semantics, case-insensitivity, combination with legacy syntax, malformed-term safety, and a guard that plain-text search treats `@` literally.

## What I tested and results

- **Step 2 (RED)** — `.venv/Scripts/python.exe -m pytest tests/test_searchmove_attributes.py -v`:
  - Before implementation: **20 failed, 2 passed**. Failures were `KeyError: '@'` raised inside `ET`'s `findall` path parser via `_xml_tag_match` (e.g. `findall('rating@name')`), exactly as the brief predicted. The two passes were `test_malformed_terms_no_crash_no_match[rating@]` (no `:` → legacy split raises `ValueError` → `None`, coincidentally correct) and `test_text_search_treats_at_literally` (text search unaffected). ✓ RED confirmed before proceeding.
- **Step 4 (GREEN)** — after implementation, the new file: **22 passed in 0.08s**.
- **Full three-file suite** — `.venv/Scripts/python.exe -m pytest tests/test_searchmove.py tests/test_searchmove_mover.py tests/test_searchmove_attributes.py -v`: **53 passed in 0.32s** (31 pre-existing + 22 new). The refactored generic branch is behavior-preserving: legacy semantics verified by the passing pre-existing tests, including the brief's named cases (`rating:>5.4&nfostatus:!exists`, `nfostatus:`, `genre:*Action*`, `plot_sim_score:>0.9`).

## Files changed

- `src/avior_dedup/searchmove/searcher.py` (modified, +293/−39 total across both files)
- `tests/test_searchmove_attributes.py` (created)

Committed only these two files via explicit `git add` of both paths. The user's unrelated uncommitted changes (`.vscode/launch.json`, `Ingest_add_rating/`) were never touched or staged. No formatters, linters, or project-wide suite were run.

## TDD Evidence

- **RED:** `pytest tests/test_searchmove_attributes.py -v` → `20 failed, 2 passed`; failure summary shows `KeyError: '@'` from `xml.etree.ElementPath` (`ops[token[0]]` → `KeyError: '@'`) — the `@` syntax had no routing and was passed straight into `root.findall`. Expected: any `@` term must not be silently mis-parsed as a tag path.
- **GREEN:** same command → `22 passed`; full suite → `53 passed`.

## Self-review findings

- **Completeness:** all 5 brief steps executed (tests → red → implement → full suite green → commit with exact message `feat(searchmove): XML attribute matching in search expressions`). ✓
- **Quality:** implementation is byte-for-byte the brief's code; the `rating` special case in `_xml_tag_match` is untouched; shared `_match_value` removes the duplicated numeric/wildcard/exact logic in `_xml_tag_match`.
- **Behavior preservation:** pre-existing tests all pass; the refactor's only ordering change (existence checks before value comparison) is safe because `parse_condition` returns `None` for `"exists"`/`"!exists"`, and empty-condition semantics are handled explicitly.
- **Discipline:** no scope creep, no extra commits, user's working-tree changes left alone.
- **Concerns:** none material. Minor observations: (1) `test_malformed_terms_no_crash_no_match[rating@]` passed even in RED (harmless; it still passes GREEN); (2) `.superpowers/` is untracked in the repo (contains the brief and this report) — not committed, by design.

## Issues / concerns

None blocking. Task 2 (docs/templates/UI placeholder) depends only on the `path@selector:cond` syntax, which is implemented exactly as specified.

---

## Fix report — Task 1 review findings (Important)

Both Important findings from the review were fixed and verified.

### Finding 1 — unguarded `findall` raised on malformed XPath
`_xml_attr_match` wrapped its `findall(path)` / `findall(".//" + path)` calls in
`try/except (SyntaxError, TypeError, KeyError)` returning `None` on any of them.
Previously-verified crash forms now return no match without raising:
- `rating[0@name:x` (was TypeError), `rating]@name:x` (was KeyError),
  `title:user@x` (was SyntaxError) — the last also no longer routes to
  `_xml_attr_match` at all (see Finding 2).

### Finding 2 — @ routing hijacked legacy `tag:value` terms with @ in value
Routing in `search_xml_file._xml_match` changed from `if "@" in search_string`
to `if "@" in search_string.split(":", 1)[0]`, so attribute matching only
triggers when `@` appears before the first colon. Legacy terms like
`title:user@host` (exact text match on `<title>`) keep working.

### Tests
- Parametrized block extended with `rating[0@name:themoviedb`,
  `rating]@name:themoviedb`, and `rating[0@name:themoviedb@default:true`
  (all must return no match and never raise).
- New `test_legacy_tag_value_with_at_in_value`: inline NFO with
  `<title>user@host</title>`, asserts `title:user@host` matches via the legacy
  exact-match path and `found_values` contains `user@host`.

### Verification
```
.venv/Scripts/python.exe -m pytest tests/test_searchmove_attributes.py tests/test_searchmove.py tests/test_searchmove_mover.py -q
57 passed in 0.25s
```
Direct check of the previously-crashing `title:user@x` form returns `None`
without raising.

### Commit
`3b1124206c87adcdb2d24cf18dd6f9763b88d5b9`
`fix(searchmove): guard malformed @ paths and restore legacy @-value terms`
(2 files changed: `src/avior_dedup/searchmove/searcher.py`,
`tests/test_searchmove_attributes.py`; user's unrelated changes untouched)
