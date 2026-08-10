# Final Fix Report — searchmove attribute matching (Minor findings)

Date: 2026-08-07
Commit: `8b7a6c6 test(searchmove): pin findall guard arms; document * wildcard semantics`
Files committed (only these two): `src/avior_dedup/searchmove/searcher.py`, `tests/test_searchmove_attributes.py`

## Probe results (Finding 1)

Runtime: Python 3.12.9 (venv `.venv/Scripts/python.exe`). Note: `xml.etree._elementpath` (C
accelerator) is not importable on this runtime, so `Element.findall` uses the pure-Python
`ElementPath` tokenizer.

Direct `root.findall(".//<path>")` probe on the fixture NFO root:

| path | exception |
|---|---|
| `rating[0` | `TypeError: 'NoneType' object is not callable` (unterminated `[`) |
| `rating]` | `KeyError: ']'` (stray `]`) |
| `rating[]` | `SyntaxError: invalid predicate` (empty predicate) |
| `x:rating` / `.//x:rating` | `SyntaxError: prefix ... not found` / `invalid descendant` |

Arm mapping of the existing parametrized cases (through `_xml_attr_match`):
- `rating[0@name:themoviedb` → **TypeError** arm
- `rating[0@name:themoviedb@default:true` → **TypeError** arm (multi-spec)
- `rating]@name:themoviedb` → **KeyError** arm
- **SyntaxError arm was NOT exercised by any existing case** → added one.

Routing verification (as flagged in the finding): `x:rating@name:themoviedb` is NOT routed to
`_xml_attr_match` because `"@" in search_string.split(":", 1)[0]` is False (the `@` sits after the
first colon), so a namespace-prefix path cannot pin a guard arm through the public `search_xml_file`
path. Confirmed empirically; no namespace-prefix case was added.

## Changes

1. `tests/test_searchmove_attributes.py` — malformed-term parametrize block (around line 142):
   - Added `"rating[]@name:themoviedb"` (empty predicate → `SyntaxError: invalid predicate`) to pin
     the previously missing SyntaxError arm.
   - Annotated the malformed XPath cases with the guard arm each pins, with a block comment stating
     the block covers all three arms of the findall guard (SyntaxError, TypeError, KeyError).
   - All malformed cases still assert `m is None` (no match, no raise).
2. `src/avior_dedup/searchmove/searcher.py` — `_match_value` docstring: added the sentence
   "A bare ``*`` wildcard also matches empty text (``'' in ''`` is true), consistent with the legacy
   ``tag:*`` behavior." No behavior change.

## Test output

```
.venv/Scripts/python.exe -m pytest tests/test_searchmove_attributes.py tests/test_searchmove.py tests/test_searchmove_mover.py -q
..........................................................               [100%]
58 passed in 0.23s
```

Pristine output, no failures, no warnings.

## Commit

```
8b7a6c6 test(searchmove): pin findall guard arms; document * wildcard semantics
 src/avior_dedup/searchmove/searcher.py | 3 +++
 tests/test_searchmove_attributes.py    | 9 ++++++---
 2 files changed, 9 insertions(+), 3 deletions(-)
```

`git add` was explicit for the two files only; the user's unrelated working-copy changes
(`.vscode/launch.json`, `Ingest_add_rating/add_rating_description.md`, `.superpowers/`) were not
staged or touched.

## Concern

The exception type raised by a given malformed path is runtime-dependent: pure-Python ElementPath
(3.12, used here) raises TypeError/KeyError/SyntaxError as mapped above, while the C accelerator
(3.13+) raises SyntaxError for `[0`/`]` too. The parametrized cases remain valid on both (all raised
types are inside the guard's `except (SyntaxError, TypeError, KeyError)`), but the per-arm comments
describe the arm mapping as observed on this runtime.
