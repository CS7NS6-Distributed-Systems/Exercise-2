from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import json
import logging

from app.db import get_cockroach_connection, release_cockroach_connection
from app.user_routes import session_required

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

osm_blueprint = Blueprint('osm', __name__)

@osm_blueprint.route('/regions', methods=['GET'])
def get_regions():
    """Get all available regions"""
    try:
        # Parse query parameters for filtering
        country = request.args.get('country')

        # Build query
        query = "SELECT id, name, country, code FROM regions WHERE 1=1"
        params = []

        if country:
            query += " AND country = %s"
            params.append(country)

        query += " ORDER BY name"

        # Execute query
        with get_cockroach_connection() as cockroach_conn:
            with cockroach_conn.cursor() as cursor:
                cursor.execute(query, tuple(params))
                regions = cursor.fetchall()

                # Get column names
                column_names = [desc[0] for desc in cursor.description]

                # Format results as list of dictionaries
                result = []
                for region in regions:
                    region_dict = dict(zip(column_names, region))
                    result.append(region_dict)

        return jsonify({
            "regions": result,
            "count": len(result)
        }), 200

    except Exception as e:
        logger.error(f"Error fetching regions: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@osm_blueprint.route('/roads', methods=['GET'])
def get_roads():
    """Get roads with filtering options"""
    try:
        # Parse query parameters
        road_type = request.args.get('type')
        country = request.args.get('country')
        region_id = request.args.get('region_id')
        name_query = request.args.get('name')
        limit = min(int(request.args.get('limit', 100)), 1000)  # Max 1000 results
        offset = int(request.args.get('offset', 0))

        # Build query dynamically - join with regions table
        query = """
            SELECT r.id, r.name, r.road_type, r.country,
                   reg.name as region_name, reg.id as region_id,
                   COUNT(rs.segment_id) as segment_count
            FROM roads r
            LEFT JOIN regions reg ON r.region_id = reg.id
            LEFT JOIN road_segments rs ON r.id = rs.road_id
            WHERE 1=1
        """
        params = []

        if road_type:
            query += " AND r.road_type = %s"
            params.append(road_type)

        if country:
            query += " AND r.country = %s"
            params.append(country)

        if region_id:
            query += " AND r.region_id = %s"
            params.append(int(region_id))

        if name_query:
            query += " AND r.name ILIKE %s"
            params.append(f"%{name_query}%")

        # Group by to handle segment count
        query += " GROUP BY r.id, r.name, r.road_type, r.country, reg.name, reg.id"

        # Add pagination
        query += " ORDER BY r.name LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        # Execute query
        with get_cockroach_connection() as cockroach_conn:
            with cockroach_conn.cursor() as cursor:
                cursor.execute(query, tuple(params))
                roads = cursor.fetchall()

                # Get column names
                column_names = [desc[0] for desc in cursor.description]

                # Format results as list of dictionaries
                result = []
                for road in roads:
                    road_dict = dict(zip(column_names, road))
                    result.append(road_dict)

        # Return results
        return jsonify({
            "roads": result,
            "count": len(result),
            "limit": limit,
            "offset": offset
        }), 200

    except Exception as e:
        logger.error(f"Error fetching roads: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@osm_blueprint.route('/roads/<int:road_id>', methods=['GET'])
def get_road(road_id):
    """Get details for a specific road by ID with its segments"""
    try:
        with get_cockroach_connection() as cockroach_conn:
            with cockroach_conn.cursor() as cursor:
                # First get the road details
                cursor.execute(
                    """
                    SELECT r.id, r.name, r.road_type, r.country,
                           reg.name as region_name, r.tags
                    FROM roads r
                    LEFT JOIN regions reg ON r.region_id = reg.id
                    WHERE r.id = %s
                    """,
                    (road_id,)
                )
                road = cursor.fetchone()

                if not road:
                    return jsonify({"error": "Road not found"}), 404

                # Format road result
                road_column_names = ["id", "name", "road_type", "country", "region_name", "tags"]
                road_dict = dict(zip(road_column_names, road))

                # Parse tags if they exist
                if road_dict["tags"]:
                    try:
                        road_dict["tags"] = json.loads(road_dict["tags"])
                    except:
                        pass

                # Now get all segments for this road
                cursor.execute(
                    """
                    SELECT segment_id, osm_way_id, geometry, length_meters,
                           start_node_id, end_node_id, tags
                    FROM road_segments
                    WHERE road_id = %s
                    """,
                    (road_id,)
                )
                segments = cursor.fetchall()

                # Format segments
                segment_column_names = ["id", "osm_way_id", "geometry", "length_meters",
                                        "start_node_id", "end_node_id", "tags"]
                segments_list = []

                for segment in segments:
                    segment_dict = dict(zip(segment_column_names, segment))

                    # Parse geometry and tags
                    if segment_dict["geometry"]:
                        try:
                            segment_dict["geometry"] = json.loads(segment_dict["geometry"])
                        except:
                            pass

                    if segment_dict["tags"]:
                        try:
                            segment_dict["tags"] = json.loads(segment_dict["tags"])
                        except:
                            pass

                    segments_list.append(segment_dict)

                # Add segments to road data
                road_dict["segments"] = segments_list
                road_dict["segment_count"] = len(segments_list)

                # Calculate total length if possible
                try:
                    road_dict["total_length_meters"] = sum(seg["length_meters"] for seg in segments_list if seg["length_meters"])
                except:
                    road_dict["total_length_meters"] = None

        return jsonify(road_dict), 200

    except Exception as e:
        logger.error(f"Error fetching road {road_id}: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@osm_blueprint.route('/road-segments', methods=['GET'])
def get_road_segments():
    """Get road segments with filtering options"""
    try:
        # Parse query parameters
        road_id = request.args.get('road_id')
        limit = min(int(request.args.get('limit', 100)), 1000)  # Max 1000 results
        offset = int(request.args.get('offset', 0))

        # Build query dynamically
        query = """
            SELECT rs.segment_id, rs.road_id, rs.osm_way_id, rs.length_meters,
                   r.name as road_name, r.road_type
            FROM road_segments rs
            JOIN roads r ON rs.road_id = r.id
            WHERE 1=1
        """
        params = []

        if road_id:
            query += " AND rs.road_id = %s"
            params.append(int(road_id))

        # Add pagination
        query += " ORDER BY rs.segment_id LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        # Execute query
        with get_cockroach_connection() as cockroach_conn:
            with cockroach_conn.cursor() as cursor:
                cursor.execute(query, tuple(params))
                segments = cursor.fetchall()

                # Get column names
                column_names = [desc[0] for desc in cursor.description]

                # Format results as list of dictionaries
                result = []
                for segment in segments:
                    segment_dict = dict(zip(column_names, segment))
                    result.append(segment_dict)

        # Return results
        return jsonify({
            "segments": result,
            "count": len(result),
            "limit": limit,
            "offset": offset
        }), 200

    except Exception as e:
        logger.error(f"Error fetching road segments: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@osm_blueprint.route('/road-segments/<int:segment_id>', methods=['GET'])
def get_road_segment(segment_id):
    """Get details for a specific road segment by ID"""
    try:
        with get_cockroach_connection() as cockroach_conn:
            with cockroach_conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT rs.segment_id, rs.road_id, rs.osm_way_id, rs.geometry,
                           rs.length_meters, rs.start_node_id, rs.end_node_id, rs.tags,
                           r.name as road_name, r.road_type
                    FROM road_segments rs
                    JOIN roads r ON rs.road_id = r.id
                    WHERE rs.segment_id = %s
                    """,
                    (segment_id,)
                )
                segment = cursor.fetchone()

        if not segment:
            return jsonify({"error": "Road segment not found"}), 404

        # Format result
        column_names = ["id", "road_id", "osm_way_id", "geometry", "length_meters",
                       "start_node_id", "end_node_id", "tags", "road_name", "road_type"]
        segment_dict = dict(zip(column_names, segment))

        # Parse geometry and tags if they exist
        if segment_dict["geometry"]:
            try:
                segment_dict["geometry"] = json.loads(segment_dict["geometry"])
            except:
                pass

        if segment_dict["tags"]:
            try:
                segment_dict["tags"] = json.loads(segment_dict["tags"])
            except:
                pass

        return jsonify(segment_dict), 200

    except Exception as e:
        logger.error(f"Error fetching road segment {segment_id}: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@osm_blueprint.route('/roads/search', methods=['POST'])
def search_roads():
    """Advanced search for roads"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No search criteria provided"}), 400

        # Build query dynamically with joins
        query = """
            SELECT r.id, r.name, r.road_type, r.country,
                   reg.name as region_name, reg.id as region_id,
                   COUNT(rs.segment_id) as segment_count
            FROM roads r
            LEFT JOIN regions reg ON r.region_id = reg.id
            LEFT JOIN road_segments rs ON r.id = rs.road_id
            WHERE 1=1
        """
        params = []

        # Process different search criteria
        if "boundingBox" in data:
            # Format: [min_lat, min_lon, max_lat, max_lon] in the request
            # But ST_MakeEnvelope expects [min_lon, min_lat, max_lon, max_lat]
            bb = data["boundingBox"]
            # Reorder coordinates for ST_MakeEnvelope (xmin, ymin, xmax, ymax)
            bbox_coords = [bb[1], bb[0], bb[3], bb[2]]

            # Use a subquery to find roads with segments in the bounding box
            query += """
                AND r.id IN (
                    SELECT DISTINCT road_id FROM road_segments
                    WHERE ST_Intersects(
                        ST_GeomFromGeoJSON(geometry),
                        ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                    )
                )
            """
            params.extend(bbox_coords)

        # Add point-based search
        elif "point" in data:
            # Data should contain point [lat, lng] and radius in meters
            point = data["point"]
            radius = data.get("radius", 20)  # Default 20 meters if not specified

            # Create a point and buffer using ST_DWithin
            query += """
                AND r.id IN (
                    SELECT DISTINCT road_id FROM road_segments
                    WHERE ST_DWithin(
                        ST_GeomFromGeoJSON(geometry),
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                        %s
                    )
                )
            """
            # Add parameters: longitude first, then latitude, then radius (in meters)
            params.extend([point[1], point[0], radius])

        if "roadTypes" in data and data["roadTypes"]:
            placeholders = ", ".join(["%s"] * len(data["roadTypes"]))
            query += f" AND r.road_type IN ({placeholders})"
            params.extend(data["roadTypes"])

        if "countries" in data and data["countries"]:
            placeholders = ", ".join(["%s"] * len(data["countries"]))
            query += f" AND r.country IN ({placeholders})"
            params.extend(data["countries"])

        # Group by for aggregate functions
        query += " GROUP BY r.id, r.name, r.road_type, r.country, reg.name, reg.id"

        # Add pagination
        limit = min(int(data.get("limit", 100)), 1000)  # Max 1000 results
        offset = int(data.get("offset", 0))
        query += " ORDER BY r.name LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        # Log the query and params for debugging
        logger.info(f"Search query: {query}")
        logger.info(f"Search params: {params}")

        # Execute query
        with get_cockroach_connection() as cockroach_conn:
            with cockroach_conn.cursor() as cursor:
                cursor.execute(query, tuple(params))
                roads = cursor.fetchall()

                # Get column names
                column_names = [desc[0] for desc in cursor.description]

                # Format results as list of dictionaries
                result = []
                for road in roads:
                    road_dict = dict(zip(column_names, road))
                    result.append(road_dict)

        # Return results
        return jsonify({
            "roads": result,
            "count": len(result),
            "limit": limit,
            "offset": offset
        }), 200

    except Exception as e:
        logger.error(f"Error searching roads: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@osm_blueprint.route('/roads/in-bounds', methods=['POST'])
def get_roads_in_bounds():
    """Get roads within a bounding box"""
    cockroach_conn = None
    try:
        data = request.json
        if not data or 'bounds' not in data:
            return jsonify({"error": "Missing bounding box coordinates"}), 400

        # Extract bounding box coordinates [south, west, north, east]
        bounds = data['bounds']
        if len(bounds) != 4:
            return jsonify({"error": "Invalid bounding box format. Expected [south, west, north, east]"}), 400

        # Extract parameters
        south, west, north, east = bounds
        limit = min(int(data.get('limit', 100)), 100000)  # Max 1000 results to prevent performance issues

        # Optional road type filter
        road_types = data.get('roadTypes', [])

        # Build query - find the road segments first, then join with roads
        query = """
        SELECT DISTINCT r.id, r.name, r.road_type, r.country, reg.name as region_name,
               rs.segment_id, rs.geometry
        FROM road_segments rs
        JOIN roads r ON rs.road_id = r.id
        LEFT JOIN regions reg ON r.region_id = reg.id
        WHERE ST_Intersects(
            ST_GeomFromGeoJSON(rs.geometry),
            ST_MakeEnvelope(%s, %s, %s, %s, 4326)
        )
        """

        params = [west, south, east, north]  # Note: ST_MakeEnvelope expects (xmin, ymin, xmax, ymax)

        # Add optional road type filter
        if road_types:
            placeholders = ", ".join(["%s"] * len(road_types))
            query += f" AND r.road_type IN ({placeholders})"
            params.extend(road_types)

        # Add limit
        query += " LIMIT %s"
        params.append(limit)

        # Log what we're doing
        logger.info(f"Fetching roads in bounds: {bounds}")
        logger.debug(f"Query: {query}")
        logger.debug(f"Params: {params}")

        # Execute query
        result = []
        cockroach_conn = get_cockroach_connection()
        with cockroach_conn.cursor() as cursor:
            cursor.execute(query, params)
            roads = cursor.fetchall()

            # Get column names
            column_names = [desc[0] for desc in cursor.description]

            # Format results
            for road in roads:
                road_dict = dict(zip(column_names, road))

                # Parse GeoJSON for geometry
                if road_dict["geometry"]:
                    try:
                        road_dict["geometry"] = json.loads(road_dict["geometry"])
                    except:
                        pass  # Keep it as string if parsing fails

                result.append(road_dict)

        # Count roads by type for informational purposes
        road_types_count = {}
        for road in result:
            road_type = road.get("road_type", "unknown")
            road_types_count[road_type] = road_types_count.get(road_type, 0) + 1

        logger.info(f"Returning {len(result)} roads within bounds. Types: {road_types_count}")

        return jsonify({
            "roads": result,
            "count": len(result),
            "limit": limit
        }), 200

    except Exception as e:
        logger.error(f"Error fetching roads in bounds: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500
    finally:
        # Ensure connection is always released back to the pool
        if cockroach_conn:
            release_cockroach_connection(cockroach_conn)

@osm_blueprint.route('/route-segments', methods=['POST'])
def get_route_segments():
    """Find road segments in the database that match a given route"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No route data provided"}), 400

        # Extract route parameters
        origin = data.get('origin')
        destination = data.get('destination')
        route_geometry = data.get('route_geometry')

        if not route_geometry or not origin or not destination:
            return jsonify({"error": "Missing route parameters"}), 400

        # Create a buffer around the route to find intersecting segments
        # We'll use a simplified approach - using the route coordinates
        # to create a polygon that we can use to find intersecting segments

        # Extract route coordinates
        coordinates = route_geometry.get('coordinates', [])
        if not coordinates or len(coordinates) < 2:
            return jsonify({"error": "Invalid route geometry"}), 400

        # Create a LineString from the coordinates
        linestring = {
            "type": "LineString",
            "coordinates": coordinates
        }

        # Calculate buffer distance - a reasonable value in meters
        buffer_distance = 50  # meters

        with get_cockroach_connection() as cockroach_conn:
            with cockroach_conn.cursor() as cursor:
                # Find all segments that intersect with our route buffer
                # We use ST_DWithin to create a buffer around our route
                query = """
                    SELECT rs.segment_id, rs.road_id, rs.geometry, rs.length_meters,
                           rs.osm_way_id, r.name as road_name, r.road_type
                    FROM road_segments rs
                    JOIN roads r ON rs.road_id = r.id
                    WHERE ST_DWithin(
                        ST_GeomFromGeoJSON(%s),
                        ST_GeomFromGeoJSON(rs.geometry),
                        %s
                    )
                """
                cursor.execute(query, (json.dumps(linestring), buffer_distance))

                segments = cursor.fetchall()

                # Format results as list of dictionaries
                column_names = ["id", "road_id", "geometry", "length_meters",
                               "osm_way_id", "road_name", "road_type"]
                result = []

                total_length = 0
                route_length = 0

                # Calculate approximate route length
                if len(coordinates) > 1:
                    # Simple implementation - straight line distance between points
                    for i in range(len(coordinates) - 1):
                        pt1 = coordinates[i]
                        pt2 = coordinates[i + 1]
                        # Rough distance calculation in meters
                        route_length += calculate_distance(
                            pt1[1], pt1[0], pt2[1], pt2[0]
                        )

                # Process segments
                for segment in segments:
                    segment_dict = dict(zip(column_names, segment))

                    # Parse geometry JSON
                    if segment_dict["geometry"]:
                        try:
                            segment_dict["geometry"] = json.loads(segment_dict["geometry"])
                        except:
                            pass

                    # Add to result and track length
                    if segment_dict["length_meters"]:
                        total_length += segment_dict["length_meters"]

                    result.append(segment_dict)

                # Calculate coverage percentage
                coverage_percent = 0
                if route_length > 0:
                    coverage_percent = min(100, (total_length / route_length) * 100)

        return jsonify({
            "segments": result,
            "count": len(result),
            "total_length_meters": total_length,
            "route_length_meters": route_length,
            "coverage_percent": coverage_percent
        }), 200

    except Exception as e:
        logger.error(f"Error finding route segments: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@osm_blueprint.route('/road-segments/by-node-ids', methods=['POST'])
def get_road_segments_by_node_ids():
    """Get road segments from the database that connect to the given OSM node IDs"""
    try:
        data = request.json
        if not data or 'node_ids' not in data:
            return jsonify({"error": "No node IDs provided"}), 400

        node_ids = data.get('node_ids', [])
        if not node_ids:
            return jsonify({"error": "Empty node_ids list"}), 400

        # Limit the number of node IDs to prevent overloading the DB
        max_ids = 10000
        if len(node_ids) > max_ids:
            logger.warning(f"Too many node IDs ({len(node_ids)}), limiting to {max_ids}")
            node_ids = node_ids[:max_ids]

        logger.info(f"Searching for road segments matching {len(node_ids)} OSM node IDs")

        with get_cockroach_connection() as cockroach_conn:
            with cockroach_conn.cursor() as cursor:
                # Find all road segments that have any of the given node IDs as start or end nodes
                query = """
                    SELECT rs.segment_id, rs.road_id, rs.osm_way_id, rs.geometry,
                           rs.start_node_id, rs.end_node_id, rs.length_meters,
                           r.name as road_name, r.road_type
                    FROM road_segments rs
                    JOIN roads r ON rs.road_id = r.id
                    WHERE rs.start_node_id IN %s OR rs.end_node_id IN %s
                """

                # Execute the query with node IDs as tuple parameters for both start and end nodes
                cursor.execute(query, (tuple(node_ids), tuple(node_ids)))
                segments = cursor.fetchall()

                # Format results
                column_names = ["id", "road_id", "osm_way_id", "geometry",
                               "start_node_id", "end_node_id", "length_meters",
                               "road_name", "road_type"]

                result = []
                matched_nodes = set()  # Keep track of which nodes we actually found

                for segment in segments:
                    segment_dict = dict(zip(column_names, segment))

                    # Track which nodes were actually matched
                    if segment_dict["start_node_id"] in node_ids:
                        matched_nodes.add(segment_dict["start_node_id"])
                    if segment_dict["end_node_id"] in node_ids:
                        matched_nodes.add(segment_dict["end_node_id"])

                    # Parse geometry JSON
                    if segment_dict["geometry"]:
                        try:
                            segment_dict["geometry"] = json.loads(segment_dict["geometry"])
                        except:
                            pass

                    result.append(segment_dict)

        # Return the results with statistics
        return jsonify({
            "segments": result,
            "count": len(result),
            "nodes_matched": len(matched_nodes),
            "nodes_requested": len(node_ids),
            "coverage_percent": (len(matched_nodes) / len(node_ids) * 100) if node_ids else 0
        }), 200

    except Exception as e:
        logger.error(f"Error fetching road segments by node IDs: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

# Helper function for distance calculation
def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance between two points on earth (specified in decimal degrees)"""
    import math

    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371000  # Radius of earth in meters

    return c * r