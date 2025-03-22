from flask import Blueprint, request, jsonify, send_file, render_template
from flask_bcrypt import Bcrypt
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from functools import wraps
import psycopg2
from bson import ObjectId
from pymongo.errors import PyMongoError
from datetime import timedelta
import io
import logging

from app import limiter
from app.db import get_cockroach_connection, release_cockroach_connection, mongo_db, redis_client
from app.const import ( 
    SESSION_EXPIRY_SECONDS,
    TOKEN_EXPIRY_HOURS,
    COCKROACHDB_USERS_TABLE,
    MONGODB_LICENSES_COLLECTION,
    ERROR_MISSING_FIELDS,
    ERROR_USER_EXISTS,
    ERROR_USER_NOT_FOUND,
    ERROR_INVALID_CREDENTIALS,
    ERROR_UNAUTHORIZED_ACCESS,
    ERROR_SESSION_EXPIRED,
    ERROR_DATABASE,
    ERROR_UNEXPECTED,
    SUCCESS_REGISTRATION,
    SUCCESS_LOGIN,
    SUCCESS_LOGOUT,
    RATE_LIMIT_LOGIN,
    RATE_LIMIT_REGISTER,
)

user_blueprint = Blueprint("user", __name__)
bcrypt = Bcrypt()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def session_required(fn):
    @wraps(fn)
    @jwt_required()
    def decorated_fn(*args, **kwargs):
        username = get_jwt_identity()
        if not redis_client.get(f"session: {username}"):
            return jsonify({"error": ERROR_SESSION_EXPIRED}), 401
        redis_client.expire(f"session: {username}", SESSION_EXPIRY_SECONDS)
        return fn(*args, **kwargs)
    return decorated_fn

@user_blueprint.route("/register", methods=["GET"])
def register_form():
    return render_template("register.html")

@user_blueprint.route("/login", methods=["GET"])
def login_form():
    return render_template("login.html")

@user_blueprint.route("/register", methods=["POST"])
@limiter.limit(RATE_LIMIT_REGISTER)
def register():
    try:
        cockroach_conn = get_cockroach_connection()
        
        givennames = request.form.get("givennames")
        lastname = request.form.get("lastname")
        username = request.form.get("username")
        password = request.form.get("password")
        license_img = request.files.get("license_img")

        if not all([givennames, lastname, username, password, license_img]):
            return jsonify({"error": ERROR_MISSING_FIELDS}), 400

        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

        file_extension = license_img.filename.split(".")[-1]
        license_data = {
            "filename": f"{username}_license.{file_extension}",
            "license_image": license_img.read()
        }
        license_collection = mongo_db[MONGODB_LICENSES_COLLECTION]
        inserted_license = license_collection.insert_one(license_data)
        license_img_id = str(inserted_license.inserted_id)

        with cockroach_conn.cursor() as cursor:
            cursor.execute(f"SELECT username FROM {COCKROACHDB_USERS_TABLE} WHERE username = %s", (username,))
            if cursor.fetchone():
                return jsonify({"error": ERROR_USER_EXISTS}), 400

            cursor.execute(
                f"INSERT INTO {COCKROACHDB_USERS_TABLE} (givennames, lastname, username, password, license_image_id) VALUES (%s, %s, %s, %s, %s)",
                (givennames, lastname, username, hashed_password, license_img_id)
            )
            cockroach_conn.commit()

        return jsonify({"message": SUCCESS_REGISTRATION}), 200

    except (psycopg2.Error, PyMongoError) as e:
        cockroach_conn.rollback()
        if "inserted_license" in locals():
            license_collection.delete_one({"_id": inserted_license.inserted_id})
        logger.error(f"Database error: {str(e)}")
        return jsonify({"error": ERROR_DATABASE, "details": str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": ERROR_UNEXPECTED, "details": str(e)}), 500
    finally:
        if cockroach_conn:
            release_cockroach_connection(cockroach_conn)

@user_blueprint.route("/login", methods=["POST"])
@limiter.limit(RATE_LIMIT_LOGIN)
def login():
    try:
        username = request.form.get("username")
        password = request.form.get("password")
        cockroach_conn = get_cockroach_connection()

        if not (username and password):
            # return jsonify({"error": ERROR_MISSING_FIELDS}), 400
            return jsonify({"error": f"vals u {username}; p {password}"}), 400

        with cockroach_conn.cursor() as cursor:
            cursor.execute(f"SELECT password FROM {COCKROACHDB_USERS_TABLE} WHERE username = %s", (username,))
            user_password_hash = cursor.fetchone()

        if not user_password_hash:
            return jsonify({"error": ERROR_USER_NOT_FOUND}), 401

        if bcrypt.check_password_hash(user_password_hash[0], password):
            token = create_access_token(identity=username, expires_delta=timedelta(hours=TOKEN_EXPIRY_HOURS))
            redis_client.setex(f"session: {username}", SESSION_EXPIRY_SECONDS, token)
            return jsonify({"message": SUCCESS_LOGIN, "access_token": token}), 200

        return jsonify({"error": ERROR_INVALID_CREDENTIALS}), 401

    except psycopg2.Error as e:
        logger.error(f"Database error: {str(e)}")
        return jsonify({"error": ERROR_DATABASE, "details": str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": ERROR_UNEXPECTED, "details": str(e)}), 500
    finally:
        if cockroach_conn:
            release_cockroach_connection(cockroach_conn)

@user_blueprint.route("/logout", methods=["POST"])
@session_required
def logout():
    try:
        username = get_jwt_identity()
        redis_client.delete(f"session: {username}")
        return jsonify({"message": SUCCESS_LOGOUT}), 200
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": ERROR_UNEXPECTED, "details": str(e)}), 500

@user_blueprint.route("/profile", methods=["GET"])
@session_required
def profile():
    try:
        username = get_jwt_identity()
        cockroach_conn = get_cockroach_connection()
        with cockroach_conn.cursor() as cursor:
            cursor.execute(
                f"SELECT givennames, lastname, username, license_image_id FROM {COCKROACHDB_USERS_TABLE} WHERE username = %s", (username,)
            )
            user_record = cursor.fetchone()

        if not user_record:
            return jsonify({"error": ERROR_USER_NOT_FOUND}), 404

        givennames, lastname, username, license_image_id = user_record
        return jsonify({
            "givennames": givennames,
            "lastname": lastname,
            "username": username,
            "license_image_id": license_image_id,
        }), 200
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": ERROR_UNEXPECTED, "details": str(e)}), 500
    finally:
        release_cockroach_connection(cockroach_conn)

@user_blueprint.route("/licenses/<license_image_id>", methods=["GET"])
@session_required
def get_license_image(license_image_id):
    try:
        username = get_jwt_identity()
        cockroach_conn = get_cockroach_connection()
        with cockroach_conn.cursor() as cursor:
            cursor.execute(
                f"SELECT license_image_id FROM {COCKROACHDB_USERS_TABLE} WHERE username = %s", (username,)
            )
            user_license_id = cursor.fetchone()

        if not user_license_id or user_license_id[0] != license_image_id:
            return jsonify({"error": ERROR_UNAUTHORIZED_ACCESS}), 403

        license_data = mongo_db[MONGODB_LICENSES_COLLECTION].find_one({"_id": ObjectId(license_image_id)})
        if not license_data:
            return jsonify({"error": ERROR_USER_NOT_FOUND}), 404

        image_type = license_data["filename"].split(".")[-1]
        return send_file(
            io.BytesIO(license_data["license_image"]),
            mimetype=f"image/{image_type}",
            as_attachment=False
        )
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": ERROR_UNEXPECTED, "details": str(e)}), 500
    finally:
        release_cockroach_connection(cockroach_conn)