# booking-service/tests/test_booking.py

from app.db import get_cockroach_connection, release_cockroach_connection

def get_first_available_slot(client, token, road_id):
    resp = client.post(
        "/booking/available-slots",
        headers={"Authorization": f"Bearer {token}"},
        json={"road_ids": [road_id], "duration_minutes": 10, "distance_meters": 5000}
    )
    slots = resp.get_json()["available_slots"].get(road_id, [])
    return slots[0] if slots else None

def test_booking_create_and_cancel(client, token, test_road_id):
    slot = get_first_available_slot(client, token, test_road_id)
    assert slot, "No available slot"

    create_resp = client.post(
        "/booking/create-booking",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "bookings": [
                {
                    "road_id": test_road_id,
                    "slots": [{"start_time": slot["start_time"], "slot_id": slot["slot_id"]}],
                    "quantity": 1
                }
            ],
            "origin": "A",
            "destination": "B"
        }
    )
    assert create_resp.status_code == 200
    booking_id = create_resp.get_json()["booking_id"]

    cancel_resp = client.post(
        f"/booking/{booking_id}/cancel",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.get_json()["status"] == "cancelled"
