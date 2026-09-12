"""REST endpoints for the Urban Analytics module."""

from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_

from backend.database import get_db
from backend.models import (
    Event,
    Bus,
    Route,
    RouteTrip,
    TrafficMeasurement,
    VehicleDetection,
    lat_lon_from_point,
)
from backend.schemas.analytics import (
    AnalyticsMeta,
    AnalyticsSummaryResponse,
    VehicleCountsResponse,
    VehicleTypeCount,
    VehicleCountTimelineItem,
    TrafficDensityResponse,
    DensityDistributionItem,
    CongestionHotspotsResponse,
    HotspotItem,
    EventsByTypeResponse,
    EventTypeItem,
    EventsByLocationResponse,
    EventLocationItem,
    EventsByTimeResponse,
    EventTimelineItem,
    RouteDelaysResponse,
    RouteDelayItem,
    BusActivityResponse,
    BusActivityItem,
    RoadDefectsFrequencyResponse,
    DefectSubtypeFrequencyItem,
    ODMatrixResponse,
    ODMatrixSummary,
    ODPairItem,
)
from backend.services.od_analysis import compute_od_matrix, ROUTE_STOPS

router = APIRouter(prefix="/analytics", tags=["Urban Analytics"])


def _parse_time_filters(
    time_range: Optional[str] = "all",
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> Tuple[Optional[datetime], Optional[datetime], str]:
    """Resolves date/time range query filters into start and end UTC timestamps."""
    now = datetime.now(timezone.utc)
    tr = (time_range or "all").lower()

    if start_time or end_time:
        st = start_time if start_time else (now - timedelta(days=365))
        et = end_time if end_time else now
        return st, et, "custom"

    if tr == "1h":
        return now - timedelta(hours=1), now, "1h"
    elif tr == "6h":
        return now - timedelta(hours=6), now, "6h"
    elif tr == "24h":
        return now - timedelta(hours=24), now, "24h"
    elif tr == "today":
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return today_start, now, "today"
    elif tr == "7d":
        return now - timedelta(days=7), now, "7d"
    elif tr == "30d":
        return now - timedelta(days=30), now, "30d"
    
    return None, None, "all"


# ==============================================================================
# 1. SUMMARY METRIC CARDS
# ==============================================================================
@router.get("/summary", response_model=AnalyticsSummaryResponse, summary="Get high-level urban analytics KPI summary")
def get_analytics_summary(
    time_range: Optional[str] = Query("all", description="Time range: 1h, 6h, 24h, today, 7d, 30d, all"),
    start_time: Optional[datetime] = Query(None, description="Custom start UTC ISO timestamp"),
    end_time: Optional[datetime] = Query(None, description="Custom end UTC ISO timestamp"),
    route_id: Optional[str] = Query(None, description="Filter by transit route ID"),
    bus_id: Optional[str] = Query(None, description="Filter by bus fleet ID"),
    db: Session = Depends(get_db),
):
    """Computes real-time top-level metrics across vehicles, defects, incidents, and transit delays."""
    st, et, resolved_range = _parse_time_filters(time_range, start_time, end_time)

    meta = AnalyticsMeta(
        time_range=resolved_range,
        start_time=st,
        end_time=et,
        route_id=route_id,
        bus_id=bus_id,
        has_data=False,
    )

    if db is None:
        meta.message = "Database offline - simulation fallback mode"
        return AnalyticsSummaryResponse(meta=meta)

    try:
        # 1. Traffic Measurements
        t_query = db.query(TrafficMeasurement)
        if st:
            t_query = t_query.filter(TrafficMeasurement.timestamp >= st)
        if et:
            t_query = t_query.filter(TrafficMeasurement.timestamp <= et)
        if bus_id:
            t_query = t_query.filter(TrafficMeasurement.bus_id == bus_id)

        traffic_records = t_query.all()

        total_vehicles = sum(t.total_vehicle_count for t in traffic_records)
        density_weights = {"low": 0.25, "medium": 0.5, "moderate": 0.5, "high": 0.75, "severe": 1.0}
        avg_density = 0.0
        if traffic_records:
            avg_density = sum(density_weights.get(t.traffic_density.lower(), 0.25) for t in traffic_records) / len(traffic_records)

        # 2. Events Query
        e_query = db.query(Event)
        if st:
            e_query = e_query.filter(Event.timestamp >= st)
        if et:
            e_query = e_query.filter(Event.timestamp <= et)
        if bus_id:
            e_query = e_query.filter(Event.bus_id == bus_id)

        events = e_query.all()
        total_events = len(events)
        defects_count = sum(1 for e in events if not ("incident" in (e.event_type or "").lower() or "rash" in (e.event_type or "").lower() or "hit" in (e.event_type or "").lower() or "congestion" in (e.event_type or "").lower()))
        incidents_count = sum(1 for e in events if "incident" in (e.event_type or "").lower() or "rash" in (e.event_type or "").lower() or "hit" in (e.event_type or "").lower())
        hotspots_count = sum(1 for t in traffic_records if t.traffic_density.lower() in ("high", "severe"))

        # 3. Route Delays: delay = actual_duration - expected_duration
        trip_query = db.query(RouteTrip)
        if st:
            trip_query = trip_query.filter(RouteTrip.start_time >= st)
        if et:
            trip_query = trip_query.filter(RouteTrip.start_time <= et)
        if route_id:
            trip_query = trip_query.filter(RouteTrip.route_id == route_id)
        if bus_id:
            trip_query = trip_query.filter(RouteTrip.bus_id == bus_id)

        trips = trip_query.all()
        delays = []
        on_time_count = 0
        for trip in trips:
            if trip.actual_duration is not None and trip.expected_duration is not None:
                delay = trip.actual_duration - trip.expected_duration
                delays.append(delay)
                if delay <= 0:
                    on_time_count += 1

        avg_delay = round(sum(delays) / len(delays), 1) if delays else 0.0
        on_time_rate = round((on_time_count / len(delays)) * 100, 1) if delays else 0.0

        # 4. Active Fleet Buses
        b_query = db.query(Bus)
        if route_id:
            b_query = b_query.filter(Bus.route_id == route_id)
        active_buses = b_query.filter(Bus.status == "active").count()

        has_data = bool(traffic_records or events or trips or active_buses > 0)
        meta.has_data = has_data
        if not has_data:
            meta.message = "Insufficient data in the selected time window."

        return AnalyticsSummaryResponse(
            meta=meta,
            total_vehicles_counted=total_vehicles,
            avg_traffic_density_index=round(avg_density, 2),
            active_congestion_hotspots=hotspots_count,
            total_events_detected=total_events,
            road_defects_count=defects_count,
            safety_incidents_count=incidents_count,
            avg_route_delay_minutes=avg_delay,
            active_fleet_buses=active_buses,
            on_time_trip_rate_pct=on_time_rate,
        )
    except Exception as err:
        meta.message = f"Error querying analytics summary: {str(err)}"
        return AnalyticsSummaryResponse(meta=meta)


# ==============================================================================
# 2. VEHICLE COUNTS
# ==============================================================================
@router.get("/vehicle-counts", response_model=VehicleCountsResponse, summary="Get vehicle count breakdown & timeline")
def get_vehicle_counts(
    time_range: Optional[str] = Query("all"),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    bus_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Returns aggregated vehicle counts by classification and chronological timeline."""
    st, et, resolved_range = _parse_time_filters(time_range, start_time, end_time)
    meta = AnalyticsMeta(time_range=resolved_range, start_time=st, end_time=et, bus_id=bus_id, has_data=False)

    if db is None:
        meta.message = "Database not connected."
        return VehicleCountsResponse(meta=meta)

    try:
        q = db.query(TrafficMeasurement)
        if st:
            q = q.filter(TrafficMeasurement.timestamp >= st)
        if et:
            q = q.filter(TrafficMeasurement.timestamp <= et)
        if bus_id:
            q = q.filter(TrafficMeasurement.bus_id == bus_id)

        records = q.order_by(TrafficMeasurement.timestamp.asc()).all()
        if not records:
            meta.message = "Insufficient data"
            return VehicleCountsResponse(meta=meta)

        cars = sum(r.car_count for r in records)
        buses = sum(r.bus_count for r in records)
        trucks = sum(r.truck_count for r in records)
        motorcycles = sum(r.motorcycle_count for r in records)
        total = cars + buses + trucks + motorcycles

        by_cat = [
            VehicleTypeCount(category="Cars", count=cars, percentage=round((cars / total * 100), 1) if total else 0.0),
            VehicleTypeCount(category="Buses", count=buses, percentage=round((buses / total * 100), 1) if total else 0.0),
            VehicleTypeCount(category="Trucks", count=trucks, percentage=round((trucks / total * 100), 1) if total else 0.0),
            VehicleTypeCount(category="Motorcycles", count=motorcycles, percentage=round((motorcycles / total * 100), 1) if total else 0.0),
        ]

        # Build timeline buckets
        timeline = []
        for r in records:
            label = r.timestamp.strftime("%H:%M" if resolved_range in ("1h", "6h", "24h", "today") else "%b %d %H:%M")
            timeline.append(
                VehicleCountTimelineItem(
                    timestamp=r.timestamp,
                    label=label,
                    car_count=r.car_count,
                    bus_count=r.bus_count,
                    truck_count=r.truck_count,
                    motorcycle_count=r.motorcycle_count,
                    total_count=r.total_vehicle_count,
                )
            )

        meta.has_data = total > 0
        return VehicleCountsResponse(meta=meta, total_count=total, by_category=by_cat, timeline=timeline)
    except Exception as e:
        meta.message = f"Error: {str(e)}"
        return VehicleCountsResponse(meta=meta)


# ==============================================================================
# 3. TRAFFIC DENSITY
# ==============================================================================
@router.get("/traffic-density", response_model=TrafficDensityResponse, summary="Get traffic density distribution")
def get_traffic_density(
    time_range: Optional[str] = Query("all"),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    bus_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Calculates distribution of traffic density classifications (LOW, MEDIUM, HIGH, SEVERE)."""
    st, et, resolved_range = _parse_time_filters(time_range, start_time, end_time)
    meta = AnalyticsMeta(time_range=resolved_range, start_time=st, end_time=et, bus_id=bus_id, has_data=False)

    if db is None:
        meta.message = "Database not connected."
        return TrafficDensityResponse(meta=meta)

    try:
        q = db.query(TrafficMeasurement)
        if st:
            q = q.filter(TrafficMeasurement.timestamp >= st)
        if et:
            q = q.filter(TrafficMeasurement.timestamp <= et)
        if bus_id:
            q = q.filter(TrafficMeasurement.bus_id == bus_id)

        records = q.all()
        if not records:
            meta.message = "Insufficient data"
            return TrafficDensityResponse(meta=meta)

        counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "SEVERE": 0}
        for r in records:
            den = (r.traffic_density or "LOW").upper()
            if den in counts:
                counts[den] += 1
            elif den in ("MODERATE", "NORMAL"):
                counts["MEDIUM"] += 1
            else:
                counts["LOW"] += 1

        total = len(records)
        dist = [
            DensityDistributionItem(density_level=lvl, sample_count=cnt, percentage=round(cnt / total * 100, 1))
            for lvl, cnt in counts.items()
        ]

        most_common = max(counts.items(), key=lambda x: x[1])[0] if total else "LOW"
        meta.has_data = total > 0

        return TrafficDensityResponse(
            meta=meta,
            distribution=dist,
            average_density_label=most_common,
            total_measurements=total,
        )
    except Exception as e:
        meta.message = f"Error: {str(e)}"
        return TrafficDensityResponse(meta=meta)


# ==============================================================================
# 4. CONGESTION HOTSPOTS
# ==============================================================================
@router.get("/congestion-hotspots", response_model=CongestionHotspotsResponse, summary="Get top urban congestion hotspots")
def get_congestion_hotspots(
    time_range: Optional[str] = Query("all"),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Retrieves ranked congestion bottlenecks based on high traffic density measurements."""
    st, et, resolved_range = _parse_time_filters(time_range, start_time, end_time)
    meta = AnalyticsMeta(time_range=resolved_range, start_time=st, end_time=et, has_data=False)

    if db is None:
        meta.message = "Database not connected."
        return CongestionHotspotsResponse(meta=meta)

    try:
        q = db.query(TrafficMeasurement).filter(
            func.lower(TrafficMeasurement.traffic_density).in_(["high", "severe", "moderate"])
        )
        if st:
            q = q.filter(TrafficMeasurement.timestamp >= st)
        if et:
            q = q.filter(TrafficMeasurement.timestamp <= et)

        records = q.order_by(TrafficMeasurement.total_vehicle_count.desc(), TrafficMeasurement.timestamp.desc()).limit(limit).all()
        if not records:
            meta.message = "Insufficient data"
            return CongestionHotspotsResponse(meta=meta)

        hotspots = []
        for i, r in enumerate(records):
            lat = getattr(r, "latitude", None)
            lon = getattr(r, "longitude", None)
            if lat is None or lon is None:
                lat, lon = lat_lon_from_point(getattr(r, "location", None))
            if lat is None or lon is None:
                continue
            hotspots.append(
                HotspotItem(
                    hotspot_id=f"HOT_{r.measurement_id[:8]}",
                    location_name=f"Corridor Sector near ({round(lat, 4)}, {round(lon, 4)})",
                    route_id=getattr(r.bus, "route_id", "216") if r.bus else "216",
                    latitude=lat,
                    longitude=lon,
                    density_level=r.traffic_density.upper(),
                    observed_vehicles=r.total_vehicle_count,
                    measurement_count=1,
                    last_detected=r.timestamp,
                )
            )

        meta.has_data = len(hotspots) > 0
        return CongestionHotspotsResponse(meta=meta, hotspots=hotspots, total_hotspots=len(hotspots))
    except Exception as e:
        meta.message = f"Error: {str(e)}"
        return CongestionHotspotsResponse(meta=meta)


# ==============================================================================
# 5. EVENTS BY TYPE
# ==============================================================================
@router.get("/events-by-type", response_model=EventsByTypeResponse, summary="Get event distribution by event type")
def get_events_by_type(
    time_range: Optional[str] = Query("all"),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    bus_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Categorizes all urban events by their specific event_type."""
    st, et, resolved_range = _parse_time_filters(time_range, start_time, end_time)
    meta = AnalyticsMeta(time_range=resolved_range, start_time=st, end_time=et, bus_id=bus_id, has_data=False)

    if db is None:
        meta.message = "Database not connected."
        return EventsByTypeResponse(meta=meta)

    try:
        q = db.query(Event)
        if st:
            q = q.filter(Event.timestamp >= st)
        if et:
            q = q.filter(Event.timestamp <= et)
        if bus_id:
            q = q.filter(Event.bus_id == bus_id)

        events = q.all()
        if not events:
            meta.message = "Insufficient data"
            return EventsByTypeResponse(meta=meta)

        counts: Dict[str, Tuple[str, int]] = {}
        for e in events:
            raw_type = (e.event_type or "OTHER").upper()
            cat = (getattr(e, "event_category", None) or "ROAD_DEFECT").upper()
            if raw_type not in counts:
                counts[raw_type] = (cat, 0)
            cat_name, cur_cnt = counts[raw_type]
            counts[raw_type] = (cat_name, cur_cnt + 1)

        total = len(events)
        items = [
            EventTypeItem(
                event_type=t,
                category=cat,
                count=cnt,
                percentage=round(cnt / total * 100, 1),
            )
            for t, (cat, cnt) in counts.items()
        ]
        items.sort(key=lambda x: x.count, reverse=True)

        meta.has_data = total > 0
        return EventsByTypeResponse(meta=meta, total_events=total, types=items)
    except Exception as e:
        meta.message = f"Error: {str(e)}"
        return EventsByTypeResponse(meta=meta)


# ==============================================================================
# 6. EVENTS BY LOCATION
# ==============================================================================
@router.get("/events-by-location", response_model=EventsByLocationResponse, summary="Get event breakdown by route / location")
def get_events_by_location(
    time_range: Optional[str] = Query("all"),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
):
    """Groups detected events across transit routes and geographic corridors."""
    st, et, resolved_range = _parse_time_filters(time_range, start_time, end_time)
    meta = AnalyticsMeta(time_range=resolved_range, start_time=st, end_time=et, has_data=False)

    if db is None:
        meta.message = "Database not connected."
        return EventsByLocationResponse(meta=meta)

    try:
        q = db.query(Event)
        if st:
            q = q.filter(Event.timestamp >= st)
        if et:
            q = q.filter(Event.timestamp <= et)

        events = q.all()
        if not events:
            meta.message = "Insufficient data"
            return EventsByLocationResponse(meta=meta)

        locations: Dict[str, Dict[str, int]] = {}
        for e in events:
            rid = getattr(e.bus, "route_id", "Route 216") if e.bus and e.bus.route_id else "Route 216"
            if rid not in locations:
                locations[rid] = {"defects": 0, "incidents": 0, "congestion": 0, "total": 0}

            t = (e.event_type or "").upper()
            cat = (getattr(e, "event_category", None) or "").upper()
            if "INCIDENT" in cat or "RASH" in t or "HIT" in t:
                locations[rid]["incidents"] += 1
            elif "CONGESTION" in t or "TRAFFIC" in cat:
                locations[rid]["congestion"] += 1
            else:
                locations[rid]["defects"] += 1
            locations[rid]["total"] += 1

        items = [
            EventLocationItem(
                location_identifier=rid,
                route_name=f"Corridor {rid}",
                defect_count=data["defects"],
                incident_count=data["incidents"],
                congestion_count=data["congestion"],
                total_count=data["total"],
            )
            for rid, data in locations.items()
        ]
        items.sort(key=lambda x: x.total_count, reverse=True)

        meta.has_data = len(events) > 0
        return EventsByLocationResponse(meta=meta, locations=items, total_events=len(events))
    except Exception as e:
        meta.message = f"Error: {str(e)}"
        return EventsByLocationResponse(meta=meta)


# ==============================================================================
# 7. EVENTS BY TIME
# ==============================================================================
@router.get("/events-by-time", response_model=EventsByTimeResponse, summary="Get chronological time series of events")
def get_events_by_time(
    time_range: Optional[str] = Query("all"),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    bus_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Aggregates event timelines into hourly / daily buckets."""
    st, et, resolved_range = _parse_time_filters(time_range, start_time, end_time)
    meta = AnalyticsMeta(time_range=resolved_range, start_time=st, end_time=et, bus_id=bus_id, has_data=False)

    if db is None:
        meta.message = "Database not connected."
        return EventsByTimeResponse(meta=meta)

    try:
        q = db.query(Event)
        if st:
            q = q.filter(Event.timestamp >= st)
        if et:
            q = q.filter(Event.timestamp <= et)
        if bus_id:
            q = q.filter(Event.bus_id == bus_id)

        events = q.order_by(Event.timestamp.asc()).all()
        if not events:
            meta.message = "Insufficient data"
            return EventsByTimeResponse(meta=meta)

        # Bucket by interval
        buckets: Dict[str, Dict[str, Any]] = {}
        for e in events:
            fmt = "%Y-%m-%d %H:00" if resolved_range in ("1h", "6h", "24h", "today") else "%Y-%m-%d"
            key = e.timestamp.strftime(fmt)
            if key not in buckets:
                label = e.timestamp.strftime("%H:00" if resolved_range in ("1h", "6h", "24h", "today") else "%b %d")
                buckets[key] = {"timestamp": e.timestamp, "label": label, "defects": 0, "incidents": 0, "congestion": 0, "total": 0}

            t = (e.event_type or "").upper()
            cat = (getattr(e, "event_category", None) or "").upper()
            if "INCIDENT" in cat or "RASH" in t or "HIT" in t:
                buckets[key]["incidents"] += 1
            elif "CONGESTION" in t or "TRAFFIC" in cat:
                buckets[key]["congestion"] += 1
            else:
                buckets[key]["defects"] += 1
            buckets[key]["total"] += 1

        timeline = [
            EventTimelineItem(
                timestamp=b["timestamp"],
                label=b["label"],
                defects=b["defects"],
                incidents=b["incidents"],
                congestion=b["congestion"],
                total=b["total"],
            )
            for b in buckets.values()
        ]

        meta.has_data = len(events) > 0
        return EventsByTimeResponse(meta=meta, timeline=timeline, total_events=len(events))
    except Exception as e:
        meta.message = f"Error: {str(e)}"
        return EventsByTimeResponse(meta=meta)


# ==============================================================================
# 8. ROUTE DELAYS
# ==============================================================================
@router.get("/route-delays", response_model=RouteDelaysResponse, summary="Get transit schedule delay analytics")
def get_route_delays(
    time_range: Optional[str] = Query("all"),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    route_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Calculates route delays using formula: delay = actual_duration - expected_duration."""
    st, et, resolved_range = _parse_time_filters(time_range, start_time, end_time)
    meta = AnalyticsMeta(time_range=resolved_range, start_time=st, end_time=et, route_id=route_id, has_data=False)

    if db is None:
        meta.message = "Database not connected."
        return RouteDelaysResponse(meta=meta)

    try:
        q = db.query(RouteTrip)
        if st:
            q = q.filter(RouteTrip.start_time >= st)
        if et:
            q = q.filter(RouteTrip.start_time <= et)
        if route_id:
            q = q.filter(RouteTrip.route_id == route_id)

        trips = q.all()
        if not trips:
            meta.message = "Insufficient data"
            return RouteDelaysResponse(meta=meta)

        routes_map: Dict[str, Dict[str, Any]] = {}
        all_delays = []
        overall_on_time = 0

        for trip in trips:
            rid = trip.route_id or "UNKNOWN"
            if rid not in routes_map:
                r_name = getattr(trip.route, "route_name", f"Route {rid}") if trip.route else f"Route {rid}"
                routes_map[rid] = {
                    "route_name": r_name,
                    "trips": [],
                    "expected_durations": [],
                    "actual_durations": [],
                    "delays": [],
                    "on_time": 0,
                }

            exp = trip.expected_duration or 30.0
            act = trip.actual_duration if trip.actual_duration is not None else exp
            # Calculate route delay: delay = actual_duration - expected_duration
            delay = act - exp
            routes_map[rid]["trips"].append(trip)
            routes_map[rid]["expected_durations"].append(exp)
            routes_map[rid]["actual_durations"].append(act)
            routes_map[rid]["delays"].append(delay)
            all_delays.append(delay)

            if delay <= 0:
                routes_map[rid]["on_time"] += 1
                overall_on_time += 1

        route_items = []
        for rid, data in routes_map.items():
            cnt = len(data["trips"])
            avg_exp = sum(data["expected_durations"]) / cnt if cnt else 0.0
            avg_act = sum(data["actual_durations"]) / cnt if cnt else 0.0
            avg_del = sum(data["delays"]) / cnt if cnt else 0.0
            max_del = max(data["delays"]) if data["delays"] else 0.0
            on_time_pct = (data["on_time"] / cnt * 100) if cnt else 0.0

            route_items.append(
                RouteDelayItem(
                    route_id=rid,
                    route_name=data["route_name"],
                    total_trips=cnt,
                    avg_expected_duration_min=round(avg_exp, 1),
                    avg_actual_duration_min=round(avg_act, 1),
                    avg_delay_minutes=round(avg_del, 1),
                    max_delay_minutes=round(max_del, 1),
                    on_time_trips=data["on_time"],
                    on_time_rate_pct=round(on_time_pct, 1),
                )
            )

        overall_avg_delay = round(sum(all_delays) / len(all_delays), 1) if all_delays else 0.0
        overall_on_time_pct = round(overall_on_time / len(all_delays) * 100, 1) if all_delays else 0.0
        meta.has_data = len(trips) > 0

        return RouteDelaysResponse(
            meta=meta,
            routes=route_items,
            overall_avg_delay_minutes=overall_avg_delay,
            overall_on_time_pct=overall_on_time_pct,
        )
    except Exception as e:
        meta.message = f"Error: {str(e)}"
        return RouteDelaysResponse(meta=meta)


# ==============================================================================
# 9. BUS ACTIVITY
# ==============================================================================
@router.get("/bus-activity", response_model=BusActivityResponse, summary="Get fleet sensing activity metrics")
def get_bus_activity(
    route_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Measures bus productivity: trips executed, events detected, measurements taken."""
    meta = AnalyticsMeta(route_id=route_id, has_data=False)

    if db is None:
        meta.message = "Database not connected."
        return BusActivityResponse(meta=meta)

    try:
        q = db.query(Bus)
        if route_id:
            q = q.filter(Bus.route_id == route_id)

        buses = q.all()
        if not buses:
            meta.message = "Insufficient data"
            return BusActivityResponse(meta=meta)

        items = []
        active_count = 0
        for b in buses:
            if b.status == "active":
                active_count += 1

            trip_count = len(b.trips) if b.trips else 0
            event_count = len(b.events) if b.events else 0
            traffic_count = len(b.traffic_measurements) if b.traffic_measurements else 0

            items.append(
                BusActivityItem(
                    bus_id=b.bus_id,
                    route_id=b.route_id,
                    status=b.status,
                    speed_kmh=b.speed or 0.0,
                    last_seen=b.last_seen or datetime.now(timezone.utc),
                    trips_completed=trip_count,
                    total_events_logged=event_count,
                    traffic_measurements_taken=traffic_count,
                )
            )

        meta.has_data = len(buses) > 0
        return BusActivityResponse(
            meta=meta,
            fleet=items,
            total_buses=len(buses),
            active_buses=active_count,
        )
    except Exception as e:
        meta.message = f"Error: {str(e)}"
        return BusActivityResponse(meta=meta)


# ==============================================================================
# 10. ROAD-DEFECT FREQUENCY BY SUBTYPE
# ==============================================================================
@router.get("/road-defects-frequency", response_model=RoadDefectsFrequencyResponse, summary="Get road-defect frequency by BEL subtype")
def get_road_defects_frequency(
    time_range: Optional[str] = Query("all"),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    bus_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Analyzes road defect occurrences by official BEL subtypes (POTHOLE, DAMAGED_ROAD, WATERLOGGING, MISSING_DIVIDER, DAMAGED_SIGNBOARD)."""
    st, et, resolved_range = _parse_time_filters(time_range, start_time, end_time)
    meta = AnalyticsMeta(time_range=resolved_range, start_time=st, end_time=et, bus_id=bus_id, has_data=False)

    if db is None:
        meta.message = "Database not connected."
        return RoadDefectsFrequencyResponse(meta=meta)

    try:
        q = db.query(Event)
        if st:
            q = q.filter(Event.timestamp >= st)
        if et:
            q = q.filter(Event.timestamp <= et)
        if bus_id:
            q = q.filter(Event.bus_id == bus_id)

        all_events = q.all()
        # Filter strictly for road defects
        defect_events = [
            e for e in all_events
            if not ("incident" in (e.event_type or "").lower() or "rash" in (e.event_type or "").lower() or "hit" in (e.event_type or "").lower() or "congestion" in (e.event_type or "").lower())
        ]

        if not defect_events:
            meta.message = "Insufficient data"
            return RoadDefectsFrequencyResponse(meta=meta)

        subtype_names = {
            "POTHOLE": "Potholes",
            "DAMAGED_ROAD": "Damaged Road / Fractures",
            "WATERLOGGING": "Waterlogging",
            "MISSING_DIVIDER": "Missing Divider / Barrier",
            "DAMAGED_SIGNBOARD": "Damaged / Obscured Sign",
        }

        counts: Dict[str, Dict[str, int]] = {
            k: {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0} for k in subtype_names
        }

        for d in defect_events:
            t = (d.event_type or "POTHOLE").upper()
            # Normalize to one of the 5 BEL subtypes
            matched_subtype = "POTHOLE"
            if "DAMAGED_ROAD" in t or "CRACK" in t:
                matched_subtype = "DAMAGED_ROAD"
            elif "WATERLOG" in t or "FLOOD" in t:
                matched_subtype = "WATERLOGGING"
            elif "DIVIDER" in t or "BARRIER" in t:
                matched_subtype = "MISSING_DIVIDER"
            elif "SIGN" in t or "BOARD" in t:
                matched_subtype = "DAMAGED_SIGNBOARD"
            elif "POTHOLE" in t:
                matched_subtype = "POTHOLE"

            sev = (d.severity or "HIGH").lower()
            counts[matched_subtype]["total"] += 1
            if sev in counts[matched_subtype]:
                counts[matched_subtype][sev] += 1
            else:
                counts[matched_subtype]["medium"] += 1

        total_defects = len(defect_events)
        items = []
        for st_key, d_data in counts.items():
            cnt = d_data["total"]
            pct = round(cnt / total_defects * 100, 1) if total_defects else 0.0
            items.append(
                DefectSubtypeFrequencyItem(
                    subtype=st_key,
                    display_name=subtype_names[st_key],
                    count=cnt,
                    percentage=pct,
                    critical_count=d_data["critical"],
                    high_count=d_data["high"],
                    medium_count=d_data["medium"],
                    low_count=d_data["low"],
                )
            )

        items.sort(key=lambda x: x.count, reverse=True)
        meta.has_data = total_defects > 0

        return RoadDefectsFrequencyResponse(meta=meta, subtypes=items, total_defects=total_defects)
    except Exception as e:
        meta.message = f"Error: {str(e)}"
        return RoadDefectsFrequencyResponse(meta=meta)


# ==============================================================================
# 11. ORIGIN-DESTINATION (OD) TRAFFIC MATRIX
# ==============================================================================
@router.get("/od-matrix", response_model=ODMatrixResponse, summary="Get fleet origin-destination (OD) traffic matrix")
def get_od_traffic_matrix(
    time_range: Optional[str] = Query("all", description="Time filter: 1h, 6h, 24h, today, 7d, 30d, all"),
    start_time: Optional[datetime] = Query(None, description="Custom start UTC ISO timestamp"),
    end_time: Optional[datetime] = Query(None, description="Custom end UTC ISO timestamp"),
    route_id: Optional[str] = Query(None, description="Filter OD pairs by specific transit route ID (e.g. 216, 10, 49M)"),
    min_trips: int = Query(1, ge=1, description="Minimum trip count threshold"),
    db: Session = Depends(get_db),
):
    """Computes Origin-Destination (OD) traffic matrix inferred from bus transit stop passages.
    
    DISCLAIMER: This analysis reflects fleet vehicle movements and stop-to-stop capacity supply.
    It does NOT track individual passengers.
    """
    st, et, resolved_range = _parse_time_filters(time_range, start_time, end_time)
    meta = AnalyticsMeta(
        time_range=resolved_range,
        start_time=st,
        end_time=et,
        route_id=route_id,
        has_data=False,
    )

    try:
        # Compute OD matrix using the OD analysis service
        od_results = compute_od_matrix(
            data_dir="data/gps",
            target_route_id=route_id,
            min_trips=min_trips,
        )

        meta.has_data = bool(od_results["od_pairs"])
        if not meta.has_data:
            meta.message = "Insufficient OD trip segment data for the selected filters."

        summary_data = od_results["summary"]
        od_summary = ODMatrixSummary(
            total_od_pairs=summary_data["total_od_pairs"],
            total_trips_analyzed=summary_data["total_trips_analyzed"],
            busiest_corridor=summary_data["busiest_corridor"],
            busiest_pair=summary_data["busiest_pair"],
            avg_trip_duration_minutes=summary_data["avg_trip_duration_minutes"],
            data_source=summary_data["data_source"],
            disclaimer=summary_data["disclaimer"],
        )

        pair_items = [ODPairItem(**p) for p in od_results["od_pairs"]]

        return ODMatrixResponse(
            meta=meta,
            summary=od_summary,
            od_pairs=pair_items,
            stops_by_route=od_results["stops_by_route"],
            matrix_grid=od_results["matrix_grid"],
        )
    except Exception as e:
        meta.message = f"Error computing OD traffic matrix: {str(e)}"
        return ODMatrixResponse(
            meta=meta,
            summary=ODMatrixSummary(),
            od_pairs=[],
            stops_by_route={},
            matrix_grid={},
        )

