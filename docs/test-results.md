# Verification record

Verified locally in the build environment on 2026-10-28.

- `python -m unittest discover -s tests -v` — **12 tests passed**.
- `node --check static/app.js` — passed (JavaScript syntax check).
- `python -m py_compile server.py tests/test_app.py` — passed (Python syntax/compile check).
- HTTP smoke test — `GET /api/health` returned HTTP 200 and JSON `{ "ok": true, "database": "sqlite", ... }`.
- HTTP smoke test — `GET /api/services` returned the five required seeded services and prices.
- HTTP smoke test — `GET /` returned HTTP 200.

The tests cover required seed data and statuses, booking field/phone validation, slot availability, duration overlap, conflicting booking rejection, booking lookup, admin authentication and valid/invalid status transitions, server-calculated invoice totals, multilingual price lookup in the deterministic fallback, refusal of unsupported/privacy-intrusion requests, and presence of the system-prompt file.

No public hosting deployment, GitHub publication, or external LLM API call is claimed here. Those require the candidate's account credentials and (for the LLM) a provider API key.
