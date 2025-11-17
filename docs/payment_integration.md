# Yoco Payment Integration Notes

Goal: accept USD payments for coin packs and subscriptions via Yoco.

Important considerations
- Yoco supports card payments and hosted checkout flows. Use server-side endpoints to create transaction intents and return checkout links/tokens to the client.
- Ensure currency mapping: USD. Validate supported currencies in the Yoco account.
- Always verify webhook signatures on the server before processing events.
- Use idempotency keys for server-side purchase creation to avoid double-charges.

Suggested flow (Coins)
1. Client calls POST /api/v1/coins/purchase with pack_id.
2. Server creates an order record and a Yoco checkout session (or token) with metadata: user_id, pack_id, order_id.
3. Return checkout_url to client. Client opens in a new window/tab.
4. Yoco redirects to your success URL or sends webhook to /api/v1/webhooks/yoco.
5. On webhook payment_success, verify signature, mark order paid, credit user coins, and notify client via WS or push.

Suggested flow (Subscription)
1. Client requests /api/v1/subscriptions/create for plan_id (premium_monthly).
2. Server creates a subscription session with Yoco and returns checkout link.
3. On successful subscription activation via webhook, mark user as premium, grant monthly 50 coins.
4. Handle subscription_renewal and subscription_canceled via webhooks.

Security
- Store Yoco webhook secret in env and never in client-side code.
- Use HTTPS endpoints and validate all incoming data.

Testing
- Use Yoco sandbox/testing keys for local dev and test both one-time purchases and recurring subscriptions.

Idempotency & refunds
- Maintain order records and map Yoco transaction IDs to local transactions to support refunds and disputes.

