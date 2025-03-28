import pytest
from app import app as flask_app

@pytest.fixture
def app():
    flask_app.config.update({
        "TESTING": True,
    })
    yield flask_app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def token(client):
    login_response = client.post(
        "/user/login",
        json={"username": "testuser", "password": "testpassword"}
    )
    assert login_response.status_code == 200
    return login_response.get_json()["access_token"]
