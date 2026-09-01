#!/usr/bin/env python3
"""Benchmark runner for the LLM Gateway, per PLAN.md Section 14 / Phase 9.

This drives the four scenarios in benchmark/scenarios.py against a *running*
gateway instance over real HTTP. It never fabricates numbers -- every figure
in the generated report comes from an actual request/response measured
during the run.

REQUIREMENTS TO RUN FOR REAL
-----------------------------
This benchmark is a separate, manual operation from the automated pytest
suite. It requires:
  1. The full stack running via Docker Compose (`docker-compose up --build`),
     with `OPENAI_API_KEY` and `GROQ_API_KEY` set in `.env` to real,
     funded provider credentials. Never hardcode or commit these.
  2. A seeded API key for the gateway itself (see scripts/seed_api_keys.py),
     passed to this script via --api-key or the GATEWAY_API_KEY env var.

USAGE
-----
    # Scenario 1: baseline (both providers healthy)
    python benchmark/run_benchmark.py --scenario baseline_throughput \\
        --base-url http://localhost:8000 --api-key <gateway-key>

    # Scenario 2: forced fallback -- first blackhole the primary provider
    # for the "fast-cheap" alias (groq). One way to do this without touching
    # application code: inside the running gateway container, route the
    # provider's hostname to an unreachable address, e.g.:
    #     docker-compose exec gateway sh -c \\
    #         "echo '127.0.0.1 api.groq.com' >> /etc/hosts"
    # Then run:
    python benchmark/run_benchmark.py --scenario forced_fallback \\
        --base-url http://localhost:8000 --api-key <gateway-key>
    # Afterwards, remove that /etc/hosts line (or recreate the container) to
    # restore connectivity.

    # Scenario 3: rate limit behavior -- use a key whose rate_limit_per_min
    # is set low (see scripts/seed_api_keys.py or an UPDATE against api_keys)
    # so the default request volume actually exceeds it.
    python benchmark/run_benchmark.py --scenario rate_limit_behavior \\
        --base-url http://localhost:8000 --api-key <low-limit-key>

    # Scenario 4: all-providers-down recovery -- blackhole BOTH
    # api.openai.com and api.groq.com the same way as above, run this
    # scenario (it sends one request to confirm a clean 502), then restore
    # connectivity while the script is polling; it reports recovery time.
    python benchmark/run_benchmark.py --scenario all_providers_down_recovery \\
        --base-url http://localhost:8000 --api-key <gateway-key>

    # Or run all four in sequence (only sensible if you can blackhole/restore
    # providers interactively between scenarios 1->2->3->4):
    python benchmark/run_benchmark.py --scenario all \\
        --base-url http://localhost:8000 --api-key <gateway-key>

Each scenario's raw per-request records are written to
benchmark/results/<scenario>.json. After a full "all" run (or after running
every scenario individually), regenerate the combined report with:

    python benchmark/run_benchmark.py --report-only

which reads whatever benchmark/results/<scenario>.json files are present and
(re)writes benchmark/results/report.md from them.
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scenarios import SCENARIOS, ScenarioResult  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _write_json(scenario_name: str, result: ScenarioResult) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{scenario_name}.json"
    path.write_text(json.dumps(result.to_dict(), indent=2))
    return path


def _load_json(scenario_name: str) -> dict | None:
    path = RESULTS_DIR / f"{scenario_name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _render_report(summaries: dict) -> str:
    lines = [
        "# LLM Gateway -- Benchmark Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        "All figures below were measured by running `benchmark/run_benchmark.py` "
        "against a live gateway instance; none are estimated or fabricated. "
        "Scenarios not yet run are shown as \"not run\".",
        "",
    ]

    scenario_titles = {
        "baseline_throughput": "1. Baseline Throughput / Latency",
        "forced_fallback": "2. Forced Fallback",
        "rate_limit_behavior": "3. Rate Limit Behavior",
        "all_providers_down_recovery": "4. All-Providers-Down Recovery",
    }

    for key, title in scenario_titles.items():
        lines.append(f"## {title}")
        lines.append("")
        summary = summaries.get(key)
        if summary is None:
            lines.append("_Not run._")
            lines.append("")
            continue
        for field_name, value in summary.items():
            if field_name == "name":
                continue
            lines.append(f"- **{field_name}**: {value}")
        lines.append("")

    return "\n".join(lines)


def write_report() -> Path:
    summaries = {}
    for scenario_name in SCENARIOS:
        data = _load_json(scenario_name)
        if data is not None:
            summaries[scenario_name] = data["summary"]

    report = _render_report(summaries)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = RESULTS_DIR / "report.md"
    report_path.write_text(report)
    return report_path


async def run_scenario(name: str, args: argparse.Namespace) -> ScenarioResult:
    func = SCENARIOS[name]
    kwargs = {"base_url": args.base_url, "api_key": args.api_key, "model_alias": args.model_alias}
    if name == "baseline_throughput":
        kwargs["concurrency"] = args.concurrency
        kwargs["total_requests"] = args.requests
    elif name in ("forced_fallback", "rate_limit_behavior"):
        kwargs["total_requests"] = args.requests
    elif name == "all_providers_down_recovery":
        kwargs["probe_interval_seconds"] = args.probe_interval
        kwargs["max_wait_seconds"] = args.max_wait
    return await func(**kwargs)


async def main_async(args: argparse.Namespace) -> None:
    if args.report_only:
        path = write_report()
        print(f"Wrote {path}")
        return

    scenario_names = list(SCENARIOS) if args.scenario == "all" else [args.scenario]

    for name in scenario_names:
        print(f"Running scenario: {name} ...")
        result = await run_scenario(name, args)
        json_path = _write_json(name, result)
        print(f"  -> {json_path}")
        print(f"  summary: {json.dumps(result.to_summary_dict(), indent=2)}")

    report_path = write_report()
    print(f"Wrote {report_path}")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LLM Gateway benchmark runner (PLAN.md Phase 9)")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Running gateway base URL")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("GATEWAY_API_KEY", ""),
        help="Gateway API key (or set GATEWAY_API_KEY env var). Never hardcode this.",
    )
    parser.add_argument(
        "--scenario",
        choices=[*SCENARIOS.keys(), "all"],
        default="all",
        help="Which scenario to run (default: all, run sequentially)",
    )
    parser.add_argument("--model-alias", default="fast-cheap", help="Model alias to send requests to")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent requests for baseline_throughput")
    parser.add_argument("--requests", type=int, default=20, help="Total requests for most scenarios")
    parser.add_argument("--probe-interval", type=float, default=1.0, help="Seconds between recovery probes")
    parser.add_argument("--max-wait", type=float, default=60.0, help="Max seconds to wait for recovery")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Skip running scenarios; just (re)generate report.md from existing results/*.json",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    if not args.report_only and not args.api_key:
        print(
            "error: --api-key (or GATEWAY_API_KEY env var) is required to run a scenario",
            file=sys.stderr,
        )
        sys.exit(1)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
