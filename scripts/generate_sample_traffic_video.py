"""Generates a sample urban traffic video with realistic moving vehicles for testing edge AI detection.

Output: data/videos/sample_bus_feed.mp4
NOTE: SIMULATED VIDEO FEED FOR HACKATHON PROTOTYPE TESTING.
"""

import math
import numpy as np
import cv2
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_VIDEO_PATH = PROJECT_ROOT / "data" / "videos" / "sample_bus_feed.mp4"


def draw_car(frame: np.ndarray, x: int, y: int, color=(40, 40, 200), width=90, height=45):
    """Draws a stylized top/front view of a car."""
    # Body
    cv2.rectangle(frame, (x, y), (x + width, y + height), color, -1)
    cv2.rectangle(frame, (x, y), (x + width, y + height), (20, 20, 20), 2)
    # Windshield / roof
    cv2.rectangle(frame, (x + 15, y + 6), (x + width - 15, y + height - 6), (200, 220, 240), -1)
    # Headlights / Taillights
    cv2.circle(frame, (x + 4, y + 8), 4, (0, 255, 255), -1)
    cv2.circle(frame, (x + 4, y + height - 8), 4, (0, 255, 255), -1)
    cv2.circle(frame, (x + width - 4, y + 8), 4, (0, 0, 255), -1)
    cv2.circle(frame, (x + width - 4, y + height - 8), 4, (0, 0, 255), -1)


def draw_bus(frame: np.ndarray, x: int, y: int, color=(34, 139, 34), width=180, height=60):
    """Draws a stylized bus."""
    cv2.rectangle(frame, (x, y), (x + width, y + height), color, -1)
    cv2.rectangle(frame, (x, y), (x + width, y + height), (10, 50, 10), 2)
    # Side windows
    for wx in range(x + 20, x + width - 25, 25):
        cv2.rectangle(frame, (wx, y + 8), (wx + 18, y + 25), (220, 240, 255), -1)
        cv2.rectangle(frame, (wx, y + height - 25), (wx + 18, y + height - 8), (220, 240, 255), -1)


def draw_truck(frame: np.ndarray, x: int, y: int, color=(180, 120, 30), width=160, height=55):
    """Draws a cargo truck."""
    # Cabin
    cv2.rectangle(frame, (x, y), (x + 45, y + height), (40, 40, 40), -1)
    # Cargo container
    cv2.rectangle(frame, (x + 48, y - 2), (x + width, y + height + 2), color, -1)
    cv2.rectangle(frame, (x + 48, y - 2), (x + width, y + height + 2), (20, 20, 20), 2)


def draw_motorcycle(frame: np.ndarray, x: int, y: int, color=(180, 50, 180), width=45, height=18):
    """Draws a motorcycle."""
    cv2.rectangle(frame, (x, y), (x + width, y + height), color, -1)
    cv2.circle(frame, (x + 6, y + height // 2), 6, (30, 30, 30), -1)
    cv2.circle(frame, (x + width - 6, y + height // 2), 6, (30, 30, 30), -1)


def generate_traffic_video(output_path=OUTPUT_VIDEO_PATH, num_frames=90, width=640, height=480, fps=25):
    """Generates synthetic urban road video with dynamic moving vehicles."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    print(f"[*] Generating {num_frames} frames of simulated urban traffic video -> {output_path}")

    # Simulated vehicle trajectories (x, y, speed_x, draw_func, color)
    vehicles = [
        {"type": "car", "x": 50, "y": 140, "spd": 4, "func": draw_car, "color": (50, 50, 220)},
        {"type": "bus", "x": 200, "y": 210, "spd": 3, "func": draw_bus, "color": (34, 197, 94)},
        {"type": "car", "x": 400, "y": 290, "spd": -5, "func": draw_car, "color": (220, 100, 50)},
        {"type": "truck", "x": 10, "y": 360, "spd": 2, "func": draw_truck, "color": (200, 140, 20)},
        {"type": "motorcycle", "x": 300, "y": 160, "spd": 6, "func": draw_motorcycle, "color": (160, 50, 200)},
    ]

    for frame_idx in range(num_frames):
        # Road Background (Asphalt Gray)
        frame = np.full((height, width, 3), (60, 60, 65), dtype=np.uint8)

        # Sidewalk curbs
        cv2.rectangle(frame, (0, 0), (width, 80), (120, 130, 135), -1)
        cv2.rectangle(frame, (0, height - 60), (width, height), (120, 130, 135), -1)

        # Road Lane Markings (White dashed lines)
        dash_offset = (frame_idx * 10) % 60
        for lane_y in [190, 270, 350]:
            for dash_x in range(-60 + dash_offset, width + 60, 60):
                cv2.rectangle(frame, (dash_x, lane_y), (dash_x + 30, lane_y + 4), (240, 240, 240), -1)

        # Draw moving vehicles
        for v in vehicles:
            v["func"](frame, int(v["x"]), int(v["y"]), v["color"])
            v["x"] += v["spd"]

            # Wrap around screen edges
            if v["spd"] > 0 and v["x"] > width + 100:
                v["x"] = -150
            elif v["spd"] < 0 and v["x"] < -200:
                v["x"] = width + 50

        # Bus Dashboard / Hood overlay at the bottom
        cv2.rectangle(frame, (0, height - 30), (width, height), (25, 25, 30), -1)
        cv2.putText(frame, f"BusSense-AI | Camera Feed #CAM_01 | Frame {frame_idx:04d}", (20, height - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (56, 189, 248), 1)

        writer.write(frame)

    writer.release()
    print(f"[OK] Successfully created sample video: {output_path} ({num_frames} frames, {width}x{height} @ {fps}fps)")


if __name__ == "__main__":
    generate_traffic_video()
