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

@osm_blueprint.route('/get-all-roads', methods=['GET'])
def get_all_roads():
    """Get all roads with their segments"""
    try:
        with get_cockroach_connection() as cockroach_conn:
            with cockroach_conn.cursor() as cursor:
                # Get all roads
                cursor.execute(
                    """
                    SELECT r.id, r.name, r.road_type, r.country,
                           reg.name as region_name, r.tags
                    FROM roads r
                    LEFT JOIN regions reg ON r.region_id = reg.id
                    """
                )
                roads = cursor.fetchall()

                # Format results
                road_column_names = ["id", "name", "road_type", "country", "region_name", "tags"]
                result = []

                for road in roads:
                    road_dict = dict(zip(road_column_names, road))

                    # Parse tags if they exist
                    if road_dict["tags"]:
                        try:
                            road_dict["tags"] = json.loads(road_dict["tags"])
                        except:
                            pass

                    # Get segments for this road
                    cursor.execute(
                        """
                        SELECT segment_id, osm_way_id, geometry, length_meters,
                               start_node_id, end_node_id, tags
                        FROM road_segments
                        WHERE road_id = %s
                        """,
                        (road_dict["id"],)
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

                    result.append(road_dict)

        return jsonify({
            "roads": result,
            "count": len(result)
        }), 200

    except Exception as e:
        logger.error(f"Error fetching all roads: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500
    finally:
        # Ensure a response is always returned, even if connection fails
        if 'result' not in locals():
            return jsonify({"error": "Failed to fetch roads data", "roads": [], "count": 0}), 500

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
        max_ids = 100000
        if len(node_ids) > max_ids:
            logger.warning(f"Too many node IDs ({len(node_ids)}), limiting to {max_ids}")
            node_ids = node_ids[:max_ids]

        logger.info(f"Searching for road segments matching {len(node_ids)} OSM node IDs")

        with get_cockroach_connection() as cockroach_conn:
            with cockroach_conn.cursor() as cursor:
                # Find all road segments that have any of the given node IDs as start or end nodes
                query = """
                    SELECT rs.segment_id, rs.road_id, rs.osm_way_id, rs.geometry,
                           rs.start_node_id, rs.end_node_id, rs.length_meters, rs.tags,
                           r.name as road_name, r.road_type, r.country
                    FROM road_segments rs
                    JOIN roads r ON rs.road_id = r.id
                    WHERE rs.start_node_id IN %s OR rs.end_node_id IN %s
                """

                # Execute the query with node IDs as tuple parameters for both start and end nodes
                cursor.execute(query, (tuple(node_ids), tuple(node_ids)))
                segments = cursor.fetchall()

                # Format results
                column_names = ["id", "road_id", "osm_way_id", "geometry",
                               "start_node_id", "end_node_id", "length_meters", "tags",
                               "road_name", "road_type", "country"]

                # Group segments by road
                roads_dict = {}  # Use a dictionary to group segments by road_id
                matched_nodes = set()  # Keep track of which nodes we actually found
                total_length = 0

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
                        except Exception as e:
                            logger.warning(f"Failed to parse geometry JSON for segment {segment_dict['id']}: {str(e)}")

                    # Parse tags JSON
                    if segment_dict["tags"]:
                        try:
                            segment_dict["tags"] = json.loads(segment_dict["tags"])
                        except Exception as e:
                            logger.warning(f"Failed to parse tags JSON for segment {segment_dict['id']}: {str(e)}")

                    # Add segment length to total
                    if segment_dict["length_meters"]:
                        total_length += segment_dict["length_meters"]

                    # Add to the appropriate road in the dictionary
                    road_id = segment_dict["road_id"]
                    if road_id not in roads_dict:
                        roads_dict[road_id] = {
                            "id": road_id,
                            "name": segment_dict["road_name"],
                            "road_type": segment_dict["road_type"],
                            "country": segment_dict["country"],
                            "segments": []
                        }

                    # Remove road details from segment to avoid duplication
                    segment_data = {k: v for k, v in segment_dict.items()
                                  if k not in ["road_name", "road_type", "country"]}

                    # Add to the road's segments array
                    roads_dict[road_id]["segments"].append(segment_data)

                # Convert the dictionary to a list
                roads_list = list(roads_dict.values())

                # Calculate segment count for each road
                for road in roads_list:
                    road["segment_count"] = len(road["segments"])

                # Log some debug info
                logger.info(f"Found {len(roads_list)} roads with {len(segments)} segments matching {len(matched_nodes)} nodes")

        # Return the results with statistics
        return jsonify({
            "roads": roads_list,
            "count": len(segments),
            "road_count": len(roads_list),
            "nodes_matched": len(matched_nodes),
            "nodes_requested": len(node_ids),
            "coverage_percent": (len(matched_nodes) / len(node_ids) * 100) if node_ids else 0,
            "total_length_meters": total_length
        }), 200

    except Exception as e:
        logger.error(f"Error fetching road segments by node IDs: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500
