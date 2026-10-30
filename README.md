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

## Verification (e2e done)

- [x] auth flow (login/signup/demo) + 401 guard
- [x] create app from prompt → CRM template seeded (entities Customer/Follow-up, pages Pipeline/New Customer)
- [x] agent turn "Add entity for invoices" → spec grew, credits 20 → 18.1
- [x] page turn + theme turn → files regenerated (7 files), accent #4d33de
- [x] publish → state live, slug `crm`, public `/api/published/crm` NO auth
- [x] `/p/crm` runtime page served (5.3 KB)
- [x] logs recorded per app
