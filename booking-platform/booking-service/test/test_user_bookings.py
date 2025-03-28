# booking-service/tests/test_user_bookings.py

def test_user_bookings_empty(client, token):
    resp = client.get(
        "/booking/user-bookings",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)

def test_user_bookings_after_booking(client, token, test_road_id):
    # Create a booking
    slot_resp = client.post(
        "/booking/available-slots",
        headers={"Authorization": f"Bearer {token}"},
        json={"road_ids": [test_road_id], "duration_minutes": 10, "distance_meters": 1000}
    )
    slot = slot_resp.get_json()["available_slots"][test_road_id][0]

    client.post(
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
            "origin": "TestA",
            "destination": "TestB"
        }
    )

    # Then fetch
    fetch = client.get("/booking/user-bookings", headers={"Authorization": f"Bearer {token}"})
    assert fetch.status_code == 200
    assert isinstance(fetch.get_json(), list)
    assert len(fetch.get_json()) > 0
