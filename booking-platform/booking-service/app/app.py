from flask import Flask
from app.user_routes import user_blueprint
from flask_jwt_extended import JWTManager

app = Flask(__name__)

app.config["JWT_SECRET_KEY"] = "tempsecretkey"
jwt = JWTManager(app)

# Default route
@app.route('/')
def hello():
    return "Welcome to the Booking Platform!"

# Route registeration for user register and login
app.register_blueprint(user_blueprint, url_prefix='/user')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)