# Base44 Platform — nafs TUI, nafs logic, nafs pages

Clone platform **rebuilt from scratch** (mch proxy mta3 the prod code):
workspace, agent builder, app pages, data, publish flow — el visualidl kmar
tokens **el 7a9i9in** mta3 base44 (stone/orange/Dazzed), same favicon/fonts.

## Screens (hash routes, like base44)

| route | page |
|---|---|
| `#/login` | Auth (signup + login + demo workspace) |
| `#/` | Home: hero prompt ("Build useful apps, fast with Base44.") + apps grid + credits |
| `#/app/:id` | **Builder**: agent chat (left) + Preview iframe / Code / Data / Logs / Publish tabs |
| `#/explore` | Templates: CRM, Task Manager, Blog, Expense Tracker, Notes |
| `#/settings` | Account/workspace/session |
| `/p/:slug` | **Published public app** (runtime w/ entity tables + CRUD) |

## Agent logic (server-side, deterministic NL → app spec)

- Templates detector: CRM / tasks / blog / expenses / notes → seeded entities
  (fields, types, sample rows) + pages.
- Generic fallback: invents entity from prompt nouns.
- Turn instructions: "add entity for X", "add page Y", "theme purple / #RRGGBB",
  "rename it Z" — mutates spec, regenerates files, consumes **0.4 credits**
  (limit 20/day, 402 when dry).
- Code tab shows generated `entities/*.js` + `pages/*.jsx` runtime-source.

## API (JSON + Bearer)

```
POST /api/auth/signup|login|logout    GET /api/me
GET  /api/workspaces                  GET /api/credits
GET  /api/workspace_apps              POST /api/apps (prompt|empty shell)
GET/PATCH/DELETE /api/apps/:id        POST /api/apps/:id/agent
POST /api/apps/:id/publish            GET /api/apps/:id/logs
GET  /api/published/:slug   (public)  GET /p/:slug (runtime page)
401 guard on everything private; catch-all /api fallback disabled here.
```

Storage: `data/db.json` (+ per-app logs). Sessions: bearer tokens.

## Run

```sh
cd base44-platform && python3 server.py   # → http://localhost:8510
```

Open `http://localhost:8510` → login screen → demo button → home → build.

### UI root selection (server.py)

`server.py` serves the first existing root, in order:
`./dist` (built React) → `../base44-react/dist` → `./www` (vanilla fallback).
Build `base44-react` once (`pnpm build`) and the React app is served automatically.

## Docker

No daemon here — the repo ships the compose recipe; run it on any docker host:

```sh
git clone https://github.com/Youssefzdb/base44-platform   # this repo
git clone https://github.com/Youssefzdb/base44-react      # sibling dir
cd base44-platform
docker compose up --build      # → http://localhost:8510
```

Multi-stage: `node:24-alpine` (pnpm → vite build of the React app via the
`react` named build-context) → `python:3.14-slim` runtime (stdlib-only server),
non-root user, healthcheck on `/index.html`.

## Release

```sh
GITHUB_TOKEN=ghp_xxx ./release.sh [version]   # default: date-based
```

Rebuilds the frontend, packages `server.py + www + dist + tests` into
`base44-platform-<ver>.tar.gz`, creates the GitHub Release and uploads the asset.

**v1.0.0 shipped:**
https://github.com/Youssefzdb/base44-platform/releases/download/v1.0.0/base44-platform-1.0.0.tar.gz
(695 KB — unpacked & smoke-tested: index 200, chunk 243 KB, API auth guard live)

## Browser e2e (Playwright)

```sh
python3 -m pip install playwright && python3 -m playwright install chromium
python3 server.py &                       # :8510
python3 tests/browser_test.py             # exit 0 = pass
```

Real chromium drives the REAL react build — 8 checks:

```
✓ 1. login card              ✓ 5. code viewer has entity
✓ 2. hero after demo login   ✓ 6. dark class applied (pre-paint)
✓ 3. builder loaded          ✓ 7. runtime entity table (iframe)
✓ 4. agent steps rendered    ✓ 8. publish + custom domain input
{"pass": 8, "fail": 0}
```

## Verification (e2e done)

- [x] auth flow (login/signup/demo) + 401 guard
- [x] create app from prompt → CRM template seeded (entities Customer/Follow-up, pages Pipeline/New Customer)
- [x] agent turn "Add entity for invoices" → spec grew, credits 20 → 18.1
- [x] page turn + theme turn → files regenerated (7 files), accent #4d33de
- [x] publish → state live, slug `crm`, public `/api/published/crm` NO auth
- [x] `/p/crm` runtime page served (5.3 KB)
- [x] logs recorded per app

## AI agent (OpenAI — tool calls + thinking, SSE)

Keys: `/gpt.txt` (7 project keys, comma-separated; loaded at boot, **rotated on 401/429**,
models fallback `gpt-4.1-mini → gpt-4o-mini → gpt-4o`). Keys are never stored in the repo.

`AGENT` endpoint: `POST /api/apps/:id/agent/stream` (SSE). Event chain:

```
start → thinking → tool* → preview → tool* … → done(+credits)     (AI mode)
start (template) → step* → done                                  (fallback, B44_DISABLE_AI=1)
```

Tools the model calls (executed deterministically by the backend → spec + code files):
`think(plan)` · `upsert_entity(name, fields, seed_rows)` · `add_page(name, type, entity)`
· `set_theme(accent_rgb_hex)` · `rename_app(name)` · `set_summary(text)`

- **thinking** = the model's plan streamed live into the chat UI.
- **preview** event emitted on every spec mutation → React bumps the runtime iframe (`rev=`)
  → **live preview** re-renders while the agent applies changes.
- **create** (`POST /api/apps` with prompt) is AI-first too: baseline spec built entirely via tool calls.
- Every event is persisted: `logs_<app>.jsonl`, app `ai_history` (last 8 msgs as model context).

Verbose smoke (real Expectations): `AI create ~12s`, turn `~5-7s`.


## lp.dev sandbox (`s` tool — remote runner)

`/usr/local/bin/s` → `/root/s.py`: a thin shell over the **lp.dev terminal sandbox** (remote Linux
container; python 3.13 / node 26 / bun 1.3, open egress). Rate-limited by the lp.dev Cloudflare
edge (~1 call / 20s from the same IP). Two integration tools use it:

| Tool | What it does |
|---|---|
| `tools/sandbox_check.sh` | ships a **lean tarball** (server + runtime.html, no data/, no vendor) → remote `py_compile` → boots `B44_DISABLE_AI=1` server → 6 smoke steps (login, create, publish, /p) — **no OpenAI keys ever leave the host** |
| `tools/sandbox_jsx_check.py <app_id>` | pulls the app's `gen_files` → remote **bun Transpiler** parses every .jsx/.js → per-file OK/BAD verdict |

```sh
bash tools/sandbox_check.sh
python3 tools/sandbox_jsx_check.py a_bb0f216e70 http://localhost:8510 /tmp/siteapp3.txt
```

`tests/ai_site_test.py` runs the remote bun parse automatically as check **6** when `s` is on PATH
(skipped gracefully otherwise).
