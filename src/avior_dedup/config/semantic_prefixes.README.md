semantic_prefixes.yaml — usage

This file contains a list of regular-expression patterns (one per YAML list item).
Each pattern is applied to filenames when performing "semantic" duplicate matching. If a pattern matches a prefix in a filename it will be stripped for the purposes of semantic comparison.

Guidelines and examples:
- Patterns are plain Python regular expressions (case sensitive by default). The frontend and server treat the pattern string as a regex.
- Use anchors if you want the pattern to match only at the start: `^the\s+` matches leading "The ".
- Use `\s` for whitespace and `*`/`+` quantifiers, e.g. `terra\s*x\s*-\s*`.
- Escape backslashes in YAML strings or use single-quoted YAML entries when necessary.

Examples:
- `"terra\\s*x\\s*-\\s*"`  -> matches prefixes like "Terra X - "
- `"^the\\s+"`                -> matches leading "The "
- `"^a\\s+"`                  -> matches leading "A "

Editing:
- Admins can edit `semantic_prefixes.yaml` directly in the config directory or use the API endpoint `/api/config/semantic_prefixes` (GET/PUT).
- In the UI, configured prefixes appear as checkboxes in the job form; users can select them per-job and also add custom patterns.

Notes:
- Be careful with overly-broad patterns — they may remove meaningful title parts.
- Test patterns on a small sample before applying globally.