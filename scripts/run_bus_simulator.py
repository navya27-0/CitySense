"""Bus Fleet Simulator for BusSense-AI.

Simulates simultaneous real-time GPS telemetry transmission for prototype transit fleet:
- BUS_101 (Route 216)
- BUS_102 (Route 10)
- BUS_103 (Route 49)

Reads GPS CSV trajectory logs, moves buses along their routes, and posts telemetry to FastAPI /api/telemetry.

Usage:
    python scripts/run_bus_simulator.py [--speed 5x] [--loop] [--endpoint http://127.0.0.1:8000/api/telemetry]

NOTE: SIMULATED TELEMETRY FOR HACKATHON PROTOTYPE DEMONSTRATION.
"""

import sys
import time
import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import httpx

# Project root path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
GPS_DATA_DIR = PROJECT_ROOT / "data" / "gps"

BUS_CONFIGS = [
    {
        "bus_id": "BUS_101",
        "route_id": "216",
        "csv_file": GPS_DATA_DIR / "BUS_101.csv",
        "color": "\033[94m",  # Blue
    },
    {
        "bus_id": "BUS_102",
        "route_id": "10",
        "csv_file": GPS_DATA_DIR / "BUS_102.csv",
        "color": "\033[92m",  # Green
    },
    {
        "bus_id": "BUS_103",
        "route_id": "49",
        "csv_file": GPS_DATA_DIR / "BUS_103.csv",
        "color": "\033[93m",  # Yellow
    },
]
RESET_COLOR = "\033[0m"


async def simulate_single_bus(
    bus_config: dict,
    client: httpx.AsyncClient,
    endpoint: str,
    speed_multiplier: float,
    loop_continuously: bool,
    max_steps: int = 0,
):
    """Simulates GPS streaming for a single bus along its trajectory."""
    bus_id = bus_config["bus_id"]
    route_id = bus_config["route_id"]
    csv_file = bus_config["csv_file"]
    color = bus_config["color"]

    if not csv_file.exists():
        print(f"[ERROR] CSV trajectory not found for {bus_id}: {csv_file}")
        return

    df = pd.read_csv(csv_file)
    total_waypoints = len(df)
    delay_between_points = max(0.01, 1.0 / speed_multiplier)

    print(f"[*] Started simulation for {color}{bus_id}{RESET_COLOR} (Route {route_id}) with {total_waypoints} waypoints @ {speed_multiplier}x speed")

    iteration = 0
    while True:
        iteration += 1
        for idx, row in df.iterrows():
            if max_steps > 0 and idx >= max_steps:
                break

            payload = {
                "bus_id": bus_id,
                "route_id": route_id,
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "speed": float(row["speed"]),
                "heading": float(row["heading"]),
                "status": "active" if float(row["speed"]) > 0 else "idle",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            try:
                start_t = time.time()
                resp = await client.post(endpoint, json=payload, timeout=5.0)
                elapsed_ms = (time.time() - start_t) * 1000

                if resp.status_code == 200:
                    status_symbol = "[OK]"
                else:
                    status_symbol = f"[HTTP {resp.status_code}]"

                print(
                    f"[SIMULATED TELEMETRY] {color}{bus_id}{RESET_COLOR} (R-{route_id}) "
                    f"| Lat: {payload['latitude']:.5f}, Lon: {payload['longitude']:.5f} "
                    f"| Spd: {payload['speed']:4.1f} km/h | Hdg: {payload['heading']:5.1f} deg "
                    f"| Step {idx + 1}/{total_waypoints} | {status_symbol} ({elapsed_ms:.1f}ms)"
                )
            except Exception as e:
                print(f"[ERROR] {bus_id} telemetry transmission failed: {e}")

            await asyncio.sleep(delay_between_points)

        if not loop_continuously or (max_steps > 0):
            break
        print(f"[*] {color}{bus_id}{RESET_COLOR} completed trajectory cycle {iteration}. Looping back to start...")


async def main_async(endpoint: str, speed_multiplier: float, loop_continuously: bool, max_steps: int):
    print("==================================================================")
    print(" BusSense-AI Fleet Telemetry Simulator (SIMULATED TELEMETRY)")
    print("==================================================================")
    print(f" Target API Endpoint: {endpoint}")
    print(f" Simulation Speed:    {speed_multiplier}x real-time")
    print(f" Continuous Looping:  {loop_continuously}")
    print(f" Active Buses:        {[b['bus_id'] for b in BUS_CONFIGS]}")
    print("==================================================================\n")

    limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
    async with httpx.AsyncClient(limits=limits) as client:
        tasks = [
            simulate_single_bus(
                bus_config=cfg,
                client=client,
                endpoint=endpoint,
                speed_multiplier=speed_multiplier,
                loop_continuously=loop_continuously,
                max_steps=max_steps,
            )
            for cfg in BUS_CONFIGS
        ]
        await asyncio.gather(*tasks)

    print("\n[OK] Fleet simulation run finished.")


def main():
    parser = argparse.ArgumentParser(description="Simulate BusSense-AI bus fleet telemetry.")
    parser.add_argument(
        "--speed",
        type=str,
        default="5x",
        help="Playback speed multiplier, e.g. '1x', '5x', '10x' (default: 5x)",
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default="http://127.0.0.1:8000/api/telemetry",
        help="Target FastAPI telemetry ingestion endpoint",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Continuously loop GPS trajectories for long-running demonstrations",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=0,
        help="Limit number of trajectory steps (0 = full trajectory)",
    )
    args = parser.parse_args()

    # Parse speed multiplier string (e.g. "5x" -> 5.0)
    speed_str = args.speed.lower().replace("x", "").strip()
    try:
        speed_multiplier = float(speed_str)
    except ValueError:
        speed_multiplier = 5.0

    asyncio.run(
        main_async(
            endpoint=args.endpoint,
            speed_multiplier=speed_multiplier,
            loop_continuously=args.loop,
            max_steps=args.steps,
        )
    )


if __name__ == "__main__":
    main()
