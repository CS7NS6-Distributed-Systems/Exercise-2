from flask import Blueprint, request, jsonify
from flask_bcrypt import Bcrypt
from flask_jwt_extended import create_access_token
import psycopg2
from pymongo.errors import PyMongoError
from datetime import timedelta

from app.db import cockroach_conn, mongo_db

user_blueprint = Blueprint('user', __name__)
bcrypt = Bcrypt()

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
            return jsonify({"message": "Login successful", "access_token": token}), 200

        return jsonify({"error": "Invalid username or password"}), 401

    except psycopg2.Error as e:
        return jsonify({"error": "Database error", "details": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "An unexpected error occurred", "details": str(e)}), 500