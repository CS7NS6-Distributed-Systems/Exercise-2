# booking-service/tests/test_slots.py

def test_slots_success(client, token, test_road_id):
    resp = client.post(
        "/booking/available-slots",
        headers={"Authorization": f"Bearer {token}"},
        json={"road_ids": [test_road_id], "duration_minutes": 10, "distance_meters": 1000}
    )
    assert resp.status_code == 200
    assert "available_slots" in resp.get_json()

def test_slots_no_auth(client, test_road_id):
    resp = client.post("/booking/available-slots", json={"road_ids": [test_road_id]})
    assert resp.status_code == 401

def test_slots_invalid_payload(client, token):
    resp = client.post(
        "/booking/available-slots",
        headers={"Authorization": f"Bearer {token}"},
        json={}
    )
    assert resp.status_code == 400

