import pytest

pytestmark = pytest.mark.asyncio


async def test_protected_route_without_key_returns_401(client):
    resp = await client.get("/v1/_whoami")
    assert resp.status_code == 401


async def test_protected_route_with_malformed_header_returns_401(client):
    resp = await client.get("/v1/_whoami", headers={"Authorization": "not-a-bearer-token"})
    assert resp.status_code == 401


async def test_protected_route_with_unknown_key_returns_401(client):
    resp = await client.get("/v1/_whoami", headers={"Authorization": "Bearer does-not-exist"})
    assert resp.status_code == 401


async def test_protected_route_with_seeded_key_returns_200(client, seeded_api_key):
    resp = await client.get("/v1/_whoami", headers={"Authorization": f"Bearer {seeded_api_key}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["label"] == "test-client"
    assert "api_key_id" in body


async def test_health_route_is_unauthenticated(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    # Phase 6 adds per-provider circuit state to /health; the exact shape is
    # covered in test_circuit_breaker.py, this just confirms no auth is required.
    assert body["status"] == "ok"
