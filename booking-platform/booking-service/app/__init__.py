from flask import Flask, jsonify
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os

app = Flask(__name__)

app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "default_secret_key")

jwt = JWTManager(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    enabled=not os.environ.get("TESTING") == "True",
    default_limits=os.getenv("RATE_LIMIT_GLOBAL", "200 per day, 50 per hour").split(", ")
)

# Add health check endpoint for Nginx load balancer
@app.route('/health', methods=['GET'])
def health_check():
    service_instance = os.getenv('SERVICE_INSTANCE', 'unknown')
    return jsonify({
        'status': 'healthy',
        'service': 'booking-service',
        'instance': service_instance
    }), 200

from app.user_routes import user_blueprint
app.register_blueprint(user_blueprint, url_prefix='/user')

from app.osm_routes import osm_blueprint
app.register_blueprint(osm_blueprint, url_prefix='/osm')

from app.admin_routes import admin_blueprint
app.register_blueprint(admin_blueprint)

from app.booking_routes import booking_blueprint
app.register_blueprint(booking_blueprint, url_prefix='/booking')
