const API_URL = 'http://localhost:8000';

// Initialize map
let map = L.map('map').setView([42.0, -83.0], 8);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors'
}).addTo(map);

// Global variables
let currentPathLayer = null;
let allPlanes = [];
let liveMarkers = {};
let livePlaneCache = {};
let liveTrails = {};

function getSessionBounds(icao, callsign) {
    const matches = allPlanes.filter(plane =>
        plane.icao === icao && (plane.callsign || '') === (callsign || '')
    );

    if (matches.length === 0) {
        return { startTime: null, endTime: null };
    }

    matches.sort((a, b) => new Date(b.session_end) - new Date(a.session_end));
    return {
        startTime: matches[0].session_start,
        endTime: matches[0].session_end
    };
}

function focusLivePlane(plane) {
    if (!plane || !plane.icao) return false;

    const marker = liveMarkers[plane.icao];
    const lat = plane.lat ? parseFloat(plane.lat) : null;
    const lon = plane.lon ? parseFloat(plane.lon) : null;

    if (marker) {
        map.flyTo(marker.getLatLng(), Math.max(map.getZoom(), 9));
        marker.openPopup();
        return true;
    }

    if (lat === null || lon === null || Number.isNaN(lat) || Number.isNaN(lon)) {
        return false;
    }

    const markerHeading = plane.heading;
    const fallbackMarker = L.marker([lat, lon], { icon: getPlaneIcon(markerHeading) }).addTo(map);
    fallbackMarker.bindPopup(`
        <b>${plane.callsign || plane.icao}</b><br>
        Alt: ${plane.altitude || '---'} ft<br>
        Speed: ${plane.speed || '---'} kt<br>
        Heading: ${markerHeading || '---'}°
    `);
    liveMarkers[plane.icao] = fallbackMarker;
    map.flyTo([lat, lon], Math.max(map.getZoom(), 9));
    fallbackMarker.openPopup();
    return true;
}

// Create rotating airplane icon
function getPlaneIcon(heading) {
    const rotation = heading ? `transform: rotate(${parseFloat(heading)}deg);` : '';
    return L.divIcon({
        html: `<div style="font-size: 24px; ${rotation} display: inline-block; filter: drop-shadow(2px 2px 2px rgba(0,0,0,0.5));">✈️</div>`,
        iconSize: [24, 24],
        className: 'plane-marker'
    });
}

// Function to update trail for a live plane
function updateLiveTrail(icao, lat, lon) {
    if (!liveTrails[icao]) {
        liveTrails[icao] = [];
    }

    // Add new position
    liveTrails[icao].push({ lat, lon, timestamp: Date.now() });

    // Keep only last 5 positions
    if (liveTrails[icao].length > 5) {
        liveTrails[icao].shift();
    }

    // Remove old trail layer if exists
    if (liveTrails[icao].layer) {
        map.removeLayer(liveTrails[icao].layer);
    }

    // Draw new trail (only if we have at least 2 points)
    if (liveTrails[icao].length >= 2) {
        const trailPoints = liveTrails[icao].map(p => [p.lat, p.lon]);
        liveTrails[icao].layer = L.polyline(trailPoints, {
            color: '#00ffaa',
            weight: 3,
            opacity: 0.7,
            dashArray: '5, 5'
        }).addTo(map);
    }
}

// Show FULL historical path for a live plane (from database)
async function showLivePlanePath(icao, callsign) {
    try {
        // Get the most recent session for this aircraft
        const matches = allPlanes.filter(plane => plane.icao === icao);
        if (matches.length === 0) {
            console.log('No historical data for this plane yet');
            return;
        }

        // Use the most recent session
        matches.sort((a, b) => new Date(b.session_end) - new Date(a.session_end));
        const latestSession = matches[0];

        // Fetch trips for this session
        const params = new URLSearchParams();
        if (latestSession.session_start) params.set('start_time', latestSession.session_start);
        if (latestSession.session_end) params.set('end_time', latestSession.session_end);

        const response = await fetch(`${API_URL}/api/plane/${icao}/trips${params.toString() ? `?${params.toString()}` : ''}`);
        const trips = await response.json();

        if (trips.length === 0) {
            console.log('No trips found for this plane');
            return;
        }

        // Get the most recent trip
        const latestTrip = trips[0];

        // Fetch the full path for that trip
        const pathResponse = await fetch(`${API_URL}/api/trip/${icao}/${latestTrip.trip_id}${params.toString() ? `?${params.toString()}` : ''}`);
        const points = await pathResponse.json();

        if (points.length === 0) return;

        // Remove any existing path layer
        if (currentPathLayer) {
            map.removeLayer(currentPathLayer);
        }

        // Create new path layer with altitude coloring
        currentPathLayer = L.featureGroup().addTo(map);
        const latlngs = points.map(p => [p.lat, p.lon]);

        for (let i = 0; i < points.length - 1; i++) {
            const p1 = points[i];
            const p2 = points[i + 1];
            if (!p1.altitude || !p2.altitude) continue;

            const avgAlt = (p1.altitude + p2.altitude) / 2;
            let color;
            if (avgAlt < 10000) color = '#00ff00';
            else if (avgAlt < 25000) color = '#ffff00';
            else color = '#ff4444';

            const segment = L.polyline([[p1.lat, p1.lon], [p2.lat, p2.lon]], {
                color: color,
                weight: 3
            });
            currentPathLayer.addLayer(segment);
        }

        // Add start and end markers
        const start = points[0];
        const end = points[points.length - 1];
        currentPathLayer.addLayer(L.marker([start.lat, start.lon]).bindPopup('Start'));
        currentPathLayer.addLayer(L.marker([end.lat, end.lon]).bindPopup('End'));

        // Auto-zoom to fit the path
        map.fitBounds(latlngs);

        // Also show the trips panel so user can see trip details
        document.getElementById('selected-aircraft').textContent = `${latestSession.callsign || icao} - Recent Trip`;
        document.getElementById('trips-panel').classList.remove('hidden');
        displayTrips(trips, icao, latestSession.session_start, latestSession.session_end);

    } catch (error) {
        console.error('Error showing live plane path:', error);
    }
}

// Update live planes on map
async function updateLiveMap() {
    try {
        const res = await fetch(`${API_URL}/api/live-direct`);
        const livePlanes = await res.json();
        livePlaneCache = Object.fromEntries(livePlanes.map(plane => [plane.icao, plane]));

        // Remove markers and trails for planes no longer live
        const currentIcaos = new Set(livePlanes.map(p => p.icao));
        for (let icao in liveMarkers) {
            if (!currentIcaos.has(icao)) {
                map.removeLayer(liveMarkers[icao]);
                delete liveMarkers[icao];
                // Also remove trail
                if (liveTrails[icao] && liveTrails[icao].layer) {
                    map.removeLayer(liveTrails[icao].layer);
                }
                delete liveTrails[icao];
            }
        }

        // Add/update markers for live planes with position
        livePlanes.forEach(plane => {
            if (plane.lat && plane.lon) {
                const lat = parseFloat(plane.lat);
                const lon = parseFloat(plane.lon);
                const heading = plane.heading;

                // Update trail
                updateLiveTrail(plane.icao, lat, lon);

                if (liveMarkers[plane.icao]) {
                    // Update existing marker position
                    liveMarkers[plane.icao].setLatLng([lat, lon]);
                    liveMarkers[plane.icao].setIcon(getPlaneIcon(heading));
                    liveMarkers[plane.icao].bindPopup(`
                        <b>${plane.callsign || plane.icao}</b><br>
                        Alt: ${plane.altitude || '---'} ft<br>
                        Speed: ${plane.speed || '---'} kt<br>
                        Heading: ${heading || '---'}°
                    `);
                } else {
                    // Create new marker
                    const marker = L.marker([lat, lon], { icon: getPlaneIcon(heading) }).addTo(map);
                    marker.bindPopup(`
                        <b>${plane.callsign || plane.icao}</b><br>
                        Alt: ${plane.altitude || '---'} ft<br>
                        Speed: ${plane.speed || '---'} kt<br>
                        Heading: ${heading || '---'}°
                    `);
                    marker.on('click', () => {
                        showLivePlanePath(plane.icao, plane.callsign);
                        focusLivePlane(livePlaneCache[plane.icao] || plane);
                    });
                    liveMarkers[plane.icao] = marker;
                }
            }
        });

    } catch (err) {
        console.error('Error updating live map:', err);
    }
}

// Load live aircraft list
async function loadLiveDirect() {
    try {
        const res = await fetch(`${API_URL}/api/live-direct`);
        const livePlanes = await res.json();

        const container = document.getElementById('live-list');
        const liveSection = document.getElementById('live-section');

        if (livePlanes.length === 0) {
            liveSection.style.display = 'none';
            document.getElementById('status').innerHTML = `${allPlanes.length} aircraft | 0 live now`;
        } else {
            liveSection.style.display = 'block';
            container.innerHTML = '';

            livePlanes.forEach(plane => {
                const div = document.createElement('div');
                div.className = 'live-aircraft-item';
                div.innerHTML = `
                    <div class="aircraft-callsign">${plane.callsign || plane.icao} 🟢</div>
                    <div class="aircraft-stats">Alt: ${plane.altitude || '---'} ft | Spd: ${plane.speed || '---'} kt</div>
                `;
                div.onclick = () => {
                    showLivePlanePath(plane.icao, plane.callsign);
                    focusLivePlane(livePlaneCache[plane.icao] || plane);
                };
                container.appendChild(div);
            });

            document.getElementById('status').innerHTML = `${allPlanes.length} aircraft | ${livePlanes.length} live now`;
        }

        // Update map markers
        updateLiveMap();

        // Refresh every 1 second (was 3 seconds)
        setTimeout(loadLiveDirect, 1000);

    } catch (err) {
        console.error('Error loading live aircraft:', err);
        setTimeout(loadLiveDirect, 5000);
    }
}

// Load historical planes
async function loadPlanes() {
    try {
        const res = await fetch(`${API_URL}/api/planes?limit=100&offset=0`);
        const planes = await res.json();
        allPlanes = planes;
        displayPlanes(planes);
        loadLiveDirect();
    } catch (err) {
        document.getElementById('status').innerHTML = 'Error loading planes';
        console.error(err);
    }
}

function displayPlanes(planes) {
    const container = document.getElementById('aircraft-list');
    container.innerHTML = '';

    planes.forEach(plane => {
        const div = document.createElement('div');
        div.className = 'aircraft-item';
        div.onclick = () => showPlaneTrips(plane.icao, plane.callsign);

        div.innerHTML = `
            <div class="aircraft-callsign">${plane.callsign || 'Unknown'}</div>
            <div class="aircraft-stats">📊 ${plane.total_records} records | ⛰️ ${plane.max_altitude} ft</div>
        `;
        container.appendChild(div);
    });
}

async function showPlaneTrips(icao, callsign, startTime = null, endTime = null) {
    try {
        document.getElementById('selected-aircraft').textContent = `${callsign || icao} - Trips`;
        document.getElementById('trips-panel').classList.remove('hidden');
        document.getElementById('trips-list').innerHTML = '<div class="loading">Loading trips...</div>';

        const params = new URLSearchParams();
        if (startTime) params.set('start_time', startTime);
        if (endTime) params.set('end_time', endTime);

        const queryString = params.toString();
        const response = await fetch(`${API_URL}/api/plane/${icao}/trips${queryString ? `?${queryString}` : ''}`);
        const trips = await response.json();

        if (trips.length === 0) {
            document.getElementById('trips-list').innerHTML = '<div class="loading">No trips found</div>';
            return;
        }

        displayTrips(trips, icao, startTime, endTime);
    } catch (error) {
        console.error('Error:', error);
        document.getElementById('trips-list').innerHTML = '<div class="error">Failed to load trips</div>';
    }
}

function displayTrips(trips, icao, startTime, endTime) {
    const container = document.getElementById('trips-list');
    container.innerHTML = '';

    trips.forEach(trip => {
        const startDate = new Date(trip.start_time).toLocaleString();
        const endDate = new Date(trip.end_time).toLocaleTimeString();

        const div = document.createElement('div');
        div.className = 'trip-item';
        div.onclick = () => showTripPath(icao, trip.trip_id, startTime, endTime);

        div.innerHTML = `
            <div class="trip-date">📅 ${startDate} → ${endDate}</div>
            <div class="trip-details">
                Duration: ${trip.duration_min} min | 
                <span class="trip-altitude">Max Alt: ${trip.max_altitude} ft</span>
            </div>
            <div class="trip-details">
                📍 ${trip.points} position points
            </div>
        `;
        container.appendChild(div);
    });
}

async function showTripPath(icao, tripId, startTime = null, endTime = null) {
    try {
        const params = new URLSearchParams();
        if (startTime) params.set('start_time', startTime);
        if (endTime) params.set('end_time', endTime);

        const queryString = params.toString();
        const response = await fetch(`${API_URL}/api/trip/${icao}/${tripId}${queryString ? `?${queryString}` : ''}`);
        const points = await response.json();

        if (points.length === 0) return;

        if (currentPathLayer) map.removeLayer(currentPathLayer);

        currentPathLayer = L.featureGroup().addTo(map);
        const latlngs = points.map(p => [p.lat, p.lon]);

        for (let i = 0; i < points.length - 1; i++) {
            const p1 = points[i];
            const p2 = points[i + 1];
            if (!p1.altitude || !p2.altitude) continue;

            const avgAlt = (p1.altitude + p2.altitude) / 2;
            let color;
            if (avgAlt < 10000) color = '#00ff00';
            else if (avgAlt < 25000) color = '#ffff00';
            else color = '#ff4444';

            const segment = L.polyline([[p1.lat, p1.lon], [p2.lat, p2.lon]], {
                color: color,
                weight: 3
            });
            currentPathLayer.addLayer(segment);
        }

        const start = points[0];
        const end = points[points.length - 1];
        currentPathLayer.addLayer(L.marker([start.lat, start.lon]).bindPopup('Start'));
        currentPathLayer.addLayer(L.marker([end.lat, end.lon]).bindPopup('End'));

        map.fitBounds(latlngs);

    } catch (error) {
        console.error('Error:', error);
    }
}

// Close trips panel and remove path
document.getElementById('close-trips').onclick = () => {
    document.getElementById('trips-panel').classList.add('hidden');
    if (currentPathLayer) {
        map.removeLayer(currentPathLayer);
        currentPathLayer = null;
    }
};

// Start everything
loadPlanes();