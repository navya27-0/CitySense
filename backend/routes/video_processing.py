"""REST endpoints for asynchronous video AI pipeline processing."""

import os
import re
import json
import shutil
import tempfile
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status

from backend.schemas.video_processing import (
    VideoProcessResponse,
    JobStatusResponse,
)
from backend.services.pipeline_service import (
    submit_video_job,
    get_job,
    list_jobs,
)
from ai.pipeline.edge_pipeline import PipelineConfig

router = APIRouter()

# Uploads directory
UPLOADS_DIR = Path("data/uploads")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


@router.post(
    "/process-video",
    response_model=VideoProcessResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit video for asynchronous Edge AI processing",
)
async def process_video_endpoint(
    video: UploadFile = File(..., description="Video stream or MP4 recording file"),
    gps: UploadFile = File(..., description="Mandatory synchronized GPS CSV log"),
    bus_id: str = Form(default="BUS_101", description="Transit bus fleet ID"),
    route_id: str = Form(default="216", description="Assigned transit route identifier"),
    enable_vehicles: bool = Form(default=True, description="Toggle vehicle tracking stage"),
    enable_defects: bool = Form(default=True, description="Toggle road defect detection stage"),
    enable_ocr: bool = Form(default=True, description="Toggle ANPR OCR extraction stage"),
    enable_incidents: bool = Form(default=True, description="Toggle incident detection stage"),
    enable_density: bool = Form(default=True, description="Toggle traffic density estimation stage"),
):
    """Submits a video file and mandatory synchronized GPS CSV for non-blocking asynchronous processing.
    
    1. Validates and saves video and GPS inputs.
    2. Spawns background worker thread running `EdgeAIPipeline`.
    3. As events are generated, persists them to PostgreSQL and broadcasts over WebSocket `/ws/events`.
    4. Immediately returns `job_id` and polling status URL.
    """
    if not video.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No video file provided.")

    if not gps or not gps.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mandatory GPS CSV telemetry log is required for dynamic edge processing.")

    # Save uploaded video with sanitized filename
    clean_vid = re.sub(r'[^a-zA-Z0-9._-]', '_', Path(video.filename).name)
    safe_video_name = f"upload_{bus_id}_{clean_vid}"
    video_dest = UPLOADS_DIR / safe_video_name
    try:
        with open(video_dest, "wb") as f:
            shutil.copyfileobj(video.file, f)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to save video: {e}")

    # Save mandatory GPS CSV with sanitized filename
    clean_gps = re.sub(r'[^a-zA-Z0-9._-]', '_', Path(gps.filename).name)
    safe_gps_name = f"upload_gps_{bus_id}_{clean_gps}"
    gps_dest = UPLOADS_DIR / safe_gps_name
    try:
        with open(gps_dest, "wb") as f:
            shutil.copyfileobj(gps.file, f)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to save GPS CSV: {e}")

    # Configure pipeline
    config = PipelineConfig(
        bus_id=bus_id,
        route_id=route_id,
        enable_vehicle_detection=enable_vehicles,
        enable_road_defect_detection=enable_defects,
        enable_ocr=enable_ocr,
        enable_incident_detection=enable_incidents,
        enable_density_estimation=enable_density,
    )

    out_video = Path(f"data/outputs/jobs/{bus_id}_{safe_video_name}")
    out_json = Path(f"data/outputs/jobs/{bus_id}_{safe_video_name}.json")
    evidence_dir = Path("data/outputs/unified_evidence")

    # Enqueue background execution
    job_id = submit_video_job(
        video_path=video_dest,
        gps_path=gps_dest,
        bus_id=bus_id,
        route_id=route_id,
        output_video_path=out_video,
        output_json_path=out_json,
        output_evidence_dir=evidence_dir,
        config=config,
    )

    return VideoProcessResponse(
        job_id=job_id,
        status="queued",
        message="Video processing job queued and running asynchronously in background",
        bus_id=bus_id,
        route_id=route_id,
        status_url=f"/api/process-video/{job_id}",
        websocket_url="/ws/events",
        is_simulated=True,
    )


@router.get(
    "/process-video/{job_id}",
    response_model=JobStatusResponse,
    summary="Get video processing job status and progress",
)
def get_job_status(job_id: str):
    """Retrieves current execution status, frame progress, and event counts for a submitted job. Returns 404 if invalid ID."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )

    return JobStatusResponse(**job)


@router.get(
    "/process-video/{job_id}/results",
    summary="Get full structured output detection results JSON for a completed job",
)
def get_job_results(job_id: str):
    """Returns the full detection summary JSON payload generated by the edge AI pipeline."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )
    if job.get("results"):
        return job["results"]
    if job.get("output_json") and Path(job["output_json"]).exists():
        with open(job["output_json"], "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "status": job.get("status", "processing"),
        "job_id": job_id,
        "message": "Job is still processing or has not generated summary output yet.",
    }


@router.get(
    "/process-video",
    response_model=List[JobStatusResponse],
    summary="List all video processing jobs",
)
def list_all_jobs():
    """Returns a list of all active, completed, and queued video processing jobs."""
    jobs = list_jobs()
    return [JobStatusResponse(**j) for j in jobs]
