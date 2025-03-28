# tests/conftest.py
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
def token():
    # Return a valid token or generate one using the login endpoint
    return "your_valid_jwt_token_here"
