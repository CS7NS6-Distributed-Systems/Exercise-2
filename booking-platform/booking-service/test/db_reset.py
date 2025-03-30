from app.db import get_cockroach_connection, release_cockroach_connection
import psycopg2

def reset_test_db():
    conn = None
    try:
        conn = get_cockroach_connection()
        cursor = conn.cursor()

        tables = [
            "booking_lines",
            "road_booking_slots",
            "bookings",
            "users",
            "roads"
        ]

        for table in tables:
            try:
                cursor.execute(f"DELETE FROM {table}")
            except psycopg2.Error as e:
                print(f"Failed to clear {table}: {e}")

        conn.commit()

    except Exception as e:
        print(f"Reset DB failed: {e}")
    finally:
        if conn and not conn.closed:
            try:
                release_cockroach_connection(conn)
            except Exception as e:
                print(f"Warning: failed to release conn - {e}")
