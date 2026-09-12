# BusSense-AI | Road Defect Detection Model & Training Guide

This guide details the end-to-end dataset preparation, labeling specifications, custom YOLOv8 model training, drop-in integration, and troubleshooting for the **BusSense-AI Road Defect Detection Module** (covering BEL problem statement requirements).

---

## 1. Defect Subtypes & Dataset Labeling Requirements

The road defect module detects 6 municipal urban infrastructure anomalies as standard subtypes:

| Subtype Key | Display Name | Visual Characteristics | Recommended Bounding Box Rules |
| :--- | :--- | :--- | :--- |
| `POTHOLE` | Pothole | Asphalt cavities, deep depressions, crumbling road surface pits. | Tightly bound the pit perimeter including fractured edges. |
| `DAMAGED_ROAD` | Damaged Road / Cracking | Alligator/crocodile cracks, longitudinal/transverse splits, surface unraveling, severe rutting. | Enclose the full contiguous cracked surface region. |
| `MISSING_DIVIDER` | Missing / Broken Road Divider | Broken central median barriers, missing concrete kerbs, knocked-over road studs / bollards. | Bound the damaged/missing segment of median barrier. |
| `MISSING_ZEBRA_CROSSING` | Faded / Missing Zebra Crossing | Worn-out, faded, or absent pedestrian crosswalk road markings at designated junctions. | Bound the crosswalk road lane marking area. |
| `DAMAGED_SIGNBOARD` | Damaged / Missing Traffic Signboard | Bent, rusted, graffiti-covered, obscured, rotated, or knocked-over traffic warning / speed limit signs. | Bound the signboard head and mounting pole. |
| `WATERLOGGING` | Waterlogging / Standing Water | Standing rainwater pools covering road lanes, flooded curbs, standing puddles causing hydroplaning risk. | Bound the surface reflection puddle boundary on asphalt. |

### Dataset Annotation Format (YOLO Darknet TXT)
Annotations follow the standard YOLO normalized bounding box format:
```text
<class_id> <center_x> <center_y> <width> <height>
```
All coordinate values are floats normalized between `0.0` and `1.0`.

### Recommended Public Datasets for Fine-Tuning:
1. **RDD2022 (Road Damage Dataset)**: Contains 47,000+ multi-country road damage images (`D00`: longitudinal crack/pothole, `D10`: transverse crack, `D20`: alligator crack, `D40`: rutting/pothole).
2. **Roboflow Universe - Pothole & Road Anomaly Datasets**: Pre-labeled datasets for potholes, flooded roads, and damaged signboards.
3. **Indian Driving Dataset (IDD)**: Diverse Indian road conditions with varied road markings and dividers.

---

## 2. Training Pipeline (Ultralytics YOLOv8)

### Step 1: Create `road_defects.yaml` Dataset Configuration
```yaml
# data/datasets/road_defects.yaml
path: ../datasets/road_defects  # dataset root dir
train: images/train
val: images/val
test: images/test

# Number of classes
nc: 6

# Class names (dynamically introspected by BusSense-AI)
names:
  0: pothole
  1: damaged_road
  2: missing_divider
  3: missing_zebra_crossing
  4: damaged_signboard
  5: waterlogging
```

### Step 2: Run Custom Training Command
Train lightweight `yolov8n.pt` (Nano) or `yolov8s.pt` (Small) for edge laptop deployment:

```bash
# Using Python CLI
yolo detect train \
  data=data/datasets/road_defects.yaml \
  model=yolov8n.pt \
  epochs=100 \
  imgsz=640 \
  batch=16 \
  device=0 \
  workers=8 \
  name=bussense_road_defects \
  pretrained=True \
  optimizer=AdamW \
  lr0=0.001
```

### Step 3: Drop-In Trained Weights
Once training completes, copy the best weights into the designated project directory:
```bash
cp runs/detect/bussense_road_defects/weights/best.pt models/road_defects/best.pt
```

`RoadDefectDetector` automatically detects and loads `models/road_defects/best.pt` on initialization without requiring any source code modifications.

---

## 3. Inference & Verification Command

Run the standalone road-defect detection script on any MP4 video feed:

```powershell
.\venv\Scripts\python.exe scripts/test_road_defect_detection.py `
  --video data/videos/road_test.mp4 `
  --gps-csv data/gps/BUS_101.csv `
  --model models/road_defects/best.pt `
  --conf 0.30 `
  --bus-id BUS_101 `
  --out-video data/outputs/road_defect_output.mp4 `
  --out-json data/outputs/road_defect_events.json `
  --events-dir data/outputs/events `
  --max-frames 200
```

---

## 4. Example Output Schema

### Saved Evidence Image
Evidence frames are saved to `data/outputs/events/` with distinct bounding boxes and HUD watermark:
- **Filename**: `roaddefect_BUS101_POTHOLE_000050.jpg`

### Structured Event JSON (`data/outputs/road_defect_events.json`)
```json
{
  "metadata": {
    "source_video": "data\\videos\\road_test.mp4",
    "model_source": "Custom YOLO (best.pt)",
    "custom_weights_loaded": true,
    "confidence_threshold": 0.30,
    "bus_id": "BUS_101",
    "total_frames_processed": 200,
    "processing_time_seconds": 45.2,
    "is_simulated": true
  },
  "aggregate_statistics": {
    "total_events_logged": 5,
    "events_by_subtype": {
      "POTHOLE": 2,
      "DAMAGED_ROAD": 1,
      "MISSING_DIVIDER": 1,
      "MISSING_ZEBRA_CROSSING": 0,
      "DAMAGED_SIGNBOARD": 0,
      "WATERLOGGING": 1
    },
    "events_by_severity": {
      "low": 1,
      "medium": 2,
      "high": 1,
      "critical": 1
    }
  },
  "events": [
    {
      "event_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
      "bus_id": "BUS_101",
      "event_type": "POTHOLE",
      "defect_subtype": "POTHOLE",
      "confidence": 0.88,
      "frame_number": 50,
      "video_timestamp": 1.67,
      "timestamp": "2026-09-09T14:30:22.800000+00:00",
      "latitude": 17.392193,
      "longitude": 78.433200,
      "speed_kmh": 37.25,
      "heading_deg": 289.0,
      "severity": "high",
      "image_path": "data/outputs/events/roaddefect_BUS101_POTHOLE_000050.jpg",
      "bounding_box": [1536, 1404, 2227, 1771],
      "area": 253591,
      "status": "detected",
      "is_simulated": true
    }
  ]
}
```

---

## 5. Troubleshooting & Best Practices

| Issue | Cause | Recommended Solution |
| :--- | :--- | :--- |
| **No custom weights present** | Initial setup before fine-tuning | System automatically engages **DEMO / FALLBACK MODE** with calibrated CV anomaly filters. Logs clear notification without failing. |
| **Pothole false positives in shadows** | Tree/bridge shadows resembling dark asphalt cavities | Apply data augmentation during training: `hsv_v=0.4` (brightness variance), `mosaic=1.0`, and increase `conf_threshold` to `0.40`. |
| **High latency on edge laptop CPU** | 4K video resolution ($3840 \times 2160$) | Resize frames to $640 \times 640$ or $1280 \times 720$ during preprocessing before running inference. |
| **Duplicate events for same defect** | Bus driving over same pothole across multiple consecutive frames | Handled automatically by `dedup_window_seconds=2.0` (ignores identical defect triggers within 2 seconds / 15 meters). |
| **Waterlogging false detections** | Asphalt reflections during sunny midday | Include dry shiny asphalt negative samples in training dataset. |
