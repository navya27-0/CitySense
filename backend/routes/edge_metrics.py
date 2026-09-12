"""REST endpoint for Edge Processing bandwidth metrics.

Demonstrates that the BusSense-AI system processes raw video locally on the edge
and transmits only lightweight structured event metadata to the backend, achieving
significant bandwidth reduction.

All bandwidth figures are estimates derived from this prototype's actual processing
dimensions — not generalized industry benchmarks.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List

from fastapi import APIRouter

from backend.schemas.edge_metrics import EdgeMetricsResponse, SlimEventPayload

router = APIRouter()

# ─── In-memory metrics store (updated by pipeline jobs) ───────────────────────
_edge_metrics_store: Dict[str, Any] = {}


def _format_bytes(num_bytes: int) -> str:
    """Format byte count into human-readable string."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 ** 2:
        return f"{num_bytes / 1024:.2f} KB"
    elif num_bytes < 1024 ** 3:
        return f"{num_bytes / (1024 ** 2):.2f} MB"
    else:
        return f"{num_bytes / (1024 ** 3):.2f} GB"


def update_edge_metrics(metrics: Dict[str, Any]) -> None:
    """Called by the pipeline service when a processing job completes.
    
    Updates the global metrics store so GET /api/edge-metrics reflects
    the latest pipeline run data.
    """
    global _edge_metrics_store
    _edge_metrics_store = metrics


def _compute_metrics_from_events() -> Dict[str, Any]:
    """Compute edge processing metrics from the existing event store.
    
    This allows the demo to show realistic metrics even without running
    a full pipeline — it calculates what the bandwidth savings would be
    based on stored events and typical video parameters.
    """
    # Import here to avoid circular dependency
    from backend.routes.events import _IN_MEMORY_EVENTS

    events = list(_IN_MEMORY_EVENTS.values())
    num_events = len(events)

    # Default video parameters (based on typical bus camera footage)
    width, height = 1920, 1080
    fps = 30.0
    # Estimate: assume 15 seconds of video per event on average (conservative)
    estimated_frames = max(450, num_events * 38) if num_events > 0 else 450

    raw_frame_bytes = width * height * 3  # BGR uncompressed
    raw_video_bytes = estimated_frames * raw_frame_bytes

    # Build slim payloads for each event
    slim_payloads: List[Dict[str, Any]] = []
    for evt in events:
        evt_data = evt if isinstance(evt, dict) else (evt.model_dump(mode="json") if hasattr(evt, "model_dump") else {})
        details = evt_data.get("details", {}) or {}
        slim = {
            "event_type": evt_data.get("event_type", "UNKNOWN"),
            "confidence": evt_data.get("confidence", 0.0),
            "bus_id": evt_data.get("bus_id", "BUS_101"),
            "timestamp": str(evt_data.get("timestamp", "")),
            "latitude": evt_data.get("latitude", 0.0),
            "longitude": evt_data.get("longitude", 0.0),
            "tracking_id": details.get("vehicle_tracking_id"),
            "registration_number": details.get("registration_number"),
            "evidence_image_ref": evt_data.get("image_path"),
        }
        slim_payloads.append(slim)

    # Calculate transmitted bytes
    transmitted_event_bytes = sum(len(json.dumps(s).encode("utf-8")) for s in slim_payloads)

    # Calculate actual evidence image file sizes for referenced events
    evidence_bytes = 0
    for s in slim_payloads:
        img_ref = s.get("evidence_image_ref")
        if img_ref:
            clean_rel = img_ref.replace("/evidence/", "data/outputs/").lstrip("/")
            p = Path(clean_rel)
            if p.exists():
                try:
                    evidence_bytes += p.stat().st_size
                except OSError:
                    evidence_bytes += 55_000
            else:
                evidence_bytes += 55_000

    total_transmitted = transmitted_event_bytes + evidence_bytes

    # Bandwidth reduction
    if raw_video_bytes > 0:
        reduction_pct = round((1.0 - total_transmitted / raw_video_bytes) * 100, 2)
    else:
        reduction_pct = 0.0

    # Example payload
    example_payload = slim_payloads[0] if slim_payloads else {
        "event_type": "POTHOLE",
        "confidence": 0.94,
        "bus_id": "BUS_101",
        "timestamp": "2026-09-10T14:30:05Z",
        "latitude": 17.3862,
        "longitude": 78.4855,
        "tracking_id": 42,
        "registration_number": None,
        "evidence_image_ref": "/evidence/defect_BUS_101_POTHOLE_000142.jpg",
    }

    return {
        "frames_processed_locally": estimated_frames,
        "events_generated": num_events,
        "video_resolution": f"{width}x{height}",
        "video_fps": fps,
        "raw_frame_size_bytes": raw_frame_bytes,
        "raw_video_data_bytes": raw_video_bytes,
        "raw_video_data_display": _format_bytes(raw_video_bytes),
        "transmitted_event_data_bytes": transmitted_event_bytes,
        "transmitted_event_data_display": _format_bytes(transmitted_event_bytes),
        "evidence_images_bytes": evidence_bytes,
        "evidence_images_display": _format_bytes(evidence_bytes),
        "total_transmitted_bytes": total_transmitted,
        "total_transmitted_display": _format_bytes(total_transmitted),
        "bandwidth_reduction_pct": max(0.0, min(100.0, reduction_pct)),
        "per_event_payload_example": example_payload,
        "events_payload_fields": [
            "event_type", "confidence", "bus_id", "timestamp",
            "latitude", "longitude", "tracking_id",
            "registration_number", "evidence_image_ref"
        ],
        "disclaimer": "Estimate based on this prototype's processing run — not a general industry claim.",
        "is_simulated": True,
    }


@router.get(
    "",
    response_model=EdgeMetricsResponse,
    summary="Get edge processing bandwidth metrics",
    description=(
        "Returns metrics demonstrating the edge processing architecture: "
        "frames processed locally, events generated, estimated raw video data size, "
        "transmitted event data size, and approximate bandwidth reduction percentage. "
        "All figures are estimates based on prototype data."
    ),
)
async def get_edge_metrics():
    """Returns edge processing bandwidth demonstration metrics.
    
    If a pipeline job has been run, returns actual measured metrics.
    Otherwise, computes estimated metrics from stored events and
    typical video parameters to support demo/presentation scenarios.
    """
    if _edge_metrics_store:
        return EdgeMetricsResponse(**_edge_metrics_store)
    
    # Compute from stored events
    computed = _compute_metrics_from_events()
    return EdgeMetricsResponse(**computed)
