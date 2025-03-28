# booking-service/tests/test_auth_protection.py

def test_protected_routes_require_token(client):
    protected_endpoints = [
        ("/booking/available-slots", "post"),
        ("/booking/create-booking", "post"),
        ("/booking/user-bookings", "get"),
    ]

    for route, method in protected_endpoints:
        resp = getattr(client, method)(route)
        assert resp.status_code == 401
