# Series Marker Completeness Design

## Goal

Replace the default `clean_name` selection priority with a configurable
`series_marker_completeness` priority that prefers the duplicate copy whose
filename carries the most explicit episode marker.

## Problem

`clean_name` currently counts repeated filename tokens. This treats useful
metadata as noise. For example:

```text
Blinded (6) - 48 Stunden
Blinded (6) - 48 Stunden (Staffel 1, Folge 6)
```

The second filename repeats the episode number `6`, so `clean_name` selects the
shorter name even though the second copy carries a more explicit series/episode
marker. The current metric is also too uncommon and too cosmetic to justify its
position in the default selection policy.

## Scope

### In scope

- Add `series_marker_completeness` as a selectable selection priority.
- Replace `clean_name` with it in the default CLI and server priority lists.
- Score filename episode markers using configurable regular expressions in YAML.
- Use the highest matching score for a filename; never sum multiple matching
  markers.
- Keep `clean_name` available as an explicit optional priority for compatibility.
- Document the new priority, scoring rules, configuration format, and its limits.
- Add focused tests for scoring, priority selection, configuration loading, and
  the Blinded regression case.

### Out of scope

- Changing semantic duplicate grouping.
- Automatically detecting distinct episodes during grouping.
- Using free-text length as a proxy for metadata quality.
- Adding bitrate, file-size, or video-quality scoring.
- Removing the existing `clean_name` implementation or enum value.

## Scoring contract

The score is an integer. A missing or unrecognised marker scores `0`. If several
patterns match one filename, the maximum `points` value wins.

Default patterns:

| Points | Recognised form | Examples |
|---:|---|---|
| 1 | Single episode number | `(7)` |
| 2 | Episode range/group | `(1_7)`, `(1-7)`, `(1/7)` |
| 3 | Explicit season and episode | `(Staffel 1, Folge 3)`, `3. Staffel (1_10)` |
| 4 | Compact season/episode | `(S10_E03)`, `(S10E03)`, `(S10-E03)` |

The patterns apply to the original filename stem, before semantic episode
number removal. They are selection metadata only; they do not alter grouping
keys.

Example:

```text
Blinded (6) - 48 Stunden
```

scores `1`, while:

```text
Blinded (6) - 48 Stunden (Staffel 1, Folge 6)
```

scores `3`; the latter wins when all earlier priorities tie.

The priority does not prevent distinct episodes from entering one semantic
group. For example, `(1-2_6)`, `(3-4_6)`, and `(5-6_6)` all score `2` and
still require the separate distinct-episode protection.

## Configuration

Add a dedicated YAML file, `series_marker_scores.yaml`, in the existing
config directory mechanism. Each entry has:

```yaml
- points: 4
  pattern: '(?i)\(\s*s\d{1,2}\s*[_ -]?\s*e\d{1,3}\s*\)'
```

The loader compiles every pattern when the configuration is read. Invalid
patterns are configuration errors and must be reported rather than silently
ignored. Users can add future filename formats by adding another YAML entry;
no Python code change is needed when the format can be expressed by a regular
expression.

The bundled defaults contain the four scoring levels listed above. Matching is
case-insensitive either through the pattern or the regular-expression flags
used by the loader. The score is bounded only by the configured integer; the
highest matching configured value is returned.

## Selection behavior

Default order becomes:

```text
multichannel
resolution
fewer_errors
log_include
year_match
closest_duration
series_marker_completeness
recording_date
```

`series_marker_completeness` is a late correctness/identity tiebreaker. It
must not override technical quality, recording provenance, year consistency, or
duration validity. If scores tie, later configured priorities decide.

`clean_name` remains a valid explicit priority but is no longer part of the
default CLI or server priority list.

The keep-reason report uses `series_marker_completeness` when this criterion is
the first configured priority that separates the selected record from another
valid record. The existing `cleaner_name` reason remains for explicit uses of
`clean_name`.

## Data flow

1. The scanner already retains the original file path in each `FileRecord`.
2. The planner computes the marker score from the filename stem during sort-key
   construction.
3. The planner compares the score according to the configured priority order.
4. The selected representative and all same-stem siblings continue to use the
   existing move/keep behavior.

No `.txt` or `.nfo` parsing is required for this priority. Structured metadata
validation remains a separate concern.

## Testing

Required focused tests:

- `(7)` scores `1`.
- `(1_7)`, `(1-7)`, and `(1/7)` score `2`.
- `(Staffel 1, Folge 3)` and `3. Staffel (1_10)` score `3`.
- `S10_E03`, `S10E03`, and `S10-E03` score `4`.
- A filename with both `(6)` and `(Staffel 1, Folge 6)` scores `3`, not `4` or `1 + 3`.
- An unmarked filename scores `0`.
- The explicit Blinded pair selects the filename with `(Staffel 1, Folge 6)` when all earlier fields tie.
- The existing duplicated-title `clean_name` behavior still works when that
  optional priority is explicitly requested.
- Invalid configured regular expressions are reported.
- Default CLI and server priority lists contain
  `series_marker_completeness` and do not contain `clean_name`.

The Bonusfamilie distinct-episode case is not expected to be fixed by this
feature; it remains a separate grouping/episode-distinctness test concern.
