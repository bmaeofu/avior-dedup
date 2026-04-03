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

WORKDIR /app

# Install the Python package
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

CMD GIT_HASH=$(cat /app/git_hash.txt 2>/dev/null || echo unknown); \
    export GIT_HASH; \
    exec avior-dedup-server
