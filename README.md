# Avior Tools

Finds and cleans up duplicate media files in DVR recording libraries. If you record TV, you end up with multiple copies of the same thing -- different encodings, leftover metadata, multichannel and stereo versions with different error counts. This tool sorts through that mess.

## How it works

You point it at a source directory and it groups files into duplicate sets. Three matching modes:

- **Case-insensitive** -- same name, different capitalization
- **Exact** -- identical filenames in different subdirectories
- **Semantic** -- strips configurable prefixes (e.g. "Terra X -"), drops episode numbers, collapses punctuation, then compares what's left

Once it finds duplicates, it picks which copy to keep based on:

- Whether there's actually a video file (or just orphaned metadata)
- Multichannel audio (AC3 5.x) over stereo, when available
- Video resolution from timer/recording lines (higher wins)
- Encoding error count from `.log` files
- Allowed duration delta window (`video_duration - rec_duration`) with separate limits for longer/shorter
- Recording date from `.log` files (preferred when configured)

Selection behavior notes:

- Default priority order: `multichannel`, `resolution`, `fewer_errors`, `recording_date`, `closest_duration`.
- Multichannel detection uses the recording-start section of `.log` files: the last AC3 audio state within the first ~15 seconds after `Start`/`Start Recording` decides.
- Resolution detection uses the recording-start section of `.log` files: the last video resolution in the first ~15 seconds decides (e.g. `1920x1080` and `1920x1088` are treated as `1080`).
- Trailing `avior-go` metadata is excluded from log-based analysis.
- `recording_date` prefers newer recordings when present; if a recording has no `rec_date`, the filesystem `mod_date` is used as a fallback only when `recording_date` is part of the active priority list.
- `closest_duration` only penalizes candidates that fall outside the configured duration thresholds; recordings within the allowed window are treated as equal for that criterion.

Everything that isn't the best copy gets moved out: normal duplicates to one directory, error-laden copies to another, orphaned metadata to a third. You can also run in dry-run mode to just see what it would do before committing.

## Installation

Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Usage

### CLI

```bash
# Dry run -- find duplicates, don't move anything
uv run avior-dedup f /path/to/source /path/to/target log.txt --duptype case

# Move duplicates, keep the ones with fewer errors
uv run avior-dedup m /path/to/source /path/to/target log.txt \
  --duptype semantic \
  --prefer-errors \
  --max-errors-when-mc 3 \
  --max-duration-diff-longer 600 \
  --max-duration-diff-shorter 600

# Semantic matching with custom prefix stripping
uv run avior-dedup f /path/to/docs /path/to/target log.txt \
  --duptype semantic \
  --semantic-prefixes "terra\s*x\s*-\s*" "^erlebnis\s+erde\s*-?\s*" \
  --remove-episode-nos
```

### Web UI

There's also a web interface (FastAPI + Vue 3 + Vuetify 3).

```bash
uv run avior-dedup-server   # API + frontend on port 8642
```

You get a job form with all the CLI options as proper controls, live progress over WebSocket, results with action stats, and a config editor for the YAML files. Supports light and dark mode.

### Docker

A combined image bundles the frontend and backend. Config files are seeded into the mounted volume on first start.

```yaml
# docker-compose.yaml
services:
  avior-dedup:
    build: .
    # or: image: ghcr.io/your-org/avior-dedup:latest
    ports:
      - "8642:8642"
    volumes:
      - ./config:/config         # YAML config files (seeded on first run)
      - /mnt/media:/mnt/media    # make your media directories accessible
    environment:
      - AVIOR_DEDUP_PORT=8642    # optional, 8642 is default
```

| Variable | Default | Description |
|---|---|---|
| `AVIOR_DEDUP_HOST` | `0.0.0.0` | Server bind address |
| `AVIOR_DEDUP_PORT` | `8642` | Server port |
| `AVIOR_DEDUP_CONFIG_DIR` | `/config` | Config directory (mounted volume) |

```bash
docker compose up -d
```

### Frontend development

Frontend is in `frontend/`, built with Vite. A nix shell provides pnpm:

```bash
nix-shell
cd frontend
pnpm install
pnpm dev       # Dev server, proxies API to localhost:8642
pnpm build     # Production build to frontend/dist/
```

## Configuration

Keyword lists and filters live in YAML files under `src/avior_dedup/config/`. You can edit them from the web UI or directly:

- `ignored_files.yaml` -- filenames to skip
- `ignored_dirs.yaml` -- directories to skip
- `suffixes.yaml` -- file suffixes and video extensions
- `episode_keywords.yaml` -- keywords that prevent episode number stripping in semantic mode
- `path_suggestions.yaml` -- directory suggestions for the web UI dropdowns

## Project layout

```
src/avior_dedup/
├── cli.py              # CLI entry point
├── config/             # YAML config files and loader
├── dedup/              # Core dedup logic
│   ├── scanner.py      # Directory walking, duplicate detection
│   ├── planner.py      # Move plan building and execution
│   ├── reporting.py    # Log sorting and summary
│   ├── normalize.py    # Filename normalization
│   ├── suffix.py       # Suffix matching
│   └── models.py       # FileRecord, MoveAction
└── server/             # Web interface
    ├── server.py       # FastAPI + WebSocket progress
    ├── schemas.py      # Pydantic models
    └── progress.py     # Thread-safe progress reporter
```
