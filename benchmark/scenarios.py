"""Benchmark scenario implementations, per PLAN.md Section 14.

Each scenario is an async function that exercises a *running* gateway
instance over real HTTP (via httpx.AsyncClient) and returns a ScenarioResult
holding both the raw per-request records and computed summary statistics.
No scenario invents, estimates, or hardcodes a result -- every number comes
from an actual HTTP round trip against whatever `base_url` points at.

These are intentionally decoupled from any particular gateway process
(Docker Compose, local uvicorn, etc.) -- run_benchmark.py wires them up to a
concrete `base_url` and API key.
"""
import asyncio
import time
from dataclasses import dataclass, field

import httpx

DEFAULT_PAYLOAD = {
    "model": "fast-cheap",
    "messages": [{"role": "user", "content": "Say hello in one short sentence."}],
}


@dataclass
class RequestRecord:
    status_code: int
    latency_ms: float
    fallback_occurred: bool | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "status_code": self.status_code,
            "latency_ms": round(self.latency_ms, 3),
            "fallback_occurred": self.fallback_occurred,
            "error": self.error,
        }


@dataclass
class ScenarioResult:
    name: str
    records: list[RequestRecord]
    extra: dict = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.records)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.records if 200 <= r.status_code < 300)

    @property
    def success_rate(self) -> float:
        return self.success_count / self.total if self.total else 0.0

    def latency_percentile(self, pct: float) -> float:
        """Linear-interpolation percentile over observed latencies -- no
        numpy/scipy dependency needed for this."""
        latencies = sorted(r.latency_ms for r in self.records if r.status_code != 0)
        if not latencies:
            return 0.0
        k = (len(latencies) - 1) * (pct / 100)
        f = int(k)
        c = min(f + 1, len(latencies) - 1)
        if f == c:
            return latencies[f]
        return latencies[f] + (latencies[c] - latencies[f]) * (k - f)

    def to_summary_dict(self) -> dict:
        return {
            "name": self.name,
            "total_requests": self.total,
            "success_count": self.success_count,
            "success_rate": round(self.success_rate, 4),
            "p50_latency_ms": round(self.latency_percentile(50), 2),
            "p95_latency_ms": round(self.latency_percentile(95), 2),
            "p99_latency_ms": round(self.latency_percentile(99), 2),
            **self.extra,
        }

    def to_dict(self) -> dict:
        return {
            "summary": self.to_summary_dict(),
            "records": [r.to_dict() for r in self.records],
        }


async def _timed_post(client: httpx.AsyncClient, url: str, headers: dict, json_body: dict) -> RequestRecord:
    start = time.perf_counter()
    try:
        resp = await client.post(url, headers=headers, json=json_body)
        latency_ms = (time.perf_counter() - start) * 1000
        fallback_occurred = None
        if resp.status_code == 200:
            try:
                fallback_occurred = resp.json().get("fallback_occurred")
            except ValueError:
                pass
        return RequestRecord(status_code=resp.status_code, latency_ms=latency_ms, fallback_occurred=fallback_occurred)
    except httpx.HTTPError as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        return RequestRecord(status_code=0, latency_ms=latency_ms, error=str(exc))


async def run_baseline_throughput(
    base_url: str,
    api_key: str,
    concurrency: int = 10,
    total_requests: int = 50,
    model_alias: str = "fast-cheap",
) -> ScenarioResult:
    """Scenario 1 (PLAN.md Section 14 #1): N concurrent requests against
    `model_alias` with both providers healthy. Measures p50/p95/p99 latency,
    success rate, and requests/sec."""
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {**DEFAULT_PAYLOAD, "model": model_alias}
    url = f"{base_url}/v1/chat"

    async with httpx.AsyncClient(timeout=60.0) as client:
        semaphore = asyncio.Semaphore(concurrency)

        async def bound_call() -> RequestRecord:
            async with semaphore:
                return await _timed_post(client, url, headers, payload)

        wall_start = time.perf_counter()
        records = list(await asyncio.gather(*[bound_call() for _ in range(total_requests)]))
        wall_seconds = time.perf_counter() - wall_start

    result = ScenarioResult(name="baseline_throughput", records=records)
    result.extra["requests_per_sec"] = round(total_requests / wall_seconds, 2) if wall_seconds > 0 else 0.0
    result.extra["wall_clock_seconds"] = round(wall_seconds, 3)
    result.extra["concurrency"] = concurrency
    return result


async def run_forced_fallback(
    base_url: str,
    api_key: str,
    total_requests: int = 20,
    model_alias: str = "fast-cheap",
) -> ScenarioResult:
    """Scenario 2 (PLAN.md Section 14 #2): run once the operator has made the
    primary provider for `model_alias` unreachable (see run_benchmark.py's
    module docstring for how). Measures how many requests still succeed via
    fallback and the added latency vs a healthy baseline."""
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {**DEFAULT_PAYLOAD, "model": model_alias}
    url = f"{base_url}/v1/chat"

    async with httpx.AsyncClient(timeout=60.0) as client:
        records = [await _timed_post(client, url, headers, payload) for _ in range(total_requests)]

    result = ScenarioResult(name="forced_fallback", records=records)
    fallback_count = sum(1 for r in records if r.fallback_occurred)
    result.extra["fallback_count"] = fallback_count
    result.extra["fallback_rate"] = round(fallback_count / len(records), 4) if records else 0.0
    return result


async def run_rate_limit_behavior(
    base_url: str,
    api_key: str,
    total_requests: int = 20,
    model_alias: str = "fast-cheap",
) -> ScenarioResult:
    """Scenario 3 (PLAN.md Section 14 #3): fire requests back-to-back
    (sequentially, no inter-request delay) against a key with a known
    configured per-minute limit, and measure how many are accepted (200) vs
    rejected (429), confirming the limiter enforces the configured rate."""
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {**DEFAULT_PAYLOAD, "model": model_alias}
    url = f"{base_url}/v1/chat"

    async with httpx.AsyncClient(timeout=60.0) as client:
        records = [await _timed_post(client, url, headers, payload) for _ in range(total_requests)]

    result = ScenarioResult(name="rate_limit_behavior", records=records)
    result.extra["rejected_429_count"] = sum(1 for r in records if r.status_code == 429)
    result.extra["accepted_count"] = sum(1 for r in records if r.status_code == 200)
    return result


async def run_all_providers_down_recovery(
    base_url: str,
    api_key: str,
    probe_interval_seconds: float = 1.0,
    max_wait_seconds: float = 60.0,
    model_alias: str = "fast-cheap",
) -> ScenarioResult:
    """Scenario 4 (PLAN.md Section 14 #4): assumes both providers are
    currently unreachable (see run_benchmark.py's module docstring). Sends
    one request to confirm a clean 502 with no crash/hang, then the operator
    restores connectivity; this function polls with single requests until the
    first success, reporting the recovery time from restoration."""
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {**DEFAULT_PAYLOAD, "model": model_alias}
    url = f"{base_url}/v1/chat"

    async with httpx.AsyncClient(timeout=60.0) as client:
        initial = await _timed_post(client, url, headers, payload)
        records = [initial]

        recovery_start = time.perf_counter()
        recovered = False
        elapsed = 0.0
        while elapsed < max_wait_seconds:
            record = await _timed_post(client, url, headers, payload)
            records.append(record)
            if record.status_code == 200:
                recovered = True
                break
            await asyncio.sleep(probe_interval_seconds)
            elapsed = time.perf_counter() - recovery_start

    result = ScenarioResult(name="all_providers_down_recovery", records=records)
    result.extra["initial_status_code"] = initial.status_code
    result.extra["recovered"] = recovered
    result.extra["recovery_time_seconds"] = round(elapsed, 2) if recovered else None
    return result


SCENARIOS = {
    "baseline_throughput": run_baseline_throughput,
    "forced_fallback": run_forced_fallback,
    "rate_limit_behavior": run_rate_limit_behavior,
    "all_providers_down_recovery": run_all_providers_down_recovery,
}
