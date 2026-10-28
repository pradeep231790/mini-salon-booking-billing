# Aura Salon & Studio — Mini Salon Booking & Billing System

A responsive salon booking app with a persistent SQLite database, REST API, availability checking, reschedule/cancel flow, admin appointment diary, invoices, and an embedded multilingual assistant. Built to cover the GURU AI Technologies Prompt Engineer hiring task.

## Requirements

- Python 3.10+ (standard library only; no `pip install` required)
- Modern browser
- Optional: an LLM API key for live provider responses

## Run locally

```bash
python server.py
```

Open **http://127.0.0.1:8000**. The database `salon.db` is created on first run. Service seeding is idempotent and creates the five required services plus three sample bookings once. The app stores future bookings and invoices in SQLite, so refreshing/restarting the server does not clear data.

### Demo admin login

- Password: `AuraDemo2026!`
- Change it before sharing/deployment by setting `ADMIN_PASSWORD` in your environment.

For PowerShell:

```powershell
$env:ADMIN_PASSWORD="choose-a-strong-demo-password"
python server.py
```

For macOS/Linux:

```bash
ADMIN_PASSWORD='choose-a-strong-demo-password' python server.py
```

This evaluation build uses a shared demo password, not production-grade identity management. Use HTTPS and proper authentication/authorization before any real business use.

## Optional LLM setup

The chatbot works without an API key using a deterministic, database-grounded fallback. To use an OpenAI-compatible API:

```bash
LLM_PROVIDER=openai
LLM_API_KEY=your_key
LLM_MODEL=gpt-4o-mini
```

For Gemini, set `LLM_PROVIDER=gemini` and `LLM_API_KEY=your_key`. Environment variables must be set in the server environment; never add keys to `static/app.js`, HTML, or Git. If no provider key is configured, chat responses report grounded fallback mode internally and the UI continues to work.

## Business rules

- Service catalog (INR): Haircut ₹200 / 30 min; Beard Trim ₹100 / 15 min; Hair Spa ₹800 / 45 min; Facial ₹500 / 40 min; Bridal Makeup ₹5,000 / 120 min.
- Salon hours: 10:00 AM–8:00 PM, 15-minute start intervals. An appointment must finish by closing.
- Phone number: 10 digits.
- Pending and Confirmed bookings block overlapping times. Cancelled and Done bookings do not block future availability.
- Booking creation uses a database write lock/transaction and rechecks overlap on the server. A conflict returns HTTP 409.
- Booking reference + matching phone are required for customer lookup, rescheduling, and cancellation.
- Admin status transitions: Pending → Confirmed or Cancelled; Confirmed → Done or Cancelled. Terminal states cannot be changed through the admin status endpoint.
- Invoice prices are resolved server-side from the service catalog; browser-supplied prices are not accepted.

## Tests

Run:

```bash
python -m unittest discover -s tests -v
```

The test suite uses a temporary database and covers seeded services, slot overlap, server-side validation, booking persistence/conflicts, status transitions, chatbot grounding/refusal, and prompt-file presence. No external LLM credentials are needed for the tests.

## Deploying

This app can run on any host that supports a persistent Python process and writable disk. Set `PORT` if the host provides it. For a small evaluation deployment, attach persistent disk storage and set `DATABASE_PATH` to that mounted location. Do not deploy to a purely static host: the API and SQLite database require a running backend. SQLite on ephemeral serverless filesystems will lose data; use persistent disk or migrate the schema to a hosted PostgreSQL database before using such a platform. Set `ADMIN_PASSWORD`, enable HTTPS, and configure `FRONTEND_ORIGIN` for the deployment domain.

A live URL, GitHub repository, and screen-recording link are not included because these require access to your hosting/GitHub accounts and an actual recording. Follow the submission checklist below after deployment.

## Submission checklist

- [ ] Publish repository and share link/access with evaluator.
- [ ] Deploy backend with persistent storage and test the public live URL.
- [ ] Configure `ADMIN_PASSWORD` and optional LLM key as server environment variables.
- [ ] Test booking, occupied-slot rejection, rescheduling, cancellation, admin status changes, invoices, and chatbot on deployed version.
- [ ] Record a 2–3 minute walkthrough (booking → admin → billing → chatbot) and explain one technical decision in your own words.
- [ ] Submit `prompts/salon-chatbot-system-prompt.txt` and `docs/prompt-iteration-note.md`.

## Project structure

```text
mini-salon/
├── server.py
├── static/ (HTML, CSS, JS)
├── database/ (reserved for schema/migration notes)
├── prompts/salon-chatbot-system-prompt.txt
├── docs/architecture.md
├── docs/prompt-iteration-note.md
└── tests/test_app.py
```
