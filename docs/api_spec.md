# API Specification (Connectwell)

Base: /api/v1

## Auth

POST /api/v1/auth/send_pin
- Body: { "email": "user@example.com" }
- Action: generate 4-digit PIN, store hashed with expiry (5-10 minutes), email PIN to address via transactional email provider (SendGrid/Postmark)
- Rate-limit: e.g., 5 sends per hour per email and per IP
- Response: { "ok": true, "message": "PIN sent" }

POST /api/v1/auth/verify_pin
- Body: { "email": "user@example.com", "pin": "1234" }
- Action: verify PIN, create or fetch user, issue JWT session token and mark as verified
- Response: { "token": "<JWT>", "user": { "id": 1, "email": "...", "is_verified": true, "coins": 0, "is_premium": false } }

POST /api/v1/auth/continue_anonymous
- Body: {}
- Action: create ephemeral anon session and return token stored in localStorage
- Response: { "token": "<anon-token>", "user": { "id": null, "anon_id": "..." } }

## Wallet / Coins

GET /api/v1/wallet
- Auth: optional (anon token or JWT)
- Response: { "coins": 120 }

POST /api/v1/coins/purchase
- Body: { "pack_id": "starter_pack" }
- Action: create payment intent with Yoco, return checkout URL/token for client
- Response: { "checkout_url": "https://yoco..." }

POST /api/v1/coins/confirm
- Body: { "transaction_id": "..." }
- Action: confirm via webhook or client callback, credit coins

POST /api/v1/coins/spend
- Body: { "action": "unblur", "cost": 20 }
- Auth: required for spending coins
- Action: debit coins, return success or failure

## Subscriptions

POST /api/v1/subscriptions/create
- Body: { "plan_id": "premium_monthly" }
- Action: create subscription with Yoco, return checkout

POST /api/v1/webhooks/yoco
- Action: verify signature, handle events: payment_success, subscription_renewal, subscription_cancel

## Chat & Matchmaking (HTTP)

POST /api/v1/chat/start
- Body: { "mode": "video", "interests": ["music"], "filters": { } }
- Response: { "status": "queued" }

POST /api/v1/chat/next
- Body: { "session_id": "..." }
- Action: mark session ended and enqueue user for next match. Track "next" counts for ad logic.

## WebSocket (ASGI) — /ws/chat/

Events:
- connect: client sends auth token for session
- enqueue: { "action": "enqueue", "mode": "video", "filters": {} }
- match_found: server -> { "peer_id": "...", "session_id": "..." }
- signal: SDP/ICE messages for WebRTC
- chat_message: { "text": "..." }
- next: { "reason": "skip" }
- ad_required: server -> { "ad_url": "..." }

Notes
- Keep signaling messages small and stateless. Use Redis for transient session mapping.
- Authenticate WS connections via token passed as query param or initial message, and enforce expiry.

