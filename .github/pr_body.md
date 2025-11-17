Summary
- Implement premium-priority matchmaking queue (premium-premium -> premium-normal -> normal-normal).
- Add persistent premium filters and PurchaseFilters endpoint changes (premium users not charged).
- Add purchase/premium flows and lobby buttons in frontend.
- Add unit tests: `chat/tests_priority.py`, updated `chat/tests_next.py`, `chat/tests_filters.py`.
- Add consumer improvements (include peer_is_premium in match payloads, respect user-scoped filters).
- Add CI workflow skeleton on branch `ci/add-e2e-workflow` (lint, mypy, unit tests, Playwright E2E).

Verification
- Ran focused chat unit tests locally: `chat.tests_filters`, `chat.tests_next`, `chat.tests_priority` → OK.
- Ran mypy in venv: success (note: `mypy.ini` contains an unsupported `per-module-ignores` option which is a harmless config warning).

Notes / Next steps
- Full E2E uses Playwright and mock checkout and will run in CI. Expect CI to reveal any environment-specific failures.
- Follow-ups (not yet implemented in this branch):
  - Subscription expiry / billing cycle automation for premium.
  - TURN server / STUN / production WebRTC infrastructure and managed Postgres/Redis migration.
  - Extend priority-level tests to simulate Lua eval across Redis lists (optional deeper integration test).

How to test locally (recommended)
1) Activate the backend venv and install dev deps:
```powershell
cd C:\Users\Administrator\Desktop\connectwell\backend
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```
2) Run linters/types and unit tests:
```powershell
flake8
mypy backend --config-file=..\mypy.ini
.\.venv\Scripts\python.exe -m pytest -q
```
3) Optional: run Playwright E2E (requires Playwright browsers):
```powershell
.\.venv\Scripts\python.exe -m playwright install
.\.venv\Scripts\python.exe -m pytest tests/e2e -q
```

If you'd like me to push the branch and open the PR, provide the remote URL (or run the push commands locally). I can also produce the `gh pr create` command to open the PR once pushed.
