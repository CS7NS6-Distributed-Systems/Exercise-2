def test_create_booking_missing_data(client, token):
    response = client.post(
        "/booking/create-booking",
        headers={"Authorization": f"Bearer {token}"},
        json={}  # No bookings provided
    )
    assert response.status_code == 400
    assert "error" in response.get_json()

def test_create_booking_success(client, token):
    # Sample input — replace with actual road_id and slot info
    response = client.post(
        "/booking/create-booking",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "bookings": [
                {
                    "road_id": "test-road-id",
                    "slots": [
                        {
                            "start_time": "2025-03-29T10:00:00Z",
                            "slot_id": None
                        }
                    ],
                    "quantity": 1
                }
            ],
            "origin": "Point A",
            "destination": "Point B"
        }
    )
    assert response.status_code in [200, 400]  # Depends on slot availability

def test_cancel_booking(client, token):
    # Create a booking first
    create_resp = client.post(
        "/booking/create-booking",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "bookings": [
                {
                    "road_id": "test-road-id",  # Use a real road ID
                    "slots": [
                        {
                            "start_time": "2025-03-29T12:00:00+00:00",  # Must be a valid future time
                            "slot_id": None
                        }
                    ],
                    "quantity": 1
                }
            ],
            "origin": "Test Origin",
            "destination": "Test Destination"
        }
    )

    assert create_resp.status_code == 200, f"Create booking failed: {create_resp.json}"
    booking_id = create_resp.get_json().get("booking_id")

    # Now cancel the booking
    cancel_resp = client.post(
        f"/booking/{booking_id}/cancel",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert cancel_resp.status_code == 200, f"Cancel failed: {cancel_resp.json}"
    assert cancel_resp.get_json()["status"] == "cancelled"

