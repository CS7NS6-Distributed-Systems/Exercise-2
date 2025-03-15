from flask import Flask
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from app.user_routes import user_blueprint
from app.const import RATE_LIMIT_GLOBAL

app = Flask(__name__)

# JWT Configuration
app.config["JWT_SECRET_KEY"] = "tempsecretkey"
jwt = JWTManager(app)

# Rate Limiter Configuration
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=RATE_LIMIT_GLOBAL,
)

# Default route
@app.route('/')
def hello():
    return "Welcome to the Booking Platform!"

# Register Blueprints
app.register_blueprint(user_blueprint, url_prefix='/user')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
