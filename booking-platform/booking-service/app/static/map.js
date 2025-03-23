// Initialize the map centered at Dublin
const map = L.map('map').setView([53.35, -6.26], 13);

// Add OpenStreetMap tiles
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19
}).addTo(map);

// Create a layer for the highlighted road
let highlightedRoadLayer = L.layerGroup().addTo(map);

// Create a layer for all roads
let allRoadsLayer = L.layerGroup();
// Add variable to store all roads data in memory
let allRoadsData = null;
let allRoadsLoaded = false;

// Create layers for routing
let routeLayer = L.layerGroup().addTo(map);
let dbRoadsLayer = L.layerGroup().addTo(map);
let routeMarkers = L.layerGroup().addTo(map);

// Track bookable road segments
let bookableSegments = [];

// Track route segments and info
let routeSegmentIds = [];
let routeRoadIds = []; // Add tracking for roads
let routeDuration = 0;
let routeDistance = 0;

// Road style based on type
function getRoadStyle(roadType, highlighted = false) {
    const styles = {
        'motorway': { color: '#e34a33', weight: highlighted ? 7 : 5 },
        'trunk': { color: '#fc8d59', weight: highlighted ? 6 : 4 },
        'primary': { color: '#fdbb84', weight: highlighted ? 5 : 3 },
        'secondary': { color: '#fdd49e', weight: highlighted ? 4 : 2.5 },
        'tertiary': { color: '#fee8c8', weight: highlighted ? 3.5 : 2 },
        'residential': { color: '#f7f7f7', weight: highlighted ? 3 : 1.5 },
        'default': { color: '#969696', weight: highlighted ? 3 : 1 }
    };

    const style = styles[roadType] || styles['default'];

    if (highlighted) {
        style.opacity = 1;
        style.className = 'highlighted-road';
    }

    return style;
}

// Function to handle map clicks and detect roads
map.on('click', async function(e) {
    const latlng = e.latlng;
    const radius = 10; // meters

    try {
        // Query roads near the clicked point
        const response = await fetch('/osm/roads/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                point: [latlng.lat, latlng.lng],
                radius: radius,
                limit: 1
            })
        });

        const data = await response.json();

        // Clear previous highlighted road
        highlightedRoadLayer.clearLayers();
        document.getElementById('road-info').style.display = 'none';

        if (data.roads && data.roads.length > 0) {
            const road = data.roads[0];
            displayRoadDetails(road.id);
        }
    } catch (error) {
        console.error('Error detecting road:', error);
    }
});

// Function to display road details
async function displayRoadDetails(roadId) {
    try {
        const response = await fetch(`/osm/roads/${roadId}`);
        const roadDetail = await response.json();

        if (roadDetail.geometry) {
            // Clear previous highlighted road
            highlightedRoadLayer.clearLayers();

            // Parse the geometry if it's a string, otherwise use as is
            const geometry = typeof roadDetail.geometry === 'string'
                ? JSON.parse(roadDetail.geometry)
                : roadDetail.geometry;

            // Apply style based on road type
            const style = getRoadStyle(roadDetail.road_type, true);

            // Create GeoJSON object if we have just the LineString part
            let geoJsonData = geometry;
            if (geometry.type && !geometry.features) {
                geoJsonData = {
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": {}
                };
            }

            // Create the GeoJSON layer with the properly formatted data
            const roadLine = L.geoJSON(geoJsonData, {
                style: style,
                onEachFeature: (feature, layer) => {
                    // You can add additional interactivity here if needed
                    if (layer.setStyle) {
                        layer.setStyle(style);
                    }
                }
            });

            // Add the road to the highlight layer
            highlightedRoadLayer.addLayer(roadLine);

            // Fit map to road bounds with padding
            map.fitBounds(roadLine.getBounds(), {
                padding: [50, 50],
                maxZoom: 18
            });

            // Extract useful information from tags if available
            let speedLimit = '';
            let additionalInfo = '';

            if (roadDetail.tags) {
                const tags = typeof roadDetail.tags === 'string'
                    ? JSON.parse(roadDetail.tags)
                    : roadDetail.tags;

                speedLimit = tags.maxspeed || '';

                // Extract other useful information
                if (tags.lanes) additionalInfo += `<p><strong>Lanes:</strong> ${tags.lanes}</p>`;
                if (tags.surface) additionalInfo += `<p><strong>Surface:</strong> ${tags.surface}</p>`;
                if (tags.width) additionalInfo += `<p><strong>Width:</strong> ${tags.width}</p>`;
            }

            // Show road info
            const roadInfo = document.getElementById('road-info');
            roadInfo.innerHTML = `
                <h3>${roadDetail.name || 'Unnamed road'}</h3>
                <p><strong>Type:</strong> ${roadDetail.road_type || 'Unknown'}</p>
                ${roadDetail.country ? '<p><strong>Country:</strong> ' + roadDetail.country + '</p>' : ''}
                ${roadDetail.region ? '<p><strong>Region:</strong> ' + roadDetail.region + '</p>' : ''}
                ${speedLimit ? '<p><strong>Speed limit:</strong> ' + speedLimit + '</p>' : ''}
                ${additionalInfo}
                <p><small>Click anywhere else to close</small></p>
            `;
            roadInfo.style.display = 'block';

            // Log the geometry to check what was processed
            console.log("Road geometry:", geometry);
        }
    } catch (error) {
        console.error(`Error fetching details for road ${roadId}:`, error);
    }
}

// Function to load and display all roads
async function loadAllRoads() {
    // If we already loaded the roads data, just display from memory
    if (allRoadsLoaded && allRoadsData) {
        displayRoadsFromMemory();
        return;
    }

    // Show loading indicator
    document.getElementById('loading-roads').style.display = 'inline';

    try {
        const response = await fetch('/osm/get-all-roads', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        // Store the data in memory
        allRoadsData = data.roads;
        allRoadsLoaded = true;

        // Display the roads from memory
        displayRoadsFromMemory();

        console.log(`Loaded ${data.roads.length} roads into memory`);
    } catch (error) {
        console.error('Error loading roads:', error);
    } finally {
        // Hide loading indicator
        document.getElementById('loading-roads').style.display = 'none';
    }
}

// Function to display roads from memory
function displayRoadsFromMemory() {
    // Clear existing roads
    allRoadsLayer.clearLayers();

    // Make sure we have data
    if (!allRoadsData || !allRoadsData.length) {
        console.warn('No road data available to display');
        return;
    }

    // Add each road to the layer
    allRoadsData.forEach(road => {
        if (road.segments) {
            road.segments.forEach(segment => {
                if (segment.geometry) {
                    try {
                        // Parse the geometry if it's a string
                        const geometry = typeof segment.geometry === 'string'
                            ? JSON.parse(segment.geometry)
                            : segment.geometry;

                        // Apply style based on road type
                        const style = getRoadStyle(road.road_type);

                        // Create GeoJSON object
                        let geoJsonData = geometry;
                        if (geometry.type && !geometry.features) {
                            geoJsonData = {
                                "type": "Feature",
                                "geometry": geometry,
                                "properties": {
                                    name: road.name,
                                    road_type: road.road_type,
                                    id: road.id
                                }
                            };
                        }

                        // Create the GeoJSON layer
                        const roadLine = L.geoJSON(geoJsonData, {
                            style: style,
                            onEachFeature: (feature, layer) => {
                                // Add click event to show road details
                                layer.on('click', () => {
                                    displayRoadDetails(road.id);
                                });

                                // Add tooltip with road name
                                if (road.name) {
                                    layer.bindTooltip(road.name);
                                }
                            }
                        });

                        // Add the road to the layer
                        allRoadsLayer.addLayer(roadLine);
                    } catch (error) {
                        console.error(`Error processing road segment for ${road.id}:`, error);
                    }
                }
            });
        }
    });

    console.log(`Displayed ${allRoadsData.length} roads on the map from memory`);
}

// Handle checkbox change
document.getElementById('show-all-roads').addEventListener('change', function(e) {
    if (e.target.checked) {
        // Load and show all roads
        loadAllRoads();
        map.addLayer(allRoadsLayer);
    } else {
        // Hide all roads but keep data in memory
        map.removeLayer(allRoadsLayer);
    }
});

// Remove the moveend event handler that reloads roads when map is moved
// Replace with a version that only displays roads from memory if checkbox is checked
map.on('moveend', function() {
    if (document.getElementById('show-all-roads').checked && allRoadsLoaded) {
        // Just make sure roads are displayed (no new request)
        map.addLayer(allRoadsLayer);
    }
});

// ----- Route Planning Code -----

// Origin and destination coordinates
let originCoords = null;
let destCoords = null;
let currentRoute = null;

// Initialize the autocomplete functionality directly
document.addEventListener('DOMContentLoaded', function() {
    // Set up origin autocomplete
    setupAutocomplete('route-origin', function(item) {
        originCoords = [item.lat, item.lon];
        document.getElementById('route-origin').value = item.display_name;
    });

    // Set up destination autocomplete
    setupAutocomplete('route-destination', function(item) {
        destCoords = [item.lat, item.lon];
        document.getElementById('route-destination').value = item.display_name;
    });
});

// Simple cache for geocoding results
const geocodingCache = {};

// Function to set up autocomplete on an input element
function setupAutocomplete(inputId, selectionCallback) {
    const input = document.getElementById(inputId);
    const resultsContainerId = `${inputId}-results`;

    // Create results container if it doesn't exist
    let resultsContainer = document.getElementById(resultsContainerId);
    if (!resultsContainer) {
        resultsContainer = document.createElement('div');
        resultsContainer.id = resultsContainerId;
        resultsContainer.className = 'autocomplete-results';
        input.parentNode.appendChild(resultsContainer);
    }

    let debounceTimer;

    // Add input event listener
    input.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        const query = this.value.trim();

        // Clear results if input is too short
        if (query.length < 3) {
            resultsContainer.innerHTML = '';
            resultsContainer.style.display = 'none';
            return;
        }

        // Show loading indicator
        resultsContainer.innerHTML = '<div class="loading-item">Searching locations...</div>';
        resultsContainer.style.display = 'block';

        // Debounce the search - wait 300ms before actually searching
        debounceTimer = setTimeout(async function() {
            try {
                const results = await searchLocations(query);
                displayResults(results, resultsContainer, selectionCallback);
            } catch (error) {
                resultsContainer.innerHTML = `<div class="error-item">Error: ${error.message}</div>`;
            }
        }, 300);
    });

    // Hide results when clicking outside
    document.addEventListener('click', function(e) {
        if (e.target !== input && !resultsContainer.contains(e.target)) {
            resultsContainer.style.display = 'none';
        }
    });

    // Show results again when focusing on input
    input.addEventListener('focus', function() {
        const query = this.value.trim();
        if (query.length >= 3 && resultsContainer.innerHTML) {
            resultsContainer.style.display = 'block';
        }
    });
}

// Function to search locations using Nominatim API
async function searchLocations(query) {
    console.log("Searching for:", query);

    // Check cache first
    const cacheKey = query.toLowerCase();
    if (geocodingCache[cacheKey]) {
        console.log("Using cached results");
        return geocodingCache[cacheKey];
    }

    // Construct the URL with proper parameters
    const params = new URLSearchParams({
        format: 'json',
        q: query,
        limit: 5,
        addressdetails: 1,
        "_": new Date().getTime() // Cache buster
    });

    const url = `https://nominatim.openstreetmap.org/search?${params.toString()}`;
    console.log("Sending request to:", url);

    // Make request to Nominatim API
    try {
        const response = await fetch(url);

        if (!response.ok) {
            throw new Error(`API Error: ${response.status}`);
        }

        const data = await response.json();
        console.log("Received results:", data.length);

        // Cache the results
        geocodingCache[cacheKey] = data;

        return data;
    } catch (error) {
        console.error("Search error:", error);
        throw error;
    }
}

// Function to display the search results
function displayResults(results, container, selectionCallback) {
    if (results.length === 0) {
        container.innerHTML = '<div class="no-results">No locations found</div>';
        return;
    }

    let html = '';
    results.forEach(item => {
        html += `<div class="result-item" data-lat="${item.lat}" data-lon="${item.lon}">${item.display_name}</div>`;
    });

    container.innerHTML = html;

    // Add click event listeners to results
    container.querySelectorAll('.result-item').forEach(el => {
        el.addEventListener('click', function() {
            const lat = this.getAttribute('data-lat');
            const lon = this.getAttribute('data-lon');

            // Find the full item from results
            const selectedItem = results.find(r => r.lat === lat && r.lon === lon);

            if (selectedItem) {
                selectionCallback(selectedItem);
                container.style.display = 'none';
            }
        });
    });
}

// Find route button handler
document.getElementById('find-route-btn').addEventListener('click', async function() {
    if (!originCoords || !destCoords) {
        alert("Please select both origin and destination locations");
        return;
    }

    // Clear previous routes
    routeLayer.clearLayers();
    dbRoadsLayer.clearLayers();
    routeMarkers.clearLayers();

    // Clear route data
    routeSegmentIds = [];
    routeDuration = 0;
    routeDistance = 0;

    document.getElementById('route-booking-info').innerHTML = '<p>Finding route...</p>';
    document.getElementById('find-route-btn').disabled = true;
    document.getElementById('route-details').innerHTML = "Finding route...";

    try {
        // Use OSRM API to get the route
        const response = await fetch(`https://router.project-osrm.org/route/v1/driving/${originCoords[1]},${originCoords[0]};${destCoords[1]},${destCoords[0]}?overview=full&geometries=geojson&steps=true&annotations=true`);

        if (!response.ok) {
            throw new Error(`OSRM API error: ${response.statusText}`);
        }

        const data = await response.json();

        if (data.code !== 'Ok') {
            throw new Error(`Routing error: ${data.message || "Could not find route"}`);
        }

        // Get the first route
        currentRoute = data.routes[0];
        const geometry = currentRoute.geometry;

        // Store route info
        routeDuration = Math.round(currentRoute.duration / 60); // convert to minutes
        routeDistance = Math.round(currentRoute.distance); // in meters

        // Add route to map in blue
        const routePath = L.geoJSON(geometry, {
            style: {
                color: '#3388ff',
                weight: 4,
                opacity: 0.7
            }
        }).addTo(routeLayer);

        const startMarker = L.marker([originCoords[0], originCoords[1]], {
            title: 'Origin'
        }).addTo(routeMarkers);

        const endMarker = L.marker([destCoords[0], destCoords[1]], {
            title: 'Destination'
        }).addTo(routeMarkers);

        // Fit map to show the route
        map.fitBounds(routePath.getBounds(), {
            padding: [50, 50]
        });

        // Extract OSM node IDs from the route annotations
        const nodeIds = extractNodeIdsFromRoute(data);

        console.log('Extracted OSM node IDs:', nodeIds.length > 100 ?
            `${nodeIds.length} nodes (first 5: ${nodeIds.slice(0, 5).join(', ')}...)` :
            nodeIds);

        // Display route information
        document.getElementById('route-details').innerHTML = `
            <p><strong>Distance:</strong> ${(routeDistance / 1000).toFixed(2)} km</p>
            <p><strong>Duration:</strong> ${routeDuration} minutes</p>
            <p><strong>OSM nodes:</strong> ${nodeIds.length}</p>
        `;

        // If we have node IDs, fetch the road geometries from our database
        if (nodeIds.length > 0) {
            await fetchRoadSegmentsByNodeIds(nodeIds);
        } else {
            document.getElementById('route-details').innerHTML += `
                <p class="error">No OSM node IDs found in the route</p>
            `;
            document.getElementById('route-booking-info').innerHTML = '<p class="no-route">Cannot book this route - no road segments found</p>';
        }

    } catch (error) {
        console.error('Error finding route:', error);
        document.getElementById('route-details').innerHTML = `<p class="error">Error finding route: ${error.message}</p>`;
        document.getElementById('route-booking-info').innerHTML = '<p class="no-route">Error finding route</p>';
    } finally {
        document.getElementById('find-route-btn').disabled = false;
    }
});

// Extract node IDs from OSRM route response
function extractNodeIdsFromRoute(routeData) {
    const nodeIds = new Set(); // Use a Set to avoid duplicates

    if (routeData.routes && routeData.routes.length > 0) {
        const route = routeData.routes[0];

        // Extract from legs annotations - this is where OSRM provides node IDs
        if (route.legs) {
            route.legs.forEach(leg => {
                if (leg.annotation && leg.annotation.nodes) {
                    // Add all node IDs from this leg
                    leg.annotation.nodes.forEach(nodeId => {
                        if (nodeId > 0) { // Valid OSM node IDs are positive
                            nodeIds.add(nodeId);
                        }
                    });
                }
            });
        }
    }

    return Array.from(nodeIds);
}

// Fetch road segments from our database by node IDs
async function fetchRoadSegmentsByNodeIds(nodeIds) {
    try {
        // Update status
        document.getElementById('route-details').innerHTML += `
            <p>Fetching database road segments...</p>
        `;

        // Call our backend API with the list of node IDs
        const response = await fetch('/osm/road-segments/by-node-ids', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('accessToken')}`
            },
            body: JSON.stringify({
                node_ids: nodeIds
            })
        });

        if (!response.ok) {
            throw new Error(`API error: ${response.statusText}`);
        }

        const data = await response.json();
        console.log("API response:", data);  // Debug log to see the actual response

        // Clear previous db roads
        dbRoadsLayer.clearLayers();
        routeSegmentIds = [];
        routeRoadIds = []; // Clear road IDs

        if (data.roads && data.roads.length > 0) {
            console.log(`Found ${data.roads.length} roads with segments`);
            let totalSegmentCount = 0;

            // Process each road
            data.roads.forEach(road => {
                console.log(`Processing road: ${road.name || 'Unnamed'} with ${road.segments?.length || 0} segments`);

                // Store the road ID for booking
                if (road.id && !routeRoadIds.includes(road.id)) {
                    routeRoadIds.push(road.id);
                }

                if (road.segments && road.segments.length > 0) {
                    totalSegmentCount += road.segments.length;

                    // Process each segment in the road
                    road.segments.forEach(segment => {
                        if (segment.geometry) {
                            try {
                                // Parse the geometry if it's a string
                                const geometry = typeof segment.geometry === 'string'
                                    ? JSON.parse(segment.geometry)
                                    : segment.geometry;

                                // Save segment ID for reference (we'll use road IDs for booking)
                                routeSegmentIds.push(segment.id);

                                // Create a GeoJSON object for Leaflet if needed
                                let geoJsonData = geometry;
                                if (geometry.type && !geometry.features) {
                                    geoJsonData = {
                                        "type": "Feature",
                                        "geometry": geometry,
                                        "properties": {
                                            road_id: road.id,
                                            road_name: road.name,
                                            segment_id: segment.id
                                        }
                                    };
                                }

                                // Create GeoJSON layer with the segment
                                const segmentLayer = L.geoJSON(geoJsonData, {
                                    style: {
                                        color: '#e31a1c',
                                        weight: 6,
                                        opacity: 0.8
                                    },
                                    onEachFeature: (feature, layer) => {
                                        const tooltipContent = `${road.name || 'Unnamed Road'}
                                            (Road ID: ${road.id})`;
                                        layer.bindTooltip(tooltipContent);
                                    }
                                });

                                // Add to map layer
                                dbRoadsLayer.addLayer(segmentLayer);
                            } catch (error) {
                                console.error(`Error processing segment geometry:`, error, segment);
                            }
                        } else {
                            console.warn(`Segment ${segment.id} has no geometry`);
                        }
                    });
                } else {
                    console.warn(`Road ${road.id} has no segments`);
                }
            });

            // Make sure the road layer is added to the map
            dbRoadsLayer.addTo(map);

            // Update route details with DB coverage
            const roadCount = data.roads.length;

            // Show route booking option in sidebar
            document.getElementById('route-booking-info').innerHTML = `
                <div class="route-summary">
                    <p><strong>Distance:</strong> ${(routeDistance / 1000).toFixed(2)} km</p>
                    <p><strong>Duration:</strong> ${routeDuration} minutes</p>
                    <p><strong>Roads:</strong> ${roadCount}</p>
                </div>
                <button class="btn btn-primary mt-2 w-100" id="book-route-btn">Book This Route</button>
            `;

            // Add event listener for booking button
            document.getElementById('book-route-btn').addEventListener('click', () => {
                openRouteBookingModal();
            });

        } else {
            console.warn("No roads found in API response");
            document.getElementById('route-details').innerHTML += `
                <p class="error">No matching road segments found in database</p>
            `;
            document.getElementById('route-booking-info').innerHTML = '<p class="no-route">No bookable segments found</p>';
        }

    } catch (error) {
        console.error('Error fetching road segments:', error);
        document.getElementById('route-details').innerHTML += `
            <p class="error">Error fetching database segments: ${error.message}</p>
        `;
        document.getElementById('route-booking-info').innerHTML = '<p class="no-route">Error loading segments</p>';
    }
}

// Open the booking modal for the entire route
function openRouteBookingModal() {
    if (routeRoadIds.length === 0) {
        alert('No roads found for booking');
        return;
    }

    // Trigger the booking modal with route information
    showRouteBookingModal(routeRoadIds, routeDistance, routeDuration);
}

// Clear route button handler
document.getElementById('clear-route-btn').addEventListener('click', function() {
    // Clear inputs
    document.getElementById('route-origin').value = '';
    document.getElementById('route-destination').value = '';

    // Clear coordinates and route data
    originCoords = null;
    destCoords = null;
    currentRoute = null;
    routeSegmentIds = [];
    routeDuration = 0;
    routeDistance = 0;

    // Clear layers
    routeLayer.clearLayers();
    dbRoadsLayer.clearLayers();
    routeMarkers.clearLayers();

    // Clear route details and booking info
    document.getElementById('route-details').innerHTML = '';
    document.getElementById('route-booking-info').innerHTML = '<p class="no-route">Find a route to book</p>';
});
