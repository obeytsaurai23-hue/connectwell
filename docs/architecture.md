# Connectwell Architecture (Overview)

## High-level components

1. Web Client (mobile-first)
   - Landing / Auth / Lobby / Chat pages
   - Handles WebRTC peer connection for media
   - Uses WebSocket for signaling and real-time events

2. Backend API (Django + DRF)
   - REST endpoints for auth (email PIN), coins, purchases, subscriptions
   - Admin panel for moderation and analytics

3. Realtime Layer (Django Channels)
   - WebSocket endpoints for signaling, chat messages, match events
   - Redis as the channel layer + matchmaking queue

4. Media (WebRTC)
   - STUN/TURN (coturn) for NAT traversal
   - Clients perform direct P2P connections where possible; fallback to media relay when necessary

5. Data Stores
   - PostgreSQL: users, wallets, transactions, matches, subscriptions
   - Redis: channels layer, ephemeral matchmaking queues, rate-limits, session state

6. AI/Moderation
   - NSFW image/video classifier runs on snapshots or periodic frames
   - Anomaly detection model flags abusive users, bots, or suspicious activity

7. Payments
   - Yoco: handle coin pack purchases and subscription payments
   - Server validates webhooks, updates wallet and subscription state

## Matchmaking flow (summary)
1. User requests "Start Chat" with mode (text/video) and optional interests.
2. Client opens WebSocket to the Channels consumer and enqueues the user into Redis matchmaking queue.
3. Matchmaker pops two compatible users using hybrid scoring (ELO + embeddings + activity score) and starts a session record.
4. Signaling messages exchange via WS to establish WebRTC connection.
5. Video starts blurred until NSFW background check passes or until user spends coins/unblurs.
6. "Next" increments skip count; after 3 "Next" in session for free users, ad is served before next match.

## Security / Privacy
- Quick-mode uses ephemeral anonymous token (JWT) stored in browser localStorage with short expiry and refresh path.
- Verified mode stores only email and minimal profile metadata; display name remains "Stranger" publicly.
- Rate-limit PIN sends and attempts by IP and email to prevent abuse.
- All sensitive endpoints require HTTPS and proper CSRF protection for browser flows.

## Scalability notes
- Use Redis clusters for channel layer and matchmaking scale.
- Separate matchmakers into worker pools consuming Redis queues.
- Use horizontal scaling for Django ASGI workers behind an ASGI-capable server (daphne/uvicorn + nginx).
- Media (coturn) should run on multiple instances behind LB; monitor bandwidth costs.

