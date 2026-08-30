# LLM Gateway

Implementation in progress per `PLAN.md`. This README covers only what's
built so far (through Phase 1); the full project README is a Phase 10
deliverable.

## Current status

- **Phase 0** — project scaffolding, Docker Compose (gateway + Postgres +
  Redis), `/health` endpoint.
- **Phase 1** — `api_keys` / `request_logs` schema (`app/db/migrations/init.sql`),
  DB session dependency, API key auth dependency (`Authorization: Bearer <key>`),
  a seed script for local dev keys, and a temporary `/v1/_whoami` route used
  only to verify the auth dependency end-to-end (superseded by `/v1/chat` in
  Phase 4).

## Setup

```bash
cp .env.example .env
docker-compose up --build
```

Seed a demo API key once the stack is up:

```bash
docker-compose exec gateway python scripts/seed_api_keys.py demo-client
```

This prints a raw key once — save it. Verify auth works:

```bash
curl http://localhost:8000/health

curl http://localhost:8000/v1/_whoami \
  -H "Authorization: Bearer <the-key-you-just-seeded>"
```

## Tests

Run without Docker or any provider keys (uses an in-memory SQLite DB):

```bash
pip install -r requirements.txt
pytest
```
