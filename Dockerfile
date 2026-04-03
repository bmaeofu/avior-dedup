# ---- Stage 1: Build frontend ----
FROM node:22-alpine AS frontend-build

RUN corepack enable && corepack prepare pnpm@10.33.0 --activate

ARG GIT_HASH=unknown

WORKDIR /app/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN VITE_GIT_HASH=${GIT_HASH} pnpm run build

# ---- Stage 2: Production image ----
FROM python:3.12-slim

WORKDIR /app

# Install the Python package
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist /app/frontend-dist

# Environment defaults
ARG GIT_HASH=unknown
ENV AVIOR_DEDUP_HOST=0.0.0.0
ENV AVIOR_DEDUP_PORT=8642
ENV AVIOR_DEDUP_FRONTEND_DIST=/app/frontend-dist
ENV AVIOR_DEDUP_CONFIG_DIR=/config
ENV GIT_HASH=${GIT_HASH}

VOLUME /config

EXPOSE 8642

CMD ["avior-dedup-server"]
