# BusSense-AI API Reference & Curl Examples

This document provides complete `curl` and WebSocket examples for all endpoints exposed by the BusSense-AI FastAPI backend.

Base URL: `http://127.0.0.1:8000`

---

## 1. Urban Sensing Events

### `POST /api/events`
Ingest or record a new urban sensing event (road defect, incident, congestion).

**Request:**
```bash
curl -X POST "http://127.0.0.1:8000/api/events" \
  -H "Content-Type: application/json" \
  -d '{
    "bus_id": "BUS_101",
    "route_id": "216",
    "event_type": "POTHOLE",
    "event_category": "ROAD_DEFECT",
    "confidence": 0.91,
    "latitude": 17.385044,
    "longitude": 78.486671,
    "severity": "HIGH",
    "status": "detected",
    "image_path": "/evidence/road_defects/defect_BUS_101_POTHOLE_000045.jpg",
    "video_timestamp": 1.5,
    "details": {
      "bounding_box": [500, 600, 750, 800],
      "area": 50000
    }
  }'
```

**Response (201 Created):**
```json
{
  "bus_id": "BUS_101",
  "event_type": "POTHOLE",
  "event_category": "ROAD_DEFECT",
  "confidence": 0.91,
  "latitude": 17.385044,
  "longitude": 78.486671,
  "severity": "HIGH",
  "status": "detected",
  "image_path": "/evidence/road_defects/defect_BUS_101_POTHOLE_000045.jpg",
  "video_timestamp": 1.5,
  "details": {
    "bounding_box": [500, 600, 750, 800],
    "area": 50000
  },
  "timestamp": "2026-09-09T14:30:20.630412Z",
  "event_id": "evt_7f8a19bc34e1",
  "route_id": "216",
  "is_simulated": true,
  "disclaimer": "prototype heuristic estimation — rule-based detection, not forensic determination"
}
```

---

### `GET /api/events`
Query all events with optional filters (`event_type`, `severity`, `bus_id`, `status`, `limit`, `offset`).

**Request:**
```bash
curl -X GET "http://127.0.0.1:8000/api/events?event_type=POTHOLE&severity=HIGH&limit=10"
```

**Response (200 OK):**
```json
{
  "total": 42,
  "count": 10,
  "limit": 10,
  "offset": 0,
  "events": [
    {
      "event_id": "evt_7f8a19bc34e1",
      "bus_id": "BUS_101",
      "route_id": "216",
      "event_type": "POTHOLE",
      "event_category": "ROAD_DEFECT",
      "confidence": 0.91,
      "latitude": 17.385044,
      "longitude": 78.486671,
      "severity": "HIGH",
      "status": "detected",
      "image_path": "/evidence/road_defects/defect_BUS_101_POTHOLE_000045.jpg",
      "video_timestamp": 1.5,
      "details": {
        "bounding_box": [500, 600, 750, 800],
        "area": 50000
      },
      "timestamp": "2026-09-09T14:30:20.630412Z",
      "is_simulated": true,
      "disclaimer": "prototype heuristic estimation — rule-based detection, not forensic determination"
    }
  ],
  "is_simulated": true
}
```

---

### `GET /api/events/{event_id}`
Retrieve full details of a specific event.

**Request:**
```bash
curl -X GET "http://127.0.0.1:8000/api/events/evt_7f8a19bc34e1"
```

**Response (200 OK):**
```json
{
  "event_id": "evt_7f8a19bc34e1",
  "bus_id": "BUS_101",
  "route_id": "216",
  "event_type": "POTHOLE",
  "event_category": "ROAD_DEFECT",
  "confidence": 0.91,
  "latitude": 17.385044,
  "longitude": 78.486671,
  "severity": "HIGH",
  "status": "detected",
  "image_path": "/evidence/road_defects/defect_BUS_101_POTHOLE_000045.jpg",
  "video_timestamp": 1.5,
  "details": {
    "bounding_box": [500, 600, 750, 800],
    "area": 50000
  },
  "timestamp": "2026-09-09T14:30:20.630412Z",
  "is_simulated": true,
  "disclaimer": "prototype heuristic estimation — rule-based detection, not forensic determination"
}
```

---

## 2. Bus Fleet Telemetry & Locations

### `POST /api/telemetry`
Ingest real-time bus telemetry and broadcast to `/ws/buses`.

**Request:**
```bash
curl -X POST "http://127.0.0.1:8000/api/telemetry" \
  -H "Content-Type: application/json" \
  -d '{
    "bus_id": "BUS_101",
    "route_id": "216",
    "latitude": 17.385044,
    "longitude": 78.486671,
    "speed": 34.5,
    "heading": 180.0,
    "status": "active"
  }'
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Simulated telemetry processed and broadcasted",
  "bus_id": "BUS_101",
  "is_simulated": true,
  "simulation_notice": "SIMULATED TELEMETRY FOR HACKATHON PROTOTYPE DEMONSTRATION",
  "data": {
    "bus_id": "BUS_101",
    "route_id": "216",
    "latitude": 17.385044,
    "longitude": 78.486671,
    "speed": 34.5,
    "heading": 180.0,
    "status": "active",
    "last_seen": "2026-09-09T14:30:22.105400Z",
    "is_simulated": true
  }
}
```

---

### `GET /api/buses`
List all active transit buses with their current GPS locations and operational status.

**Request:**
```bash
curl -X GET "http://127.0.0.1:8000/api/buses"
```

**Response (200 OK):**
```json
[
  {
    "bus_id": "BUS_101",
    "route_id": "216",
    "latitude": 17.385044,
    "longitude": 78.486671,
    "speed": 34.5,
    "heading": 180.0,
    "status": "active",
    "last_seen": "2026-09-09T14:30:22.105400Z",
    "is_simulated": true
  },
  {
    "bus_id": "BUS_102",
    "route_id": "216",
    "latitude": 17.391600,
    "longitude": 78.435000,
    "speed": 28.0,
    "heading": 289.0,
    "status": "active",
    "last_seen": "2026-09-09T14:30:25.000000Z",
    "is_simulated": true
  }
]
```

---

### `GET /api/buses/{bus_id}`
Retrieve a specific bus by ID including recent detected events.

**Request:**
```bash
curl -X GET "http://127.0.0.1:8000/api/buses/BUS_101"
```

**Response (200 OK):**
```json
{
  "bus_id": "BUS_101",
  "route_id": "216",
  "latitude": 17.385044,
  "longitude": 78.486671,
  "speed": 34.5,
  "heading": 180.0,
  "status": "active",
  "last_seen": "2026-09-09T14:30:22.105400Z",
  "active_events_count": 3,
  "recent_events": [
    {
      "event_id": "evt_7f8a19bc34e1",
      "bus_id": "BUS_101",
      "route_id": "216",
      "event_type": "POTHOLE",
      "event_category": "ROAD_DEFECT",
      "confidence": 0.91,
      "latitude": 17.385044,
      "longitude": 78.486671,
      "severity": "HIGH",
      "status": "detected",
      "image_path": "/evidence/road_defects/defect_BUS_101_POTHOLE_000045.jpg",
      "video_timestamp": 1.5,
      "details": {},
      "timestamp": "2026-09-09T14:30:20Z",
      "is_simulated": true,
      "disclaimer": "prototype heuristic estimation — rule-based detection, not forensic determination"
    }
  ],
  "is_simulated": true
}
```

---

## 3. Traffic Density & Spatial Heatmaps

### `GET /api/traffic`
List aggregated traffic density measurements.

**Request:**
```bash
curl -X GET "http://127.0.0.1:8000/api/traffic?density=HIGH&limit=10"
```

**Response (200 OK):**
```json
{
  "total": 15,
  "count": 10,
  "limit": 10,
  "offset": 0,
  "measurements": [
    {
      "measurement_id": "meas_1a2b3c4d",
      "bus_id": "BUS_101",
      "latitude": 17.385044,
      "longitude": 78.486671,
      "car_count": 8,
      "bus_count": 1,
      "truck_count": 2,
      "motorcycle_count": 4,
      "total_vehicle_count": 15,
      "traffic_density": "HIGH",
      "timestamp": "2026-09-09T14:30:25Z",
      "is_simulated": true,
      "disclaimer": "prototype traffic-density estimation — not scientifically calibrated"
    }
  ],
  "is_simulated": true
}
```

---

### `GET /api/heatmap`
Retrieve severity-weighted geographic coordinates for GIS heatmaps.

**Request:**
```bash
curl -X GET "http://127.0.0.1:8000/api/heatmap?category=DEFECTS&min_weight=1.0"
```

**Response (200 OK):**
```json
{
  "total_points": 3,
  "points": [
    {
      "latitude": 17.385044,
      "longitude": 78.486671,
      "weight": 3.0,
      "intensity": "high",
      "event_type": "POTHOLE",
      "severity": "HIGH",
      "bus_id": "BUS_101",
      "timestamp": "2026-09-09T14:30:20Z"
    },
    {
      "latitude": 17.391600,
      "longitude": 78.435000,
      "weight": 2.0,
      "intensity": "medium",
      "event_type": "DAMAGED_ROAD",
      "severity": "MEDIUM",
      "bus_id": "BUS_101",
      "timestamp": "2026-09-09T14:30:25Z"
    }
  ],
  "filters_applied": {
    "category": "DEFECTS",
    "min_weight": 1.0,
    "bus_id": null
  },
  "is_simulated": true,
  "disclaimer": "prototype spatial aggregation — for demonstration visualization"
}
```

---

## 4. Asynchronous Video Processing

### `POST /api/process-video`
Submit a video and optional GPS CSV file for non-blocking edge AI execution.

**Request:**
```bash
curl -X POST "http://127.0.0.1:8000/api/process-video" \
  -F "video=@data/videos/road_test.mp4;type=video/mp4" \
  -F "gps=@data/gps/BUS_101.csv;type=text/csv" \
  -F "bus_id=BUS_101" \
  -F "route_id=216" \
  -F "enable_ocr=true"
```

**Response (202 Accepted):**
```json
{
  "job_id": "job_a1b2c3d4e5f6",
  "status": "queued",
  "message": "Video processing job queued and running asynchronously in background",
  "bus_id": "BUS_101",
  "route_id": "216",
  "created_at": "2026-09-09T14:35:00Z",
  "status_url": "/api/process-video/job_a1b2c3d4e5f6",
  "websocket_url": "/ws/events",
  "is_simulated": true
}
```

---

### `GET /api/process-video/{job_id}`
Poll the execution progress, frame rate, and event count of an asynchronous job.

**Request:**
```bash
curl -X GET "http://127.0.0.1:8000/api/process-video/job_a1b2c3d4e5f6"
```

**Response (200 OK):**
```json
{
  "job_id": "job_a1b2c3d4e5f6",
  "status": "completed",
  "progress_pct": 100.0,
  "bus_id": "BUS_101",
  "route_id": "216",
  "created_at": "2026-09-09T14:35:00Z",
  "started_at": "2026-09-09T14:35:01Z",
  "completed_at": "2026-09-09T14:35:45Z",
  "elapsed_seconds": 44.2,
  "total_frames": 624,
  "processed_frames": 624,
  "fps": 14.1,
  "events_generated": 18,
  "events_by_category": {
    "ROAD_DEFECT": 16,
    "TRAFFIC_DENSITY": 2
  },
  "unique_vehicles_counted": 24,
  "output_video": "data/outputs/jobs/BUS_101_upload_road_test.mp4",
  "output_json": "data/outputs/jobs/BUS_101_upload_road_test.mp4.json",
  "evidence_dir": "data/outputs/unified_evidence",
  "error": null,
  "is_simulated": true,
  "disclaimer": "prototype heuristic estimation — rule-based detection, not forensic determination"
}
```

---

## 5. WebSockets Real-Time Streaming

### Dedicated Events Stream: `WS /ws/events`
Connect to receive real-time road defects, incidents, and congestion alerts as they are detected.

```javascript
const ws = new WebSocket("ws://127.0.0.1:8000/ws/events");
ws.onmessage = (event) => {
  const payload = JSON.parse(event.data);
  console.log("New Event Received:", payload);
};
```

### Dedicated Bus Telemetry Stream: `WS /ws/buses`
Connect to receive continuous GPS movements and speed/heading updates of the active fleet.

```javascript
const ws = new WebSocket("ws://127.0.0.1:8000/ws/buses");
ws.onmessage = (event) => {
  const payload = JSON.parse(event.data);
  console.log("Bus Position Update:", payload);
};
```
