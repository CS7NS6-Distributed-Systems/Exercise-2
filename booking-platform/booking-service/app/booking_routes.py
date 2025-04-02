from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
import psycopg2
from datetime import datetime, timedelta
import uuid

from app.db import get_cockroach_connection, release_cockroach_connection
from app.user_routes import session_required
from app.const import ERROR_UNEXPECTED, ERROR_DATABASE, ERROR_UNAUTHORIZED_ACCESS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

booking_blueprint = Blueprint('booking', __name__)

@booking_blueprint.route('/available-slots', methods=['POST'])
@jwt_required()
def get_available_slots():
    """
    Get available time slots for each road in the route
    """
    current_user = get_jwt_identity()

    try:
        data = request.json
        road_ids = data.get('road_ids', [])
        duration_minutes = data.get('duration_minutes', 60)
        distance_meters = data.get('distance_meters', 0)

        if not road_ids:
            return jsonify({'error': 'No road IDs provided'}), 400

        # Get available time slots for each road
        available_slots = {}

        for road_id in road_ids:
            road_slots = get_road_available_slots(road_id)
            available_slots[road_id] = road_slots

        return jsonify({
            'available_slots': available_slots
        }), 200

    except Exception as e:
        logger.error(f"Error getting available time slots: {str(e)}")
        return jsonify({'error': ERROR_UNEXPECTED}), 500

def get_road_available_slots(road_id):
    """Get available time slots for a specific road"""
    conn = None
    available_slots = []

    try:
        conn = get_cockroach_connection()
        cursor = conn.cursor()

        # Get the road info
        cursor.execute("""
            SELECT id, name, hourly_capacity
            FROM roads
            WHERE id = %s
        """, (road_id,))

        road = cursor.fetchone()
        if not road:
            logger.warning(f"Road {road_id} not found")
            return []

        road_name = road[1]
        capacity = road[2]

        if not capacity:
            logger.warning(f"Road {road_id} has no capacity, set it to 10")
            capacity = 100

        # Get the current date
        now = datetime.now()

        # For each of the next 7 days
        for day_offset in range(0, 7):
            day_date = now + timedelta(days=day_offset)
            day_start = day_date.replace(hour=0, minute=0, second=0, microsecond=0)

            # Create time slots for each hour of the day
            for hour in range(0, 24):  # 0-23 hours
                slot_start = day_start + timedelta(hours=hour)
                slot_end = slot_start + timedelta(hours=1)

                # Skip slots in the past
                if slot_start <= now:
                    continue

                # Check existing bookings for this road in this time slot
                cursor.execute("""
                    SELECT rbs.road_booking_slot_id, rbs.available_capacity
                    FROM road_booking_slots rbs
                    WHERE rbs.road_id = %s
                    AND rbs.slot_time = %s
                """, (road_id, slot_start))

                slot_result = cursor.fetchone()

                if slot_result:
                    # Slot exists, check availability
                    slot_id = slot_result[0]
                    available = slot_result[1]

                    available_slots.append({
                        'road_id': road_id,
                        'road_name': road_name,
                        'start_time': slot_start.isoformat(),
                        'end_time': slot_end.isoformat(),
                        'available': available > 0,
                        'capacity': capacity,
                        'available_capacity': available,
                        'slot_id': slot_id
                    })
                else:
                    # Slot doesn't exist yet - fully available
                    available_slots.append({
                        'road_id': road_id,
                        'road_name': road_name,
                        'start_time': slot_start.isoformat(),
                        'end_time': slot_end.isoformat(),
                        'available': True,
                        'capacity': capacity,
                        'available_capacity': capacity,
                        'slot_id': None  # Will be created when booked
                    })

        return available_slots

    except Exception as e:
        logger.error(f"Database error in get_road_available_slots: {str(e)}")
        return []
    finally:
        if conn:
            release_cockroach_connection(conn)

@booking_blueprint.route('/create-booking', methods=['POST'])
@jwt_required()
def create_booking_route():
    """
    Create bookings for multiple roads with selected time slots
    """
    current_user = get_jwt_identity()

    try:
        data = request.json
        bookings = data.get('bookings', [])
        origin = data.get('origin', '')
        destination = data.get('destination', '')

        if not bookings:
            return jsonify({'error': 'No bookings provided'}), 400

        # Create the booking with multiple booking lines
        result = create_route_booking(current_user, bookings, origin, destination)

        return jsonify(result), 200 if result.get('success', False) else 400

    except Exception as e:
        logger.error(f"Error creating booking: {str(e)}")
        return jsonify({'error': ERROR_UNEXPECTED}), 500

def create_route_booking(username, bookings_data, origin, destination):
    """Create bookings for multiple roads as part of a route with capacity check"""
    conn = None

    try:
        conn = get_cockroach_connection()
        cursor = conn.cursor()

        # Start a transaction
        conn.autocommit = False

        # Generate a booking ID
        booking_id = str(uuid.uuid4())

        # Get user ID
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        user_result = cursor.fetchone()

        if not user_result:
            raise Exception("User not found")

        user_id = user_result[0]

        # Create a booking record
        booking_timestamp = datetime.now()
        cursor.execute("""
            INSERT INTO bookings
            (booking_id, user_id, origin, destination, booking_timestamp)
            VALUES (%s, %s, %s, %s, %s)
        """, (booking_id, user_id, origin, destination, booking_timestamp))

        # Track successful bookings
        success_count = 0
        total_count = 0
        booking_lines_data = [] # Store data for booking lines to insert later

        # Pre-check and prepare booking data
        for booking_data in bookings_data:
            road_id = booking_data.get('road_id')
            slots = booking_data.get('slots', [])
            quantity = booking_data.get('quantity', 1)

            if not road_id or not slots:
                continue

            total_count += 1

            for slot in slots:
                slot_start = datetime.fromisoformat(slot.get('start_time').replace('Z', '+00:00'))
                if slot_start < datetime.now():
                    conn.rollback()
                    return {
                        'success': False,
                        'error': "Booking failed: Cannot book a past time slot"
                    }
                slot_id = slot.get('slot_id')

                if slot_id:
                    # Check capacity for existing slot using FOR UPDATE to lock the row
                    cursor.execute("""
                        SELECT available_capacity
                        FROM road_booking_slots
                        WHERE road_booking_slot_id = %s
                        FOR UPDATE
                    """, (slot_id,))
                    result = cursor.fetchone()

                    if not result or result[0] < quantity:
                        conn.rollback()
                        return {
                            'success': False,
                            'error': "Booking failed: Road already booked" # Changed error message
                        }
                    booking_lines_data.append({'slot_id': slot_id, 'quantity': quantity, 'slot_exists': True, 'road_id': road_id, 'slot_start': slot_start})

                else:
                    # Get road capacity and check if enough for a new slot
                    cursor.execute("SELECT hourly_capacity FROM roads WHERE id = %s", (road_id,))
                    road_capacity_result = cursor.fetchone()
                    if not road_capacity_result:
                        conn.rollback()
                        return {
                            'success': False,
                            'error': f"Road with id {road_id} not found" # Keep specific error for road not found
                        }
                    road_capacity = road_capacity_result[0]

                    if road_capacity < quantity: # Check against road capacity initially
                         conn.rollback()
                         return {
                            'success': False,
                            'error': "Booking failed: Road already booked" # Changed error message
                        }
                    booking_lines_data.append({'slot_id': None, 'quantity': quantity, 'slot_exists': False, 'road_id': road_id, 'slot_start': slot_start, 'road_capacity': road_capacity})


        # Process booking lines and update/create slots and booking lines
        for booking_line_item in booking_lines_data:
            slot_id = booking_line_item['slot_id']
            quantity = booking_line_item['quantity']
            slot_exists = booking_line_item['slot_exists']
            road_id = booking_line_item['road_id']
            slot_start = booking_line_item['slot_start']


            if slot_exists:
                # Update existing slot - capacity is already checked above with FOR UPDATE
                cursor.execute("""
                    UPDATE road_booking_slots
                    SET available_capacity = available_capacity - %s
                    WHERE road_booking_slot_id = %s
                """, (quantity, slot_id))
            else:
                # Create new booking slot - capacity is already checked above
                cursor.execute("""
                    INSERT INTO road_booking_slots
                    (road_id, slot_time, capacity, available_capacity)
                    VALUES (%s, %s, %s, %s)
                    RETURNING road_booking_slot_id
                """, (road_id, slot_start, booking_line_item['road_capacity'], booking_line_item['road_capacity'] - quantity))
                slot_id = cursor.fetchone()[0]


            # Create booking line
            booking_line_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO booking_lines
                (booking_line_id, booking_id, road_booking_slot_id, quantity)
                VALUES (%s, %s, %s, %s)
            """, (booking_line_id, booking_id, slot_id, quantity))
            success_count += 1


        # Commit the transaction
        conn.commit()

        return {
            'success': success_count > 0,
            'booking_id': booking_id,
            'success_count': success_count,
            'total_count': total_count
        }

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error in create_route_booking: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        if conn:
            conn.autocommit = True
            release_cockroach_connection(conn)

@booking_blueprint.route('/user-bookings', methods=['GET'])
@jwt_required()
def get_user_bookings():
    """Get all bookings for the current user"""
    current_user = get_jwt_identity()
    conn = None

    try:
        conn = get_cockroach_connection()
        cursor = conn.cursor()

        # Get user ID
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_user,))
        user_result = cursor.fetchone()

        if not user_result:
            return jsonify({"error": "User not found"}), 404

        user_id = user_result[0]

        # Get all bookings for this user
        cursor.execute("""
            SELECT
                b.booking_id,
                b.origin,
                b.destination,
                b.booking_timestamp,
                MIN(rbs.slot_time) as start_time,
                MAX(rbs.slot_time) as end_time,
                COUNT(DISTINCT bl.booking_line_id) as booking_count,
                COUNT(DISTINCT rbs.road_id) as road_count,
                MAX(bl.quantity) as quantity
            FROM bookings b
            JOIN booking_lines bl ON b.booking_id = bl.booking_id
            JOIN road_booking_slots rbs ON bl.road_booking_slot_id = rbs.road_booking_slot_id
            WHERE b.user_id = %s
            GROUP BY b.booking_id, b.origin, b.destination, b.booking_timestamp
            ORDER BY b.booking_timestamp DESC
        """, (user_id,))

        bookings = []
        for row in cursor.fetchall():
            bookings.append({
                'booking_id': row[0],
                'origin': row[1],
                'destination': row[2],
                'created_at': row[3].isoformat() if row[3] else None,
                'start_time': row[4].isoformat() if row[4] else None,
                'end_time': row[5].isoformat() if row[5] else None,
                'booking_count': row[6],
                'road_count': row[7],
                'quantity': row[8]
            })

        return jsonify(bookings), 200

    except Exception as e:
        logger.error(f"Error getting user bookings: {str(e)}")
        return jsonify({'error': ERROR_UNEXPECTED}), 500
    finally:
        if conn:
            release_cockroach_connection(conn)

@booking_blueprint.route('/<booking_id>/cancel', methods=['POST'])
@jwt_required()
def cancel_booking(booking_id):
    """Cancel a booking and all its booking lines"""
    current_user = get_jwt_identity()
    conn = None

    try:
        conn = get_cockroach_connection()
        cursor = conn.cursor()

        # Start transaction
        conn.autocommit = False

        # First check if the booking exists at all
        cursor.execute("""
            SELECT 1 FROM bookings WHERE booking_id = %s
        """, (booking_id,))

        if not cursor.fetchone():
            # Booking doesn't exist at all
            conn.rollback()
            return jsonify({
                "error": "Booking not found. It may have already been cancelled.",
                "status": "not_found"
            }), 404

        # Check if booking belongs to this user
        cursor.execute("""
            SELECT b.booking_id
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            WHERE b.booking_id = %s AND u.username = %s
        """, (booking_id, current_user))

        if not cursor.fetchone():
            conn.rollback()
            return jsonify({
                "error": "Access denied. This booking doesn't belong to your account.",
                "status": "access_denied"
            }), 403

        # Get all booking lines to update road booking slots
        cursor.execute("""
            SELECT bl.booking_line_id, bl.road_booking_slot_id, bl.quantity
            FROM booking_lines bl
            WHERE bl.booking_id = %s
        """, (booking_id,))

        booking_lines = cursor.fetchall()

        if not booking_lines:
            # We found the booking but no lines - might be partially cancelled
            cursor.execute("DELETE FROM bookings WHERE booking_id = %s", (booking_id,))
            conn.commit()
            return jsonify({
                "success": True,
                "cancelled_count": 0,
                "status": "empty_booking"
            }), 200

        cancelled_count = 0

        # Update capacity for each booking slot
        for line in booking_lines:
            booking_line_id, slot_id, quantity = line

            # Update available capacity in the slot
            cursor.execute("""
                UPDATE road_booking_slots
                SET available_capacity = available_capacity + %s
                WHERE road_booking_slot_id = %s
            """, (quantity, slot_id))

            cancelled_count += 1

        # Delete all booking lines for this booking
        cursor.execute("""
            DELETE FROM booking_lines
            WHERE booking_id = %s
        """, (booking_id,))

        # Delete the booking
        cursor.execute("""
            DELETE FROM bookings
            WHERE booking_id = %s
        """, (booking_id,))

        # Commit the transaction
        conn.commit()

        return jsonify({
            "success": True,
            "cancelled_count": cancelled_count,
            "status": "cancelled"
        }), 200

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error cancelling booking: {str(e)}")
        return jsonify({
            'error': str(e) if str(e) else ERROR_UNEXPECTED,
            'status': 'error'
        }), 500
    finally:
        if conn:
            conn.autocommit = True
            release_cockroach_connection(conn)
