from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import psycopg2
import json
import logging

from app.db import cockroach_conn
from app.user_routes import session_required

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

osm_blueprint = Blueprint('osm', __name__)

@osm_blueprint.route('/roads', methods=['GET'])
def get_roads():
    """Get roads with filtering options"""
    try:
        # Parse query parameters
        road_type = request.args.get('type')
        country = request.args.get('country')
        region = request.args.get('region')
        name_query = request.args.get('name')
        limit = min(int(request.args.get('limit', 100)), 1000)  # Max 1000 results
        offset = int(request.args.get('offset', 0))

        # Build query dynamically
        query = "SELECT id, name, road_type, country, region FROM osm_roads WHERE 1=1"
        params = []

        if road_type:
            query += " AND road_type = %s"
            params.append(road_type)

        if country:
            query += " AND country = %s"
            params.append(country)

        if region:
            query += " AND region = %s"
            params.append(region)

        if name_query:
            query += " AND name ILIKE %s"
            params.append(f"%{name_query}%")

        # Add pagination
        query += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        # Execute query
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
    """Get details for a specific road by ID"""
    try:
        with cockroach_conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, name, road_type, country, region, geometry, tags FROM osm_roads WHERE id = %s",
                (road_id,)
            )
            road = cursor.fetchone()

        if not road:
            return jsonify({"error": "Road not found"}), 404

        # Format result
        column_names = ["id", "name", "road_type", "country", "region", "geometry", "tags"]
        road_dict = dict(zip(column_names, road))

        # Parse GeoJSON and tags if they exist
        if road_dict["geometry"]:
            try:
                road_dict["geometry"] = json.loads(road_dict["geometry"])
            except:
                pass

        if road_dict["tags"]:
            try:
                road_dict["tags"] = json.loads(road_dict["tags"])
            except:
                pass

        return jsonify(road_dict), 200

    except Exception as e:
        logger.error(f"Error fetching road {road_id}: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@osm_blueprint.route('/roads/search', methods=['POST'])
def search_roads():
    """Advanced search for roads"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No search criteria provided"}), 400

        # Build query dynamically
        query = "SELECT id, name, road_type, country, region FROM osm_roads WHERE 1=1"
        params = []

        # Process different search criteria
        if "boundingBox" in data:
            # Format: [min_lat, min_lon, max_lat, max_lon] in the request
            # But ST_MakeEnvelope expects [min_lon, min_lat, max_lon, max_lat]
            bb = data["boundingBox"]
            # Reorder coordinates for ST_MakeEnvelope (xmin, ymin, xmax, ymax)
            bbox_coords = [bb[1], bb[0], bb[3], bb[2]]
            # Use ST_Intersects on the geometry column (cast the geometry column from its text representation)
            query += " AND ST_Intersects(ST_GeomFromGeoJSON(geometry), ST_MakeEnvelope(%s, %s, %s, %s, 4326))"
            params.extend(bbox_coords)

        # Add point-based search
        elif "point" in data:
            # Data should contain point [lat, lng] and radius in meters
            point = data["point"]
            radius = data.get("radius", 20)  # Default 20 meters if not specified

            # Create a point and buffer using ST_DWithin
            # ST_DWithin(geometry A, geometry B, distance)
            # Convert from lat/lng to point format (lng, lat) for PostGIS
            query += " AND ST_DWithin(ST_GeomFromGeoJSON(geometry), ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s)"

            # Add parameters: longitude first, then latitude, then radius (in meters)
            params.extend([point[1], point[0], radius])

            # Sort by distance to the clicked point to get closest roads first
            query += " ORDER BY ST_Distance(ST_GeomFromGeoJSON(geometry), ST_SetSRID(ST_MakePoint(%s, %s), 4326))"
            params.extend([point[1], point[0]])

        if "roadTypes" in data and data["roadTypes"]:
            placeholders = ", ".join(["%s"] * len(data["roadTypes"]))
            query += f" AND road_type IN ({placeholders})"
            params.extend(data["roadTypes"])

        if "countries" in data and data["countries"]:
            placeholders = ", ".join(["%s"] * len(data["countries"]))
            query += f" AND country IN ({placeholders})"
            params.extend(data["countries"])

        # Add pagination
        limit = min(int(data.get("limit", 100)), 1000)  # Max 1000 results
        offset = int(data.get("offset", 0))
        query += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        # Log the query and params for debugging
        logger.info(f"Search query: {query}")
        logger.info(f"Search params: {params}")

        # Execute query
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
        limit = min(int(data.get('limit', 100)), 1000)  # Max 1000 results to prevent performance issues

        # Optional road type filter
        road_types = data.get('roadTypes', [])

        # Build query
        query = """
        SELECT id, name, road_type, country, region, geometry
        FROM osm_roads
        WHERE ST_Intersects(
            ST_GeomFromGeoJSON(geometry),
            ST_MakeEnvelope(%s, %s, %s, %s, 4326)
        )
        """

        params = [west, south, east, north]  # Note: ST_MakeEnvelope expects (xmin, ymin, xmax, ymax)

        # Add optional road type filter
        if road_types:
            placeholders = ", ".join(["%s"] * len(road_types))
            query += f" AND road_type IN ({placeholders})"
            params.extend(road_types)

        # Add limit
        query += " LIMIT %s"
        params.append(limit)

        # Log what we're doing
        logger.info(f"Fetching roads in bounds: {bounds}")
        logger.debug(f"Query: {query}")
        logger.debug(f"Params: {params}")

        # Execute query
        with cockroach_conn.cursor() as cursor:
            cursor.execute(query, params)
            roads = cursor.fetchall()

            # Get column names
            column_names = [desc[0] for desc in cursor.description]

            # Format results
            result = []
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