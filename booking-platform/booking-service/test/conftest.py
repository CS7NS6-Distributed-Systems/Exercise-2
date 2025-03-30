# booking-service/tests/conftest.py

import os
os.environ["TESTING"] = "True"

import pytest
from app import app as flask_app
from app.db import get_cockroach_connection, release_cockroach_connection
import uuid
import datetime
from test.db_reset import reset_test_db

# Reset DB before the test session starts
@pytest.fixture(scope="session", autouse=True)
def clean_db_once():
    reset_test_db()
    yield  # Allows other tests to run
    
def insert_test_user_and_road():
    #Insert a test user and road into the database.
    conn = get_cockroach_connection()
    cursor = conn.cursor()

    # Insert user
    username = "testuser"
    password = "testpassword"
    givennames = "Test"
    lastname = "User"
    license_image_id = "test_license_img_001"
    cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
    result = cursor.fetchone()
    if not result:
        cursor.execute("""
            INSERT INTO users (id, username, password, givennames, lastname, license_image_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            str(uuid.uuid4()),
            username,
            password,
            givennames,
            lastname,
            license_image_id
        ))

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
