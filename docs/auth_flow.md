# Simplified Auth Flow — Email + 4-digit PIN

This document describes the Email+PIN authentication design and quick anonymous mode.

Goals
- Minimal friction: users can "Continue without Login" or verify an email with a 4-digit PIN.
- Privacy: only store email (for verified accounts) and minimal metadata. Public display name remains "Stranger".
- Security: protect against abuse (rate-limit PIN sends, PIN attempt limits, expiry, hashed storage).

Flows

1) Quick Mode (No Login)
- Client requests POST /api/v1/auth/continue_anonymous
- Server returns a short-lived anon JWT (signed) stored in localStorage with a refresh path
- Anon token contains: anon_id (uuid), issued_at, expires_at (e.g., 7 days)
- No email collected. Anon users can buy coins only if they later verify email (or we allow anonymous purchases via guest checkout)

2) Verified Mode (Email + PIN)
- Step A: Client POST /api/v1/auth/send_pin
  - Body: { "email": "user@example.com" }
  - Server behaviour:
    - Validate email format
    - Rate-limit by IP and email (e.g., 5 sends per hour)
    - Generate 4-digit numeric PIN (random)
    - Hash PIN server-side (bcrypt or HMAC) and store PinCode with expiry (5-10 minutes) and attempt counter
    - Send transactional email with the PIN using SendGrid/Postmark
    - Return generic message: { "ok": true, "message": "If that email exists, a PIN was sent" }

- Step B: Client POST /api/v1/auth/verify_pin
  - Body: { "email": "user@example.com", "pin": "1234" }
  - Server behaviour:
    - Look up latest PinCode for email, verify not expired
    - Compare hashed PIN using constant-time compare
    - Increment attempts; after N failed attempts (e.g., 5) invalidate and require a new PIN
    - On success: create or fetch User, set is_verified=True, issue JWT (longer expiry), return user object

- PIN reuse & expiry
  - PINs expire after a short time (5-10 minutes). After successful verification, delete/mark used.
  - If too many attempts, lock PIN and force resend.

Security considerations
- Rate-limiting: per-IP and per-email limits on send_pin and verify_pin attempts.
- Hashing: never store PIN plaintext. Use bcrypt or HMAC-SHA256 with server secret.
- Tokenization: issue JWTs signed with server secret; for anonymous tokens, shorter TTL and no PII.
- CSRF & CORS: treat REST endpoints as public — protect mutating endpoints appropriately. For WS, require token on connect.
- Email enumeration: standardize responses so callers cannot determine whether an email exists.

UX details
- The client shows a single email input. After send_pin success, show PIN input.
- Provide "Resend PIN" with cooldown UI (e.g., 60s timer).
- Provide "Continue without Login" shortcut.

Edge cases
- User loses PIN: they can re-enter email to request a new PIN.
- Email bounces: server logs and admin notifications; consider blocking high-bounce addresses.
- Shared devices: recommend user clear localStorage to prevent anonymous session persistence.

API endpoints referenced
- POST /api/v1/auth/send_pin
- POST /api/v1/auth/verify_pin
- POST /api/v1/auth/continue_anonymous

Implementation notes
- Use Django + DRF for endpoints.
- Use a short Celery worker or background task to send emails asynchronously.
- Track metrics for send_pin volume, verify success rate, and abuse signals.
