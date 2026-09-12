/**
 * CitySense - REST API & WebSocket Communication Layer
 */

(function () {
    class ApiService {
        async get(endpoint, params = {}) {
            const config = window.CONFIG || {};
            const baseUrl = config.API?.BASE || 'http://localhost:8000';
            const rootUrl = baseUrl.startsWith('http') ? baseUrl : window.location.origin;
            const url = new URL(endpoint, rootUrl);
            Object.keys(params).forEach(key => {
                if (params[key] !== undefined && params[key] !== null && params[key] !== '') {
                    url.searchParams.append(key, params[key]);
                }
            });

            try {
                const response = await fetch(url.toString(), {
                    headers: { 'Accept': 'application/json' }
                });
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                return await response.json();
            } catch (error) {
                console.warn(`[API GET Error] ${endpoint}:`, error.message);
                throw error;
            }
        }

        async post(endpoint, data = {}, isFormData = false) {
            try {
                const config = window.CONFIG || {};
                const baseUrl = config.API?.BASE || 'http://localhost:8000';
                const targetUrl = endpoint.startsWith('http') ? endpoint : `${baseUrl}${endpoint}`;
                const options = {
                    method: 'POST',
                };

                if (isFormData) {
                    options.body = data;
                } else {
                    options.headers = {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    };
                    options.body = JSON.stringify(data);
                }

                const response = await fetch(targetUrl, options);
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                return await response.json();
            } catch (error) {
                console.warn(`[API POST Error] ${endpoint}:`, error.message);
                throw error;
            }
        }

        async patch(endpoint, data = {}) {
            try {
                const config = window.CONFIG || {};
                const baseUrl = config.API?.BASE || 'http://localhost:8000';
                const targetUrl = endpoint.startsWith('http') ? endpoint : `${baseUrl}${endpoint}`;
                const options = {
                    method: 'PATCH',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify(data)
                };

                const response = await fetch(targetUrl, options);
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                return await response.json();
            } catch (error) {
                console.warn(`[API PATCH Error] ${endpoint}:`, error.message);
                throw error;
            }
        }

        // Bus Fleet
        async fetchBuses(status = null, routeId = null) {
            return await this.get(window.CONFIG.API.BUSES, { status, route_id: routeId });
        }

        async fetchBusDetail(busId) {
            return await this.get(`${window.CONFIG.API.BUSES}/${busId}`);
        }

        // Urban Events
        async fetchEvents(params = {}) {
            return await this.get(window.CONFIG.API.EVENTS, params);
        }

        async fetchEventDetail(eventId) {
            return await this.get(`${window.CONFIG.API.EVENTS}/${eventId}`);
        }

        async createEvent(eventData) {
            return await this.post(window.CONFIG.API.EVENTS, eventData);
        }

        // Traffic & GIS
        async fetchTraffic(status = null, limit = 50) {
            return await this.get(window.CONFIG.API.TRAFFIC, { status, limit });
        }

        async fetchHeatmap(category = null) {
            return await this.get(window.CONFIG.API.HEATMAP, { category });
        }

        // Video Processing Job
        async submitVideoJob(formData) {
            return await this.post(window.CONFIG.API.PROCESS_VIDEO, formData, true);
        }

        async fetchJobStatus(jobId) {
            return await this.get(`${window.CONFIG.API.PROCESS_VIDEO}/${jobId}`);
        }

        // =====================================================================
        // Urban Analytics Endpoints
        // =====================================================================
        async fetchAnalyticsSummary(params = {}) {
            return await this.get(window.CONFIG.API.ANALYTICS.SUMMARY, params);
        }

        async fetchVehicleCounts(params = {}) {
            return await this.get(window.CONFIG.API.ANALYTICS.VEHICLE_COUNTS, params);
        }

        async fetchTrafficDensity(params = {}) {
            return await this.get(window.CONFIG.API.ANALYTICS.TRAFFIC_DENSITY, params);
        }

        async fetchCongestionHotspots(params = {}) {
            return await this.get(window.CONFIG.API.ANALYTICS.CONGESTION_HOTSPOTS, params);
        }

        async fetchEventsByType(params = {}) {
            return await this.get(window.CONFIG.API.ANALYTICS.EVENTS_BY_TYPE, params);
        }

        async fetchEventsByLocation(params = {}) {
            return await this.get(window.CONFIG.API.ANALYTICS.EVENTS_BY_LOCATION, params);
        }

        async fetchEventsByTime(params = {}) {
            return await this.get(window.CONFIG.API.ANALYTICS.EVENTS_BY_TIME, params);
        }

        async fetchRouteDelays(params = {}) {
            return await this.get(window.CONFIG.API.ANALYTICS.ROUTE_DELAYS, params);
        }

        async fetchBusActivity(params = {}) {
            return await this.get(window.CONFIG.API.ANALYTICS.BUS_ACTIVITY, params);
        }

        async fetchRoadDefectsFrequency(params = {}) {
            return await this.get(window.CONFIG.API.ANALYTICS.ROAD_DEFECTS_FREQUENCY, params);
        }

        async fetchODMatrix(params = {}) {
            return await this.get(window.CONFIG.API.ANALYTICS.OD_MATRIX, params);
        }

        // =====================================================================
        // Edge Processing Metrics
        // =====================================================================
        async fetchEdgeMetrics() {
            return await this.get(window.CONFIG.API.EDGE_METRICS);
        }

        // =====================================================================
        // Incident Management & PDF Reports
        // =====================================================================
        async updateEventStatus(eventId, status) {
            const url = `${window.CONFIG.API.EVENTS}/${eventId}/status`;
            return await this.patch(url, { status });
        }

        getIncidentPdfUrl(eventId) {
            const config = window.CONFIG || {};
            const baseUrl = config.API?.BASE || 'http://localhost:8000';
            const rootUrl = baseUrl.startsWith('http') ? baseUrl : window.location.origin;
            return `${rootUrl}/api/reports/incidents/${eventId}/pdf`;
        }

        getBatchIncidentsPdfUrl(params = {}) {
            const config = window.CONFIG || {};
            const baseUrl = config.API?.BASE || 'http://localhost:8000';
            const rootUrl = baseUrl.startsWith('http') ? baseUrl : window.location.origin;
            const url = new URL('/api/reports/incidents/batch-pdf', rootUrl);
            Object.keys(params).forEach(k => {
                if (params[k] !== undefined && params[k] !== null && params[k] !== '') {
                    url.searchParams.append(k, params[k]);
                }
            });
            return url.toString();
        }
    }

    const api = new ApiService();
    window.api = api;

    /**
     * Robust WebSocket Manager with Auto-Reconnect and Event Dispatch
     */
    class WSClient {
        constructor(url, channelName, onMessageCallback, onStatusCallback) {
            this.url = url;
            this.channelName = channelName;
            this.onMessage = onMessageCallback;
            this.onStatus = onStatusCallback;
            this.ws = null;
            this.reconnectAttempts = 0;
            this.maxReconnectDelay = 10000;
            this.isConnected = false;
            this.connect();
        }

        connect() {
            if (window.location.protocol === 'file:') {
                console.log(`[WS:${this.channelName}] Standalone file mode (simulated telemetry active).`);
                return;
            }
            try {
                this.ws = new WebSocket(this.url);

                this.ws.onopen = () => {
                    console.log(`[WS:${this.channelName}] Connected to ${this.url}`);
                    this.isConnected = true;
                    this.reconnectAttempts = 0;
                    if (this.onStatus) this.onStatus(true, this.channelName);
                };

                this.ws.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        if (this.onMessage) this.onMessage(data);
                    } catch (err) {
                        console.error(`[WS:${this.channelName}] Parse error:`, err);
                    }
                };

                this.ws.onerror = (err) => {
                    // Suppress excessive error noise if backend is not started yet
                };

                this.ws.onclose = () => {
                    this.isConnected = false;
                    if (this.onStatus) this.onStatus(false, this.channelName);
                    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), this.maxReconnectDelay);
                    this.reconnectAttempts++;
                    setTimeout(() => this.connect(), delay);
                };
            } catch (err) {
                // Connection exception handling
            }
        }

        send(data) {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(typeof data === 'string' ? data : JSON.stringify(data));
            }
        }
    }

    window.WSClient = WSClient;
})();

