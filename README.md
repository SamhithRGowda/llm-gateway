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
- **Phase 2** — Provider abstraction (`app/providers/base.py`: `NormalizedRequest`,
  `NormalizedResponse`, `ProviderAdapter`), the provider error hierarchy
  (`app/providers/errors.py`), a generic async retry/backoff helper
  (`app/reliability/retry.py`), and the OpenAI provider adapter
  (`app/providers/openai_adapter.py`). No routing, fallback, circuit breaker,
  rate limiting, or `/v1/chat` endpoint yet -- those are later phases. All
  provider tests use mocked HTTP (`respx`); no real API calls are made in the
  test suite.

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
