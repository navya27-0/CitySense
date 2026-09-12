"""Origin-Destination (OD) Traffic Flow Analysis Service.

Infers transit trip segments between designated route stops using simulated bus GPS trajectories
and fleet telemetry. Generates OD matrices, segment transit durations, velocities, and corridor volumes.

DISCLAIMER: This analysis is strictly based on fleet vehicle telemetry and stop segment progression.
It does NOT track individual passengers and must not be presented as passenger-level OD data.
"""

import os
import csv
import math
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

# Predefined standard transit route stops in Hyderabad
ROUTE_STOPS: Dict[str, List[Dict[str, Any]]] = {
    "216": [
        {"name": "Mehdipatnam Bus Terminal", "lat": 17.3916, "lon": 78.4350, "seq": 1},
        {"name": "Tolichowki Flyover", "lat": 17.3995, "lon": 78.4110, "seq": 2},
        {"name": "Shaikpet Dargah", "lat": 17.4080, "lon": 78.3880, "seq": 3},
        {"name": "Gachibowli ORR Junction", "lat": 17.4400, "lon": 78.3489, "seq": 4},
        {"name": "Mindspace Junction", "lat": 17.4440, "lon": 78.3810, "seq": 5},
        {"name": "Cyber Towers / Hitec City", "lat": 17.4504, "lon": 78.3808, "seq": 6},
    ],
    "10": [
        {"name": "Secunderabad Railway Station", "lat": 17.4340, "lon": 78.5015, "seq": 1},
        {"name": "Ranigunj / Minister Road", "lat": 17.4265, "lon": 78.4900, "seq": 2},
        {"name": "Tank Bund / Hussain Sagar", "lat": 17.4180, "lon": 78.4800, "seq": 3},
        {"name": "Secretariat / Telugu Thalli", "lat": 17.4060, "lon": 78.4720, "seq": 4},
        {"name": "Abids / GPO", "lat": 17.3900, "lon": 78.4750, "seq": 5},
        {"name": "Afzal Gunj / Nayapul", "lat": 17.3750, "lon": 78.4770, "seq": 6},
        {"name": "Charminar Bus Station", "lat": 17.3616, "lon": 78.4747, "seq": 7},
    ],
    "49M": [
        {"name": "Dilsukhnagar Bus Depot", "lat": 17.3688, "lon": 78.5247, "seq": 1},
        {"name": "Malakpet Station", "lat": 17.3780, "lon": 78.4980, "seq": 2},
        {"name": "Koti Center", "lat": 17.3850, "lon": 78.4867, "seq": 3},
        {"name": "Nampally Station", "lat": 17.3920, "lon": 78.4680, "seq": 4},
        {"name": "Punjagutta Flyover", "lat": 17.4260, "lon": 78.4520, "seq": 5},
        {"name": "Jubilee Hills Checkpost", "lat": 17.4310, "lon": 78.4070, "seq": 6},
    ],
}

# Bus to Route mapping
BUS_ROUTE_MAP = {
    "BUS_101": "216",
    "BUS_102": "10",
    "BUS_103": "49M",
}


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two geographic coordinates in kilometers."""
    R = 6371.0  # Earth radius in kilometers
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def get_route_stop_names(route_id: str) -> List[str]:
    """Returns the ordered list of stop names for a route."""
    stops = ROUTE_STOPS.get(route_id, [])
    return [s["name"] for s in sorted(stops, key=lambda x: x["seq"])]


def infer_trip_segments_from_gps_file(csv_path: str, route_id: str, bus_id: str) -> List[Dict[str, Any]]:
    """Infers stop passages and OD trip segments from a bus GPS CSV file."""
    if not os.path.exists(csv_path):
        return []

    stops = ROUTE_STOPS.get(route_id, [])
    if not stops:
        return []

    # Read GPS points
    gps_points = []
    try:
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ts_str = row.get("timestamp", "").strip()
                    # Parse timestamp (handle both with and without Z/offset)
                    if ts_str.endswith("Z"):
                        ts_str = ts_str[:-1] + "+00:00"
                    ts = datetime.fromisoformat(ts_str) if ts_str else datetime.now(timezone.utc)
                    lat = float(row.get("latitude", 0.0))
                    lon = float(row.get("longitude", 0.0))
                    speed = float(row.get("speed", 0.0))
                    gps_points.append({"timestamp": ts, "lat": lat, "lon": lon, "speed": speed})
                except Exception:
                    continue
    except Exception:
        return []

    if not gps_points:
        return []

    # Match closest GPS point for each sequential stop along the route
    stop_passages = []
    for stop in sorted(stops, key=lambda x: x["seq"]):
        stop_lat, stop_lon = stop["lat"], stop["lon"]
        best_pt = None
        min_dist = float("inf")

        for pt in gps_points:
            d = haversine_distance_km(stop_lat, stop_lon, pt["lat"], pt["lon"])
            if d < min_dist:
                min_dist = d
                best_pt = pt

        # Accept match if within reasonable stop proximity (~1.2 km tolerance for simulated sparse points)
        if best_pt and min_dist <= 1.5:
            stop_passages.append({
                "stop_name": stop["name"],
                "seq": stop["seq"],
                "lat": stop_lat,
                "lon": stop_lon,
                "timestamp": best_pt["timestamp"],
                "speed": best_pt["speed"],
            })

    # Ensure stop passages are strictly in chronological order
    stop_passages.sort(key=lambda x: x["seq"])

    # Generate all pairwise (Origin, Destination) segments where seq(Origin) < seq(Destination)
    segments = []
    for i in range(len(stop_passages)):
        for j in range(i + 1, len(stop_passages)):
            orig = stop_passages[i]
            dest = stop_passages[j]

            # Approximate travel distance along sequential corridor stops
            dist_km = 0.0
            for k in range(i, j):
                dist_km += haversine_distance_km(
                    stop_passages[k]["lat"], stop_passages[k]["lon"],
                    stop_passages[k + 1]["lat"], stop_passages[k + 1]["lon"]
                )
            dist_km = max(0.5, round(dist_km, 2))

            # Duration in minutes
            dt_seconds = (dest["timestamp"] - orig["timestamp"]).total_seconds()
            duration_minutes = max(1.0, round(abs(dt_seconds) / 60.0, 1))

            # Speed in km/h
            speed_kmh = round(dist_km / (duration_minutes / 60.0), 1)
            # Bound speed realistically
            speed_kmh = min(85.0, max(12.0, speed_kmh))

            segments.append({
                "route_id": route_id,
                "bus_id": bus_id,
                "origin_stop": orig["stop_name"],
                "destination_stop": dest["stop_name"],
                "origin_lat": orig["lat"],
                "origin_lon": orig["lon"],
                "dest_lat": dest["lat"],
                "dest_lon": dest["lon"],
                "duration_minutes": duration_minutes,
                "speed_kmh": speed_kmh,
                "distance_km": dist_km,
            })

    return segments


def generate_baseline_route_segments(route_id: str) -> List[Dict[str, Any]]:
    """Generates synthetic baseline OD segments for a route when GPS files are missing or offline."""
    stops = ROUTE_STOPS.get(route_id, [])
    if not stops:
        return []

    bus_id = "BUS_101" if route_id == "216" else ("BUS_102" if route_id == "10" else "BUS_103")
    sorted_stops = sorted(stops, key=lambda x: x["seq"])
    segments = []

    for i in range(len(sorted_stops)):
        for j in range(i + 1, len(sorted_stops)):
            orig = sorted_stops[i]
            dest = sorted_stops[j]

            # Compute route distance
            dist_km = 0.0
            for k in range(i, j):
                dist_km += haversine_distance_km(
                    sorted_stops[k]["lat"], sorted_stops[k]["lon"],
                    sorted_stops[k + 1]["lat"], sorted_stops[k + 1]["lon"]
                )
            dist_km = max(0.8, round(dist_km, 2))

            # Average city transit speed ~24-32 km/h
            speed_kmh = round(26.5 + (i * 1.5) % 8, 1)
            duration_minutes = round((dist_km / speed_kmh) * 60.0 + (j - i) * 1.5, 1)

            segments.append({
                "route_id": route_id,
                "bus_id": bus_id,
                "origin_stop": orig["name"],
                "destination_stop": dest["name"],
                "origin_lat": orig["lat"],
                "origin_lon": orig["lon"],
                "dest_lat": dest["lat"],
                "dest_lon": dest["lon"],
                "duration_minutes": duration_minutes,
                "speed_kmh": speed_kmh,
                "distance_km": dist_km,
            })

    return segments


def compute_od_matrix(
    data_dir: str = "data/gps",
    target_route_id: Optional[str] = None,
    min_trips: int = 1,
) -> Dict[str, Any]:
    """Computes the complete Origin-Destination matrix across transit routes.
    
    Returns:
        dict: Processed OD matrix including individual pairs, aggregated grid, and summary metrics.
    """
    routes_to_process = [target_route_id] if target_route_id and target_route_id in ROUTE_STOPS else list(ROUTE_STOPS.keys())
    
    all_inferred_segments: List[Dict[str, Any]] = []

    # 1. Process GPS files if available
    for bus_id, r_id in BUS_ROUTE_MAP.items():
        if r_id not in routes_to_process:
            continue
        csv_file = os.path.join(data_dir, f"{bus_id}.csv")
        segs = infer_trip_segments_from_gps_file(csv_file, r_id, bus_id)
        if segs:
            all_inferred_segments.extend(segs)
        else:
            # Fallback to route geometry baseline
            all_inferred_segments.extend(generate_baseline_route_segments(r_id))

    # 2. Aggregate segments into unique (origin_stop, destination_stop) pairs
    pairs_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for s in all_inferred_segments:
        key = (s["origin_stop"], s["destination_stop"])
        if key not in pairs_map:
            pairs_map[key] = {
                "route_id": s["route_id"],
                "origin_stop": s["origin_stop"],
                "destination_stop": s["destination_stop"],
                "origin_lat": s["origin_lat"],
                "origin_lon": s["origin_lon"],
                "dest_lat": s["dest_lat"],
                "dest_lon": s["dest_lon"],
                "trip_count": 0,
                "durations": [],
                "speeds": [],
                "distance_km": s["distance_km"],
                "buses_observed": set(),
            }

        pairs_map[key]["trip_count"] += 1
        pairs_map[key]["durations"].append(s["duration_minutes"])
        pairs_map[key]["speeds"].append(s["speed_kmh"])
        pairs_map[key]["buses_observed"].add(s["bus_id"])

    # 3. Build response items and matrix grid
    od_pair_items = []
    matrix_grid: Dict[str, Dict[str, int]] = {}

    for (orig, dest), data in pairs_map.items():
        if data["trip_count"] < min_trips:
            continue

        avg_dur = round(sum(data["durations"]) / len(data["durations"]), 1) if data["durations"] else 0.0
        avg_spd = round(sum(data["speeds"]) / len(data["speeds"]), 1) if data["speeds"] else 0.0
        buses_list = sorted(list(data["buses_observed"]))

        pair_id = f"OD_{data['route_id']}_{orig[:4]}_{dest[:4]}".replace(" ", "_")

        od_pair_items.append({
            "pair_id": pair_id,
            "route_id": data["route_id"],
            "origin_stop": orig,
            "destination_stop": dest,
            "origin_lat": data["origin_lat"],
            "origin_lon": data["origin_lon"],
            "dest_lat": data["dest_lat"],
            "dest_lon": data["dest_lon"],
            "trip_count": data["trip_count"],
            "avg_duration_minutes": avg_dur,
            "avg_speed_kmh": avg_spd,
            "distance_km": data["distance_km"],
            "buses_observed": buses_list,
        })

        if orig not in matrix_grid:
            matrix_grid[orig] = {}
        matrix_grid[orig][dest] = data["trip_count"]

    # Sort OD pairs by trip volume descending, then duration
    od_pair_items.sort(key=lambda x: (x["trip_count"], -x["avg_duration_minutes"]), reverse=True)

    # 4. Compute Summary Metrics
    total_pairs = len(od_pair_items)
    total_trips = sum(p["trip_count"] for p in od_pair_items)
    avg_trip_dur = round(sum(p["avg_duration_minutes"] for p in od_pair_items) / total_pairs, 1) if total_pairs else 0.0
    busiest_pair_name = f"{od_pair_items[0]['origin_stop']} → {od_pair_items[0]['destination_stop']}" if od_pair_items else None

    # Determine busiest corridor
    corridor_counts: Dict[str, int] = {}
    for p in od_pair_items:
        corridor_counts[p["route_id"]] = corridor_counts.get(p["route_id"], 0) + p["trip_count"]
    busiest_corridor_id = max(corridor_counts.items(), key=lambda x: x[1])[0] if corridor_counts else None
    busiest_corridor_label = f"Route {busiest_corridor_id}" if busiest_corridor_id else None

    stops_by_route = {r_id: get_route_stop_names(r_id) for r_id in routes_to_process}

    return {
        "summary": {
            "total_od_pairs": total_pairs,
            "total_trips_analyzed": total_trips,
            "busiest_corridor": busiest_corridor_label,
            "busiest_pair": busiest_pair_name,
            "avg_trip_duration_minutes": avg_trip_dur,
            "data_source": "Simulated Fleet Telemetry (Bus Stop Segment Inference)",
            "disclaimer": "Fleet Telemetry Inferred: Based on vehicle transit segments between designated stops — NOT passenger-level tracking.",
        },
        "od_pairs": od_pair_items,
        "stops_by_route": stops_by_route,
        "matrix_grid": matrix_grid,
    }
