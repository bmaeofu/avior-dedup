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
| 4 | `log_include` | a `.log` **without** an avior-go `log_include` match |
| 5 | `year_match` | an `.nfo` year that matches the `.txt` year |
| 6 | `closest_duration` | the duration closest to the recorded length |
| 7 | `clean_name` | the cleaner filename |
| 8 | `recording_date` | the newer recording |

The order is grouped by what a criterion actually says about the copy:

| Tier | Criteria | Meaning |
|------|----------|---------|
| Quality | `multichannel`, `resolution`, `fewer_errors`, `log_include` | the source is technically better / not marked for replacement |
| Correctness | `year_match`, `closest_duration` | the file belongs to this episode and is complete |
| Cosmetics | `clean_name` | only the filename is nicer |
| Tiebreak | `recording_date` | no information; keeps the choice deterministic |

`recording_date` is **last on purpose**: a re-run of the same episode always has a
different date, so this criterion fires in almost every group and would shadow
everything below it. In a real 241-group library run it decided 229 groups (95 %),
while `year_match` and `clean_name` never got a chance. It is not a quality
signal — it only picks a stable winner when two copies are otherwise identical
(including their names).

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

### `log_include`
Prefers the copy that is **not** marked for replacement by avior-go.

In avior-go a `log_include` match on a file means "this recording is the one to
replace" (see `comparator/logmatch.go`, `LogMatchModule` mode `include`).

The terms are read from avior-go's MongoDB collection `Avior.log_include` (field
`Name`) — the same list avior-go itself uses. `AVIOR_DEDUP_MONGO_URL` (e.g.
`mongodb://192.168.178.75:27017`) selects the database. Terms match as
case-insensitive substrings of the `.log`; avior-go itself matches
case-sensitively, which is why the collection carries both `PHOENIX HD` and
`phoenix HD`.

MongoDB is the only source — there is no local copy. When
`AVIOR_DEDUP_MONGO_URL` is unset, the criterion is inert (nothing is marked as
replaceable). When the database is unreachable, the run prints
`[avior-dedup] log_include: MongoDB unreachable (<url>)` and the criterion is
inert for that run. The list is cached per run and re-read at the start of every
job.

Note that some terms (`Device: Digital Devices DVB-S/S2 Tuner`) appear in almost
every recording. They do not break the ranking — within a group both copies carry
them and tie — but they also do not discriminate. The criterion only decides when
the copies differ in these markers, e.g. one has `Lost Data:`.

The comparison uses the log with the avior-go trailer removed (everything from
`avior-go info` onwards), so a recording never matches through its own module
output — e.g. its own `LogMatchModule: allow replacement …` line.

A copy without any analysable log ranks with the marked copies: only an
explicitly clean log wins.

### `clean_name`
Prefers the filename with the **fewest redundant word tokens**. Inside one group
every candidate normalizes to the same key, so any extra tokens in the raw name
are redundant.

```text
42 - Die Antwort auf fast alles - Werden wir uns einfrieren.mkv              (10 tokens)
Werden wir uns einfrieren - 42 - Die Antwort auf fast alles.mkv              (10 tokens)
42 - Die Antwort auf fast alles - Werden wir uns einfrieren - 42 - Die …      (17 tokens)  ← loses
```

The first two are equally clean and tie; the repeated series title loses.

This criterion is about cosmetics only, so it sits below every quality and
correctness criterion: a tidier name never overrides a better source or a
correctly matched episode. It still beats `recording_date`, because the recording
date carries no information about which copy is better.

Note that the *kept copy* determines the resulting filename set; the duplicate is
moved away unchanged.

### `recording_date`
Prefers the newer recording, using `rec_date` from the `.log`. Only when a copy
has no `rec_date` does the filesystem modification time act as a fallback — and
only because `recording_date` is part of the active list. Modification times have
day granularity, so two recordings from the same day tie.

This is the **last** criterion by default, and deliberately so: a second
recording of the same broadcast always carries a different date, so as a
high-priority criterion it would decide nearly every group and hide every
criterion below it. In a real library run it decided 95 % of all groups while
`year_match` and `clean_name` never fired. Keep it last — or move it up only if
you really want "the later broadcast" to outrank correctness and cosmetics.

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

Because the hard pre-filter below already removes every copy outside that window,
this criterion is `0` for all remaining candidates and only decides when the
fallback pool is used (no copy was inside the window at all).

## Hard pre-filter (runs before any priority)

A copy can only be kept when **both** durations are known and the difference is
inside that window. Copies outside it are never selected — unless no candidate at
all qualifies, in which case the full list is used so that one copy is always
kept.

## Changing the order

**CLI**

```bash
avior-dedup --selection-priorities resolution log_include multichannel fewer_errors year_match closest_duration clean_name recording_date ...
```

Order matters, values are space-separated. Omitting a criterion removes it.

**Web UI** — the job form shows the list with up/down buttons; the top entry has
the highest weight.

**`log_include` terms** — the terms themselves are not part of the priority list;
they come from avior-go's MongoDB (`Avior.log_include`), read fresh at the start
of every job. Without `AVIOR_DEDUP_MONGO_URL` the criterion is inert — nothing is
marked as replaceable.

## Reading the log

The keep report (`keep_dedup_log.txt`) names the criterion that decided:

| Reason | Criterion |
|--------|-----------|
| `multichannel` | `multichannel` |
| `higher_resolution` | `resolution` |
| `fewer_errors` | `fewer_errors` |
| `no_include_match` | `log_include` |
| `cleaner_name` | `clean_name` |
| `newer` | `recording_date` |
| `year_match` | `year_match` |
| `closest_duration` | `closest_duration` |
| `selected` | no criterion separated the copies; the first one was taken |
