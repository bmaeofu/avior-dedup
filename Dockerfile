# ---- Stage 1: Build frontend ----
FROM node:22-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile

COPY frontend/ ./
RUN pnpm build

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
ENV AVIOR_DEDUP_HOST=0.0.0.0
ENV AVIOR_DEDUP_PORT=8642
ENV AVIOR_DEDUP_FRONTEND_DIST=/app/frontend-dist
ENV AVIOR_DEDUP_CONFIG_DIR=/config

VOLUME /config

EXPOSE 8642

CMD ["avior-dedup-server"]
