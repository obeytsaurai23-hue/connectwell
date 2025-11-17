# Connectwell — Copilot instructions

This file gives concise, actionable guidance to an AI coding agent working in the Connectwell repository. Focus on precise, local conventions, important files, and developer workflows so you can be productive quickly.

## Big picture (what this project is)
- Backend: Django (ASGI) app in `backend/` with Channels for realtime. Key apps: `accounts`, `chat`, `payments`.
- Frontend: Vanilla HTML/JS under `frontend/` used for local demos (chat UI, mock checkout, wallet pages).
- Data & runtime: SQLite for dev/tests, Redis used for the channel layer and matchmaking when `REDIS_URL` is set, WebRTC for peer media (client-side). Payments are scaffolded around a provider webhook (Yoco) and a local `mock_checkout.html` for dev.

## Where to look first (quick map)
- `backend/manage.py`, `backend/connectwell/settings.py` — run/test/migrations entrypoints.
- `backend/accounts/` — custom `User` model (UUID PK) and auth flows (email+PIN). See `models.py`, `views.py`, `serializers.py`.
- `backend/chat/` — matchmaking and blur/unblur logic. See `consumers.py` (WebSocket pairing, Redis queue, Lua pairing), `models.py` (MatchSession), and `views.py` (session actions like `/unblur/`).
- `backend/payments/` — `Order`, `WalletTransaction`, `WebhookEvent` models and `views.py` for purchase creation and `YocoWebhookView` handling webhook events.
- `frontend/` — `chat_demo.html`, `mock_checkout.html`, `login.html`, `lobby.html`, `wallet.html`, and `style.css` (dev styling). The dev server serves these under `/demo/` when `DEBUG=True`.
- `coins_config.json` — coin packs and pricing used by payment logic.
- `docker-compose.yml` — optional services (Redis, TURN) referenced in README but not required for basic local flow.

## Key design & patterns to preserve
- UUID primary keys for users/sessions (see `accounts.models.User` and `chat.models.MatchSession`).
- Unblur/charge flow is session-scoped: `MatchSession.unblur_price` and `user_a_unblurred`/`user_b_unblurred` indicate per-session visibility. Modifying this logic requires updates in `chat/consumers.py` and `chat/views.py`.
- Webhook idempotency: `payments.models.WebhookEvent` records processed event ids. Webhook handler reads raw request body and optionally verifies HMAC via `YOCO_WEBHOOK_SECRET` (see `payments/views.py`). Maintain idempotency checks when changing webhook code.
- Redis reverse mappings: consumers store `connectwell:user_channel:{user_id}` and `connectwell:channel_user` to map WebSocket channels ↔ user ids. Use `get_redis()` helpers in `chat/consumers.py`.
- Matchmaking uses an atomic Lua script (`PAIR_LUA`) to pop two items atomically from a Redis list — don't replace with non-atomic pops unless a safe alternative is used.

## Developer workflows (how to run, test, debug)
- Setup & venv: project uses a virtualenv in examples; ensure you use the Python that the workspace uses.
- Run tests (from `backend/`):
```powershell
# run Django tests from backend directory
cd backend
C:\path\to\python.exe manage.py test --verbosity=2
```
- Run dev server (serve backend + frontend demo at `/demo/`):
```powershell
cd backend
$env:MOCK_CHECKOUT='1'   # optional: make purchases route to local mock checkout
C:\path\to\python.exe manage.py runserver
# demo pages available at http://127.0.0.1:8000/demo/
```
- Debugging tips:
  - If static demo pages return 404 under `/demo/`, check `backend/connectwell/urls.py` for `FRONTEND_ROOT` and that `DEBUG=True`.
  - For webhook debugging, `mock_checkout.html` posts to `/api/v1/webhooks/yoco/` to emulate provider events.
  - When making changes in Channels code, restart the dev server; in-memory channel layer is used if `REDIS_URL` is unset (tests default to in-memory layer).

## Integration points & external dependencies
- Redis (optional): `REDIS_URL` environment variable enables `channels_redis` channel layer and matchmaking queue persistence.
- Payment provider (Yoco): webhook endpoint at `/api/v1/webhooks/yoco/`. Production requires setting `YOCO_WEBHOOK_SECRET` and verifying signatures.
- WebRTC: client-side uses STUN servers (see `frontend/chat_demo.html`), TURN is optional and referenced in `docker-compose.yml`.

## Project-specific conventions
- Anonymous quick-mode: clients may obtain a short anonymous token via `/api/v1/auth/continue_anonymous` and use it in WebSocket connect query `?token=...`. Frontend stores tokens in localStorage keys like `anon_token` and `access_token`.
- Auto-buy flow: Users have `auto_unblur` and `auto_buy_coins` flags on `User` to allow the server to automatically create orders and attempt purchases (dev-only behavior controlled by `AUTO_COMPLETE_PURCHASES`).
- Database migrations: migrations are authoritative; if adding or changing models, update migrations (see `backend/payments/migrations/0001_initial.py` which includes `WebhookEvent`). Tests run migrations into an in-memory sqlite DB.

## Quick examples for common tasks
- To simulate a purchase locally:
  1. POST to `/api/v1/coins/purchase` (pack_id in body). Server returns `order_id` and `checkout_url`.
  2. Open `/demo/mock_checkout.html?order_id=<order_id>` or let the modal iframe load it. Click "Pay now" to POST a simulated webhook and postMessage to the parent page.
- To trace a matchmaking flow: read `chat/consumers.py` (enqueue -> PAIR_LUA -> MatchSession create -> notify peers). Use the WebSocket debug logs in `chat_demo.html` to see actions like `match_found` and `unblur`.

## What to change carefully
- Changing the atomic queue pairing (Lua) or Redis key names requires updating consumers and any code that reads `connectwell:user_channel` or `connectwell:channel_user`.
- Changing webhook payload parsing must preserve the raw-body read + optional HMAC verification and idempotency via `WebhookEvent`.
- Modifying `MatchSession` fields or the unblur charge flow requires updating tests in `backend/chat/tests.py` and `backend/payments/tests.py`.

## Files to reference during edits
- `backend/chat/consumers.py`, `backend/chat/views.py`, `backend/chat/models.py`
- `backend/payments/views.py`, `backend/payments/models.py`
- `backend/accounts/models.py`, `backend/accounts/views.py`
- `frontend/chat_demo.html`, `frontend/mock_checkout.html`, `frontend/style.css`
- `coins_config.json` (pack ids/prices)

## Tone and scope for edits
- Be minimally invasive: prefer small, well-tested changes. Follow existing patterns (UUID pks, atomic Redis ops). Update tests where behavior changes.
- When adding new dev-only features (mock pages, `/demo/` serving), keep them gated by `DEBUG` or env vars (e.g., `MOCK_CHECKOUT`) and document usage in README.

---
If anything above is unclear or you'd like a shorter/longer tone, or additional examples (e.g., how to write a Playwright test for the buy->webhook->unblur flow), tell me which section to expand and I will iterate.
