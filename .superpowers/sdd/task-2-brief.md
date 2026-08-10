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