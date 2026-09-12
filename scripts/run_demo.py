"""One-Command Demo Mode Runner for SIH Presentation.

Orchestrates all BusSense-AI subsystems in a single execution:
1. Verifies database and backend environment.
2. Seeds high-quality realistic datasets & visual evidence frames.
3. Spawns FastAPI backend server (if not already running).
4. Launches multi-bus fleet telemetry simulator (BUS_101, BUS_102, BUS_103) at demo speed (5x).
5. Kicks off edge AI video processing on benchmark footage in background.
6. Automatically opens the web browser to the CitySense Light Mode dashboard.
7. Displays synchronized live terminal telemetry monitoring.

Usage:
    python scripts/run_demo.py [--speed 5.0] [--port 8000] [--reset] [--no-browser]
"""

import os
import sys
import time
import signal
import socket
import argparse
import subprocess
import webbrowser
import threading
from pathlib import Path
from datetime import datetime, timezone

# Project root setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.seed_demo_dataset import seed_all_demo_data


def check_port_open(host: str, port: int) -> bool:
    """Checks if a network port is already accepting connections."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    try:
        s.connect((host, port))
        s.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def start_backend_server(port: int = 8000) -> subprocess.Popen:
    """Starts Uvicorn server in a subprocess if not running."""
    if check_port_open("127.0.0.1", port):
        print(f" [*] FastAPI Backend already running on http://127.0.0.1:{port}")
        return None

    print(f" [*] Launching FastAPI Backend on http://127.0.0.1:{port}...")
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    # Wait for server to become healthy
    for _ in range(25):
        time.sleep(0.4)
        if check_port_open("127.0.0.1", port):
            print(f" [OK] FastAPI Backend online on http://127.0.0.1:{port}")
            return proc

    print(" [!] Backend startup wait timeout. Proceeding...")
    return proc


def run_bus_simulator_thread(speed_multiplier: float, port: int):
    """Runs the bus fleet simulator in a background worker thread."""
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "run_bus_simulator.py"),
        "--speed",
        f"{speed_multiplier}x",
        "--endpoint",
        f"http://127.0.0.1:{port}/api/telemetry",
        "--loop",
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    for line in iter(proc.stdout.readline, ""):
        if line.strip():
            if "[SIMULATED TELEMETRY]" in line or "[*]" in line:
                print(f" {line.strip()}")


def run_edge_demo_pipeline(port: int):
    """Dispatches a benchmark video clip to the edge pipeline in background after 30 seconds."""
    time.sleep(15.0)
    print("\n [*] Triggering Edge AI Video Pipeline on benchmark clip (Pothole Defect)...")
    video_path = PROJECT_ROOT / "data" / "videos" / "Pothole.mp4"
    gps_path = PROJECT_ROOT / "data" / "gps" / "BUS_101.csv"

    if video_path.exists() and gps_path.exists():
        try:
            import httpx
            with open(video_path, "rb") as vf, open(gps_path, "rb") as gf:
                files = {
                    "video": ("Pothole.mp4", vf, "video/mp4"),
                    "gps": ("BUS_101.csv", gf, "text/csv"),
                }
                data = {
                    "bus_id": "BUS_101",
                    "route_id": "216",
                    "enable_vehicles": "true",
                    "enable_defects": "true",
                    "enable_ocr": "false",
                    "enable_incidents": "false",
                    "enable_density": "true",
                }
                resp = httpx.post(
                    f"http://127.0.0.1:{port}/api/process-video",
                    files=files,
                    data=data,
                    timeout=10.0,
                )
                if resp.status_code in (200, 202):
                    print(" [OK] Benchmark video job enqueued successfully! Live detections streaming to map...")
        except Exception as e:
            print(f" [!] Edge demo dispatch note: {e}")


def main():
    parser = argparse.ArgumentParser(description="BusSense-AI One-Command Demo Mode Runner")
    parser.add_argument("--speed", type=float, default=5.0, help="Bus movement speed multiplier (default: 5.0x)")
    parser.add_argument("--port", type=int, default=8000, help="Backend port (default: 8000)")
    parser.add_argument("--reset", action="store_true", help="Reset all demo events & regenerate evidence")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically launch web browser")

    args = parser.parse_args()

    print("==================================================================")
    print(" BusSense-AI: SMART INDIA HACKATHON ONE-COMMAND DEMO RUNNER")
    print("==================================================================")
    print(f" Server Target:  http://127.0.0.1:{args.port}")
    print(f" Simulator Speed: {args.speed}x real-time")
    print(f" Mode:           Full Subsystem Orchestration")
    print("==================================================================\n")

    # Step 1: Seed real visual datasets and evidence frames
    seed_all_demo_data()

    # Step 2: Start backend server
    backend_proc = start_backend_server(args.port)

    # Step 3: Open browser
    dashboard_url = f"http://127.0.0.1:{args.port}/"
    if not args.no_browser:
        print(f" [*] Opening CitySense Dashboard in default browser: {dashboard_url}")
        time.sleep(1.0)
        webbrowser.open(dashboard_url)

    # Step 4: Start background Edge AI benchmark processing
    edge_thread = threading.Thread(target=run_edge_demo_pipeline, args=(args.port,), daemon=True)
    edge_thread.start()

    # Step 5: Start bus simulator in thread
    print(" [*] Starting Real-Time Transit Fleet Simulator (BUS_101, BUS_102, BUS_103)...")
    print(" [!] Press Ctrl+C at any time to stop the demo.\n")
    sim_thread = threading.Thread(target=run_bus_simulator_thread, args=(args.speed, args.port), daemon=True)
    sim_thread.start()

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n\n [*] Gracefully shutting down demo subsystems...")
        if backend_proc:
            backend_proc.terminate()
        print(" [OK] Demo shutdown complete. Ready for next presentation run!\n")


if __name__ == "__main__":
    main()
