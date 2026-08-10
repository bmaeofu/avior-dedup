**Description of the add_rating Project**

This document summarizes the purpose and main functions of `add_rating.py`, along with the structure of the related `movie_metadata` package and the `scraper` CLI project. It explains the file extensions listed in `md_candidates` and which information is derived from which files. It also describes how this data is used to improve search queries for TMDb/OMDb/IMDb and how plot comparison with LLMs increases the reliability of the matching process.

**Project Structure**
- `add_rating.py`: Consumer/orchestrator for the normal NFO validation and rating workflow. It imports all shared logic from `movie_metadata`.
- `movie_metadata/`: Python package with shared modules: `config.py` (RunConfig, API keys, constants), `text_utils.py` (read_text, has_min_words, normalize_title, similarity, parse_runtime), `metadata.py` (.txt/.log extractors, country normalization, episode detection), `apis.py` (TMDb/OMDb wrappers), `llm.py` (Ollama client, smart_compare, compare_nfo_with_external), `nfo_xml.py` (NFO template, XML persistence, rating upsert), `candidates.py` (TMDb candidate search, year fallback, title-contains fallback).
- `scraper/`: Standalone CLI project at `C:/repos/scraper`. It imports `movie_metadata` from `C:/repos/movie_nfo_lib` and creates missing `.nfo` files for `.mkv`/`.mp4` files.
- `movie_metadata/nfo_template.nfo`: XML template for NFO creation (package data, loaded via importlib.resources).

**Purpose of `add_rating.py`**
- `add_rating.py` is the consumer/orchestrator that reads, enriches, and evaluates metadata from video datasets. It gathers information from .nfo/.txt/.log/plot and image files, queries external services (TMDb, OMDb), and persists updated NFO data when needed. The `--create-missing-nfo` flag is deprecated; use the standalone scraper (`python -m scraper`) at `C:/repos/scraper` instead.
- **Core tasks**: Extraction of title/original title, year, runtime, cast, and plot; search/mapping to TMDb/IMDb; insertion/update of rating nodes in NFO; plot comparison (fast/deep) with local LLM instances; rescraping/enrichment of missing NFOs.

**Explanation of the `md_candidates` extensions**
md_candidates = [
    ".txt", ".log", ".mp2", ".mp4", ".mkv", ".ts", ".nfo",
    ".mp2.log", ".mpg.log", ".mkv.log", ".plot.txt",
    "-fanart.jpg", "-poster.jpg", "-landscape.jpg", "-thumb.jpg",
    ".mp4.INFO.log", ".mp2.INFO.log", ".ts.INFO.log", ".mkv.INFO.log",
]

- **.txt**: Recorder/EPG/extracted text (for example timer or transcript lines). Useful for extracting alternative titles, timer names, year/country hints, and short plot fragments. Often unstructured, but valuable for heuristics.
- **.plot.txt**: Sibling/result file that can be produced by the script or by users and contains aggregated plot/comparison information. It combines data from `*.txt`, `*.log`, and `*.nfo` and serves as a cache/output for plot comparisons and scoring; it is not a primary source.
- **.log / *.log / *.INFO.log / .mp2.log / .mpg.log / .mkv.log**: Recording/recorder logs that often contain timer strings, broadcaster/event metadata (country, year, title), and occasionally technical metadata. Helpful for extracting year/country/timer title information.
- **Video container extensions (.mp4, .mkv, .ts, .mp2, .mpg)**: The filenames themselves and container metadata (if available) often provide title parts, year, episode identifiers, and file sizes; they are used to identify movie files (via `VIDEO_SUFFIXES`).
- **Image suffixes (-poster.jpg, -fanart.jpg, -thumb.jpg, -landscape.jpg)**: Companion images for media entries; the names often provide identifying parts (for example, the same basename as the movie file). They are not analyzed semantically, but they help when locating complete datasets and recognizing sibling files.

What purpose do these files serve in the pipeline context?
- **Title/year narrowing**: Short texts from `.txt`/`.log` can filter possible year and country hints (regex patterns such as `TXT_META_PATTERN`) to narrow TMDb/OMDb searches.
- **ID adoption**: `uniqueid` fields in `.nfo` are direct keys for TMDb/IMDb lookups (avoiding string searches).
- **Plot source**: Longer `*.txt` sections (recorder/EPG) and `<plot>` in `.nfo` are the primary sources for plot text; `.plot.txt` is an aggregated result file and is only used as an existing cache/output. These plots are used for deep/LLM comparisons as well as TMDb/OMDb field matching (for example `get_best_tmdb_plot()` tries DE/EN fallbacks).
- **Cast/role extraction**: `cast` sections in `.nfo` or recognizable names in `.txt` increase confidence during matching (actor matching contributes to the score).
- **Runtime and year validation**: Runtime in `.nfo` or technical metadata in the log help detect runtime deviations (rules of ≤5% or ≤10% in the score table).

**Which data is extracted from which sources (concretely)**
- **From `.nfo` (XML)**: `title`, `originaltitle`, `year`, `runtime`, `country`, `plot`, `uniqueid` (tmdb/imdb), `cast` → direct mapping and score calculation.
- **From `.plot.txt`**: If present, aggregated/normalized plot information; it is read as a cache/output, can simplify normalization (`normalize_plot()`), token/word counting, and plot similarity comparisons, but it is not a primary data source.
- **From `.txt` / `.log` / `*.log`**: Timer/EPG lines, possibly combined titles with country/year → heuristic patterns (`TIMER_NAME_META_PATTERN`, `TXT_META_PATTERN`) extract year/country/genre.
- **From filenames**: The basename (without suffix) is used as an alternative title candidate; it may contain episode/season markers, release year, or language.
- **From image suffixes**: Identification of siblings — no semantic extraction, but useful for completeness checks.

**How this data improves TMDb/OMDb/IMDb queries**
- **Direct IDs**: If `tmdb_id` or `imdb_id` is present in `.nfo`, an exact API query is made (highest reliability).
- **Constraining by year/country**: Extracted year or country hints reduce false-positive hits in text-based searches.
- **Alternative titles**: `title`, `originaltitle`, filename, and timer names are combined as search variants, increasing hit rate for regionally different titles.
- **Better plots**: Longer, cleaner plots from `*.txt`/`.nfo` are supplied to TMDb/OMDb fields or used to verify matches (for example, longer plot matches beat short, generic descriptions). Aggregated `*.plot.txt` files serve as cache/output, not as a primary source.
- **Cast checks**: Found actor names validate candidates (actor matching is weighted heavily in the score).

**Score calculation — which parts contribute**
- **Title similarity**: Similarity thresholds (>=0.95 → 8 points, >=0.90 → 7, ... >=0.60 → 3). Basis: normalized title strings (`normalize_title()` + `similarity()`).
- **Plot similarity**: LLM-based semantic comparison or local heuristic comparison functions (for example `SequenceMatcher`) → stepped points (0.90+ → 8 points, etc.).
- **Actor/role matching**: Points for each matching actor found; combined bonuses if the role also matches.
- **Runtime and year**: Small point values for close runtime and year matches.
- **Country**: Very low weight, mainly used as a positive/negative indication.
- **Combination bonuses**: For example actor+role, title+actor, title+runtime, year+runtime → additive bonuses.

**Confidence levels (from code/table)**
- **Score ≤ 8** → probably wrong
- **Score 9–13** → uncertain
- **Score 14–20** → probable
- **Score >20** → very likely

**Purpose of plot comparison with LLMs**
- **Robust semantic evaluation**: Text-based similarity (for example Levenshtein/SequenceMatcher) is unreliable for paraphrases, translations, or strongly different wording. LLMs capture semantic core elements (characters, conflicts, events) and provide more robust scores.
- **Multi-stage pipeline**: A fast filter (FAST_PROMPT/FASTMODEL) can reject obvious non-matches or yes-matches; a deeper model (DEEPMODEL) produces a finer-grained score plus explanation.
- **Dealing with sparse/noisy plots**: LLMs can also contextualize unstructured, short, or fragmentary plots (for example from `.txt` logs) and decide whether the plot information is meaningful enough (`has_meaningful_content`).
- **Verification of API hits**: After a TMDb/IMDb result list, an LLM can verify the match between the NFO plot and the API plot, reducing misassignments.
- **Explainability**: Deep prompts provide a short explanation for the assigned score (in configured variants), useful for logging and manual review.

- **Practical notes / recommendations**
- **Prioritize local recorder metadata (`*.txt`) for verification**: `*.txt` (info/timer/EPG) is the primary source for determining what was actually recorded. Use `*.log` only as a fallback if `*.txt` is missing. `.nfo` remains an important structured source for enrichment/verification, but not the primary source for recorder metadata.
- **Use `*.plot.txt` as cache/output, not as a primary source**: Aggregated `*.plot.txt` files can speed up LLM comparisons, but they do not replace analysis of the original `*.txt` content.
- **Extract year/country early**: Narrowing reduces API costs and false matches.
- **Configurable token limits**: For deep LLM calls on local models, watch limits; `run_llm_with_retries()` handles cutoffs, but a suitable `cfg.max_tokens_deep` minimizes aborts.

---

This file was created as a supplement to `add_rating.py`. If you want, I can also extend it with example search queries, regex extractions, or a short flow diagram.

**Addition: Kodi scraping, validation, and missing NFO creation**

- Kodi typically generates `*.nfo` files by scraping based on the video filename (for example `Tage, die bleiben.mkv` → `Tage, die bleiben.nfo`). The title and other field contents are taken from public metadata sources, but the year, plot, or cast can be inaccurate or missing — especially for ambiguous titles.
- `add_rating.py` validates these automatically generated `*.nfo` files: it compares the structured `*.nfo` with the local recording metadata (for example `Tage, die bleiben.log`, `Tage, die bleiben.txt`) and calculates a score indicating how likely the `.nfo` corresponds to the film actually described in `.log`/`.txt`.

How this is implemented in the pipeline:
- Comparison functions: `compare_nfo_with_external()` calls the plot and metadata comparison logic and returns `nfo_score`, `plot_sim_score`, and `year_diff`; these are used to derive `nfostatus` decisions.
- Score evaluation: If `nfo_score` is above `cfg.low_score_threshold` and `plot_sim_score`/`year_diff` are acceptable, the `.nfo` is considered plausible and the routine tries to fill missing ratings and fields via TMDb/OMDb (`fetch_ratings()` → `fetch_tmdb_movie_bundle()` / `fetch_omdb_imdb_data()`).
- Negative result: If the score is low or the year deviation is too large (`cfg.year_diff_threshold`), `add_rating.py` can trigger different actions depending on the parameters:
    - If `--enable-rescraping` is set, `start_rescraping()` launches a rescrape workflow that uses alternative title candidates from `.txt`/`.log` and targeted TMDb searches (`find_matching_candidate_with_year_fallback()`).
    - Without rescraping, the file is marked (`nfostatus` set) and may be left for manual review.

Parameter-driven side effects:
- `--write-plot-comparison-data`: If set, `compare_nfo_with_external()` writes the main findings (normalized plots, comparison scores, recognized metadata fields) to a sibling file `*.plot.txt`. This file contains the extracted metadata from `.nfo`, `.txt`, and `.log` plus the result of the plot comparison — useful for debugging and manual review.

**Missing NFO creation**
- The `--create-missing-nfo` flag in `add_rating.py` is deprecated. It prints a message pointing to the standalone scraper project at `C:/repos/scraper`.
- The scraper (`python -m scraper`) scans `*.mkv`/`*.mp4` files without a sibling `.nfo` and creates NFOs:
    1. `extract_txt_metadata()` extracts title, year, description, country, genre, and `bracketed_text_from_infoline` in one pass.
    2. Title candidates from the filename and metadata are collected.
    3. TMDb candidates are searched and evaluated (`find_matching_candidate_with_year_fallback()`, optionally `find_matching_candidate_by_title_contains_plot_fallback()`).
    4. The TMDb detail bundle is loaded, the NFO template is populated, ratings (TMDb + OMDb) are set via `upsert_rating()`, and the new `*.nfo` is persisted.
    5. `persist_nfo_and_refresh()` optionally updates `.plot.txt`.
- CLI flags: `--recursive`, `--skip-series`, `--plot-min-words`, `--low-score-threshold`, `--year-diff-threshold`, `--use-plot-similarity`, `--write-plot-comparison-data`, `--llm-candidate-min-score`, `--max-tokens-deep`, `--nfo-template`.

**CLI parameters (short explanation)**

This section explains the main command-line parameters as defined in `main()` and what effect they have on the behavior of `add_rating.py`.

- `source_dir` (positional): Source directory to scan (default: `.` — current directory).
- `output_file` (positional): Output file for results (default: `rating_output.txt`).
- `--max-days <int>`: Processes only NFO files older than the given number of days. `None` (default) = always process.
- `--max-days-plot <int>`: Same as `--max-days`, but only for using stored plot similarity data.
- `--low-score-threshold <float>`: Threshold for `nfo_score`; if the score is below it, the file is marked and rescrape/extra validation may be triggered (default: 12.0).
- `--year-diff-threshold <int>`: Maximum allowed year deviation before a `year_diff` trigger for rescraping is set (default: 3).
- `--plot-min-words <int>`: Minimum word count for a plot to be considered meaningful (default: 10).
- `--all-nfo-ok`: Marks all NFOs as okay (skips some checks), useful after manual verification.
- `--nfostatus-reset`: Resets `nfostatus`; useful after batch validation to restart checks.
- `--remove-ratings`: Removes all rating entries (test/reset mode).
- `--print-score`: Prints the calculated scores for files in addition to output/log.
- `--recursive`: Searches directories recursively instead of only top-level.
- `--use-plot-similarity`: Activates the plot similarity component of the score calculation (LLM/comparison logic is used if configured).
- `--write-plot-comparison-data`: Writes extracted metadata and comparison results to `*.plot.txt` files (useful for debugging and review).
- `--remove-orphan-md`: Removes orphaned metadata files (for example `.plot.txt` without a corresponding media file), if enabled.
- `--clean-nfo-filenames`: Trims leading/trailing whitespace and `-` from NFO filenames before processing.
- `--enable-rescraping`: Enables automatic rescraping (starting `start_rescraping()`) if score/year difference issues occur.
- `--create-missing-nfo`: **Deprecated.** Prints a deprecation message and exits, pointing to the standalone scraper at `C:/repos/scraper`. Use `python -m scraper` instead.
**Which metadata is extracted from which files (concrete mapping)**

The following points describe which fields `add_rating.py` typically extracts, from which files they come, and which sections within those files are used. Examples illustrate practical use.

- **`title` / `originaltitle`**
    - Source (context-dependent):
        - `*.txt` (recorder/EPG) — preferred source for describing what was actually recorded (title, year, region).
        - `*.nfo` — result of scraping (for example Kodi): provides the scraped `title`/`originaltitle` and is the target to verify.
        - Fallback/addition: filename `Tage, die bleiben.mkv` → basename `Tage, die bleiben`.
    - Examples:
        - `Tage, die bleiben.txt` line: `Tage, die bleiben - Deutschland, 2014` → recorder title = `Tage, die bleiben`, `year=2014`.
        - `Tage, die bleiben.nfo` contains `<title>Tage, die bleiben</title>` → scraped title; it is compared with recorder data and may be accepted or rejected.

- **`year` (release year)**
    - Primary: structured info line in `*.txt` (`TXT_META_PATTERN`), e.g. `Deutschland, 2014` or `2014` in parentheses in the filename `Tage, die bleiben (2014).mkv`.
    - Secondary: `<year>` in `.nfo`, if present (used to verify the scraper view).
    - Fallback: `*.log` lines are only scanned if no `*.txt` exists. Typical log lines: `Sender - Deutschland 2014` or `20:15 - Tage, die bleiben - 2014`.
    - Example `Tage, die bleiben.txt`:
        - Content: `Tage, die bleiben - Deutschland, 2014` → `year=2014`, `country=Deutschland`.

- **`country` / production country**
    - Primary: `*.txt` contents (for example `Deutschland / Österreich, 2014`) — preferred source for determining the production country.
    - Secondary: `<country>` tags in `.nfo` (if present), for verifying the scraped result.
    - Fallback: If `*.txt` is missing, `*.log` is searched for `LOG_META_LINE_STRICT_PATTERN` / `LOG_META_LINE_PATTERN` (provided no `*.txt` exists).
    - Example `Tage, die bleiben.log` (used only if no `.txt` exists):
        - Search for lines without technical markers such as `duration:`; e.g. `ARD - Deutschland 2014` → `country=Deutschland`, `year=2014`.

- **`plot` / description**
    - Primary: longer description sections in `*.txt` (recorder/EPG) — `.txt` sources are the primary source for plots/descriptions.
    - Secondary: `<plot>` in `.nfo` (scraped field) — used as the result to verify.
    - Derivation / output: `*.plot.txt` is a sibling file produced by the script (or it may already exist), containing aggregated plot/meta information from `*.txt`/`.log`/`.nfo` and used for LLM comparisons and scoring; it is not a primary source.
    - Fallback: `.log` is only used if no `*.txt` exists; technical/encoder lines are filtered (self-test pattern for recognizing technical markers).
    - Example `Tage, die bleiben.plot.txt`: full plot description (or a script-generated aggregation), normalized and used for LLM comparison.

- **`cast` / actors and roles**
    - Primary: `<actor>` / `<role>` sections in `.nfo`.
    - Secondary: Mentions in the `*.txt` description section (for example `With: Max Mustermann, Erika Beispiel`), rarely from `.log`.

- **`runtime` / duration**
    - Primary: `<runtime>` in `.nfo` (minutes).
    - Secondary: technical metadata in `.log` (for example `duration: 01:30:00`), only if `.txt` does not provide unambiguous information.

- **`uniqueid` / TMDb/IMDb IDs**
    - Only present in `.nfo` (if Kodi/scraper set them). They are used directly; if absent, TMDb searches are attempted, optionally complemented by `create_missing_nfo`.

- **Filename fields and bracketed content**
    - Additional information such as year brackets `(... )`, language/cut hints, or Director's Cut suffixes is extracted from the filename (for example `Tage, die bleiben - Director's Cut.mkv` → pure title normalization; Director variants are added as extra candidate titles).

Important: priority order for extraction and verification

- Context: `.nfo` files are usually the result of an external scraping process (for example via Kodi) and represent an external metadata view. For verification, correction, and enrichment of NFOs, the local recorder metadata has priority because it describes the actual recording.

- Priority (for obtaining recorder metadata and verifying `.nfo`):
    1) `*.txt` (info/timer/description): highest priority — typically contains human-readable timer/EPG lines, year/region, and possibly plot fragments.
    2) `*.log` (only if no `*.txt` exists): older recordings or lost `.txt` files mean that relevant metadata is consolidated in `.log`; technical/encoder lines are filtered, and semantic info lines are extracted.
    3) `*.nfo` (scraped result): used as the target to verify — `add_rating.py` uses `.nfo` primarily to decide whether scraping was correct (match vs. recorder metadata) and whether enrichment (ratings/plot) makes sense.
    4) Filename / image siblings: auxiliary sources for title variants and to recognize complete datasets.

Historical note: In older archives, `txt` and `log` contents were often stored in a single `*.log` file. There are also cases where the `*.txt` was lost; in such cases, `*.log` is used as the primary local source if meaningful semantic lines are present.

Implementation note (code location):
- `add_rating.py` uses `_extract_txt_metadata()` to extract title, year, countries, and description from `*.txt`.
- `_extract_log_meta_year_and_countries()` / `_extract_log_metadata()` extract analogous fields from `*.log` files — but these are only called when `*.txt` is absent (see `create_missing_nfo_from_mkv()` and the fallback logic when extracting `bracketed_text_from_infoline`).

Episode information in the `.mkv`/`.mp4` filename

Most episode information appears in parentheses.
Examples:
Zora kocht's einfach (7) - Vegetarischer Vorspeisenteller.mkv
Zora kocht's einfach (2_10) - Variationen mit Ziegenfrischkäse.mkv
Wer weiß denn sowas (1188) - Gäste Ingo Zamperoni und Hannah Emde.mkv
Petrocelli (S01_E01) - Der goldene Käfig.mkv
Die Meute 2x07.mkv
Agatha Christie Mörderische Spiele - Mord beim Schulfest (Staffel 2, Folge 5) -.mkv

A four-digit number in parentheses at the end of the `.mkv`/`.mp4` filename is instead a year.
Aschenputtel (2011).mkv

Less commonly, episode information is purely textual.
Bianca - Wege zum Glück - Kapitel 16.mkv
Luther - Folge 5.mkv

---

## RunConfig fields (overview)

The `RunConfig` dataclass is the central configuration object passed through the entire pipeline. All CLI flags are mapped into `RunConfig` fields exactly once in `main()`. Global variables for configuration are forbidden.

Implementation note (code location):
- `add_rating.py` uses `extract_txt_metadata()` (from `movie_metadata.metadata`) to extract title, year, countries, and description from `*.txt`.
- `extract_log_meta_year_and_countries()` / `_extract_log_metadata()` extract analogous fields from `*.log` files — but these are only called when `*.txt` is absent (fallback logic in `create_missing_nfo_from_mkv()` in `C:/repos/scraper`).

Note: The known bugs around `year_diff_threshold` and `--llm-candidate-min-score` are fixed — both defaults are now `3` and `3.0` in both `RunConfig` and the `add_argument` definition.

---

## Constants and environment variables

| Constant | Environment variable | Default | Description |
|-----------|------------------|---------|-------------|
| `LLM_TIMEOUT` | `ADD_RATING_LLM_TIMEOUT` | `2.0` seconds | Timeout for LLM availability probes |
| `DEBUG_LLM_SELECTION` | `ADD_RATING_DEBUG_LLM=1` | `False` | Enables debug output for client selection |
| `FASTMODEL` | – | `None` (disabled) | Fast LLM model for pre-filtering |
| `DEEPMODEL` | – | `llama3:8b-instruct-q5_K_M` | Main LLM model for deeper analyses |

Global caches (all protected by `threading.RLock`):
- `UNAVAILABLE_MODELS_BY_CLIENT` — unavailable models per client
- `VERIFIED_MODELS_BY_CLIENT` — successfully verified models per client
- `SMART_COMPARE_CACHE` — deduplication of identical `smart_compare()` calls
- `active_client_key` — currently active client key (set by `get_client_for_call()`)

---

## Important functions at a glance

### LLM client architecture

| Function | Description |
|----------|-------------|
| `probe_instance()` | Calls `/models` on an Ollama/OpenAI server to check availability |
| `check_ollama_instance_and_model()` | Simple availability check for instance + model |
| `is_instance_available()` | Checks with caching whether an instance + model is available |
| `select_client()` | Chooses the first available client (preferred > fallback) |
| `get_client_for_call()` | Returns the OpenAI client + key; switches to fallback when needed |
| `ensure_llm_preflight()` | Startup-time check; raises `RuntimeError` if no client is available |
| `_llm_call_with_client_fallback()` | Executes the LLM call; if the model is not found, it switches to an alternative client |

### Relaxed fallback in `_find_matching_candidate_with_year_fallback()`

If all candidates are removed by title filters, the raw TMDb results are re-evaluated by LLM plot comparison (threshold `0.75`). This also allows foreign-language titles to be found.

### Title-contains fallback

`_find_matching_candidate_by_title_contains_plot_fallback()` — final fallback after an unsuccessful year-based search: candidates whose title contains the search title (or vice versa) are evaluated via `compare_nfo_with_external`. Requirement: sufficiently long TMDb plot (>= `plot_min_words`).

### Self-test

`run_log_description_selftest()` — checks whether log descriptions are free of technical lines. It is started via `--selftest-log-extraction`.

---

## NFO template

`nfo_template.nfo` is used by default to preserve element order in `create_missing_nfo_from_mkv()`. If the template file is missing, an in-memory minimal NFO is built.

---

## `ensure_llm_preflight` requirement

If `--use-plot-similarity` is set, `ensure_llm_preflight()` must complete successfully before processing starts; otherwise the script exits with code 2. NEVER bypass this check.
