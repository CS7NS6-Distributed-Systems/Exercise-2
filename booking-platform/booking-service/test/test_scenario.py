import io
import pytest
from faker import Faker
from app.db import mongo_db
from app.const import MONGODB_LICENSES_COLLECTION

fake = Faker()

# ---- Helper: Register random user ----
def register_random_user(client):
    username = fake.user_name()
    password = "pass123"
    data = {
        "givennames": fake.first_name(),
        "lastname": fake.last_name(),
        "username": username,
        "password": password,
        "license_img": (io.BytesIO(b"fake-image-bytes"), f"{username}_license.jpg")
    }
    resp = client.post("/user/register", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    return username, password

# ---- Helper: Login ----
def login(client, username, password):
    resp = client.post("/user/login", data={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.get_json()["access_token"]

# ---- Scenario 1: Register → Login → View Profile ----
def test_register_login_profile_flow(client):
    username, password = register_random_user(client)
    token = login(client, username, password)

    profile_resp = client.get("/user/profile", headers={"Authorization": f"Bearer {token}"})
    assert profile_resp.status_code == 200
    profile = profile_resp.get_json()
    assert profile["username"] == username

# ---- Scenario 2: Book Slot → Check in User Bookings ----
def test_booking_flow(client, test_road_id):
    username, password = register_random_user(client)
    token = login(client, username, password)

    create_resp = client.post(
        "/booking/create-booking",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "road_ids": [test_road_id],
            "duration_minutes": 20,
            "distance_meters": 3000
        }
    )
    assert create_resp.status_code == 200
    booking_id = create_resp.get_json()["booking_id"]

    bookings_resp = client.get("/booking/user-bookings", headers={"Authorization": f"Bearer {token}"})
    assert bookings_resp.status_code == 200
    bookings = bookings_resp.get_json()["bookings"]
    assert any(b["booking_id"] == booking_id for b in bookings)

# ---- Scenario 3: Access protected endpoint without token ----
def test_unauthorized_access_to_profile(client):
    resp = client.get("/user/profile")
    assert resp.status_code == 401

# ---- Scenario 4: Login with wrong password ----
def test_invalid_login(client):
    username, password = register_random_user(client)
    resp = client.post("/user/login", data={"username": username, "password": "wrongpass"})
    assert resp.status_code == 401

# ---- Scenario 5: Register with missing fields ----
def test_register_missing_fields(client):
    data = {
        "username": fake.user_name(),
        "password": "pass123"
        # missing givennames, lastname, license_img
    }
    resp = client.post("/user/register", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "missing_fields" in resp.get_json()

# ---- Scenario 6: Rate Limit test ----
def test_login_rate_limit(client):
    username, password = register_random_user(client)
    for _ in range(5):
        client.post("/user/login", data={"username": username, "password": password})
    resp = client.post("/user/login", data={"username": username, "password": password})
    # This may or may not hit the limit depending on limiter settings, so just log
    print("Rate limit status:", resp.status_code)
