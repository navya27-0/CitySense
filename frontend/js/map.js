/**
 * CitySense - Leaflet GIS Engine & Spatial Visualization Layer
 * Production-ready GIS Layer with Clustering, Defect Subtyping, Route Polylines,
 * Dynamic Traffic Heatmaps, Road Condition Overlays, and Multi-Criteria Filtering.
 */

(function () {
    // Standard Hyderabad Transit Route Geometry
    const TRANSIT_ROUTES = [
        {
            id: '216',
            name: 'Route 216 (Mehdipatnam -> Hitec City / Cyber Towers)',
            color: '#38bdf8',
            waypoints: [
                { name: 'Mehdipatnam Bus Terminal', coords: [17.3916, 78.4350], isStop: true },
                { name: 'Tolichowki Flyover', coords: [17.3995, 78.4110], isStop: true },
                { name: 'Shaikpet Dargah', coords: [17.4080, 78.3880], isStop: true },
                { name: 'Gachibowli ORR Junction', coords: [17.4400, 78.3489], isStop: true },
                { name: 'Mindspace Junction', coords: [17.4440, 78.3810], isStop: true },
                { name: 'Cyber Towers / Hitec City', coords: [17.4504, 78.3808], isStop: true }
            ]
        },
        {
            id: '10',
            name: 'Route 10 (Secunderabad Station -> Charminar)',
            color: '#34d399',
            waypoints: [
                { name: 'Secunderabad Railway Station', coords: [17.4340, 78.5015], isStop: true },
                { name: 'Ranigunj / Minister Road', coords: [17.4265, 78.4900], isStop: true },
                { name: 'Tank Bund / Hussain Sagar', coords: [17.4180, 78.4800], isStop: true },
                { name: 'Secretariat / Telugu Thalli', coords: [17.4060, 78.4720], isStop: true },
                { name: 'Abids / GPO', coords: [17.3900, 78.4750], isStop: true },
                { name: 'Afzal Gunj / Nayapul', coords: [17.3750, 78.4770], isStop: true },
                { name: 'Charminar Bus Station', coords: [17.3616, 78.4747], isStop: true }
            ]
        },
        {
            id: '49M',
            name: 'Route 49M (Dilsukhnagar -> Jubilee Hills Checkpost)',
            color: '#a78bfa',
            waypoints: [
                { name: 'Dilsukhnagar Bus Depot', coords: [17.3688, 78.5247], isStop: true },
                { name: 'Malakpet Station', coords: [17.3780, 78.4980], isStop: true },
                { name: 'Koti Center', coords: [17.3850, 78.4867], isStop: true },
                { name: 'Nampally Station', coords: [17.3920, 78.4680], isStop: true },
                { name: 'Punjagutta Flyover', coords: [17.4260, 78.4520], isStop: true },
                { name: 'Jubilee Hills Checkpost', coords: [17.4310, 78.4070], isStop: true }
            ]
        }
    ];

    class GisMapEngine {
        constructor(elementId, onEventSelect) {
            this.elementId = elementId;
            this.onEventSelect = onEventSelect;
            this.map = null;

            // Raw storage
            this.allBuses = [];
            this.allEvents = [];
            this.rawHeatmapData = [];

            // Active filters
            this.activeFilters = {
                eventType: 'ALL',
                severity: 'ALL',
                busId: 'ALL',
                routeId: 'ALL',
                timeRange: 'ALL'
            };

            // Marker storage
            this.busMarkers = new Map();     // busId -> L.Marker
            this.eventMarkers = new Map();   // eventId -> L.Marker

            // Layer Groups & Clusters
            this.layers = {
                buses: null,
                defectsCluster: null,
                traffic: null,
                incidents: null,
                routes: null,
                heat: null,
                roadCondition: null,
            };

            this.visibleLayers = {
                buses: true,
                defects: true,
                traffic: true,
                incidents: true,
                routes: true,
                heat: false,
                roadCondition: false,
            };

            this.init();
        }

        init() {
            const config = window.CONFIG || {};
            const center = config.DEFAULT_COORDINATES || [17.385044, 78.486671];
            const zoom = config.DEFAULT_ZOOM || 13;

            // 1. Initialize Leaflet Map
            this.map = L.map(this.elementId, {
                center: center,
                zoom: zoom,
                zoomControl: true,
                attributionControl: false,
            });

            // 2. High-performance CartoDB Positron Light Basemap (clean, no watermark, no API key)
            L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
                maxZoom: 19,
                subdomains: 'abcd',
            }).addTo(this.map);

            // 3. Initialize Layer Groups
            this.layers.buses = L.layerGroup().addTo(this.map);
            this.layers.traffic = L.layerGroup().addTo(this.map);
            this.layers.incidents = L.layerGroup().addTo(this.map);
            this.layers.routes = L.layerGroup().addTo(this.map);
            this.layers.roadCondition = L.layerGroup();

            // 4. Initialize Marker Cluster Group for Defects
            if (typeof L.markerClusterGroup === 'function') {
                this.layers.defectsCluster = L.markerClusterGroup({
                    chunkedLoading: true,
                    maxClusterRadius: 45,
                    spiderfyOnMaxZoom: true,
                    showCoverageOnHover: false,
                    zoomToBoundsOnClick: true,
                    iconCreateFunction: (cluster) => {
                        const count = cluster.getChildCount();
                        let sizeClass = 'marker-cluster-small';
                        if (count > 10) sizeClass = 'marker-cluster-medium';
                        if (count > 25) sizeClass = 'marker-cluster-large';

                        return L.divIcon({
                            html: `<div><span>${count}</span></div>`,
                            className: `marker-cluster ${sizeClass}`,
                            iconSize: L.point(40, 40)
                        });
                    }
                }).addTo(this.map);
            } else {
                this.layers.defectsCluster = L.layerGroup().addTo(this.map);
            }

            // 5. Initialize Heatmap Layer
            if (typeof L.heatLayer === 'function') {
                this.layers.heat = L.heatLayer([], {
                    radius: 26,
                    blur: 16,
                    maxZoom: 17,
                    max: 4.0,
                    gradient: {
                        0.2: '#10b981', // Green (Low density)
                        0.4: '#eab308', // Yellow (Medium density)
                        0.7: '#f97316', // Orange (High congestion)
                        1.0: '#ef4444'  // Red (Severe bottleneck)
                    }
                });
            }

            // 6. Draw Transit Routes on Map
            this.renderRoutePaths();
        }

        // =====================================================================
        // TRANSIT ROUTE PATHS
        // =====================================================================
        renderRoutePaths() {
            this.layers.routes.clearLayers();

            TRANSIT_ROUTES.forEach(route => {
                const latLngs = route.waypoints.map(wp => wp.coords);

                // Draw Corridor Polyline
                const polyline = L.polyline(latLngs, {
                    color: route.color,
                    weight: 4,
                    opacity: 0.75,
                    smoothFactor: 1.0,
                    dashArray: '8, 6'
                });

                polyline.bindTooltip(`<strong>${route.name}</strong>`, { sticky: true, className: 'route-tooltip' });
                polyline.addTo(this.layers.routes);

                // Add Waypoint Station Markers
                route.waypoints.forEach(wp => {
                    const circle = L.circleMarker(wp.coords, {
                        radius: 5,
                        fillColor: '#ffffff',
                        color: route.color,
                        weight: 2,
                        opacity: 1,
                        fillOpacity: 0.9
                    });
                    circle.bindTooltip(`<strong>${wp.name}</strong> (${route.id})`, { direction: 'top' });
                    circle.addTo(this.layers.routes);
                });
            });
        }

        // =====================================================================
        // CUSTOM SVG MARKER FACTORIES
        // =====================================================================
        _createBusIcon(heading = 0) {
            return L.divIcon({
                className: 'custom-map-marker marker-bus',
                html: `
                    <svg class="marker-icon-svg" viewBox="0 0 24 24" style="transform: rotate(${heading}deg);">
                        <path d="M4 16c0 .88.39 1.67 1 2.22V20c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h8v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1.78c.61-.55 1-1.34 1-2.22V6c0-3.5-3.58-4-8-4s-8 .5-8 4v10zm3.5 1c-.83 0-1.5-.67-1.5-1.5S6.67 14 7.5 14s1.5.67 1.5 1.5S8.33 17 7.5 17zm9 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm1.5-6H6V6h12v5z"/>
                    </svg>
                `,
                iconSize: [34, 34],
                iconAnchor: [17, 17],
            });
        }

        _createSubtypeDefectIcon(subtype = 'POTHOLE') {
            const st = (subtype || 'POTHOLE').toUpperCase();
            let subClass = 'marker-defect-pothole';
            let svgPath = '<path d="M12 2L1 21h22L12 2zm0 3.99L19.53 19H4.47L12 5.99zM11 10h2v4h-2zm0 6h2v2h-2z"/>';

            if (st.includes('POTHOLE')) {
                subClass = 'marker-defect-pothole';
                svgPath = '<circle cx="12" cy="12" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 9v3l2 2"/>';
            } else if (st.includes('DAMAGED_ROAD') || st.includes('CRACK')) {
                subClass = 'marker-defect-damaged_road';
                svgPath = '<path d="M4 20h16L15 4l-4 7-3-4-4 13z"/>';
            } else if (st.includes('WATERLOG') || st.includes('FLOOD')) {
                subClass = 'marker-defect-waterlogging';
                svgPath = '<path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/>';
            } else if (st.includes('DIVIDER') || st.includes('BARRIER')) {
                subClass = 'marker-defect-missing_divider';
                svgPath = '<rect x="4" y="8" width="16" height="8" rx="2"/><line x1="8" y1="4" x2="8" y2="20"/><line x1="16" y1="4" x2="16" y2="20"/>';
            } else if (st.includes('SIGN') || st.includes('BOARD')) {
                subClass = 'marker-defect-damaged_signboard';
                svgPath = '<polygon points="12 2 2 22 22 22 12 2"/><line x1="12" y1="11" x2="12" y2="15"/><circle cx="12" cy="18" r="1"/>';
            }

            return L.divIcon({
                className: `custom-map-marker marker-defect ${subClass}`,
                html: `<svg class="marker-icon-svg" viewBox="0 0 24 24">${svgPath}</svg>`,
                iconSize: [32, 32],
                iconAnchor: [16, 16],
            });
        }

        _createTrafficIcon() {
            return L.divIcon({
                className: 'custom-map-marker marker-traffic',
                html: `
                    <svg class="marker-icon-svg" viewBox="0 0 24 24">
                        <path d="M12 4c-4.41 0-8 3.59-8 8 0 1.82.62 3.49 1.64 4.83L12 21.5l6.36-4.67C19.38 15.49 20 13.82 20 12c0-4.41-3.59-8-8-8zm0 11c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3z"/>
                    </svg>
                `,
                iconSize: [30, 30],
                iconAnchor: [15, 15],
            });
        }

        _createIncidentIcon() {
            return L.divIcon({
                className: 'custom-map-marker marker-incident',
                html: `
                    <svg class="marker-icon-svg" viewBox="0 0 24 24">
                        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
                    </svg>
                `,
                iconSize: [34, 34],
                iconAnchor: [17, 17],
            });
        }

        // =====================================================================
        // POPUP GENERATORS
        // =====================================================================
        _buildEventPopup(event) {
            const config = window.CONFIG || {};
            const sevColor = config.SEVERITY?.[event.severity?.toUpperCase()]?.color || '#9ca3af';
            const sevBg = config.SEVERITY?.[event.severity?.toUpperCase()]?.bg || 'rgba(255,255,255,0.1)';
            const formattedTime = new Date(event.timestamp || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

            return `
                <div class="map-popup-card">
                    <div class="map-popup-header">
                        <span class="map-popup-title">
                            <span style="color:${sevColor}">●</span> ${(event.event_type || 'Urban Event').replace(/_/g, ' ')}
                        </span>
                        <span style="background:${sevBg}; color:${sevColor}; font-size:10px; font-weight:700; padding:2px 6px; border-radius:4px;">
                            ${event.severity?.toUpperCase() || 'INFO'}
                        </span>
                    </div>
                    <div class="map-popup-body">
                        <div class="map-popup-row"><span>Assigned Bus:</span> <strong style="color:var(--color-bus);">${event.bus_id || 'BUS_101'}</strong></div>
                        <div class="map-popup-row"><span>Route:</span> <strong>Route ${event.route_id || '216'}</strong></div>
                        <div class="map-popup-row"><span>AI Confidence:</span> <strong style="color:var(--color-success);">${Math.round((event.confidence || 0.9) * 100)}%</strong></div>
                        <div class="map-popup-row"><span>Coordinates:</span> <strong>${Number(event.latitude).toFixed(5)}, ${Number(event.longitude).toFixed(5)}</strong></div>
                        <div class="map-popup-row"><span>Detected At:</span> <strong>${formattedTime}</strong></div>
                        <div class="map-popup-disclaimer">
                            ${event.disclaimer || 'prototype heuristic estimation — rule-based detection, not forensic determination'}
                        </div>
                    </div>
                    <div class="map-popup-footer">
                        <button class="map-popup-btn" onclick="window.CitySenseApp.inspectEvent('${event.event_id}')">View Full Details</button>
                    </div>
                </div>
            `;
        }

        _buildBusPopup(bus) {
            const formattedTime = new Date(bus.last_seen || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            return `
                <div class="map-popup-card">
                    <div class="map-popup-header">
                        <span class="map-popup-title" style="color:var(--color-bus)">
                            🚍 ${bus.bus_id}
                        </span>
                        <span style="background:rgba(16,185,129,0.15); color:var(--color-success); font-size:10px; font-weight:700; padding:2px 6px; border-radius:4px;">
                            ${bus.status?.toUpperCase() || 'ACTIVE'}
                        </span>
                    </div>
                    <div class="map-popup-body">
                        <div class="map-popup-row"><span>Route:</span> <strong>Route ${bus.route_id || '216'}</strong></div>
                        <div class="map-popup-row"><span>Speed:</span> <strong>${Math.round(bus.speed || 0)} km/h</strong></div>
                        <div class="map-popup-row"><span>Heading:</span> <strong>${Math.round(bus.heading || 0)}°</strong></div>
                        <div class="map-popup-row"><span>Last Signal:</span> <strong>${formattedTime}</strong></div>
                        <div class="map-popup-row"><span>Coordinates:</span> <strong>${Number(bus.latitude).toFixed(5)}, ${Number(bus.longitude).toFixed(5)}</strong></div>
                    </div>
                    <div class="map-popup-footer">
                        <button class="map-popup-btn" onclick="window.CitySenseApp.selectBus('${bus.bus_id}')">Select in Fleet</button>
                    </div>
                </div>
            `;
        }

        // =====================================================================
        // UPDATERS & RENDERERS
        // =====================================================================
        updateBuses(busesList) {
            if (!busesList || !Array.isArray(busesList)) return;
            this.allBuses = busesList;

            const currentBusIds = new Set();

            busesList.forEach(bus => {
                if (!bus.latitude || !bus.longitude) return;
                currentBusIds.add(bus.bus_id);

                if (this.busMarkers.has(bus.bus_id)) {
                    const marker = this.busMarkers.get(bus.bus_id);
                    marker.setLatLng([bus.latitude, bus.longitude]);
                    marker.setIcon(this._createBusIcon(bus.heading || 0));
                    marker.setPopupContent(this._buildBusPopup(bus));
                } else {
                    const marker = L.marker([bus.latitude, bus.longitude], {
                        icon: this._createBusIcon(bus.heading || 0),
                        title: `Bus ${bus.bus_id}`,
                        zIndexOffset: 1000,
                    });
                    marker.bindPopup(this._buildBusPopup(bus));
                    marker.addTo(this.layers.buses);
                    this.busMarkers.set(bus.bus_id, marker);
                }
            });

            // Cleanup stale buses
            for (const [busId, marker] of this.busMarkers.entries()) {
                if (!currentBusIds.has(busId)) {
                    this.layers.buses.removeLayer(marker);
                    this.busMarkers.delete(busId);
                }
            }
        }

        updateEvents(eventsList) {
            if (!eventsList || !Array.isArray(eventsList)) return;
            this.allEvents = eventsList;
            this.renderFilteredEvents();
            this.renderRoadConditionLayer();
        }

        addLiveEvent(event) {
            this.allEvents.unshift(event);
            if (this.allEvents.length > 300) this.allEvents.pop();
            this.renderFilteredEvents();
            this.renderRoadConditionLayer();
        }

        // =====================================================================
        // MULTI-CRITERIA FILTERING
        // =====================================================================
        applyFilters(filters = {}) {
            this.activeFilters = { ...this.activeFilters, ...filters };
            this.renderFilteredEvents();
        }

        renderFilteredEvents() {
            // Clear current markers from clusters and layers
            if (this.layers.defectsCluster) this.layers.defectsCluster.clearLayers();
            if (this.layers.traffic) this.layers.traffic.clearLayers();
            if (this.layers.incidents) this.layers.incidents.clearLayers();
            this.eventMarkers.clear();

            const f = this.activeFilters;
            const now = Date.now();

            const filtered = this.allEvents.filter(event => {
                if (!event.latitude || !event.longitude) return false;

                // 1. Filter by Event Type
                if (f.eventType !== 'ALL') {
                    const type = (event.event_type || '').toUpperCase();
                    if (f.eventType === 'HIGH_CONGESTION') {
                        if (!type.includes('CONGESTION') && !type.includes('HIGH') && event.event_category !== 'TRAFFIC_DENSITY') return false;
                    } else if (type !== f.eventType) {
                        return false;
                    }
                }

                // 2. Filter by Severity
                if (f.severity !== 'ALL') {
                    if ((event.severity || '').toUpperCase() !== f.severity.toUpperCase()) return false;
                }

                // 3. Filter by Bus ID
                if (f.busId !== 'ALL') {
                    if (event.bus_id !== f.busId) return false;
                }

                // 4. Filter by Route ID (Strict matching)
                if (f.routeId !== 'ALL') {
                    const eventRoute = String(event.route_id || '').replace(/^route\s*/i, '').trim().toUpperCase();
                    const targetRoute = String(f.routeId).replace(/^route\s*/i, '').trim().toUpperCase();
                    if (eventRoute !== targetRoute) return false;
                }

                // 5. Filter by Time Range
                if (f.timeRange !== 'ALL') {
                    const eventTime = new Date(event.timestamp || now).getTime();
                    const diffMs = now - eventTime;
                    if (f.timeRange === '1h' && diffMs > 3600 * 1000) return false;
                    if (f.timeRange === '6h' && diffMs > 6 * 3600 * 1000) return false;
                    if (f.timeRange === '24h' && diffMs > 24 * 3600 * 1000) return false;
                    if (f.timeRange === '7d' && diffMs > 7 * 24 * 3600 * 1000) return false;
                    if (f.timeRange === '30d' && diffMs > 30 * 24 * 3600 * 1000) return false;
                    if (f.timeRange === 'today') {
                        const eventDate = new Date(event.timestamp || now).toDateString();
                        if (eventDate !== new Date().toDateString()) return false;
                    }
                }

                return true;
            });

            // Populate Layers & Clusters
            filtered.forEach(event => {
                const eventId = event.event_id;
                const category = (event.event_category || '').toUpperCase();
                const type = (event.event_type || '').toUpperCase();

                // 1. PURPLE: Safety Incidents
                if (category === 'TRAFFIC_INCIDENT' || type.includes('RASH') || type.includes('HIT_AND_RUN')) {
                    const marker = L.marker([event.latitude, event.longitude], {
                        icon: this._createIncidentIcon(),
                        zIndexOffset: 900,
                    });
                    marker.bindPopup(this._buildEventPopup(event));
                    marker.addTo(this.layers.incidents);
                    this.eventMarkers.set(eventId, marker);
                }
                // 2. ORANGE: Traffic Hotspots
                else if (category === 'TRAFFIC_DENSITY' || type.includes('CONGESTION') || type === 'HIGH') {
                    const marker = L.marker([event.latitude, event.longitude], {
                        icon: this._createTrafficIcon(),
                        zIndexOffset: 800,
                    });
                    marker.bindPopup(this._buildEventPopup(event));
                    marker.addTo(this.layers.traffic);
                    this.eventMarkers.set(eventId, marker);
                }
                // 3. SUBTYPE-CODED ROAD DEFECTS (Clustered)
                else {
                    const marker = L.marker([event.latitude, event.longitude], {
                        icon: this._createSubtypeDefectIcon(event.event_type),
                        zIndexOffset: 700,
                    });
                    marker.bindPopup(this._buildEventPopup(event));
                    
                    if (this.layers.defectsCluster) {
                        this.layers.defectsCluster.addLayer(marker);
                    }
                    this.eventMarkers.set(eventId, marker);
                }
            });
        }

        // =====================================================================
        // TRAFFIC HEATMAP FROM BACKEND DATA
        // =====================================================================
        updateHeatmap(heatmapData) {
            if (!this.layers.heat || !heatmapData) return;
            this.rawHeatmapData = Array.isArray(heatmapData) ? heatmapData : (heatmapData.points || []);

            const heatPoints = this.rawHeatmapData.map(pt => {
                const lat = pt.latitude || pt[0];
                const lon = pt.longitude || pt[1];
                let weight = pt.weight !== undefined ? pt.weight : 2.0;
                return [lat, lon, weight];
            }).filter(pt => pt[0] && pt[1]);

            if (typeof this.layers.heat.setLatLngs === 'function') {
                this.layers.heat.setLatLngs(heatPoints);
            }
        }

        // =====================================================================
        // ROAD CONDITION QUALITY OVERLAY
        // =====================================================================
        renderRoadConditionLayer() {
            if (!this.layers.roadCondition) return;
            this.layers.roadCondition.clearLayers();

            const defectEvents = this.allEvents.filter(e => {
                const cat = (e.event_category || '').toUpperCase();
                return cat === 'ROAD_DEFECT' || (!cat.includes('INCIDENT') && !cat.includes('TRAFFIC'));
            });

            defectEvents.forEach(defect => {
                const sev = (defect.severity || 'HIGH').toUpperCase();
                let color = '#ef4444';
                let radius = 45;
                if (sev === 'CRITICAL') { color = '#dc2626'; radius = 60; }
                else if (sev === 'HIGH') { color = '#f97316'; radius = 45; }
                else if (sev === 'MEDIUM') { color = '#eab308'; radius = 35; }
                else { color = '#10b981'; radius = 25; }

                const circle = L.circle([defect.latitude, defect.longitude], {
                    radius: radius,
                    color: color,
                    fillColor: color,
                    fillOpacity: 0.25,
                    weight: 1,
                    dashArray: '4, 4'
                });

                circle.bindTooltip(`<strong>Road Defect Zone</strong>: ${(defect.event_type || 'Defect').replace(/_/g, ' ')} (${sev})`, { direction: 'top' });
                circle.addTo(this.layers.roadCondition);
            });
        }

        // =====================================================================
        // LAYER VISIBILITY TOGGLES
        // =====================================================================
        toggleLayer(layerKey, isVisible) {
            this.visibleLayers[layerKey] = isVisible;

            let targetLayer = null;
            if (layerKey === 'buses') targetLayer = this.layers.buses;
            if (layerKey === 'defects') targetLayer = this.layers.defectsCluster;
            if (layerKey === 'traffic') targetLayer = this.layers.traffic;
            if (layerKey === 'incidents') targetLayer = this.layers.incidents;
            if (layerKey === 'routes') targetLayer = this.layers.routes;
            if (layerKey === 'heat') targetLayer = this.layers.heat;
            if (layerKey === 'roadCondition') targetLayer = this.layers.roadCondition;

            if (!targetLayer) return;

            if (isVisible) {
                if (!this.map.hasLayer(targetLayer)) this.map.addLayer(targetLayer);
            } else {
                if (this.map.hasLayer(targetLayer)) this.map.removeLayer(targetLayer);
            }
        }

        panTo(lat, lon, zoom = 15) {
            this.map.setView([lat, lon], zoom, { animate: true, duration: 0.8 });
        }

        focusBus(busId) {
            const bus = this.allBuses.find(b => b.bus_id === busId);
            if (!bus || !bus.latitude || !bus.longitude) return;

            if (this.map) {
                this.map.invalidateSize();
                this.map.setView([bus.latitude, bus.longitude], 16, { animate: true, duration: 0.8 });
            }

            const marker = this.busMarkers.get(busId);
            if (marker) {
                setTimeout(() => {
                    marker.openPopup();
                }, 350);
            }
        }

        fitBoundsToFleet() {
            const allPoints = [];
            this.busMarkers.forEach(m => allPoints.push(m.getLatLng()));
            this.eventMarkers.forEach(m => allPoints.push(m.getLatLng()));

            if (allPoints.length > 0) {
                const bounds = L.latLngBounds(allPoints);
                this.map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
            }
        }
    }

    window.GisMapEngine = GisMapEngine;
})();


