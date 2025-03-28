import datetime
from app.db import get_cockroach_connection, release_cockroach_connection

def get_any_existing_road_id():
    """Fetch any valid road_id from the CockroachDB database"""
    conn = None
    try:
        conn = get_cockroach_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM roads LIMIT 1")
        result = cursor.fetchone()
        return result[0] if result else None
    finally:
        if conn:
            release_cockroach_connection(conn)

def test_create_and_cancel_booking(client, token):
    # Step 0: Get a real road ID from the DB
    road_id = get_any_existing_road_id()
    assert road_id, "No road_id found in DB"

    # Step 1: Get available slots for that road
    slot_resp = client.post(
        "/booking/available-slots",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "road_ids": [road_id],
            "duration_minutes": 10,
            "distance_meters": 1000
        }
    )
    assert slot_resp.status_code == 200
    data = slot_resp.get_json()
    assert "available_slots" in data

    # Step 2: Extract first available slot
    available_slots = data["available_slots"]
    slots = available_slots.get(road_id, [])
    assert slots, f"No available slots found for road_id {road_id}"

    selected_slot = slots[0]

    # Step 3: Create a booking with that slot
    create_resp = client.post(
        "/booking/create-booking",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "bookings": [
                {
                    "road_id": selected_slot["road_id"],
                    "slots": [
                        {
                            "start_time": selected_slot["start_time"],
                            "slot_id": selected_slot["slot_id"]
                        }
                    ],
                    "quantity": 1
                }
            ],
            "origin": "Test Origin",
            "destination": "Test Destination"
        }
    )
    assert create_resp.status_code == 200, f"Booking failed: {create_resp.get_json()}"
    booking_id = create_resp.get_json()["booking_id"]

    # Step 4: Cancel the booking
    cancel_resp = client.post(
        f"/booking/{booking_id}/cancel",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.get_json()["status"] == "cancelled"
