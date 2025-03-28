# booking-service/tests/conftest.py

import os
os.environ["TESTING"] = "True"

import pytest
from app import app as flask_app
from app.db import get_cockroach_connection, release_cockroach_connection
import uuid
import datetime

def insert_test_user_and_road():
    #Insert a test user and road into the database.
    conn = get_cockroach_connection()
    cursor = conn.cursor()

    # Insert user
    username = "testuser"
    password = "testpassword"  # In production this would be hashed
    cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
    result = cursor.fetchone()
    if not result:
        cursor.execute("INSERT INTO users (id, username, password) VALUES (%s, %s, %s)",
                       (str(uuid.uuid4()), username, password))

    # Insert road
    road_id = str(uuid.uuid4())
    cursor.execute("SELECT id FROM roads LIMIT 1")
    existing = cursor.fetchone()
    if not existing:
        cursor.execute("INSERT INTO roads (id, name, hourly_capacity) VALUES (%s, %s, %s)",
                       (road_id, "Test Road", 10))
        conn.commit()
    else:
        road_id = existing[0]

    release_cockroach_connection(conn)
    return username, password, road_id

@pytest.fixture
def app():
    flask_app.config.update({"TESTING": True})
    yield flask_app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def token(client):
    username, password, _ = insert_test_user_and_road()
    resp = client.post("/user/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.get_json()["access_token"]

@pytest.fixture
def test_road_id():
    _, _, road_id = insert_test_user_and_road()
    return road_id
