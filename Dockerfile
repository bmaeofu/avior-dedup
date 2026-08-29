# ---- Stage 1: Build frontend ----
FROM node:22-alpine AS frontend-build

RUN corepack enable && corepack prepare pnpm@10.33.0 --activate

WORKDIR /app

# Copy .git metadata (heavy dirs excluded via .dockerignore) for commit hash
COPY .git .git

WORKDIR /app/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./

# Resolve git hash from .git metadata (no git binary needed).
# Reads HEAD, follows ref pointer, checks refs/ then packed-refs.
RUN GIT_HEAD=$(cat /app/.git/HEAD); \
    if echo "$GIT_HEAD" | grep -q "^ref: "; then \
      REF=$(echo "$GIT_HEAD" | sed 's/^ref: //'); \
      if [ -f "/app/.git/$REF" ]; then \
        HASH=$(cat "/app/.git/$REF"); \
      elif [ -f "/app/.git/packed-refs" ]; then \
        HASH=$(grep "$REF" /app/.git/packed-refs | head -1 | cut -d' ' -f1); \
      fi; \
    else \
      HASH=$GIT_HEAD; \
    fi; \
    export VITE_GIT_HASH=$(echo "${HASH:-unknown}" | cut -c1-7); \
    echo "Building frontend with git hash: $VITE_GIT_HASH"; \
    echo "$VITE_GIT_HASH" > /app/git_hash.txt; \
    pnpm run build

# ---- Stage 2: Production image ----
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# git wird für pip install git+https:// benötigt (fehlt in Debian-slim-Basis).
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Zentrale Library movie_metadata aus ihrem PRIVATEN Git-Repo installieren.
# Komodo reicht einen GitHub-Token als Build-Arg GIT_TOKEN durch (nur zur
# Build-Zeit, landet nicht im finalen Image). Der Token wird URL-encoded in
# die pip-git-URL eingebettet, damit Sonderzeichen nicht brechen.
ARG MOVIE_NFO_LIB_REF=v1.0.9
ARG GIT_TOKEN
RUN if [ -z "$GIT_TOKEN" ]; then \
      echo "FEHLER: Build-Arg GIT_TOKEN ist leer. In Komodo Stack-Environment setzen."; \
      exit 1; \
    fi \
 && TOKEN_URLENC=$(printf '%s' "$GIT_TOKEN" | sed 's/@/%40/g; s/:/%3A/g; s/\//%2F/g') \
 && git ls-remote "https://x-access-token:${TOKEN_URLENC}@github.com/bmaeofu/movie_nfo_lib" >/dev/null \
 && echo "Klon-Zugriff auf movie_nfo_lib OK" \
 && pip install --no-cache-dir --progress-bar off "movie-metadata @ git+https://x-access-token:${TOKEN_URLENC}@github.com/bmaeofu/movie_nfo_lib@${MOVIE_NFO_LIB_REF}" \
 && unset TOKEN_URLENC

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist /app/frontend-dist

# Copy git hash
COPY --from=frontend-build /app/git_hash.txt /app/git_hash.txt

# Environment defaults
ENV AVIOR_DEDUP_HOST=0.0.0.0
ENV AVIOR_DEDUP_PORT=8642
ENV AVIOR_DEDUP_FRONTEND_DIST=/app/frontend-dist
ENV AVIOR_DEDUP_CONFIG_DIR=/config

VOLUME /config

EXPOSE 8642

USER 99:100

CMD GIT_HASH=$(cat /app/git_hash.txt 2>/dev/null || echo unknown); \
    export GIT_HASH; \
    exec avior-dedup-server
