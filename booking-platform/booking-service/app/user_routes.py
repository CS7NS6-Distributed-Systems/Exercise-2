from flask import Blueprint, request, jsonify
from flask_bcrypt import Bcrypt
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from flask import send_file
from functools import wraps

import psycopg2
from bson import ObjectId
from pymongo.errors import PyMongoError
from datetime import timedelta
import io
import json

from app.db import cockroach_conn, mongo_db, redis_client

user_blueprint = Blueprint('user', __name__)
bcrypt = Bcrypt()

def session_required(fn):
    @wraps(fn)
    @jwt_required()
    def decorated_fn(*args, **kwargs):
        username = get_jwt_identity()
        if not redis_client.get(f"session: {username}"):
            return jsonify({"error": "Session expired. Log in again"}), 401
        redis_client.expire(f"session: {username}", 3600)
        return fn(*args, **kwargs)
    return decorated_fn

@user_blueprint.route('/register', methods=['POST'])
def register():
    try:
        givennames = request.form.get('givennames')
        lastname = request.form.get('lastname')
        username = request.form.get('username')
        password = request.form.get('password')
        license_img = request.files.get('license_img')

        if not all([givennames, lastname, username, password, license_img]):
            return jsonify({"error": f"All fields including are required, {[givennames, lastname, username, password, license_img]}"}), 400

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        file_extension = license_img.filename.split('.')[-1]
        license_data = {
            'filename': f'{username}_license.{file_extension}',
            'license_image': license_img.read()
        }
        license_collection = mongo_db['user_licenses']
        inserted_license = license_collection.insert_one(license_data)
        license_img_id = str(inserted_license.inserted_id)

        with cockroach_conn.cursor() as cursor:
            cursor.execute("SELECT username FROM users WHERE username = %s", (username,))
            existing_user = cursor.fetchone()
            if existing_user:
                return jsonify({"error": "Username already exists"}), 400

            cursor.execute(
                'INSERT INTO users (givennames, lastname, username, password, license_image_id) VALUES (%s, %s, %s, %s, %s)',
                (givennames, lastname, username, hashed_password, license_img_id)
            )
            cockroach_conn.commit()

        return jsonify({"message": "Registration successful"}), 200

    except (psycopg2.Error, PyMongoError) as e:
        cockroach_conn.rollback()
        license_collection.delete_one({"_id": inserted_license.inserted_id})  # Rollback MongoDB insert
        return jsonify({"error": "Database error", "details": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "An unexpected error occurred", "details": str(e)}), 500

@user_blueprint.route('/login', methods=['POST'])
def login():
    try:
        username = request.form.get('username')
        password = request.form.get('password')

        if not (username and password):
            return jsonify({"error": "All fields are required"}), 400

        with cockroach_conn.cursor() as cursor:
            cursor.execute(
                'SELECT password FROM users WHERE username = %s', (username,)
            )
            user_record = cursor.fetchone()

        if not user_record:
            return jsonify({"error": "User does not exist"}), 401

        password_hash = user_record[0]
        if bcrypt.check_password_hash(password_hash, password):
            token = create_access_token(identity=username, expires_delta=timedelta(hours=1))
            redis_client.setex(f"session: {username}", 3600, json.dumps(token))
            return jsonify({"message": "Login successful", "access_token": token}), 200

        return jsonify({"error": "Invalid username or password"}), 401

    except psycopg2.Error as e:
        return jsonify({"error": "Database error", "details": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "An unexpected error occurred", "details": str(e)}), 500
    
@user_blueprint.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    try:
        username = get_jwt_identity()
        redis_client.delete(f"session: {username}")
        return jsonify({"message": "logout successful"})
    except Exception as e:
        return jsonify({"error":"An error occured", "details": str(e)}), 500

@user_blueprint.route('/profile', methods=['GET'])
@session_required
def profile():
    try:
        username = get_jwt_identity()
        with cockroach_conn.cursor() as cursor:
            cursor.execute(
                'SELECT givennames, lastname, username, license_image_id FROM users WHERE username = %s', (username,)
            )
            user_record = cursor.fetchone()
        if not user_record:
            return jsonify({"error": "User not found"}), 404
        
        givennames, lastname, username, license_image_id = user_record
        return jsonify({
            "givennames": givennames,
            "lastname": lastname,
            "username": username,
            "license_image_id": license_image_id,
        })
    except Exception as e:
        return jsonify({"error":"An error occured", "details": str(e)}), 500
    
@user_blueprint.route('licenses/<license_image_id>', methods=['GET'])
@session_required
def get_license_image(license_image_id):
    try:
        license_data = mongo_db['user_licenses'].find_one({"_id": ObjectId(license_image_id)})
        if not license_data:
            return jsonify({"error": "License image not found"}), 404
        
        image_type = str(license_data["filename"]).split('.')[-1]
        return send_file(
            io.BytesIO(license_data["license_image"]),
            mimetype=f'image/{image_type}',
            as_attachment=False
        )
    except Exception as e:
        return jsonify({"error":"An error occured", "details": str(e)}), 500

