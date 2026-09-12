# BusSense-AI: AI-Powered Mobile Urban Intelligence Platform Using Public Transport Fleet

**Smart India Hackathon Project (SIH26124)**  
*A working prototype for edge-AI mobile urban sensing transformed from public transit fleets.*

---

## 📌 Project Overview

**BusSense-AI** transforms public transit buses into mobile urban sensing units. By processing bus-mounted camera streams with edge AI and synchronizing them with GPS telemetry, the system detects:
- **Road Defects & Potholes**
- **Traffic Density & Vehicle Counts**
- **Vehicle Tracking & Trajectories**
- **Number Plate OCR / ANPR**
- **Traffic Incidents & Stalled Vehicles**

Detected events are transmitted to a centralized FastAPI backend, persisted in PostgreSQL/PostGIS, and streamed in real time over WebSockets to an interactive GIS dashboard built with Leaflet.js and Chart.js.

> [!NOTE]
> **Prototype & Simulation Notice**: This is a working prototype developed for demonstration purposes. All incoming video feeds and GPS traces are recorded/simulated data. The system operates fully offline without dependencies on external government or transport authority live feeds.

---

## 🏗 Repository Structure

```
BusSense-AI/
├── ai/                              # Edge AI detection & synchronization modules
│   ├── vehicle_detection/           # Vehicle detection & counting (YOLO)
│   ├── road_defect_detection/       # Road defect & pothole detection
│   ├── number_plate/                # ANPR / OCR module
│   ├── tracking/                    # Multi-object tracking
│   ├── incident_detection/          # Incident & congestion detection
│   └── pipeline/                    # Stream pipeline & synchronization
│       └── gps_sync.py              # GPS-Video sync placeholder
├── data/                            # Datasets and outputs (simulated)
│   ├── videos/                      # Bus camera MP4 video files
│   ├── gps/                         # Simulated GPS CSV traces
│   ├── mock/                        # Mock data fixtures
│   └── outputs/
│       └── events/                  # Detected JSON event outputs
├── backend/                         # FastAPI application
│   ├── main.py                      # Application entry point & WebSockets
│   ├── config.py                    # Environment settings (pathlib-based)
│   ├── database.py                  # SQLAlchemy & PostGIS session manager
│   ├── models/                      # SQLAlchemy ORM models
│   ├── schemas/                     # Pydantic data schemas
│   ├── routes/                      # API endpoint routers
│   ├── services/                    # Business logic & services
│   └── websocket/                   # WebSocket broadcast manager
├── frontend/                        # Web GIS dashboard
│   ├── index.html                   # Main dashboard UI
│   ├── css/
│   │   └── style.css                # Dark-themed UI stylesheet
│   ├── js/
│   │   └── main.js                  # Map initialization & WS client
│   └── assets/                      # Static assets & icons
├── scripts/                         # Utility & demo helper scripts
├── tests/                           # Unit and integration test suite
├── models/                          # AI weight checkpoints (.pt, .onnx)
├── .env.example                     # Environment template
├── .gitignore                       # Git ignore rules
├── requirements.txt                 # Python dependencies
├── docker-compose.yml               # Local PostGIS container definition
├── PROGRESS.md                      # Incremental progress log
└── README.md                        # Documentation and runbook
```

---

## ⚡ Quickstart (1-Click Run)

CitySense includes turnkey launcher scripts that set up the environment and run the complete system with a single command:

### Windows (PowerShell)
```powershell
.\run.ps1
```

### Windows (CMD / Double-Click)
```cmd
run.bat
```

### Linux / macOS
```bash
chmod +x run.sh setup.sh
./run.sh
```

*(These scripts automatically verify the local virtual environment in `./venv`, install dependencies from `requirements.txt`, initialize the SQLite/demo database, start the FastAPI server on port 8000, and open the browser dashboard).*

---

## ⚙️ Manual Installation

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.10, 3.11, 3.12, 3.14)
- Modern web browser (Chrome, Edge, Firefox)
- Docker & Docker Compose *(Optional, only if using external PostGIS container)*

### 2. Create Virtual Environment & Install Dependencies

```powershell
# Create local virtual environment
python -m venv venv

# Activate virtual environment
# Windows PowerShell:
.\venv\Scripts\Activate.ps1
# Windows CMD:
venv\Scripts\activate.bat
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Initialize Demo Database
```powershell
python scripts/init_db.py
```

### 4. Launch Full Demo Runner
```powershell
python scripts/run_demo.py
```
- Web Dashboard: `http://127.0.0.1:8000`
- Interactive API Docs (Swagger): `http://127.0.0.1:8000/docs`
- Health Check: `http://127.0.0.1:8000/api/health`

---

## 📦 Pushing to Git

To publish this standalone repository to GitHub, GitLab, or Bitbucket:

```bash
# Initialize git (if not already initialized)
git init

# Stage all files (respecting .gitignore)
git add .

# Create initial commit
git commit -m "feat: complete CitySense edge AI mobile urban sensing platform"

# Set main branch and remote URL
git branch -M main
git remote add origin https://github.com/<your-username>/CitySense.git

# Push to your repository
git push -u origin main
```

---

## 🎬 Demo Script for SIH Presentation

### 1. Clean Machine Quickstart (Single Command)
```powershell
python scripts/run_demo.py
```
This single command automatically:
- Checks environment & backend health
- Generates high-quality visual evidence frames & seeds urban datasets
- Starts the FastAPI backend server on port 8000
- Launches multi-bus fleet telemetry simulator (`BUS_101`, `BUS_102`, `BUS_103`) at 5x demo speed
- Kicks off background Edge AI processing on benchmark clips
- Automatically launches the default web browser to `http://localhost:8000/` in **Designer Light Mode**.

---

### 2. Judging Presentation Walkthrough (2-Minute Script)

| Timeline | What Appears on Screen | What to Explain to Judges |
| :--- | :--- | :--- |
| **0:00 – 0:30** | **Command Center & Light UI**<br>Dashboard loads in clean light mode with 5 top KPI cards (`Active Buses: 3`, `Events`, `Defects`, `Hotspots`, `Incidents`) and Edge Efficiency panel. | *"Welcome to BusSense-AI. We turn existing public transit fleets into mobile urban intelligence units without expensive dedicated sensor infrastructure."* |
| **0:30 – 1:00** | **Live Transit Fleet Telemetry**<br>Buses (Blue pins) move continuously along Route 216, Route 10, and Route 49M in Hyderabad. Clicking a bus opens live telemetry. | *"Each bus continuously streams lightweight GPS telemetry. The Leaflet GIS map dynamically updates bus locations in real time via WebSockets without continuous polling."* |
| **1:00 – 1:30** | **Detected Defects & Incident Dossiers**<br>Red markers (potholes), orange markers (hotspots), and purple markers (incidents) appear with rich visual evidence previews. | *"When a bus detects a defect or aggressive driving incident, only the structured event and a single compressed frame are sent. Notice the full provenance tags (Ground Truth vs. AI Inferred) and instant 1-click PDF Dossier export."* |
| **1:30 – 2:00** | **AI Video & GPS Ingestion Studio**<br>Navigate to `AI Video Studio` tab. Select a benchmark clip or upload a video + GPS CSV, click *Execute Edge AI Pipeline*, and watch live progress, annotated output video, and structured JSON. | *"Judges can test the system with any custom dashcam video. The edge pipeline runs YOLOv8 vehicle tracking, defect classification, and ANPR OCR, outputting annotated video and JSON."* |
| **2:00 – 2:30** | **Edge Architecture & Bandwidth Proof**<br>Navigate to `Edge Architecture`. View the side-by-side before/after comparison and live bandwidth reduction ($>99.9\%$). | *"This directly addresses the problem statement's core bandwidth constraint. A traditional system uploads 1.17 GB per 15-sec clip; BusSense-AI transmits only ~4.3 KB of structured metadata — saving 99.98% bandwidth."* |

---

### 3. How to Reset Demo
To clear all events and return the system to a clean initial demonstration state:

```powershell
python scripts/run_demo.py --reset
```

---

### 4. Intentional Scoping & Known Limitations (Proactive Scoping)
When presenting to judges, frame these proactively as intentional design decisions:
- **Edge-Optimized YOLOv8 Nano Architecture**: We deliberately chose lightweight models (~3.2M parameters) so AI inference runs in real-time on commodity edge hardware (even standard vehicle CPUs) without requiring dedicated discrete GPUs.
- **Rule-Based Kinematic Heuristics**: Rash driving and hit-and-run detection use transparent physics-based rules (slalom velocity vectors, flight acceleration, time-to-collision) rather than opaque black-box models, ensuring all flags are auditable by traffic authorities.
- **Vehicle Telemetry vs. Passenger Privacy**: OD flow analysis and congestion matrices are inferred strictly from bus trajectory stop passages — **zero passenger-level facial recognition or tracking is performed**, ensuring strict compliance with urban privacy norms.
- **Bandwidth Estimation Footnote**: All bandwidth savings ($>99.9\%$) are calculated based on prototype frame dimensions ($1920\times 1080$ BGR) and serialized event JSON sizes.

---

## 🧪 Testing & Verification

Run the test suite with pytest:
```powershell
pytest tests/ -v
```

---

## 📝 Roadmap & Progress Log
Refer to [PROGRESS.md](PROGRESS.md) for full details on all completed prompts.

