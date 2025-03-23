from flask import Flask
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
    default_limits=os.getenv("RATE_LIMIT_GLOBAL", "200 per day, 50 per hour").split(", "),
)

from app.user_routes import user_blueprint
app.register_blueprint(user_blueprint, url_prefix='/user')

from app.osm_routes import osm_blueprint
app.register_blueprint(osm_blueprint, url_prefix='/osm')

from app.admin_routes import admin_blueprint
app.register_blueprint(admin_blueprint)

from app.booking_routes import booking_blueprint
app.register_blueprint(booking_blueprint, url_prefix='/booking')