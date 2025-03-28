from app.db import get_cockroach_connection, release_cockroach_connection

def reset_test_db():
    """
    Delete data from all test DB tables in dependency-safe order.
    """
    conn = get_cockroach_connection()
    cursor = conn.cursor()

    # Disable foreign key checks if needed
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
        except Exception as e:
            print(f"Failed to clear {table}: {e}")

    conn.commit()
    release_cockroach_connection(conn)
