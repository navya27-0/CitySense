/**
 * CitySense - Comprehensive Chart.js Urban Analytics Visualizations Engine
 * Renders all 9 urban intelligence dimensions with dark-matter theme & empty-state resilience.
 */

(function () {
    const FONT_FAMILY = "'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif";
    const MONO_FONT = "'JetBrains Mono', monospace";

    const CHART_COLORS = {
        blue: '#3b82f6',
        cyan: '#06b6d4',
        emerald: '#10b981',
        amber: '#f59e0b',
        orange: '#f97316',
        red: '#ef4444',
        purple: '#a855f7',
        pink: '#ec4899',
        slate: '#64748b',
    };

    class CitySenseCharts {
        constructor() {
            this.chartInstances = new Map();
        }

        _getOrCreateCanvas(containerOrId) {
            let canvas = null;
            if (typeof containerOrId === 'string') {
                canvas = document.getElementById(containerOrId);
            } else if (containerOrId instanceof HTMLCanvasElement) {
                canvas = containerOrId;
            }
            if (!canvas) return null;

            // Destroy previous instance on this canvas
            if (this.chartInstances.has(canvas.id)) {
                this.chartInstances.get(canvas.id).destroy();
                this.chartInstances.delete(canvas.id);
            }

            // Remove previous empty state placeholder if any
            const parent = canvas.parentElement;
            if (parent) {
                const existingEmpty = parent.querySelector('.chart-insufficient-data');
                if (existingEmpty) existingEmpty.remove();
                canvas.style.display = 'block';
            }

            return canvas.getContext('2d');
        }

        _showInsufficientData(canvasId, message = 'Insufficient data in the selected time window') {
            const canvas = document.getElementById(canvasId);
            if (!canvas) return;

            if (this.chartInstances.has(canvasId)) {
                this.chartInstances.get(canvasId).destroy();
                this.chartInstances.delete(canvasId);
            }

            canvas.style.display = 'none';
            const parent = canvas.parentElement;
            if (parent && !parent.querySelector('.chart-insufficient-data')) {
                const emptyDiv = document.createElement('div');
                emptyDiv.className = 'chart-insufficient-data';
                emptyDiv.innerHTML = `
                    <div class="empty-state-icon">📊</div>
                    <div class="empty-state-title">Insufficient Data</div>
                    <div class="empty-state-msg">${message}</div>
                `;
                parent.appendChild(emptyDiv);
            }
        }

        // =====================================================================
        // 1. VEHICLE COUNTS BREAKDOWN & TIMELINE
        // =====================================================================
        renderVehicleCountsChart(canvasId, data) {
            if (!data || !data.meta?.has_data || !data.timeline || data.timeline.length === 0) {
                this._showInsufficientData(canvasId, 'No vehicle count records for selected filter');
                return;
            }

            const ctx = this._getOrCreateCanvas(canvasId);
            if (!ctx) return;

            const labels = data.timeline.map(t => t.label);
            const cars = data.timeline.map(t => t.car_count);
            const buses = data.timeline.map(t => t.bus_count);
            const trucks = data.timeline.map(t => t.truck_count);
            const twoWheelers = data.timeline.map(t => t.motorcycle_count);

            const chart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [
                        { label: 'Cars', data: cars, backgroundColor: '#3b82f6', borderRadius: 4 },
                        { label: 'Buses', data: buses, backgroundColor: '#06b6d4', borderRadius: 4 },
                        { label: 'Trucks / Heavy', data: trucks, backgroundColor: '#f59e0b', borderRadius: 4 },
                        { label: 'Motorcycles', data: twoWheelers, backgroundColor: '#a855f7', borderRadius: 4 },
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { stacked: true, grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#9ca3af', font: { family: FONT_FAMILY, size: 10 } } },
                        y: { stacked: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af', font: { family: MONO_FONT, size: 10 } } }
                    },
                    plugins: {
                        legend: { position: 'top', labels: { color: '#e5e7eb', font: { family: FONT_FAMILY, size: 11, weight: '600' }, boxWidth: 12 } },
                        tooltip: { backgroundColor: 'rgba(17, 24, 39, 0.95)', titleColor: '#fff', bodyColor: '#e5e7eb' }
                    }
                }
            });

            this.chartInstances.set(canvasId, chart);
        }

        // =====================================================================
        // 2. TRAFFIC DENSITY DISTRIBUTION
        // =====================================================================
        renderTrafficDensityChart(canvasId, data) {
            if (!data || !data.meta?.has_data || !data.distribution || data.total_measurements === 0) {
                this._showInsufficientData(canvasId, 'No traffic density samples for selected window');
                return;
            }

            const ctx = this._getOrCreateCanvas(canvasId);
            if (!ctx) return;

            const labels = data.distribution.map(d => d.density_level);
            const values = data.distribution.map(d => d.sample_count);
            const colorMap = {
                'LOW': '#10b981',
                'MEDIUM': '#eab308',
                'HIGH': '#f97316',
                'SEVERE': '#ef4444'
            };
            const colors = labels.map(l => colorMap[l] || '#3b82f6');

            const chart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: labels,
                    datasets: [{
                        data: values,
                        backgroundColor: colors,
                        borderColor: '#111827',
                        borderWidth: 2,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '65%',
                    plugins: {
                        legend: { position: 'right', labels: { color: '#e5e7eb', font: { family: FONT_FAMILY, size: 11, weight: '600' }, boxWidth: 12 } },
                        tooltip: {
                            backgroundColor: 'rgba(17, 24, 39, 0.95)',
                            callbacks: {
                                label: (ctx) => ` ${ctx.label}: ${ctx.raw} samples (${Math.round((ctx.raw / data.total_measurements) * 100)}%)`
                            }
                        }
                    }
                }
            });

            this.chartInstances.set(canvasId, chart);
        }

        // =====================================================================
        // 3. CONGESTION HOTSPOTS RANKING
        // =====================================================================
        renderCongestionHotspotsChart(canvasId, data) {
            if (!data || !data.meta?.has_data || !data.hotspots || data.hotspots.length === 0) {
                this._showInsufficientData(canvasId, 'No congestion bottlenecks observed in this period');
                return;
            }

            const ctx = this._getOrCreateCanvas(canvasId);
            if (!ctx) return;

            const topHotspots = data.hotspots.slice(0, 7);
            const labels = topHotspots.map(h => `${h.route_id ? 'Route ' + h.route_id : 'Sector'} (${h.latitude.toFixed(3)}, ${h.longitude.toFixed(3)})`);
            const counts = topHotspots.map(h => h.observed_vehicles);

            const chart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Observed Vehicle Load',
                        data: counts,
                        backgroundColor: 'rgba(249, 115, 22, 0.75)',
                        borderColor: '#f97316',
                        borderWidth: 1,
                        borderRadius: 6,
                    }]
                },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af', font: { family: MONO_FONT, size: 10 } } },
                        y: { grid: { display: false }, ticks: { color: '#e5e7eb', font: { family: FONT_FAMILY, size: 10, weight: '500' } } }
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: { backgroundColor: 'rgba(17, 24, 39, 0.95)' }
                    }
                }
            });

            this.chartInstances.set(canvasId, chart);
        }

        // =====================================================================
        // 4. EVENTS BY TYPE
        // =====================================================================
        renderEventsByTypeChart(canvasId, data) {
            if (!data || !data.meta?.has_data || !data.types || data.types.length === 0) {
                this._showInsufficientData(canvasId, 'No events captured in selected range');
                return;
            }

            const ctx = this._getOrCreateCanvas(canvasId);
            if (!ctx) return;

            const labels = data.types.map(t => t.event_type.replace(/_/g, ' '));
            const values = data.types.map(t => t.count);
            const palette = ['#ef4444', '#f97316', '#06b6d4', '#eab308', '#a855f7', '#ec4899', '#3b82f6', '#10b981'];

            const chart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: labels,
                    datasets: [{
                        data: values,
                        backgroundColor: palette.slice(0, labels.length),
                        borderColor: '#111827',
                        borderWidth: 2,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '60%',
                    plugins: {
                        legend: { position: 'right', labels: { color: '#e5e7eb', font: { family: FONT_FAMILY, size: 10, weight: '600' }, boxWidth: 10 } },
                        tooltip: { backgroundColor: 'rgba(17, 24, 39, 0.95)' }
                    }
                }
            });

            this.chartInstances.set(canvasId, chart);
        }

        // =====================================================================
        // 5. EVENTS BY LOCATION / CORRIDOR
        // =====================================================================
        renderEventsByLocationChart(canvasId, data) {
            if (!data || !data.meta?.has_data || !data.locations || data.locations.length === 0) {
                this._showInsufficientData(canvasId, 'No location-specific events logged');
                return;
            }

            const ctx = this._getOrCreateCanvas(canvasId);
            if (!ctx) return;

            const labels = data.locations.map(l => l.location_identifier);
            const defects = data.locations.map(l => l.defect_count);
            const incidents = data.locations.map(l => l.incident_count);
            const congestion = data.locations.map(l => l.congestion_count);

            const chart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [
                        { label: 'Road Defects', data: defects, backgroundColor: '#ef4444', borderRadius: 4 },
                        { label: 'Safety Incidents', data: incidents, backgroundColor: '#a855f7', borderRadius: 4 },
                        { label: 'Congestion Flags', data: congestion, backgroundColor: '#f97316', borderRadius: 4 },
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { grid: { display: false }, ticks: { color: '#e5e7eb', font: { family: FONT_FAMILY, size: 10, weight: '600' } } },
                        y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af', font: { family: MONO_FONT, size: 10 } } }
                    },
                    plugins: {
                        legend: { position: 'top', labels: { color: '#e5e7eb', font: { family: FONT_FAMILY, size: 11, weight: '600' }, boxWidth: 12 } },
                        tooltip: { backgroundColor: 'rgba(17, 24, 39, 0.95)' }
                    }
                }
            });

            this.chartInstances.set(canvasId, chart);
        }

        // =====================================================================
        // 6. EVENTS BY TIME (TIMELINE)
        // =====================================================================
        renderEventsByTimeChart(canvasId, data) {
            if (!data || !data.meta?.has_data || !data.timeline || data.timeline.length === 0) {
                this._showInsufficientData(canvasId, 'No chronological event trends available');
                return;
            }

            const ctx = this._getOrCreateCanvas(canvasId);
            if (!ctx) return;

            const labels = data.timeline.map(t => t.label);
            const defects = data.timeline.map(t => t.defects);
            const incidents = data.timeline.map(t => t.incidents);
            const congestion = data.timeline.map(t => t.congestion);

            const chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Road Defects',
                            data: defects,
                            borderColor: '#ef4444',
                            backgroundColor: 'rgba(239, 68, 68, 0.1)',
                            fill: true,
                            tension: 0.35,
                            pointRadius: 3,
                        },
                        {
                            label: 'Safety Incidents',
                            data: incidents,
                            borderColor: '#a855f7',
                            backgroundColor: 'rgba(168, 85, 247, 0.1)',
                            fill: true,
                            tension: 0.35,
                            pointRadius: 3,
                        },
                        {
                            label: 'Congestion Hotspots',
                            data: congestion,
                            borderColor: '#f97316',
                            backgroundColor: 'rgba(249, 115, 22, 0.1)',
                            fill: true,
                            tension: 0.35,
                            pointRadius: 3,
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#9ca3af', font: { family: FONT_FAMILY, size: 10 } } },
                        y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af', font: { family: MONO_FONT, size: 10 } } }
                    },
                    plugins: {
                        legend: { position: 'top', labels: { color: '#e5e7eb', font: { family: FONT_FAMILY, size: 11, weight: '600' }, boxWidth: 12 } },
                        tooltip: { backgroundColor: 'rgba(17, 24, 39, 0.95)' }
                    }
                }
            });

            this.chartInstances.set(canvasId, chart);
        }

        // =====================================================================
        // 7. ROUTE DELAYS (delay = actual_duration - expected_duration)
        // =====================================================================
        renderRouteDelaysChart(canvasId, data) {
            if (!data || !data.meta?.has_data || !data.routes || data.routes.length === 0) {
                this._showInsufficientData(canvasId, 'No route schedule telemetry recorded');
                return;
            }

            const ctx = this._getOrCreateCanvas(canvasId);
            if (!ctx) return;

            const labels = data.routes.map(r => `Route ${r.route_id}`);
            const expected = data.routes.map(r => r.avg_expected_duration_min);
            const actual = data.routes.map(r => r.avg_actual_duration_min);
            const delays = data.routes.map(r => r.avg_delay_minutes);

            const chart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [
                        { label: 'Expected Duration (min)', data: expected, backgroundColor: 'rgba(59, 130, 246, 0.5)', borderColor: '#3b82f6', borderWidth: 1, borderRadius: 4 },
                        { label: 'Actual Duration (min)', data: actual, backgroundColor: 'rgba(239, 68, 68, 0.5)', borderColor: '#ef4444', borderWidth: 1, borderRadius: 4 },
                        { label: 'Schedule Delay (min)', data: delays, backgroundColor: '#f59e0b', borderRadius: 4 },
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { grid: { display: false }, ticks: { color: '#e5e7eb', font: { family: FONT_FAMILY, size: 10, weight: '600' } } },
                        y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af', font: { family: MONO_FONT, size: 10 } } }
                    },
                    plugins: {
                        legend: { position: 'top', labels: { color: '#e5e7eb', font: { family: FONT_FAMILY, size: 11, weight: '600' }, boxWidth: 12 } },
                        tooltip: {
                            backgroundColor: 'rgba(17, 24, 39, 0.95)',
                            callbacks: {
                                footer: (items) => `Formula: delay = actual - expected`
                            }
                        }
                    }
                }
            });

            this.chartInstances.set(canvasId, chart);
        }

        // =====================================================================
        // 8. BUS ACTIVITY & FLEET PRODUCTIVITY
        // =====================================================================
        renderBusActivityChart(canvasId, data) {
            if (!data || !data.meta?.has_data || !data.fleet || data.fleet.length === 0) {
                this._showInsufficientData(canvasId, 'No active bus fleet units reporting');
                return;
            }

            const ctx = this._getOrCreateCanvas(canvasId);
            if (!ctx) return;

            const labels = data.fleet.map(b => b.bus_id);
            const eventsLogged = data.fleet.map(b => b.total_events_logged);
            const measurements = data.fleet.map(b => b.traffic_measurements_taken);
            const trips = data.fleet.map(b => b.trips_completed);

            const chart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [
                        { label: 'Events Detected', data: eventsLogged, backgroundColor: '#a855f7', borderRadius: 4 },
                        { label: 'Traffic Scans', data: measurements, backgroundColor: '#06b6d4', borderRadius: 4 },
                        { label: 'Trips Done', data: trips, backgroundColor: '#10b981', borderRadius: 4 },
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { grid: { display: false }, ticks: { color: '#e5e7eb', font: { family: FONT_FAMILY, size: 10, weight: '700' } } },
                        y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af', font: { family: MONO_FONT, size: 10 } } }
                    },
                    plugins: {
                        legend: { position: 'top', labels: { color: '#e5e7eb', font: { family: FONT_FAMILY, size: 11, weight: '600' }, boxWidth: 12 } },
                        tooltip: { backgroundColor: 'rgba(17, 24, 39, 0.95)' }
                    }
                }
            });

            this.chartInstances.set(canvasId, chart);
        }

        // =====================================================================
        // 9. ROAD DEFECT FREQUENCY (BY BEL SUBTYPE)
        // =====================================================================
        renderRoadDefectsFrequencyChart(canvasId, data) {
            if (!data || !data.meta?.has_data || !data.subtypes || data.total_defects === 0) {
                this._showInsufficientData(canvasId, 'No road defects registered for selected time window');
                return;
            }

            const ctx = this._getOrCreateCanvas(canvasId);
            if (!ctx) return;

            const labels = data.subtypes.map(s => s.display_name);
            const critical = data.subtypes.map(s => s.critical_count);
            const high = data.subtypes.map(s => s.high_count);
            const medium = data.subtypes.map(s => s.medium_count);
            const low = data.subtypes.map(s => s.low_count);

            const chart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [
                        { label: 'Critical', data: critical, backgroundColor: '#dc2626', borderRadius: 4 },
                        { label: 'High', data: high, backgroundColor: '#ea580c', borderRadius: 4 },
                        { label: 'Medium', data: medium, backgroundColor: '#eab308', borderRadius: 4 },
                        { label: 'Low', data: low, backgroundColor: '#10b981', borderRadius: 4 },
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { stacked: true, grid: { display: false }, ticks: { color: '#e5e7eb', font: { family: FONT_FAMILY, size: 10, weight: '600' } } },
                        y: { stacked: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af', font: { family: MONO_FONT, size: 10 } } }
                    },
                    plugins: {
                        legend: { position: 'top', labels: { color: '#e5e7eb', font: { family: FONT_FAMILY, size: 11, weight: '600' }, boxWidth: 12 } },
                        tooltip: { backgroundColor: 'rgba(17, 24, 39, 0.95)' }
                    }
                }
            });

            this.chartInstances.set(canvasId, chart);
        }

        // =====================================================================
        // Legacy Dashboard Helper Methods
        // =====================================================================
        initDefectsChart(canvasId, data = {}) {
            const ctx = this._getOrCreateCanvas(canvasId);
            if (!ctx) return;

            const labels = Object.keys(data).length > 0 ? Object.keys(data) : ['Potholes', 'Damaged Road', 'Waterlogging', 'Missing Divider', 'Damaged Sign'];
            const values = Object.values(data).length > 0 ? Object.values(data) : [12, 8, 4, 3, 2];

            const chart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: labels,
                    datasets: [{
                        data: values,
                        backgroundColor: ['#ef4444', '#f97316', '#06b6d4', '#eab308', '#a855f7'],
                        borderWidth: 1,
                        borderColor: '#111827',
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '68%',
                    plugins: {
                        legend: { position: 'right', labels: { color: '#9ca3af', font: { family: FONT_FAMILY, size: 11, weight: '600' }, boxWidth: 12 } }
                    }
                }
            });

            this.chartInstances.set(canvasId, chart);
        }

        initTrafficChart(canvasId, timelineData = {}) {
            const ctx = this._getOrCreateCanvas(canvasId);
            if (!ctx) return;

            const labels = timelineData.labels || ['06:00', '08:00', '10:00', '12:00', '14:00', '16:00', '18:00', '20:00'];
            const vehicles = timelineData.vehicles || [45, 120, 95, 80, 85, 140, 165, 90];
            const defects = timelineData.defects || [2, 5, 3, 4, 2, 7, 8, 3];

            const chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        { label: 'Vehicle Volume', data: vehicles, borderColor: '#3b82f6', backgroundColor: 'rgba(59, 130, 246, 0.1)', fill: true, tension: 0.4, pointRadius: 3 },
                        { label: 'Defect Events', data: defects, borderColor: '#ef4444', backgroundColor: 'transparent', borderDash: [5, 5], tension: 0.4, pointRadius: 3 }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#6b7280', font: { family: FONT_FAMILY, size: 10 } } },
                        y: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#6b7280', font: { family: FONT_FAMILY, size: 10 } } }
                    },
                    plugins: {
                        legend: { position: 'top', labels: { color: '#9ca3af', font: { size: 11, weight: '600' }, boxWidth: 12 } }
                    }
                }
            });

            this.chartInstances.set(canvasId, chart);
        }

        initIncidentsChart(canvasId, rashCount = 0, hitCount = 0) {
            const ctx = this._getOrCreateCanvas(canvasId);
            if (!ctx) return;

            const chart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: ['Rash Driving Swerves', 'Suspected Collision & Flight'],
                    datasets: [{
                        label: 'Flagged Incident Triggers',
                        data: [rashCount || 3, hitCount || 1],
                        backgroundColor: ['rgba(168, 85, 247, 0.7)', 'rgba(239, 68, 68, 0.7)'],
                        borderColor: ['#c084fc', '#f87171'],
                        borderWidth: 1,
                        borderRadius: 6,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { ticks: { color: '#9ca3af', font: { size: 11, weight: '600' } }, grid: { display: false } },
                        y: { ticks: { color: '#6b7280', stepSize: 1 }, grid: { color: 'rgba(255, 255, 255, 0.05)' } }
                    }
                }
            });

            this.chartInstances.set(canvasId, chart);
        }

        updateDefects(eventsList) {
            const canvasId = 'chart-defects-breakdown';
            const chart = this.chartInstances.get(canvasId);
            if (!eventsList || !chart) return;

            const counts = {};
            eventsList.forEach(e => {
                const type = (e.event_type || 'OTHER').replace(/_/g, ' ');
                counts[type] = (counts[type] || 0) + 1;
            });

            chart.data.labels = Object.keys(counts);
            chart.data.datasets[0].data = Object.values(counts);
            chart.update();
        }
    }

    window.CitySenseCharts = CitySenseCharts;
})();
