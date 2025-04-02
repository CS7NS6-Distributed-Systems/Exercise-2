import pytest
import io
from faker import Faker
from datetime import datetime, timedelta
from flask import Flask

fake = Faker()

# --- Utility Functions ---
def register_user(client):
    username = fake.user_name()
    password = "pass123"
    data = {
        "givennames": fake.first_name(),
        "lastname": fake.last_name(),
        "username": username,
        "password": password,
        "license_img": (io.BytesIO(b"test"), f"{username}_license.jpg")
    }
    resp = client.post("/user/register", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    return username, password

def login_user(client, username, password):
    resp = client.post("/user/login", data={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.get_json()["access_token"]

# --- Advanced Tests ---

def test_invalid_login(client):
    resp = client.post("/user/login", data={"username": "nonexistent", "password": "wrong"})
    assert resp.status_code == 401


def test_duplicate_registration(client):
    username, password = register_user(client)
    data = {
        "givennames": fake.first_name(),
        "lastname": fake.last_name(),
        "username": username,
        "password": password,
        "license_img": (io.BytesIO(b"test"), f"{username}_license.jpg")
    }
    resp = client.post("/user/register", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_booking_invalid_road(client):
    username, password = register_user(client)
    token = login_user(client, username, password)
    resp = client.post(
        "/booking/create-booking",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "bookings": [{"road_id": "invalid-uuid", "slots": [], "quantity": 1}],
            "origin": "A", "destination": "B"
        }
    )
    assert resp.status_code == 400 or resp.status_code == 500


def test_license_image_download(client):
    username, password = register_user(client)
    token = login_user(client, username, password)
    profile = client.get("/user/profile", headers={"Authorization": f"Bearer {token}"})
    license_image_id = profile.get_json()["license_image_id"]
    image_resp = client.get(f"/user/licenses/{license_image_id}", headers={"Authorization": f"Bearer {token}"})
    assert image_resp.status_code == 200
    assert "image" in image_resp.content_type


def test_booking_missing_fields(client):
    username, password = register_user(client)
    token = login_user(client, username, password)
    resp = client.post("/booking/create-booking", headers={"Authorization": f"Bearer {token}"}, json={})
    assert resp.status_code == 400


def test_booking_past_slot(client, test_road_id):
    username, password = register_user(client)
    token = login_user(client, username, password)
    past_time = (datetime.now() - timedelta(days=1)).replace(minute=0, second=0, microsecond=0).isoformat()
    resp = client.post(
        "/booking/create-booking",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "bookings": [{"road_id": test_road_id, "slots": [{"start_time": past_time}], "quantity": 1}],
            "origin": "A", "destination": "B"
        }
    )
    assert resp.status_code == 400 or resp.status_code == 500


def test_user_cannot_access_others_booking(client, test_road_id):
    username1, password1 = register_user(client)
    token1 = login_user(client, username1, password1)
    # Book something valid
    slots_resp = client.post("/booking/available-slots", headers={"Authorization": f"Bearer {token1}"}, json={"road_ids": [test_road_id]})
    slot = slots_resp.get_json()["available_slots"][test_road_id][0]
    booking_resp = client.post("/booking/create-booking", headers={"Authorization": f"Bearer {token1}"}, json={
        "bookings": [{"road_id": test_road_id, "slots": [slot], "quantity": 1}],
        "origin": "X", "destination": "Y"
    })
    booking_id = booking_resp.get_json()["booking_id"]

    username2, password2 = register_user(client)
    token2 = login_user(client, username2, password2)
    cancel_resp = client.post(f"/booking/{booking_id}/cancel", headers={"Authorization": f"Bearer {token2}"})
    assert cancel_resp.status_code == 403
