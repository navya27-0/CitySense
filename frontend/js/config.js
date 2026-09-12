/**
 * CitySense - Dashboard Configuration & Global Constants
 */

(function () {
    const getBaseUrl = () => {
        if (window.location.protocol === 'file:' || !window.location.origin || window.location.origin === 'null') {
            return 'http://localhost:8000';
        }
        if (window.location.port && window.location.port !== '8000') {
            return `http://${window.location.hostname || 'localhost'}:8000`;
        }
        return window.location.origin;
    };

    const getWsUrl = (path) => {
        if (window.location.protocol === 'file:' || !window.location.host || window.location.origin === 'null') {
            return `ws://localhost:8000${path}`;
        }
        const host = (window.location.port && window.location.port !== '8000')
            ? `${window.location.hostname || 'localhost'}:8000`
            : window.location.host;
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${host}${path}`;
    };

    const CONFIG = {
        APP_NAME: 'CitySense',
        CITY_NAME: 'Hyderabad Metropolitan Region',
        DEFAULT_COORDINATES: [17.385044, 78.486671], // Hyderabad Center
        DEFAULT_ZOOM: 13,
        
        // API Endpoints
        API: {
            BASE: getBaseUrl(),
            EVENTS: '/api/events',
            BUSES: '/api/buses',
            TRAFFIC: '/api/traffic',
            HEATMAP: '/api/heatmap',
            TELEMETRY: '/api/telemetry',
            PROCESS_VIDEO: '/api/process-video',
            ANALYTICS: {
                SUMMARY: '/api/analytics/summary',
                VEHICLE_COUNTS: '/api/analytics/vehicle-counts',
                TRAFFIC_DENSITY: '/api/analytics/traffic-density',
                CONGESTION_HOTSPOTS: '/api/analytics/congestion-hotspots',
                EVENTS_BY_TYPE: '/api/analytics/events-by-type',
                EVENTS_BY_LOCATION: '/api/analytics/events-by-location',
                EVENTS_BY_TIME: '/api/analytics/events-by-time',
                ROUTE_DELAYS: '/api/analytics/route-delays',
                BUS_ACTIVITY: '/api/analytics/bus-activity',
                ROAD_DEFECTS_FREQUENCY: '/api/analytics/road-defects-frequency',
                OD_MATRIX: '/api/analytics/od-matrix',
            },
            REPORTS: {
                SINGLE_INCIDENT_PDF: (id) => `/api/reports/incidents/${id}/pdf`,
                BATCH_INCIDENTS_PDF: '/api/reports/incidents/batch-pdf',
                STATUS_UPDATE: (id) => `/api/events/${id}/status`,
            },
            EDGE_METRICS: '/api/edge-metrics',
        },

        // WebSocket Endpoints
        WS: {
            EVENTS: getWsUrl('/ws/events'),
            BUSES: getWsUrl('/ws/buses'),
            GENERAL: getWsUrl('/ws'),
        },

        // Color Code Palette
        COLORS: {
            BUS: '#3b82f6',       // BLUE
            DEFECT: '#ef4444',    // RED
            TRAFFIC: '#f97316',   // ORANGE
            INCIDENT: '#a855f7',  // PURPLE
            ONLINE: '#10b981',
            OFFLINE: '#ef4444',
        },

        // Status definitions
        STATUSES: {
            NEW: { label: 'NEW', color: '#ef4444', bg: 'rgba(239, 68, 68, 0.2)' },
            UNDER_REVIEW: { label: 'UNDER REVIEW', color: '#3b82f6', bg: 'rgba(59, 130, 246, 0.2)' },
            RESOLVED: { label: 'RESOLVED', color: '#10b981', bg: 'rgba(16, 185, 129, 0.2)' },
            FALSE_POSITIVE: { label: 'FALSE POSITIVE', color: '#94a3b8', bg: 'rgba(148, 163, 184, 0.2)' },
        },

        // Polling interval in ms (fallback if WebSockets disconnect)
        POLL_INTERVAL_MS: 5000,

        // Severity mapping
        SEVERITY: {
            LOW: { label: 'LOW', color: '#10b981', bg: 'rgba(16, 185, 129, 0.15)' },
            MEDIUM: { label: 'MEDIUM', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.15)' },
            HIGH: { label: 'HIGH', color: '#ef4444', bg: 'rgba(239, 68, 68, 0.15)' },
            CRITICAL: { label: 'CRITICAL', color: '#dc2626', bg: 'rgba(220, 38, 38, 0.25)' },
        }
    };

    window.CONFIG = CONFIG;
})();

