"""Generates realistic simulated GPS trajectory CSV files for BusSense-AI prototype fleet in Hyderabad.

Simulated Hyderabad Transit Routes:
- BUS_101 -> Route 216 (Mehdipatnam -> Hitec City / Cyber Towers)
- BUS_102 -> Route 10 (Secunderabad Station -> Charminar via Tank Bund)
- BUS_103 -> Route 49 (Dilsukhnagar -> Jubilee Hills Checkpost)

Format: timestamp,latitude,longitude,speed,heading
NOTE: SIMULATED TELEMETRY FOR HACKATHON PROTOTYPE DEMONSTRATION (HYDERABAD METROPOLITAN REGION).
"""

import math
import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path

DATA_GPS_DIR = Path(__file__).resolve().parent.parent / "data" / "gps"


def calculate_heading(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate geographic heading (bearing) in degrees from (lat1, lon1) to (lat2, lon2)."""
    d_lon = math.radians(lon2 - lon1)
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)

    y = math.sin(d_lon) * math.cos(lat2_r)
    x = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(d_lon)
    initial_bearing = math.atan2(y, x)
    initial_bearing = math.degrees(initial_bearing)
    compass_bearing = (initial_bearing + 360) % 360
    return round(compass_bearing, 1)


def interpolate_route(key_waypoints: list, steps_per_segment: int = 15, base_speed: float = 32.0) -> list:
    """Interpolate intermediate GPS waypoints between key anchor coordinates."""
    points = []
    current_time = datetime.now(timezone.utc)

    for i in range(len(key_waypoints) - 1):
        lat_start, lon_start, is_stop = key_waypoints[i]
        lat_end, lon_end, _ = key_waypoints[i + 1]

        heading = calculate_heading(lat_start, lon_start, lat_end, lon_end)

        # If it's a bus stop, add a brief 3-second dwell time with 0 speed
        if is_stop and i > 0:
            for _ in range(3):
                points.append({
                    "timestamp": current_time.isoformat(),
                    "latitude": round(lat_start, 6),
                    "longitude": round(lon_start, 6),
                    "speed": 0.0,
                    "heading": heading,
                })
                current_time += timedelta(seconds=1)

        for step in range(steps_per_segment):
            alpha = step / float(steps_per_segment)
            lat = lat_start + alpha * (lat_end - lat_start)
            lon = lon_start + alpha * (lon_end - lon_start)
            
            # Realistic urban speed variation
            speed_factor = 0.8 + 0.4 * math.sin(step * 0.5)
            speed = max(10.0, min(55.0, base_speed * speed_factor))

            points.append({
                "timestamp": current_time.isoformat(),
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "speed": round(speed, 1),
                "heading": heading,
            })
            current_time += timedelta(seconds=1)

    return points


def generate_all_trajectories():
    DATA_GPS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. BUS_101 -> Route 216 (Mehdipatnam -> Hitec City / Cyber Towers)
    # format: (lat, lon, is_bus_stop)
    route_216_waypoints = [
        (17.3916, 78.4350, False),  # Mehdipatnam Bus Terminal
        (17.3995, 78.4110, True),   # Tolichowki
        (17.4080, 78.3880, False),  # Shaikpet / Dargah
        (17.4400, 78.3489, True),   # Gachibowli ORR Junction
        (17.4440, 78.3810, False),  # Mindspace Junction
        (17.4504, 78.3808, False),  # Cyber Towers / Hitec City
    ]

    # 2. BUS_102 -> Route 10 (Secunderabad Station -> Charminar)
    route_10_waypoints = [
        (17.4340, 78.5015, False),  # Secunderabad Railway Station
        (17.4265, 78.4900, True),   # Ranigunj / Minister Road
        (17.4180, 78.4800, False),  # Tank Bund / Hussain Sagar
        (17.4060, 78.4720, True),   # Secretariat / Telugu Thalli
        (17.3900, 78.4750, False),  # Abids / GPO
        (17.3750, 78.4770, True),   # Afzal Gunj / Nayapul
        (17.3616, 78.4747, False),  # Charminar Bus Stop
    ]

    # 3. BUS_103 -> Route 49 (Dilsukhnagar -> Jubilee Hills Checkpost)
    route_49_waypoints = [
        (17.3688, 78.5247, False),  # Dilsukhnagar Terminal
        (17.3760, 78.5020, True),   # Malakpet Metro
        (17.3855, 78.4850, False),  # Koti / Sultan Bazar
        (17.4050, 78.4630, True),   # Lakdikapul
        (17.4010, 78.4480, False),  # Masab Tank
        (17.4160, 78.4420, True),   # Banjara Hills Road No 1
        (17.4278, 78.4115, False),  # Jubilee Hills Checkpost
    ]

    trajectories = {
        "BUS_101.csv": (route_216_waypoints, 20, 35.0),
        "BUS_102.csv": (route_10_waypoints, 18, 28.0),
        "BUS_103.csv": (route_49_waypoints, 18, 30.0),
    }

    for filename, (waypoints, steps, base_speed) in trajectories.items():
        points = interpolate_route(waypoints, steps_per_segment=steps, base_speed=base_speed)
        df = pd.DataFrame(points)
        output_path = DATA_GPS_DIR / filename
        df.to_csv(output_path, index=False)
        print(f"[OK] Generated {len(df)} simulated Hyderabad GPS points -> {output_path}")


if __name__ == "__main__":
    generate_all_trajectories()
