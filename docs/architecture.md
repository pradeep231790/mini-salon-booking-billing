# Architecture

- **Browser:** `static/index.html`, `static/styles.css`, `static/app.js`; responsive customer booking, service menu, lookup/reschedule/cancel, chat, admin console, and billing UI.
- **API/server:** `server.py`, Python standard library `ThreadingHTTPServer`. JSON endpoints live under `/api`.
- **Database:** persistent SQLite file `salon.db` by default, configurable with `DATABASE_PATH`. Tables: `services`, `bookings`, `invoices`, `invoice_items`. Services and three sample bookings are seeded idempotently on first initialization.
- **Booking safety:** server validates all inputs and checks duration-aware overlap. SQLite `BEGIN IMMEDIATE` serializes competing booking writes; conflicting active Pending/Confirmed appointments return HTTP 409. Cancelled and Done bookings do not block availability.
- **Admin:** demo password sent in `X-Admin-Password`; change `ADMIN_PASSWORD` before deployment. This simple shared-password gate is suitable for evaluation, not production identity management. Use HTTPS and a proper identity provider for production.
- **Chat:** `/api/chat` injects live database service data into the separate system prompt. `LLM_PROVIDER=openai` uses the OpenAI-compatible chat completions API; `LLM_PROVIDER=gemini` uses Gemini. Without `LLM_API_KEY`, a grounded deterministic fallback responds to common English/Hinglish/Marathi service and price questions. Live availability is always checked in the booking form, not guessed by the model.
- **Billing:** the server looks up prices from the service table and stores invoice and line-item snapshots. The browser's print dialog provides a clean print-to-PDF path.

## API

- `GET /api/health`
- `GET /api/services`
- `GET /api/availability?date=YYYY-MM-DD&serviceId=1`
- `POST /api/bookings`
- `GET /api/bookings?date=YYYY-MM-DD&status=Pending&search=...` (admin password required)
- `PATCH /api/bookings/:id` (admin password required)
- `GET /api/bookings/:id/public?phone=...` (booking reference + phone check)
- `POST /api/bookings/:id/reschedule`
- `POST /api/bookings/:id/cancel`
- `POST /api/invoices` and `GET /api/invoices/:id` (admin password required)
- `POST /api/admin/login`
- `POST /api/chat`
