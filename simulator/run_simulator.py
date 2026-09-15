#!/usr/bin/env python3
"""Standalone simulator: acts exactly like the Arduino node over HTTP.

It builds payloads with the shared environmental model and POSTs them to the
FastAPI backend's device endpoint with the ``X-API-Key`` header, so the data
travels through the identical validation -> normalisation -> anomaly -> risk ->
alert -> persistence -> realtime pipeline as real hardware.

Usage::

    python simulator/run_simulator.py --backend http://192.168.1.5:8000 --api-key dev-key
    python simulator/run_simulator.py --scenario storm --interval 2
    python simulator/run_simulator.py --list-scenarios
    python simulator/run_simulator.py --dry-run            # print payloads only

Environment variables (used when a flag is omitted):
``SIM_BACKEND_URL`` (or ``BACKEND_URL``), ``SIM_API_KEY`` (or ``API_KEY``),
``SIM_DEVICE_ID``, ``SIM_INTERVAL``, ``SIM_SCENARIO``.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator.environment_model import (  # noqa: E402
    SCENARIOS,
    EnvironmentSimulator,
    SensorFaultConfig,
)

RESET = "\033[0m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"

LEVEL_COLORS = {1: GREEN, 2: GREEN, 3: YELLOW, 4: "\033[38;5;208m", 5: RED}


def local_ip() -> str:
    """Best-effort LAN address of this machine (for the hint message)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Environmental monitor simulator - feeds the FastAPI backend like an Arduino node."
    )
    parser.add_argument(
        "--backend",
        default=os.environ.get("SIM_BACKEND_URL") or os.environ.get("BACKEND_URL") or "http://127.0.0.1:8000",
        help="Backend base URL (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("SIM_API_KEY") or os.environ.get("API_KEY") or "",
        help="API key sent in the X-API-Key header (default: $SIM_API_KEY or $API_KEY)",
    )
    parser.add_argument(
        "--device-id",
        default=os.environ.get("SIM_DEVICE_ID") or os.environ.get("DEVICE_ID") or "arduino-r4-wifi-01",
        help="Device identifier used in payloads (default: the backend's DEVICE_ID)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.environ.get("SIM_INTERVAL", "5")),
        help="Seconds between transmissions (default 5, the real firmware default is 15)",
    )
    parser.add_argument(
        "--scenario",
        default=os.environ.get("SIM_SCENARIO", "mixed_weather"),
        help="Simulation scenario (see --list-scenarios)",
    )
    parser.add_argument("--duration", type=float, default=0, help="Stop after N minutes (0 = run forever)")
    parser.add_argument("--speed", type=float, default=1.0, help="Simulated-time speed multiplier")
    parser.add_argument("--seed", type=int, default=int(os.environ.get("SIM_SEED", "20260915")))
    parser.add_argument("--dry-run", action="store_true", help="Print payloads instead of POSTing them")
    parser.add_argument("--list-scenarios", action="store_true", help="List scenarios and exit")
    parser.add_argument("--quiet", action="store_true", help="Only print warnings and errors")
    parser.add_argument("--fault", action="append", default=[], help="Force a scenario-style fault (repeatable)")
    return parser.parse_args(argv)


def post_payload(url: str, payload: dict, api_key: str, timeout: float = 10.0) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    if api_key:
        request.add_header("X-API-Key", api_key)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"detail": raw[:400]}


def check_backend(base_url: str, api_key: str) -> bool:
    url = f"{base_url.rstrip('/')}/api/v1/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        print(f"{GREEN}Backend reachable{RESET} at {base_url} - status={data.get('status')} "
              f"simulation_mode={data.get('simulation_mode')}")
        return True
    except Exception as exc:  # noqa: BLE001 - we report the reason to the user
        print(f"{RED}Cannot reach the backend{RESET} at {url}: {exc}")
        print(
            "  - Is the backend running?  (uvicorn app.main:app --host 0.0.0.0 --port 8000)\n"
            "  - Is it bound to 0.0.0.0 rather than 127.0.0.1?\n"
            f"  - Windows Firewall may need to allow the port. This machine's LAN IP is {local_ip()}."
        )
        _ = api_key
        return False


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.list_scenarios:
        print("Available simulation scenarios:\n")
        for key, config in SCENARIOS.items():
            print(f"  {key:<18} {config['label']}")
        return 0

    faults = SensorFaultConfig()
    if args.fault:
        for item in args.fault:
            if ":" not in item:
                print(f"{RED}--fault expects key:type (frozen|disconnected|spiking){RESET}")
                return 2
            measurement, kind = item.split(":", 1)
            if kind == "frozen":
                faults.frozen.append(measurement)
            elif kind == "disconnected":
                faults.disconnected.append(measurement)
            elif kind == "spiking":
                faults.spiking.append(measurement)
            else:
                print(f"{RED}Unknown fault type '{kind}'{RESET}")
                return 2

    simulator = EnvironmentSimulator(
        args.scenario,
        seed=args.seed,
        device_id=args.device_id,
        speed=args.speed,
        transmission_interval_ms=int(args.interval * 1000),
        faults=faults,
    )
    endpoint = f"{args.backend.rstrip('/')}/api/v1/sensors/data"
    health_ok = True if args.dry_run else check_backend(args.backend, args.api_key)
    if not args.dry_run and not args.api_key:
        print(
            f"{YELLOW}No API key supplied{RESET}: set --api-key or the SIM_API_KEY environment variable "
            "(it must match API_KEY in backend/.env)."
        )
    if not args.dry_run and not health_ok:
        print(f"{YELLOW}Starting anyway; the simulator will retry with backoff.{RESET}")
    print(
        f"Simulating scenario {CYAN}{args.scenario}{RESET} ({SCENARIOS[args.scenario]['label']}) "
        f"as device {CYAN}{args.device_id}{RESET} every {args.interval}s"
    )

    stop = {"flag": False}

    def handle_signal(_signum, _frame):
        stop["flag"] = True

    signal.signal(signal.SIGINT, handle_signal)
    try:
        signal.signal(signal.SIGTERM, handle_signal)
    except (AttributeError, ValueError):  # pragma: no cover - platform dependent
        pass

    sent = accepted = failed = rejected = 0
    latencies: list[float] = []
    backoff = 1.0
    started = time.time()

    while not stop["flag"]:
        loop_start = time.time()
        payload = simulator.step(dt_seconds=max(1.0, args.interval * args.speed))

        if args.dry_run:
            print(json.dumps(payload, indent=2))
            sent += 1
        else:
            status, body = post_payload(endpoint, payload, args.api_key)
            sent += 1
            if status == 200 and body.get("success"):
                accepted += 1
                backoff = 1.0
                if not args.quiet:
                    level = body.get("risk_level") or 1
                    color = LEVEL_COLORS.get(int(level), "")
                    warnings = body.get("warnings") or []
                    print(
                        f"{time.strftime('%H:%M:%S')} "
                        f"T={payload.get('temperature_c')}C RH={payload.get('humidity_pct')}% "
                        f"P={payload.get('pressure_hpa')}hPa AQ={payload.get('air_quality_raw')} "
                        f"rain={payload.get('rain_pct')}% light={payload.get('light_pct')}% "
                        f"-> {color}risk {body.get('risk_score')}/100 L{level} {body.get('risk_label')}{RESET}"
                        f"{' dup' if body.get('duplicate') else ''}"
                        f"{' | ' + str(warnings[0]) if warnings else ''}"
                    )
            elif status in (401, 403):
                failed += 1
                print(f"{RED}Auth failed ({status}){RESET}: {body.get('detail')}")
                print("  Fix API_KEY in backend/.env and pass the same value with --api-key.")
                stop["flag"] = True
                continue
            elif status == 422:
                rejected += 1
                print(f"{RED}Payload rejected (422){RESET}: {body.get('detail')}")
            else:
                failed += 1
                print(f"{RED}HTTP {status}{RESET}: {body.get('detail') or body}")
                time.sleep(backoff)
                backoff = min(30.0, backoff * 2)

        if args.duration and (time.time() - started) / 60.0 >= args.duration:
            break

        elapsed = time.time() - loop_start
        latencies.append(elapsed)
        sleep_for = max(0.0, args.interval - elapsed)
        while sleep_for > 0 and not stop["flag"]:
            chunk = min(0.25, sleep_for)
            time.sleep(chunk)
            sleep_for -= chunk

    print(
        f"\n{DIM}Stopped. sent={sent} accepted={accepted} failed={failed} rejected={rejected} "
        f"avg_loop={sum(latencies) / len(latencies):.2f}s{RESET}"
        if latencies
        else f"\n{DIM}Stopped. sent={sent}{RESET}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
