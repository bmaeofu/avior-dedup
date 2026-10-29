# Selection priorities

Every duplicate group is reduced to exactly **one kept copy**; everything else is
moved out. The selection priorities decide which copy survives.

The list is **ordered**. Each criterion contributes one number to a comparison
tuple ("sort key") in list order; Python's `min()` picks the smallest tuple, so a
lower value is better. The first criterion whose values differ decides the
winner — later criteria only break ties. A criterion that is not in the list is
ignored completely (not "treated as equal": it contributes no element at all).

If every criterion ties, the **first record in the group's input order** wins.
That is deterministic for a given input but not meaningful — it is why
`recording_date` is kept as a last criterion.

## At a glance

| # | Priority | Prefers the copy with … | Data source |
|---|----------|-------------------------|-------------|
| 1 | `multichannel` | multichannel (5.1) audio | `.log`, first 25 s after `Start` |
| 2 | `resolution` | the higher resolution | `.log`, whole `Start`…`Stop` block |
| 3 | `fewer_errors` | fewer encoding errors | `.log`, `Errors:` lines |
| 4 | `log_include` | no avior-go `log_include` match | `.log` (trailer excluded), terms from MongoDB |
| 5 | `year_match` | `.nfo` year equal to the `.txt` year | `.nfo`, `.txt` |
| 6 | `closest_duration` | duration closest to the recorded length | ffprobe + `.log`/EPG |
| 7 | `clean_name` | the cleaner filename | filename only |
| 8 | `recording_date` | the newer recording | `.log` first line, else file mtime |

The order groups criteria by what they say about a copy:

| Tier | Criteria | Meaning |
|------|----------|---------|
| Quality | `multichannel`, `resolution`, `fewer_errors` | the source is technically better |
| Provenance | `log_include` | avior-go did not mark this copy for replacement |
| Correctness | `year_match`, `closest_duration` | the file belongs to this episode and is complete |
| Cosmetics | `clean_name` | only the filename is nicer |
| Tiebreak | `recording_date` | carries no information; keeps the choice deterministic |

Why `recording_date` is last: a re-run of the same broadcast always has a
different date, so as a high-priority criterion it decides nearly every group and
shadows everything below it. Measured on a real 241-group library run with the
old order (`recording_date` at position 4): it decided **229 groups (95 %)**,
`closest_duration` 7, `fewer_errors` 2, `selected` 2, `multichannel` 1 — while
`year_match` and `clean_name` never fired at all.

## Hard pre-filter (runs before any priority)

Only copies with **both** durations known and inside the window may be kept:

| Option | Default | Condition |
|--------|---------|-----------|
| `--max-duration-diff-longer` | `600` | `video_duration - rec_duration <= 600` |
| `--max-duration-diff-shorter` | `240` | `video_duration - rec_duration >= -240` |

Copies outside the window are excluded from the keep pool. If **no** copy
qualifies, the full list is used instead, so one copy is always kept.

## The criteria in detail

### `multichannel`
**Prefers** a recording whose audio is multichannel (AC3 5.1) over stereo.

**Data source** — the `.log`, narrowed to the **first 25 seconds** after a line
ending in `Start` / containing `Start Recording`. Within that window the *last*
AC3 audio-state line wins. If the log has no start marker, the whole log is
searched for the last AC3 state instead.

**Parsing** (`_ac3_audio_state_from_line`) — a line counts only if it contains
`ac3` and either `audio` or the `ac3 N/N` notation. Then:

| Line content | Result |
|---|---|
| contains `stereo` | stereo |
| `5.1`, `6.1`, `7.1`, … | multichannel |
| `ac3 3/2` (front+rear > 2) | multichannel |
| `ac3 2/0`, `1.0`, `2.0` | stereo |

**Sort value** — `0` when multichannel, else `1`. The advantage is **dropped**
when the copy has more errors than `--max-errors-when-mc` (default `0`): a single
error already cancels it. Unknown (`multichannel is None`) counts as `1`.

**Example** — `PID 5316: AC3 Audio Stereo, 48 khz, 384 kbps` → stereo; a later
`AC3 Audio 5.1` in the same window would override it to multichannel.

### `resolution`
**Prefers** the higher vertical resolution.

**Data source** — the `.log`, but over the **whole recording block** from `Start`
to `Stop` (not the 25 s window; that window stays authoritative for audio). The
*last* line containing `…video…` and a `NNNxNNN` pattern decides.

**Parsing** — the height is the second number; `1088` is normalized to `1080`, so
the usual 1088-vs-1080 padding never decides anything.

**Sort value** — `-resolution` (higher resolution ⇒ smaller value). Unknown
(`None`) becomes `+10^9` and therefore ranks last.

**Example** — `H.264 Video, 16:9, 1280x720, 50 fps` → `720`.

### `fewer_errors`
**Prefers** the copy with fewer encoding errors.

**Data source** — the `.log` (avior-go trailer removed). All `Errors: <n>`
occurrences are **summed**; the legacy variant `MB) Errors: <n>` is also read.

**Sort value** — the sum; unknown (no readable log) becomes `10^9`.

**Example** — `02:18:00 Errors: 1 @5889,6 MB` → 1.

### `log_include`
**Prefers** the copy that is **not** marked for replacement by avior-go.

**Data source** — the `.log` with the avior-go trailer removed (everything from
`avior-go info` onwards), so a file never matches through its own past module
output such as its own `LogMatchModule: allow replacement …` line.

In avior-go a `log_include` match means "this recording is the one to replace"
(`comparator/logmatch.go`, `LogMatchModule` mode `include`).

**Terms** — read at the start of every job from the avior-go MongoDB instance:
database `Avior`, collection `log_include`, field `Name` (21 entries at the time
of writing, e.g. `-tune hq`, `encoder x265`, `Lost Data:`, `Digital TV DVBS2`).
The instance defaults to `mongodb://192.168.178.75:27017`; override with
`AVIOR_GO_MONGO_URL`. There is **no local copy**. If the instance is unreachable
the run prints `[avior-dedup] log_include: avior-go MongoDB unreachable (<url>)`
and the criterion is inert for that run.

**Matching** — case-insensitive substring per term (avior-go itself matches
case-sensitively, which is why the collection carries both `PHOENIX HD` and
`phoenix HD`).

**Sort value** — `0` only when the log is readable **and** free of any term;
`1` otherwise (marked, or no readable log — unanalysable copies get no bonus).

**Caveat** — some terms are identity markers, not quality signals
(`Device: Digital Devices DVB-S/S2 Tuner` occurs in ~28 % of a 300-log sample).
They do not distort the ranking — inside a group both copies carry them and tie —
but they only discriminate when copies differ, e.g. one has `Lost Data:`.

### `year_match`
**Prefers** the copy whose release year is consistent across its metadata.

**Data source** — `.nfo` `<year>` element vs. the year extracted from the EPG
`.txt` by the shared `movie_metadata` library (which falls back to the `.log`).

**Sort value** — `0` when both years are known and equal, else `1` (a missing
year also yields `1`).

**Example** — `.nfo` year 1989, `.txt` year 1990 → mismatch → `1`.

### `closest_duration`
**Prefers** the copy whose video length matches the recorded length.

**Data source** — `video_duration` from `ffprobe -show_entries format=duration`;
`rec_duration` from the EPG data in the log, falling back to the real recording
time parsed from the log.

**Sort value** — the amount by which the difference exceeds the allowed window
(`0` inside the window). Both durations unknown → `10^9`.

Because the hard pre-filter already discards everything outside the window, this
value is `0` for all remaining candidates in a normal run. It therefore only
decides when the fallback pool is used (no copy was inside the window at all) —
in practice a handful of groups per library run.

### `clean_name`
**Prefers** the filename with the **fewest redundant word tokens**.

**Data source** — the filename only. Tokens are matched with
`[0-9A-Za-zÄÖÜäöüß]+` on the stem (extension stripped).

Inside one group every candidate normalizes to the same key, so extra tokens in
the raw name are redundancy:

```text
42 - Die Antwort auf fast alles - Werden wir uns einfrieren.mkv              (10 tokens)
Werden wir uns einfrieren - 42 - Die Antwort auf fast alles.mkv              (10 tokens)
42 - Die Antwort auf fast alles - Werden wir uns einfrieren - 42 - Die …      (17 tokens)  ← loses
```

The first two tie; the repeated series title loses. Prefix-first and
title-first spellings are equally clean and therefore arbitrary among themselves.

**Sort value** — the token count.

**Note** — only the *kept* copy's name survives in place; the duplicate is moved
away unchanged.

### `recording_date`
**Prefers** the newer recording.

**Data source** — the first `.log` line, matched with
`\b\d{1,2}[./]\d{1,2}[./]\d{4}\b` (`dd.mm.yyyy` or `dd/mm/yyyy`) → ISO date. Only
when that fails is the `.log` file's modification time used.

**Sort value** — the negative ordinal of that date, i.e. **day granularity**.
Two recordings from the same day tie. Totally unknown → `0` (oldest).

**Caveat** — as a criterion it is nearly information-free (a re-run always has a
different date), which is why it is last. It only picks a stable winner for
otherwise identical copies, including identical names.

## Changing the order

**CLI**

```bash
avior-dedup f /media/source /media/target log.txt \
  --selection-priorities resolution log_include multichannel fewer_errors year_match closest_duration clean_name recording_date
```

Order matters, values are space-separated. Omitting a criterion removes it from
the ranking entirely.

**Web UI** — the job form shows the list with up/down buttons; the top entry has
the highest weight.

**`log_include` terms** — not part of the priority list. They come from avior-go's
MongoDB (`Avior.log_include`) and are re-read at the start of every job.

## Reading the log

The keep report (`keep_dedup_log.txt`) names the criterion that decided:

| Reason | Criterion |
|--------|-----------|
| `multichannel` | `multichannel` |
| `higher_resolution` | `resolution` |
| `fewer_errors` | `fewer_errors` |
| `no_include_match` | `log_include` |
| `year_match` | `year_match` |
| `closest_duration` | `closest_duration` |
| `cleaner_name` | `clean_name` |
| `newer` | `recording_date` |
| `selected` | nothing separated the copies; the first one was kept |

The report checks criteria in the order of the configured list, so the reason
always names the first criterion that actually differentiated.
