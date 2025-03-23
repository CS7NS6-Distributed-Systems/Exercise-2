from flask import Blueprint, request, jsonify, render_template, redirect, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
import psycopg2
from datetime import datetime
import json
import uuid
from functools import wraps

from app.db import get_cockroach_connection, release_cockroach_connection
from app.user_routes import session_required
from app.const import ERROR_UNEXPECTED, ERROR_DATABASE, ERROR_UNAUTHORIZED_ACCESS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

admin_blueprint = Blueprint('admin', __name__, url_prefix='/admin')

# Middleware to check if user is admin
def admin_required(fn):
    @session_required
    @wraps(fn)
    def decorated_fn(*args, **kwargs):
        username = get_jwt_identity()

        cockroach_conn = get_cockroach_connection()
        try:
            with cockroach_conn.cursor() as cursor:
                cursor.execute("SELECT is_admin FROM users WHERE username = %s", (username,))
                user_record = cursor.fetchone()

                if not user_record or not user_record[0]:
                    return jsonify({"error": ERROR_UNAUTHORIZED_ACCESS, "message": "Admin privileges required"}), 403

                return fn(*args, **kwargs)
        except Exception as e:
            logger.error(f"Admin check error: {str(e)}")
            return jsonify({"error": ERROR_UNEXPECTED, "details": str(e)}), 500
        finally:
            release_cockroach_connection(cockroach_conn)
    return decorated_fn

    try:
        return render_template('admin/dashboard.html')
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        return jsonify({"error": ERROR_UNEXPECTED, "details": str(e)}), 500

# === Bookings Management ===
@admin_blueprint.route('/bookings', methods=['GET'])
@admin_required
def list_bookings():
    try:
        cockroach_conn = get_cockroach_connection()
        with cockroach_conn.cursor() as cursor:
            cursor.execute("""
                SELECT b.booking_id, b.user_id, u.username,
                       b.origin, b.destination, b.booking_timestamp,
                       COUNT(bl.booking_line_id) as lines_count
                FROM bookings b
                JOIN users u ON b.user_id = u.id
                LEFT JOIN booking_lines bl ON b.booking_id = bl.booking_id
                GROUP BY b.booking_id, b.user_id, u.username, b.origin, b.destination, b.booking_timestamp
                ORDER BY b.booking_timestamp DESC
                LIMIT 100
            """)
            bookings = cursor.fetchall()

            # Convert to list of dicts for JSON response
            booking_list = []
            for booking in bookings:
                booking_list.append({
                    "booking_id": booking[0],
                    "user_id": booking[1],
                    "username": booking[2],
                    "origin": booking[3],
                    "destination": booking[4],
                    "booking_timestamp": booking[5].isoformat(),
                    "lines_count": booking[6]
                })

            return jsonify(booking_list)
    except Exception as e:
        logger.error(f"List bookings error: {str(e)}")
        return jsonify({"error": ERROR_UNEXPECTED, "details": str(e)}), 500
    finally:
        release_cockroach_connection(cockroach_conn)

@admin_blueprint.route('/bookings/<booking_id>', methods=['GET'])
@admin_required
def get_booking(booking_id):
    try:
        cockroach_conn = get_cockroach_connection()
        with cockroach_conn.cursor() as cursor:
            # Get booking details
            cursor.execute("""
                SELECT b.booking_id, b.user_id, u.username,
                       u.givennames, u.lastname,
                       b.origin, b.destination, b.booking_timestamp
                FROM bookings b
                JOIN users u ON b.user_id = u.id
                WHERE b.booking_id = %s
            """, (booking_id,))
            booking = cursor.fetchone()

            if not booking:
                return jsonify({"error": "Booking not found"}), 404

            booking_data = {
                "booking_id": booking[0],
                "user_id": booking[1],
                "username": booking[2],
                "givennames": booking[3],
                "lastname": booking[4],
                "origin": booking[5],
                "destination": booking[6],
                "booking_timestamp": booking[7].isoformat()
            }

            # Get booking lines
            cursor.execute("""
                SELECT bl.booking_line_id, bl.road_booking_slot_id,
                       r.name as road_name, rbs.slot_time,
                       bl.quantity
                FROM booking_lines bl
                JOIN road_booking_slots rbs ON bl.road_booking_slot_id = rbs.road_booking_slot_id
                JOIN roads r ON rbs.road_id = r.id
                WHERE bl.booking_id = %s
                ORDER BY rbs.slot_time ASC
            """, (booking_id,))
            lines = cursor.fetchall()

            booking_data["lines"] = []
            for line in lines:
                booking_data["lines"].append({
                    "booking_line_id": line[0],
                    "road_booking_slot_id": line[1],
                    "road_name": line[2],
                    "slot_time": line[3].isoformat(),
                    "quantity": line[4]
                })

            return jsonify(booking_data)
    except Exception as e:
        logger.error(f"Get booking error: {str(e)}")
        return jsonify({"error": ERROR_UNEXPECTED, "details": str(e)}), 500
    finally:
        release_cockroach_connection(cockroach_conn)

@admin_blueprint.route('/bookings/<booking_id>', methods=['DELETE'])
@admin_required
def delete_booking(booking_id):
    try:
        cockroach_conn = get_cockroach_connection()
        try:
            with cockroach_conn.cursor() as cursor:
                # Find all booking lines to update available capacity
                cursor.execute("""
                    SELECT bl.booking_line_id, bl.road_booking_slot_id, bl.quantity
                    FROM booking_lines bl
                    WHERE bl.booking_id = %s
                """, (booking_id,))
                booking_lines = cursor.fetchall()

                if not booking_lines:
                    # Check if booking exists at all
                    cursor.execute("SELECT booking_id FROM bookings WHERE booking_id = %s", (booking_id,))
                    if not cursor.fetchone():
                        return jsonify({"error": "Booking not found"}), 404

                # Update available capacity for each slot
                for line in booking_lines:
                    line_id, slot_id, quantity = line
                    cursor.execute("""
                        UPDATE road_booking_slots
                        SET available_capacity = available_capacity + %s
                        WHERE road_booking_slot_id = %s
                    """, (quantity, slot_id))

                    # Delete the booking line
                    cursor.execute("DELETE FROM booking_lines WHERE booking_line_id = %s", (line_id,))

                # Delete the booking
                cursor.execute("DELETE FROM bookings WHERE booking_id = %s", (booking_id,))

                cockroach_conn.commit()

                return jsonify({
                    "message": "Booking deleted successfully",
                    "lines_deleted": len(booking_lines)
                }), 200

        except psycopg2.Error as e:
            cockroach_conn.rollback()
            logger.error(f"Database error: {str(e)}")
            return jsonify({"error": ERROR_DATABASE, "details": str(e)}), 500
    except Exception as e:
        logger.error(f"Delete booking error: {str(e)}")
        return jsonify({"error": ERROR_UNEXPECTED, "details": str(e)}), 500
    finally:
        release_cockroach_connection(cockroach_conn)

@admin_blueprint.route('/stats', methods=['GET'])
@admin_required
def get_admin_stats():
    try:
        cockroach_conn = get_cockroach_connection()
        try:
            with cockroach_conn.cursor() as cursor:
                # Get total roads
                cursor.execute("SELECT COUNT(*) FROM roads")
                total_roads = cursor.fetchone()[0]

                # Get total road booking slots
                cursor.execute("SELECT COUNT(*) FROM road_booking_slots")
                total_slots = cursor.fetchone()[0]

                # Get total bookings
                cursor.execute("SELECT COUNT(*) FROM bookings")
                total_bookings = cursor.fetchone()[0]

                # Get total booking lines
                cursor.execute("SELECT COUNT(*) FROM booking_lines")
                total_booking_lines = cursor.fetchone()[0]

                # Get total users
                cursor.execute("SELECT COUNT(*) FROM users")
                total_users = cursor.fetchone()[0]

                return jsonify({
                    "total_roads": total_roads,
                    "total_slots": total_slots,
                    "total_bookings": total_bookings,
                    "total_booking_lines": total_booking_lines,
                    "total_users": total_users
                })
        except psycopg2.Error as e:
            logger.error(f"Database error: {str(e)}")
            return jsonify({"error": ERROR_DATABASE, "details": str(e)}), 500
    except Exception as e:
        logger.error(f"Get admin stats error: {str(e)}")
        return jsonify({"error": ERROR_UNEXPECTED, "details": str(e)}), 500
    finally:
        release_cockroach_connection(cockroach_conn)

# === Road Management ===
@admin_blueprint.route('/roads', methods=['GET'])
@admin_required
def list_roads():
    try:
        # Get query parameters for pagination
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        search = request.args.get('search', '')

        offset = (page - 1) * per_page

        cockroach_conn = get_cockroach_connection()
        with cockroach_conn.cursor() as cursor:
            # Base query with search condition
            base_query = """
                FROM roads r
                LEFT JOIN regions reg ON r.region_id = reg.id
                WHERE r.name ILIKE %s OR reg.name ILIKE %s
            """
            search_param = f"%{search}%" if search else "%%"

            # Count total matching roads
            cursor.execute(f"SELECT COUNT(*) {base_query}", (search_param, search_param))
            total_count = cursor.fetchone()[0]

            # Get paginated road data
            cursor.execute(f"""
                SELECT r.id, r.name, r.road_type, r.country,
                       reg.name as region_name, r.hourly_capacity,
                       r.created_at
                {base_query}
                ORDER BY r.name
                LIMIT %s OFFSET %s
            """, (search_param, search_param, per_page, offset))

            roads = cursor.fetchall()

            # Convert to list of dicts for JSON response
            road_list = []
            for road in roads:
                road_list.append({
                    "id": road[0],
                    "name": road[1],
                    "road_type": road[2],
                    "country": road[3],
                    "region": road[4],
                    "hourly_capacity": road[5],
                    "created_at": road[6].isoformat() if road[6] else None
                })

            return jsonify({
                "roads": road_list,
                "total": total_count,
                "page": page,
                "per_page": per_page,
                "total_pages": (total_count + per_page - 1) // per_page
            })
    except Exception as e:
        logger.error(f"List roads error: {str(e)}")
        return jsonify({"error": ERROR_UNEXPECTED, "details": str(e)}), 500
    finally:
        release_cockroach_connection(cockroach_conn)

@admin_blueprint.route('/roads/<road_id>', methods=['GET'])
@admin_required
def get_road(road_id):
    try:
        cockroach_conn = get_cockroach_connection()
        with cockroach_conn.cursor() as cursor:
            # Get road details
            cursor.execute("""
                SELECT r.id, r.osm_id, r.name, r.road_type, r.country,
                       reg.id as region_id, reg.name as region_name,
                       r.tags, r.hourly_capacity, r.created_at
                FROM roads r
                LEFT JOIN regions reg ON r.region_id = reg.id
                WHERE r.id = %s
            """, (road_id,))

            road = cursor.fetchone()
            if not road:
                return jsonify({"error": "Road not found"}), 404

            road_data = {
                "id": road[0],
                "osm_id": road[1],
                "name": road[2],
                "road_type": road[3],
                "country": road[4],
                "region_id": road[5],
                "region_name": road[6],
                "tags": road[7],
                "hourly_capacity": road[8],
                "created_at": road[9].isoformat() if road[9] else None
            }

            # Get segments for this road
            cursor.execute("""
                SELECT segment_id, osm_way_id, geometry, length_meters,
                       start_node_id, end_node_id
                FROM road_segments
                WHERE road_id = %s
                LIMIT 50
            """, (road_id,))

            segments = cursor.fetchall()
            road_data["segments"] = []

            for segment in segments:
                road_data["segments"].append({
                    "segment_id": segment[0],
                    "osm_way_id": segment[1],
                    "geometry": segment[2],
                    "length_meters": segment[3],
                    "start_node_id": segment[4],
                    "end_node_id": segment[5]
                })

            # Get booking slot information
            cursor.execute("""
                SELECT COUNT(*), MIN(slot_time), MAX(slot_time)
                FROM road_booking_slots
                WHERE road_id = %s
            """, (road_id,))

            slots_info = cursor.fetchone()
            road_data["booking_slots"] = {
                "count": slots_info[0],
                "earliest_slot": slots_info[1].isoformat() if slots_info[1] else None,
                "latest_slot": slots_info[2].isoformat() if slots_info[2] else None
            }

            return jsonify(road_data)
    except Exception as e:
        logger.error(f"Get road error: {str(e)}")
        return jsonify({"error": ERROR_UNEXPECTED, "details": str(e)}), 500
    finally:
        release_cockroach_connection(cockroach_conn)

@admin_blueprint.route('/roads/<road_id>', methods=['PUT'])
@admin_required
def update_road(road_id):
    try:
        data = request.json

        if not data:
            return jsonify({"error": "No data provided"}), 400

        cockroach_conn = get_cockroach_connection()
        try:
            with cockroach_conn.cursor() as cursor:
                # Check if road exists
                cursor.execute("SELECT id FROM roads WHERE id = %s", (road_id,))
                if not cursor.fetchone():
                    return jsonify({"error": "Road not found"}), 404

                # Build update query based on provided fields
                update_fields = []
                params = []

                if 'name' in data:
                    update_fields.append("name = %s")
                    params.append(data['name'])

                if 'hourly_capacity' in data:
                    new_capacity = int(data['hourly_capacity'])
                    if new_capacity < 1:
                        return jsonify({"error": "Hourly capacity must be at least 1"}), 400
                    update_fields.append("hourly_capacity = %s")
                    params.append(new_capacity)

                if 'road_type' in data:
                    update_fields.append("road_type = %s")
                    params.append(data['road_type'])

                if 'tags' in data:
                    update_fields.append("tags = %s")
                    params.append(json.dumps(data['tags']))

                if not update_fields:
                    return jsonify({"message": "No fields to update"}), 200

                # Execute update
                query = f"UPDATE roads SET {', '.join(update_fields)} WHERE id = %s"
                params.append(road_id)

                cursor.execute(query, params)
                cockroach_conn.commit()

                return jsonify({"message": "Road updated successfully"}), 200

        except psycopg2.Error as e:
            cockroach_conn.rollback()
            logger.error(f"Database error: {str(e)}")
            return jsonify({"error": ERROR_DATABASE, "details": str(e)}), 500
    except Exception as e:
        logger.error(f"Update road error: {str(e)}")
        return jsonify({"error": ERROR_UNEXPECTED, "details": str(e)}), 500
    finally:
        release_cockroach_connection(cockroach_conn)

@admin_blueprint.route('/road-segments/<segment_id>', methods=['GET'])
@admin_required
def get_road_segment(segment_id):
    try:
        cockroach_conn = get_cockroach_connection()
        with cockroach_conn.cursor() as cursor:
            cursor.execute("""
                SELECT rs.segment_id, rs.road_id, r.name as road_name,
                       rs.geometry, rs.length_meters, rs.start_node_id, rs.end_node_id
                FROM road_segments rs
                JOIN roads r ON rs.road_id = r.id
                WHERE rs.segment_id = %s
            """, (segment_id,))
            segment = cursor.fetchone()

            if not segment:
                return jsonify({"error": "Road segment not found"}), 404

            segment_data = {
                "segment_id": segment[0],
                "road_id": segment[1],
                "road_name": segment[2],
                "geometry": segment[3],
                "length_meters": segment[4],
                "start_node_id": segment[5],
                "end_node_id": segment[6]
            }

            return jsonify(segment_data)
    except Exception as e:
        logger.error(f"Get road segment error: {str(e)}")
        return jsonify({"error": ERROR_UNEXPECTED, "details": str(e)}), 500
    finally:
        release_cockroach_connection(cockroach_conn)

# === Booking Slots Management ===
@admin_blueprint.route('/booking-slots', methods=['GET'])
@admin_required
def list_booking_slots():
    try:
        # Get query parameters for pagination and filtering
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        road_id = request.args.get('road_id')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')

        offset = (page - 1) * per_page

        cockroach_conn = get_cockroach_connection()
        with cockroach_conn.cursor() as cursor:
            # Construct query based on filters
            query_params = []
            filter_conditions = []

            if road_id:
                filter_conditions.append("rbs.road_id = %s")
                query_params.append(road_id)

            if date_from:
                filter_conditions.append("rbs.slot_time >= %s")
                query_params.append(date_from)

            if date_to:
                filter_conditions.append("rbs.slot_time <= %s")
                query_params.append(date_to)

            where_clause = ("WHERE " + " AND ".join(filter_conditions)) if filter_conditions else ""

            # Count total matching slots
            count_query = f"""
                SELECT COUNT(*)
                FROM road_booking_slots rbs
                JOIN roads r ON rbs.road_id = r.id
                {where_clause}
            """
            cursor.execute(count_query, query_params)
            total_count = cursor.fetchone()[0]

            # Get paginated slot data
            data_query = f"""
                SELECT rbs.road_booking_slot_id, rbs.road_id, r.name as road_name,
                       rbs.slot_time, rbs.capacity, rbs.available_capacity,
                       rbs.created_at
                FROM road_booking_slots rbs
                JOIN roads r ON rbs.road_id = r.id
                {where_clause}
                ORDER BY rbs.slot_time ASC
                LIMIT %s OFFSET %s
            """
            query_params.extend([per_page, offset])

            cursor.execute(data_query, query_params)
            slots = cursor.fetchall()

            # Convert to list of dicts for JSON response
            slot_list = []
            for slot in slots:
                slot_list.append({
                    "road_booking_slot_id": slot[0],
                    "road_id": slot[1],
                    "road_name": slot[2],
                    "slot_time": slot[3].isoformat(),
                    "capacity": slot[4],
                    "available_capacity": slot[5],
                    "created_at": slot[6].isoformat() if slot[6] else None,
                    "booked": slot[4] - slot[5]
                })

            return jsonify({
                "booking_slots": slot_list,
                "total": total_count,
                "page": page,
                "per_page": per_page,
                "total_pages": (total_count + per_page - 1) // per_page
            })
    except Exception as e:
        logger.error(f"List booking slots error: {str(e)}")
        return jsonify({"error": ERROR_UNEXPECTED, "details": str(e)}), 500
    finally:
        release_cockroach_connection(cockroach_conn)

@admin_blueprint.route('/booking-slots/<slot_id>', methods=['GET'])
@admin_required
def get_booking_slot(slot_id):
    try:
        cockroach_conn = get_cockroach_connection()
        with cockroach_conn.cursor() as cursor:
            # Get slot details
            cursor.execute("""
                SELECT rbs.road_booking_slot_id, rbs.road_id, r.name as road_name,
                       rbs.slot_time, rbs.capacity, rbs.available_capacity,
                       rbs.created_at
                FROM road_booking_slots rbs
                JOIN roads r ON rbs.road_id = r.id
                WHERE rbs.road_booking_slot_id = %s
            """, (slot_id,))

            slot = cursor.fetchone()
            if not slot:
                return jsonify({"error": "Booking slot not found"}), 404

            slot_data = {
                "road_booking_slot_id": slot[0],
                "road_id": slot[1],
                "road_name": slot[2],
                "slot_time": slot[3].isoformat(),
                "capacity": slot[4],
                "available_capacity": slot[5],
                "created_at": slot[6].isoformat() if slot[6] else None,
                "booked": slot[4] - slot[5]
            }

            # Get bookings using this slot
            cursor.execute("""
                SELECT bl.booking_line_id, bl.booking_id, bl.quantity,
                       b.user_id, u.username
                FROM booking_lines bl
                JOIN bookings b ON bl.booking_id = b.booking_id
                JOIN users u ON b.user_id = u.id
                WHERE bl.road_booking_slot_id = %s
                ORDER BY bl.booking_line_id
            """, (slot_id,))

            bookings = cursor.fetchall()
            slot_data["bookings"] = []

            for booking in bookings:
                slot_data["bookings"].append({
                    "booking_line_id": booking[0],
                    "booking_id": booking[1],
                    "quantity": booking[2],
                    "user_id": booking[3],
                    "username": booking[4]
                })

            return jsonify(slot_data)
    except Exception as e:
        logger.error(f"Get booking slot error: {str(e)}")
        return jsonify({"error": ERROR_UNEXPECTED, "details": str(e)}), 500
    finally:
        release_cockroach_connection(cockroach_conn)

@admin_blueprint.route('/booking-slots/<slot_id>', methods=['PUT'])
@admin_required
def update_booking_slot(slot_id):
    try:
        data = request.json

        if not data:
            return jsonify({"error": "No data provided"}), 400

        cockroach_conn = get_cockroach_connection()
        try:
            with cockroach_conn.cursor() as cursor:
                # Check if slot exists and get current values
                cursor.execute("""
                    SELECT capacity, available_capacity
                    FROM road_booking_slots
                    WHERE road_booking_slot_id = %s
                """, (slot_id,))

                slot = cursor.fetchone()
                if not slot:
                    return jsonify({"error": "Booking slot not found"}), 404

                current_capacity = slot[0]
                current_available = slot[1]
                booked_capacity = current_capacity - current_available

                # Prepare update data
                new_capacity = int(data.get('capacity', current_capacity))

                # Validate new capacity against existing bookings
                if new_capacity < booked_capacity:
                    return jsonify({
                        "error": "Cannot reduce capacity below currently booked amount",
                        "booked_capacity": booked_capacity
                    }), 400

                # Calculate new available capacity
                new_available = new_capacity - booked_capacity

                # Update the slot
                cursor.execute("""
                    UPDATE road_booking_slots
                    SET capacity = %s, available_capacity = %s
                    WHERE road_booking_slot_id = %s
                """, (new_capacity, new_available, slot_id))

                cockroach_conn.commit()

                return jsonify({
                    "message": "Booking slot updated successfully",
                    "capacity": new_capacity,
                    "available_capacity": new_available
                })

        except psycopg2.Error as e:
            cockroach_conn.rollback()
            logger.error(f"Database error: {str(e)}")
            return jsonify({"error": ERROR_DATABASE, "details": str(e)}), 500
    except Exception as e:
        logger.error(f"Update booking slot error: {str(e)}")
        return jsonify({"error": ERROR_UNEXPECTED, "details": str(e)}), 500
    finally:
        release_cockroach_connection(cockroach_conn)

@admin_blueprint.route('/booking-slots/<slot_id>', methods=['DELETE'])
@admin_required
def delete_booking_slot(slot_id):
    try:
        cockroach_conn = get_cockroach_connection()
        try:
            with cockroach_conn.cursor() as cursor:
                # Check if the slot has any bookings
                cursor.execute("""
                    SELECT COUNT(*) FROM booking_lines
                    WHERE road_booking_slot_id = %s
                """, (slot_id,))

                booking_count = cursor.fetchone()[0]
                if booking_count > 0:
                    return jsonify({
                        "error": "Cannot delete slot with existing bookings",
                        "booking_count": booking_count
                    }), 400

                # Delete the slot if there are no bookings
                cursor.execute("""
                    DELETE FROM road_booking_slots
                    WHERE road_booking_slot_id = %s
                    RETURNING road_id, slot_time
                """, (slot_id,))

                deleted = cursor.fetchone()
                if not deleted:
                    return jsonify({"error": "Booking slot not found"}), 404

                cockroach_conn.commit()

                return jsonify({
                    "message": "Booking slot deleted successfully",
                    "road_id": deleted[0],
                    "slot_time": deleted[1].isoformat()
                })

        except psycopg2.Error as e:
            cockroach_conn.rollback()
            logger.error(f"Database error: {str(e)}")
            return jsonify({"error": ERROR_DATABASE, "details": str(e)}), 500
    except Exception as e:
        logger.error(f"Delete booking slot error: {str(e)}")
        return jsonify({"error": ERROR_UNEXPECTED, "details": str(e)}), 500
    finally:
        release_cockroach_connection(cockroach_conn)