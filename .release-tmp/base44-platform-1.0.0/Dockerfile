# syntax=docker/dockerfile:1
# ── Base44 platform ─ one container: built React UI (from base44-react repo)
#                        + mock-API backend (this repo's server.py).
#
# The frontend repo is attached as a NAMED BUILD CONTEXT called `react`:
#   docker compose up --build              (compose wires extra context)
#   # or standalone docker:
#   docker build -t base44-platform --build-context react=../base44-react .

# ── stage 1: build the React frontend ───────────────────────────────────────
FROM node:24-alpine AS front
WORKDIR /fe
COPY --from=react package.json pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY --from=react ./ .
RUN pnpm build                      # → /fe/dist (index + assets + runtime.html)

# ── stage 2: runtime (stdlib-only python server) ────────────────────────────
FROM python:3.14-slim
WORKDIR /srv
RUN useradd -m base44
COPY server.py ./
COPY www ./www                      # vanilla fallback UI
COPY --from=front /fe/dist ./dist   # react build wins (server.py auto-picks)
RUN mkdir -p /srv/data && chown -R base44:base44 /srv
USER base44
ENV PORT=8510
EXPOSE 8510
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD python3 -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8510/index.html')"
CMD ["python3", "server.py"]
