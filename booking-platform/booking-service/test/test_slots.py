# tests/test_slots.py

def test_available_slots_success(client, token):
    response = client.post(
        "/booking/available-slots",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "road_ids": ["test-road-id"],
            "duration_minutes": 15,
            "distance_meters": 5000
        }
    )
    assert response.status_code == 200
    assert "available_slots" in response.json

def test_available_slots_no_auth(client):
    response = client.post("/booking/available-slots", json={})
    assert response.status_code == 401

def test_available_slots_missing_road_ids(client, token):
    response = client.post(
        "/booking/available-slots",
        headers={"Authorization": f"Bearer {token}"},
        json={}
    )
    assert response.status_code == 400
