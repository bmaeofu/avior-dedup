# Selection priorities

When a group of duplicate recordings is reduced to one kept copy, the
**selection priorities** decide which copy survives. Everything else in the group
is moved out as a duplicate.

The list is **ordered**. Each criterion is evaluated in order and produces a
comparison value; the first criterion whose values differ decides the winner.
Criteria further down only break ties. A criterion that is not in the list is
ignored completely.

## Default order

| # | Priority | Prefers the copy with … |
|---|----------|-------------------------|
| 1 | `multichannel` | multichannel (5.1) audio |
| 2 | `resolution` | the higher resolution |
| 3 | `fewer_errors` | fewer encoding errors |
| 4 | `clean_name` | the cleaner filename |
| 5 | `recording_date` | the newer recording |
| 6 | `year_match` | an `.nfo` year that matches the `.txt` year |
| 7 | `closest_duration` | the duration closest to the recorded length |

## The criteria in detail

### `multichannel`
Prefers a recording whose audio is multichannel (AC3 5.1). Detection uses the
recording-start section of the `.log` — the last AC3 audio state within roughly
the first 15 seconds after `Start`/`Start Recording`.

The advantage is dropped when the copy has more errors than
`--max-errors-when-mc` (default `0`): a slightly better audio track does not
justify keeping a broken recording.

### `resolution`
Prefers the higher vertical resolution, taken from the recording-start section of
the `.log`. `1920x1080` and `1920x1088` are both counted as `1080`, so the usual
1088-vs-1080 padding difference does not decide anything.

### `fewer_errors`
Prefers the copy with fewer error lines in its `.log`. Copies without a log file
are treated as having an unknown (very high) error count and therefore lose.

### `clean_name`
Prefers the filename with the **fewest redundant word tokens**. Inside one group
every candidate normalizes to the same key, so any extra tokens in the raw name
are redundant.

```text
42 - Die Antwort auf fast alles - Werden wir uns einfrieren.mkv              (10 tokens)
Werden wir uns einfrieren - 42 - Die Antwort auf fast alles.mkv              (10 tokens)
42 - Die Antwort auf fast alles - Werden wir uns einfrieren - 42 - Die …      (17 tokens)  ← loses
```

The first two are equally clean and tie; the repeated series title loses. This
criterion is about cosmetics only — place it below the quality criteria unless
you really want a tidy name to outrank, say, a newer recording.

### `recording_date`
Prefers the newer recording, using `rec_date` from the `.log`. Only when a copy
has no `rec_date` does the filesystem modification time act as a fallback — and
only because `recording_date` is part of the active list. Modification times have
day granularity, so two recordings from the same day tie.

### `year_match`
Prefers the copy whose `.nfo` year equals its `.txt` year. A mismatch usually
means the metadata belongs to a different film, so this is a correctness signal
rather than a quality signal.

### `closest_duration`
Prefers the copy whose duration is closest to the recorded length
(`video_duration - rec_duration`). It only penalizes deviations **beyond** the
configured window, so everything inside the window counts as equal:

| Option | Default | Meaning |
|--------|---------|---------|
| `--max-duration-diff-longer` | `600` | allowed seconds the video may be longer than the recording |
| `--max-duration-diff-shorter` | `240` | allowed seconds the video may be shorter than the recording |

## Hard pre-filter (runs before any priority)

A copy can only be kept when **both** durations are known and the difference is
inside that window. Copies outside it are never selected — unless no candidate at
all qualifies, in which case the full list is used so that one copy is always
kept.

## Changing the order

**CLI**

```bash
avior-dedup --selection-priorities resolution clean_name multichannel fewer_errors recording_date year_match closest_duration ...
```

Order matters, values are space-separated. Omitting a criterion removes it.

**Web UI** — the job form shows the list with up/down buttons; the top entry has
the highest weight.

## Reading the log

The keep report (`keep_dedup_log.txt`) names the criterion that decided:

| Reason | Criterion |
|--------|-----------|
| `multichannel` | `multichannel` |
| `higher_resolution` | `resolution` |
| `fewer_errors` | `fewer_errors` |
| `cleaner_name` | `clean_name` |
| `newer` | `recording_date` |
| `year_match` | `year_match` |
| `closest_duration` | `closest_duration` |
| `selected` | no criterion separated the copies; the first one was taken |
