"""Seed high-quality, realistic urban sensing datasets and evidence frames for BusSense-AI.

Generates realistic visual evidence images with bounding boxes, HUD telemetry banners,
and metadata for all required urban event categories:
- Road Defects (Potholes, Road Cracks, Waterlogging, Missing Signboards)
- Traffic Incidents (Rash Driving, Suspected Hit-and-Run with ANPR license plates)
- Traffic Density Hotspots across Hyderabad Corridors (Route 216, Route 10, Route 49M)

Supports distinct timestamp distributions for 24 Hours, 7 Days, and 30 Days analytics.
"""

import os
import sys
import cv2
import json
import uuid
import random
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Paths & Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

EVIDENCE_DIR = PROJECT_ROOT / "data" / "outputs" / "unified_evidence"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Visual Evidence Frame Generator
# ---------------------------------------------------------------------------
def create_realistic_evidence_frame(
    event_type: str,
    bus_id: str,
    route_id: str,
    lat: float,
    lon: float,
    speed: float,
    confidence: float,
    severity: str,
    details: dict,
    timestamp_str: str,
) -> str:
    """Generates an annotated 1280x720 evidence frame with realistic visual cues,
    bounding box annotations, class badges, and telemetry HUD overlay.
    """
    w, h = 1280, 720
    # Create base asphalt road texture
    frame = np.full((h, w, 3), (45, 48, 52), dtype=np.uint8)

    # Draw road perspective lines (lane markings)
    cv2.line(frame, (100, h), (550, 320), (220, 220, 220), 4) # Left lane
    cv2.line(frame, (w - 100, h), (730, 320), (220, 220, 220), 4) # Right lane
    # Center dashed yellow line
    for y in range(320, h, 60):
        t1 = (y - 320) / (h - 320)
        t2 = (y + 30 - 320) / (h - 320)
        x1 = int(640 + (300 * t1 if t1 > 0 else 0) * 0.1)
        x2 = int(640 + (300 * t2 if t2 > 0 else 0) * 0.1)
        cv2.line(frame, (640, y), (640, y + 30), (0, 215, 255), 4)

    # Road surface texture noise
    noise = np.random.randint(-15, 15, (h, w, 3), dtype=np.int16)
    frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # Draw specific event visual cues
    if event_type == "POTHOLE":
        # Draw realistic dark asphalt cavity with rim
        cx, cy = 620, 520
        cv2.ellipse(frame, (cx, cy), (130, 65), 10, 0, 360, (20, 20, 24), -1)
        cv2.ellipse(frame, (cx, cy), (135, 68), 10, 0, 360, (70, 75, 80), 3)
        # Inner cracks
        cv2.polylines(frame, [np.array([[cx-80, cy-10], [cx-40, cy+15], [cx+30, cy-5], [cx+70, cy+20]])], False, (10, 10, 15), 2)
        # Bounding box
        bx1, by1, bx2, by2 = cx - 150, cy - 80, cx + 150, cy + 80
        cv2.rectangle(frame, (bx1, by1), (bx2, by2), (0, 0, 240), 3)
        label = f"POTHOLE ({confidence*100:.0f}%) | SEV: {severity.upper()}"
        cv2.rectangle(frame, (bx1, by1 - 32), (bx1 + 330, by1), (0, 0, 220), -1)
        cv2.putText(frame, label, (bx1 + 8, by1 - 10), cv2.FONT_HERSHEY_DUPLEX, 0.65, (255, 255, 255), 1, cv2.LINE_AA)

    elif event_type == "WATERLOGGING":
        cx, cy = 640, 500
        # Water puddle with reflective sheen
        cv2.ellipse(frame, (cx, cy), (240, 80), -5, 0, 360, (85, 75, 45), -1)
        cv2.ellipse(frame, (cx + 20, cy - 10), (160, 45), -5, 0, 360, (130, 115, 70), -1)
        bx1, by1, bx2, by2 = cx - 260, cy - 95, cx + 260, cy + 95
        cv2.rectangle(frame, (bx1, by1), (bx2, by2), (255, 140, 0), 3)
        label = f"WATERLOGGING ({confidence*100:.0f}%) | SEV: {severity.upper()}"
        cv2.rectangle(frame, (bx1, by1 - 32), (bx1 + 380, by1), (255, 140, 0), -1)
        cv2.putText(frame, label, (bx1 + 8, by1 - 10), cv2.FONT_HERSHEY_DUPLEX, 0.65, (255, 255, 255), 1, cv2.LINE_AA)

    elif event_type == "DAMAGED_ROAD_SURFACE":
        cx, cy = 600, 480
        # Surface spiderweb cracking
        for angle in range(0, 360, 45):
            rad = np.deg2rad(angle)
            ex = int(cx + 140 * np.cos(rad) + random.randint(-15, 15))
            ey = int(cy + 70 * np.sin(rad) + random.randint(-10, 10))
            cv2.line(frame, (cx, cy), (ex, ey), (15, 18, 20), 2)
        bx1, by1, bx2, by2 = cx - 160, cy - 80, cx + 160, cy + 80
        cv2.rectangle(frame, (bx1, by1), (bx2, by2), (0, 165, 255), 3)
        label = f"DAMAGED ROAD ({confidence*100:.0f}%) | SEV: {severity.upper()}"
        cv2.rectangle(frame, (bx1, by1 - 32), (bx1 + 360, by1), (0, 165, 255), -1)
        cv2.putText(frame, label, (bx1 + 8, by1 - 10), cv2.FONT_HERSHEY_DUPLEX, 0.65, (255, 255, 255), 1, cv2.LINE_AA)

    elif event_type in ("RASH_DRIVING", "SUSPECTED_HIT_AND_RUN"):
        # Draw aggressive moving vehicle with dynamic bounding box & velocity vector
        vx1, vy1, vx2, vy2 = 420, 330, 860, 610
        # Car body
        cv2.rectangle(frame, (vx1, vy1 + 60), (vx2, vy2), (180, 40, 40), -1)
        # Car cabin / roof
        cv2.rectangle(frame, (vx1 + 80, vy1), (vx2 - 80, vy1 + 100), (140, 30, 30), -1)
        # Rear windshield
        cv2.rectangle(frame, (vx1 + 100, vy1 + 15), (vx2 - 100, vy1 + 75), (50, 60, 70), -1)
        # Tail lights
        cv2.rectangle(frame, (vx1 + 15, vy1 + 90), (vx1 + 75, vy1 + 130), (0, 0, 255), -1)
        cv2.rectangle(frame, (vx2 - 75, vy1 + 90), (vx2 - 15, vy1 + 130), (0, 0, 255), -1)

        # License plate
        reg_num = details.get("registration_number", "TS09EA1234")
        plate_x1, plate_y1, plate_x2, plate_y2 = 570, 520, 710, 565
        cv2.rectangle(frame, (plate_x1, plate_y1), (plate_x2, plate_y2), (255, 255, 255), -1)
        cv2.rectangle(frame, (plate_x1, plate_y1), (plate_x2, plate_y2), (0, 0, 0), 2)
        cv2.putText(frame, reg_num, (plate_x1 + 10, plate_y1 + 32), cv2.FONT_HERSHEY_DUPLEX, 0.75, (0, 0, 0), 2, cv2.LINE_AA)

        # Kinematic bounding box (Red for high severity)
        cv2.rectangle(frame, (vx1 - 15, vy1 - 15), (vx2 + 15, vy2 + 15), (0, 0, 255), 3)
        # Velocity arrow vector (Slalom / surge vector)
        cv2.arrowedLine(frame, (vx2 + 15, vy1 + 50), (vx2 + 110, vy1 - 30), (0, 255, 255), 4, tipLength=0.3)
        cv2.putText(frame, "+34 km/h surge", (vx2 + 30, vy1 - 40), cv2.FONT_HERSHEY_DUPLEX, 0.55, (0, 255, 255), 1, cv2.LINE_AA)

        inc_label = f"INCIDENT: {event_type} | CONF: {confidence*100:.0f}% | PLATE: {reg_num}"
        cv2.rectangle(frame, (vx1 - 15, vy1 - 50), (vx1 + 580, vy1 - 15), (140, 20, 220), -1)
        cv2.putText(frame, inc_label, (vx1 - 5, by1 if 'by1' in locals() else vy1 - 25), cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

    else:
        # Generic defect / event
        cx, cy = 640, 500
        bx1, by1, bx2, by2 = cx - 120, cy - 60, cx + 120, cy + 60
        cv2.rectangle(frame, (bx1, by1), (bx2, by2), (0, 200, 255), 3)
        label = f"{event_type} ({confidence*100:.0f}%)"
        cv2.rectangle(frame, (bx1, by1 - 30), (bx1 + 280, by1), (0, 200, 255), -1)
        cv2.putText(frame, label, (bx1 + 8, by1 - 8), cv2.FONT_HERSHEY_DUPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)

    # -----------------------------------------------------------------------
    # Top Telemetry HUD Banner (High-contrast, professional styling)
    # -----------------------------------------------------------------------
    hud_h = 76
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, hud_h), (15, 23, 42), -1) # Dark slate
    cv2.addWeighted(overlay, 0.92, frame, 0.08, 0, frame)
    cv2.line(frame, (0, hud_h), (w, hud_h), (37, 99, 235), 2) # Accent blue line

    line1 = f"CitySense Edge AI | Fleet Unit: {bus_id} (Route {route_id}) | Sensor: FRONT_DASHCAM_1080P"
    line2 = f"GPS: {lat:.6f}, {lon:.6f} | Speed: {speed:.1f} km/h | Time: {timestamp_str} UTC | STATUS: OPERATIONAL"

    cv2.putText(frame, line1, (20, 30), cv2.FONT_HERSHEY_DUPLEX, 0.65, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, line2, (20, 60), cv2.FONT_HERSHEY_DUPLEX, 0.55, (148, 163, 184), 1, cv2.LINE_AA)

    # Bottom watermark disclaimer
    cv2.putText(frame, "SIMULATED TELEMETRY & EDGE CV EVIDENCE - SMART INDIA HACKATHON PROTOTYPE", (20, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 180, 180), 1, cv2.LINE_AA)

    # Save evidence JPEG
    filename = f"evidence_{bus_id}_{event_type.lower()}_{uuid.uuid4().hex[:8]}.jpg"
    filepath = EVIDENCE_DIR / filename
    cv2.imwrite(str(filepath), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return f"/evidence/unified_evidence/{filename}"


# ---------------------------------------------------------------------------
# Canonical Seed Events with Hyderabad Geometries & Real Evidence
# ---------------------------------------------------------------------------
CANONICAL_SEED_EVENTS = [
    # 1. Potholes on Route 216 (Mehdipatnam -> Hitec City)
    {
        "event_id": "evt_pothole_001",
        "bus_id": "BUS_101",
        "route_id": "216",
        "event_type": "POTHOLE",
        "event_category": "ROAD_DEFECT",
        "confidence": 0.94,
        "severity": "high",
        "status": "detected",
        "latitude": 17.4082,
        "longitude": 78.3884,
        "speed": 32.5,
        "heading": 285.0,
        "details": {"defect_area_px": 14200, "surface": "asphalt", "depth_est_cm": 6.5},
        "days_ago": 0,
        "hours_ago": 2,
    },
    {
        "event_id": "evt_pothole_002",
        "bus_id": "BUS_101",
        "route_id": "216",
        "event_type": "POTHOLE",
        "event_category": "ROAD_DEFECT",
        "confidence": 0.91,
        "severity": "medium",
        "status": "verified",
        "latitude": 17.4412,
        "longitude": 78.3510,
        "speed": 41.0,
        "heading": 310.0,
        "details": {"defect_area_px": 8900, "surface": "asphalt", "depth_est_cm": 4.2},
        "days_ago": 1,
        "hours_ago": 5,
    },
    # 2. Waterlogging on Route 10 (Secunderabad -> Charminar)
    {
        "event_id": "evt_waterlog_001",
        "bus_id": "BUS_102",
        "route_id": "10",
        "event_type": "WATERLOGGING",
        "event_category": "ROAD_DEFECT",
        "confidence": 0.89,
        "severity": "high",
        "status": "under_review",
        "latitude": 17.4182,
        "longitude": 78.4802,
        "speed": 18.0,
        "heading": 180.0,
        "details": {"water_spread_m2": 35.0, "submerged_lane": "left_lane", "corridor": "Tank Bund"},
        "days_ago": 0,
        "hours_ago": 1,
    },
    {
        "event_id": "evt_crack_001",
        "bus_id": "BUS_102",
        "route_id": "10",
        "event_type": "DAMAGED_ROAD_SURFACE",
        "event_category": "ROAD_DEFECT",
        "confidence": 0.86,
        "severity": "medium",
        "status": "resolved",
        "latitude": 17.3912,
        "longitude": 78.4752,
        "speed": 28.5,
        "heading": 175.0,
        "details": {"crack_pattern": "alligator_cracking", "surface_wear": "high"},
        "days_ago": 4,
        "hours_ago": 10,
    },
    # 3. Rash Driving on Route 49M (Dilsukhnagar -> Jubilee Hills)
    {
        "event_id": "evt_rash_001",
        "bus_id": "BUS_103",
        "route_id": "49M",
        "event_type": "RASH_DRIVING",
        "event_category": "TRAFFIC_INCIDENT",
        "confidence": 0.93,
        "severity": "high",
        "status": "NEW",
        "latitude": 17.4265,
        "longitude": 78.4525,
        "speed": 48.0,
        "heading": 300.0,
        "details": {
            "vehicle_tracking_id": 42,
            "registration_number": "TS09EA1234",
            "registration_confidence": 0.94,
            "rule_details": {
                "lateral_slalom_m": 2.8,
                "flight_acceleration_m_s2": 4.1,
                "ttc_seconds": 1.2
            }
        },
        "days_ago": 0,
        "hours_ago": 0.5,
    },
    # 4. Suspected Hit and Run on Route 216
    {
        "event_id": "evt_incident_002",
        "bus_id": "BUS_101",
        "route_id": "216",
        "event_type": "SUSPECTED_HIT_AND_RUN",
        "event_category": "TRAFFIC_INCIDENT",
        "confidence": 0.90,
        "severity": "critical",
        "status": "UNDER_REVIEW",
        "latitude": 17.4498,
        "longitude": 78.3812,
        "speed": 54.0,
        "heading": 45.0,
        "details": {
            "vehicle_tracking_id": 78,
            "registration_number": "TS07UK8892",
            "registration_confidence": 0.91,
            "rule_details": {
                "impact_proximity_m": 0.8,
                "flight_speed_delta_kmh": 32.0,
                "scene_departure_seconds": 2.1
            }
        },
        "days_ago": 2,
        "hours_ago": 8,
    },
    # 5. Additional Historical Events across 7d and 30d
    {
        "event_id": "evt_pothole_003",
        "bus_id": "BUS_103",
        "route_id": "49M",
        "event_type": "POTHOLE",
        "event_category": "ROAD_DEFECT",
        "confidence": 0.88,
        "severity": "low",
        "status": "resolved",
        "latitude": 17.3785,
        "longitude": 78.4985,
        "speed": 35.0,
        "heading": 290.0,
        "details": {"defect_area_px": 4500, "surface": "asphalt"},
        "days_ago": 12,
        "hours_ago": 14,
    },
    {
        "event_id": "evt_rash_002",
        "bus_id": "BUS_102",
        "route_id": "10",
        "event_type": "RASH_DRIVING",
        "event_category": "TRAFFIC_INCIDENT",
        "confidence": 0.87,
        "severity": "medium",
        "status": "RESOLVED",
        "latitude": 17.3620,
        "longitude": 78.4750,
        "speed": 42.0,
        "heading": 180.0,
        "details": {
            "vehicle_tracking_id": 19,
            "registration_number": "AP11BX4040",
            "registration_confidence": 0.88,
            "rule_details": {"lateral_slalom_m": 2.1, "ttc_seconds": 1.5}
        },
        "days_ago": 18,
        "hours_ago": 16,
    }
]


def seed_all_demo_data():
    """Generates all real visual evidence files and seeds SQLite/PostgreSQL and memory stores."""
    print("==================================================================")
    print(" BusSense-AI Realistic Demo Dataset & Visual Evidence Generator")
    print("==================================================================")

    now = datetime.now(timezone.utc)
    generated_records = []

    for item in CANONICAL_SEED_EVENTS:
        event_time = now - timedelta(days=item["days_ago"], hours=item["hours_ago"])
        time_iso = event_time.isoformat()
        time_str = event_time.strftime("%Y-%m-%d %H:%M:%S")

        # Generate realistic image frame with HUD overlay
        img_url = create_realistic_evidence_frame(
            event_type=item["event_type"],
            bus_id=item["bus_id"],
            route_id=item["route_id"],
            lat=item["latitude"],
            lon=item["longitude"],
            speed=item["speed"],
            confidence=item["confidence"],
            severity=item["severity"],
            details=item["details"],
            timestamp_str=time_str,
        )

        record = {
            "event_id": item["event_id"],
            "bus_id": item["bus_id"],
            "route_id": item["route_id"],
            "event_type": item["event_type"],
            "event_category": item["event_category"],
            "confidence": item["confidence"],
            "severity": item["severity"],
            "status": item["status"],
            "latitude": item["latitude"],
            "longitude": item["longitude"],
            "image_path": img_url,
            "video_timestamp": 12.5,
            "timestamp": time_iso,
            "details": item["details"],
            "is_simulated": True,
            "disclaimer": "prototype heuristic estimation — rule-based detection, not forensic determination",
        }
        generated_records.append(record)
        print(f" [+] Generated evidence & event: {item['event_id']} ({item['event_type']} on {item['bus_id']}) -> {img_url}")

    # Write output to mock JSON seed file
    seed_json_path = PROJECT_ROOT / "data" / "outputs" / "seeded_demo_events.json"
    seed_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(seed_json_path, "w", encoding="utf-8") as f:
        json.dump(generated_records, f, indent=2)

    # Populate backend in-memory event store directly
    try:
        from backend.routes.events import _IN_MEMORY_EVENTS
        from backend.schemas.event import EventResponse

        for rec in generated_records:
            resp = EventResponse(**rec)
            _IN_MEMORY_EVENTS[rec["event_id"]] = resp
        print(f" [*] Injected {len(generated_records)} records into backend in-memory event store.")
    except Exception as e:
        print(f" [!] In-memory event injection notice: {e}")

    # Populate PostgreSQL if database is active
    try:
        from backend.database import SessionLocal
        from backend.models import Event, Bus

        db = SessionLocal()
        try:
            for rec in generated_records:
                existing = db.query(Event).filter_by(event_id=rec["event_id"]).first()
                if not existing:
                    # Ensure bus exists
                    bus = db.query(Bus).filter_by(bus_id=rec["bus_id"]).first()
                    if not bus:
                        bus = Bus(
                            bus_id=rec["bus_id"],
                            route_id=rec["route_id"],
                            latitude=rec["latitude"],
                            longitude=rec["longitude"],
                            speed=30.0,
                            heading=180.0,
                            status="active"
                        )
                        db.add(bus)
                        db.flush()

                    db_evt = Event(
                        event_id=rec["event_id"],
                        bus_id=rec["bus_id"],
                        event_type=rec["event_type"],
                        confidence=rec["confidence"],
                        latitude=rec["latitude"],
                        longitude=rec["longitude"],
                        severity=rec["severity"],
                        status=rec["status"],
                        image_path=rec["image_path"],
                        video_timestamp=rec["video_timestamp"],
                        timestamp=datetime.fromisoformat(rec["timestamp"].replace("Z", "+00:00")),
                        metadata={
                            "event_category": rec["event_category"],
                            "route_id": rec["route_id"],
                            "details": rec["details"],
                            "is_simulated": True,
                            "disclaimer": rec["disclaimer"]
                        }
                    )
                    db.add(db_evt)
            db.commit()
            print(" [*] Successfully persisted seeded records to PostgreSQL database.")
        except Exception as e:
            db.rollback()
            print(f" [!] PostgreSQL persistence skipped (offline/unreachable): {e}")
        finally:
            db.close()
    except Exception as e:
        print(f" [!] DB connection check: {e}")

    print("==================================================================")
    print(" [OK] Dataset and visual evidence generation completed successfully!")
    print("==================================================================\n")
    return generated_records


if __name__ == "__main__":
    seed_all_demo_data()
