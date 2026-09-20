# Multi-stage Docker build for PQ-FORENSIC on Render / Docker
# Stage 1: Build Frontends (React / Vite)
FROM node:20-alpine AS frontend-builder
WORKDIR /app

COPY package.json ./
COPY scripts/build.js ./scripts/
COPY ui/package*.json ./ui/
COPY web/package*.json ./web/

RUN cd ui && npm install
RUN cd web && npm install

COPY ui/ ./ui/
COPY web/ ./web/

RUN node scripts/build.js

# Stage 2: Python Backend & Unified Server
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
RUN pip install --no-cache-dir -e .

COPY demo_seed/ ./demo_seed/
COPY demo-docs/ ./demo-docs/
COPY --from=frontend-builder /app/dist ./dist

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn pqfw_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
