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
- **Phase 3** — Groq provider adapter (`app/providers/groq_adapter.py`,
  subclassing `OpenAIAdapter` since Groq's API is OpenAI-compatible) and the
  routing engine: YAML-defined model-alias -> provider chains
  (`app/routing/model_aliases.yaml`, `app/routing/config.py`) and chain
  resolution with per-provider retry + fallback (`app/routing/router.py`).
  No circuit breaker yet (Phase 6), no observability/metrics (Phase 7). All
  new tests use mocked HTTP or fake in-memory adapters; no real API calls.
- **Phase 4** — the `POST /v1/chat` endpoint (`app/api/routes_chat.py`),
  wiring auth (Phase 1) + the router/providers (Phases 2-3) + usage/cost
  persistence. Adds `app/usage/models.py` (`RequestLog` SQLAlchemy model),
  `app/usage/repository.py`, `app/usage/cost_calculator.py`, and
  `app/pricing/pricing.yaml`. Malformed requests (missing/empty messages,
  invalid role, empty content, unknown model alias) return `400`; an
  exhausted provider chain returns `502` with per-provider attempt details.
  No rate limiting (`429`) yet (Phase 5), no circuit breaker (Phase 6), no
  `/metrics`/`/stats`/structured logging (Phase 7). All tests use mocked
  HTTP or fake in-memory adapters; no real OpenAI/Groq calls.

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
