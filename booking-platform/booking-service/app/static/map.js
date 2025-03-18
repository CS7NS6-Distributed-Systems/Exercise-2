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

// Create layers for routing
let routeLayer = L.layerGroup().addTo(map);
let dbRoadsLayer = L.layerGroup().addTo(map);
let routeMarkers = L.layerGroup().addTo(map);

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
    // Show loading indicator
    document.getElementById('loading-roads').style.display = 'inline';

    try {
        // Fetch all roads within current map bounds
        const bounds = map.getBounds();
        const southWest = bounds.getSouthWest();
        const northEast = bounds.getNorthEast();

        const response = await fetch('/osm/roads/in-bounds', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                bounds: [
                    southWest.lat,
                    southWest.lng,
                    northEast.lat,
                    northEast.lng
                ],
                limit: 1000  // Limit the number of roads to prevent performance issues
            })
        });

        const data = await response.json();

        // Clear existing roads
        allRoadsLayer.clearLayers();

        // Add each road to the layer
        if (data.roads && data.roads.length > 0) {
            data.roads.forEach(road => {
                if (road.geometry) {
                    try {
                        // Parse the geometry if it's a string
                        const geometry = typeof road.geometry === 'string'
                            ? JSON.parse(road.geometry)
                            : road.geometry;

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
                        console.error(`Error processing road ${road.id}:`, error);
                    }
                }
            });

            console.log(`Displayed ${data.roads.length} roads on the map`);
        }
    } catch (error) {
        console.error('Error loading roads:', error);
    } finally {
        // Hide loading indicator
        document.getElementById('loading-roads').style.display = 'none';
    }
}

// Handle checkbox change
document.getElementById('show-all-roads').addEventListener('change', function(e) {
    if (e.target.checked) {
        // Load and show all roads
        loadAllRoads();
        map.addLayer(allRoadsLayer);
    } else {
        // Hide all roads
        map.removeLayer(allRoadsLayer);
    }
});

// Update roads when map is moved (if checkbox is checked)
map.on('moveend', function() {
    if (document.getElementById('show-all-roads').checked) {
        loadAllRoads();
    }
});

// ----- Route Planning Code -----

// Origin and destination coordinates
let originCoords = null;
let destCoords = null;
let currentRoute = null;

// Initialize Nominatim geocoding autocomplete for origin
const originAutocomplete = new autoComplete({
    selector: "#route-origin",
    placeHolder: "Enter origin location",
    data: {
        src: async (query) => {
            try {
                const source = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${query}&limit=5`);
                const data = await source.json();
                return data;
            } catch (error) {
                console.error("Error fetching origin suggestions:", error);
                return [];
            }
        },
        keys: ["display_name"],
        cache: false
    },
    resultsList: {
        element: (list, data) => {
            if (!data.results.length) {
                const message = document.createElement("div");
                message.setAttribute("class", "no_result");
                message.innerHTML = `<span>Found No Results for "${data.query}"</span>`;
                list.prepend(message);
            }
        },
        noResults: true,
    },
    resultItem: {
        highlight: true
    },
    events: {
        input: {
            selection: (event) => {
                const selection = event.detail.selection.value;
                originAutocomplete.input.value = selection.display_name;
                originCoords = [selection.lat, selection.lon];
            }
        }
    }
});

// Initialize Nominatim geocoding autocomplete for destination
const destAutocomplete = new autoComplete({
    selector: "#route-destination",
    placeHolder: "Enter destination location",
    data: {
        src: async (query) => {
            try {
                const source = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${query}&limit=5`);
                const data = await source.json();
                return data;
            } catch (error) {
                console.error("Error fetching destination suggestions:", error);
                return [];
            }
        },
        keys: ["display_name"],
        cache: false
    },
    resultsList: {
        element: (list, data) => {
            if (!data.results.length) {
                const message = document.createElement("div");
                message.setAttribute("class", "no_result");
                message.innerHTML = `<span>Found No Results for "${data.query}"</span>`;
                list.prepend(message);
            }
        },
        noResults: true,
    },
    resultItem: {
        highlight: true
    },
    events: {
        input: {
            selection: (event) => {
                const selection = event.detail.selection.value;
                destAutocomplete.input.value = selection.display_name;
                destCoords = [selection.lat, selection.lon];
            }
        }
    }
});

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
            <p><strong>Distance:</strong> ${(currentRoute.distance / 1000).toFixed(2)} km</p>
            <p><strong>Duration:</strong> ${Math.round(currentRoute.duration / 60)} minutes</p>
            <p><strong>OSM nodes:</strong> ${nodeIds.length}</p>
        `;

        // If we have node IDs, fetch the road geometries from our database
        if (nodeIds.length > 0) {
            await fetchRoadSegmentsByNodeIds(nodeIds);
        } else {
            document.getElementById('route-details').innerHTML += `
                <p class="error">No OSM node IDs found in the route</p>
            `;
        }

    } catch (error) {
        console.error('Error finding route:', error);
        document.getElementById('route-details').innerHTML = `<p class="error">Error finding route: ${error.message}</p>`;
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
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                node_ids: nodeIds
            })
        });

        if (!response.ok) {
            throw new Error(`API error: ${response.statusText}`);
        }

        const data = await response.json();

        // Clear previous db roads
        dbRoadsLayer.clearLayers();

        if (data.segments && data.segments.length > 0) {
            // Add each segment to the map in red
            data.segments.forEach(segment => {
                if (segment.geometry) {
                    try {
                        // Parse the geometry if it's a string
                        const geometry = typeof segment.geometry === 'string'
                            ? JSON.parse(segment.geometry)
                            : segment.geometry;

                        // Create GeoJSON layer with the segment
                        const segmentLayer = L.geoJSON(geometry, {
                            style: {
                                color: '#e31a1c',
                                weight: 6,
                                opacity: 0.8
                            },
                            onEachFeature: (feature, layer) => {
                                const tooltip = `${segment.road_name || 'Unnamed'}
                                    (Road ID: ${segment.road_id}, Segment ID: ${segment.id})`;
                                layer.bindTooltip(tooltip);
                            }
                        }).addTo(dbRoadsLayer);
                    } catch (error) {
                        console.error(`Error processing segment geometry:`, error);
                    }
                }
            });

            // Update route details with DB coverage
            const dbSegmentCount = data.segments.length;
            const dbNodeCount = data.nodes_matched || 0;
            const coveragePercent = (dbNodeCount / nodeIds.length) * 100;

            document.getElementById('route-details').innerHTML += `
                <p><strong>Database segments found:</strong> ${dbSegmentCount}</p>
                <p><strong>Database nodes matched:</strong> ${dbNodeCount} of ${nodeIds.length}</p>
                <p><strong>Coverage:</strong> ${coveragePercent.toFixed(1)}%</p>
            `;
        } else {
            document.getElementById('route-details').innerHTML += `
                <p class="error">No matching road segments found in database</p>
            `;
        }

    } catch (error) {
        console.error('Error fetching road segments:', error);
        document.getElementById('route-details').innerHTML += `
            <p class="error">Error fetching database segments: ${error.message}</p>
        `;
    }
}

// Clear route button handler
document.getElementById('clear-route-btn').addEventListener('click', function() {
    // Clear inputs
    document.getElementById('route-origin').value = '';
    document.getElementById('route-destination').value = '';

    // Clear coordinates
    originCoords = null;
    destCoords = null;
    currentRoute = null;

    // Clear layers
    routeLayer.clearLayers();
    dbRoadsLayer.clearLayers();
    routeMarkers.clearLayers();

    // Clear route details
    document.getElementById('route-details').innerHTML = '';
});
