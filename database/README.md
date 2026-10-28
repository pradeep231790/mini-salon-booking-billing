# Database notes

The schema is initialized idempotently by `init_db()` in `server.py`. This project uses SQLite to keep setup dependency-free. Tables and indexes are created with `CREATE TABLE IF NOT EXISTS`; required services are inserted with `INSERT OR IGNORE`; sample bookings are inserted only when the bookings table is empty. The database file is excluded from Git so evaluators create their own persistent data on first run.
