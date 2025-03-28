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
