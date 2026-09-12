/**
 * BusSense-AI Frontend Dashboard Logic
 * Prototype for SIH26124: Mobile Urban Intelligence Sensing
 * 
 * NOTE: Displays SIMULATED TELEMETRY for hackathon demonstration.
 */

document.addEventListener('DOMContentLoaded', () => {
    initMap();
    initAnalyticsChart();
    checkBackendHealth();
    fetchExistingBuses();
    initWebSocket();
});

let map;
let analyticsChart;
const busMarkers = {};
const busSpeeds = {};

const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' 
    ? 'http://127.0.0.1:8000' 
    : '';

const BUS_COLORS = {
    'BUS_101': '#38bdf8', // Light Blue (Route 216)
    'BUS_102': '#22c55e', // Green (Route 10)
    'BUS_103': '#f59e0b', // Amber/Yellow (Route 49)
};

/**
 * Initialize Leaflet Map
 */
function initMap() {
    const mapElement = document.getElementById('map');
    if (!mapElement || typeof L === 'undefined') return;

    // Default center: Hyderabad Metropolitan Region
    map = L.map('map').setView([17.4000, 78.4400], 13);

    // OpenStreetMap Dark/Standard Tile Layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19
    }).addTo(map);
}

/**
 * Create or update a bus marker on the Leaflet map
 */
function updateBusMarker(telemetry) {
    if (!map || !telemetry || !telemetry.latitude || !telemetry.longitude) return;

    const busId = telemetry.bus_id;
    const routeId = telemetry.route_id || 'N/A';
    const lat = telemetry.latitude;
    const lon = telemetry.longitude;
    const speed = telemetry.speed || 0.0;
    const heading = telemetry.heading || 0.0;
    const status = telemetry.status || 'active';
    const color = BUS_COLORS[busId] || '#38bdf8';

    busSpeeds[busId] = speed;

    const popupContent = `
        <div style="font-family: sans-serif; font-size: 12px; min-width: 160px;">
            <strong style="color: ${color}; font-size: 14px;">🚌 ${busId}</strong><br>
            <strong>Route:</strong> ${routeId}<br>
            <strong>Speed:</strong> ${speed.toFixed(1)} km/h<br>
            <strong>Heading:</strong> ${heading.toFixed(1)}°<br>
            <strong>Status:</strong> <span style="text-transform: capitalize;">${status}</span><br>
            <div style="margin-top: 6px; padding: 2px 4px; background: rgba(245,158,11,0.15); border: 1px solid rgba(245,158,11,0.3); border-radius: 3px; font-size: 10px; color: #f59e0b; text-align: center;">
                SIMULATED TELEMETRY
            </div>
        </div>
    `;

    if (busMarkers[busId]) {
        // Move existing marker smoothly
        busMarkers[busId].setLatLng([lat, lon]);
        busMarkers[busId].setPopupContent(popupContent);
    } else {
        // Create new marker with custom style
        const marker = L.circleMarker([lat, lon], {
            color: '#ffffff',
            weight: 2,
            fillColor: color,
            fillOpacity: 0.9,
            radius: 9
        }).addTo(map);

        marker.bindPopup(popupContent);
        marker.bindTooltip(`🚌 ${busId} (${speed.toFixed(0)} km/h)`, {
            permanent: false,
            direction: 'top',
            offset: [0, -8]
        });

        busMarkers[busId] = marker;
    }

    updateFleetSidebar(busId, routeId, speed, status);
    updateAverageSpeed();
}

/**
 * Update Sidebar fleet card details
 */
function updateFleetSidebar(busId, routeId, speed, status) {
    const fleetList = document.getElementById('fleet-list');
    if (!fleetList) return;

    let card = document.getElementById(`fleet-card-${busId}`);
    if (!card) {
        card = document.createElement('div');
        card.id = `fleet-card-${busId}`;
        card.className = 'fleet-card active';
        fleetList.appendChild(card);
    }

    const color = BUS_COLORS[busId] || '#38bdf8';
    card.innerHTML = `
        <div class="fleet-info">
            <strong style="color: ${color}">🚌 ${busId}</strong>
            <span>Route ${routeId} • ${speed.toFixed(1)} km/h (${status})</span>
        </div>
        <span class="pulse-indicator ${speed > 0 ? '' : 'idle'}"></span>
    `;
}

/**
 * Update the overall average speed metric
 */
function updateAverageSpeed() {
    const speedElement = document.getElementById('stat-speed');
    if (!speedElement) return;

    const values = Object.values(busSpeeds);
    if (values.length === 0) return;
    const avg = values.reduce((a, b) => a + b, 0) / values.length;
    speedElement.textContent = `${avg.toFixed(1)} km/h`;
}

/**
 * Fetch initially recorded buses from database
 */
async function fetchExistingBuses() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/telemetry/buses`);
        if (response.ok) {
            const buses = await response.json();
            const fleetList = document.getElementById('fleet-list');
            if (fleetList && buses.length > 0) {
                fleetList.innerHTML = '';
            }
            buses.forEach(b => {
                if (b.latitude && b.longitude) {
                    updateBusMarker(b);
                }
            });
        }
    } catch (e) {
        console.log('Telemetry initial fetch notice:', e);
    }
}

/**
 * Initialize Chart.js Analytics Placeholder
 */
function initAnalyticsChart() {
    const ctx = document.getElementById('analytics-chart');
    if (!ctx || typeof Chart === 'undefined') return;

    analyticsChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'],
            datasets: [
                {
                    label: 'Potholes / Defects',
                    data: [2, 1, 5, 8, 4, 3],
                    backgroundColor: '#f59e0b'
                },
                {
                    label: 'Traffic Density (veh/min)',
                    data: [12, 5, 45, 60, 52, 38],
                    backgroundColor: '#38bdf8'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: '#94a3b8', font: { size: 10 } }
                }
            },
            scales: {
                x: { ticks: { color: '#94a3b8', font: { size: 9 } }, grid: { color: '#334155' } },
                y: { ticks: { color: '#94a3b8', font: { size: 9 } }, grid: { color: '#334155' } }
            }
        }
    });
}

/**
 * Verify Backend Health Endpoint
 */
async function checkBackendHealth() {
    const statusBadge = document.getElementById('backend-status');
    try {
        const response = await fetch(`${API_BASE_URL}/health`);
        if (response.ok) {
            const data = await response.json();
            statusBadge.textContent = 'Backend: Online';
            statusBadge.className = 'badge status-connected';
        } else {
            statusBadge.textContent = 'Backend: DB Offline';
            statusBadge.className = 'badge status-error';
        }
    } catch (err) {
        statusBadge.textContent = 'Backend: Offline (Waiting)';
        statusBadge.className = 'badge status-pending';
    }
}

/**
 * Initialize WebSocket connection for live telemetry stream
 */
function initWebSocket() {
    const wsStatusBadge = document.getElementById('ws-status');
    const wsUrl = `ws://127.0.0.1:8000/ws`;

    try {
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            if (wsStatusBadge) {
                wsStatusBadge.textContent = 'WebSocket: Connected';
                wsStatusBadge.className = 'badge status-connected';
            }
            ws.send('client_ready');
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'bus_telemetry' && msg.data) {
                    updateBusMarker(msg.data);
                }
            } catch (e) {
                console.log('Raw WS message:', event.data);
            }
        };

        ws.onerror = () => {
            if (wsStatusBadge) {
                wsStatusBadge.textContent = 'WebSocket: Error';
                wsStatusBadge.className = 'badge status-pending';
            }
        };

        ws.onclose = () => {
            if (wsStatusBadge) {
                wsStatusBadge.textContent = 'WebSocket: Offline';
                wsStatusBadge.className = 'badge status-pending';
            }
            // Auto reconnect after 3 seconds
            setTimeout(initWebSocket, 3000);
        };
    } catch (e) {
        if (wsStatusBadge) {
            wsStatusBadge.textContent = 'WebSocket: Unavailable';
            wsStatusBadge.className = 'badge status-pending';
        }
    }
}
