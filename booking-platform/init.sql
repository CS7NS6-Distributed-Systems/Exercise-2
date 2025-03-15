-- Create the database if it doesn’t exist
CREATE DATABASE IF NOT EXISTS booking;

-- Ensure we are using the correct database
SET DATABASE = booking;

-- Create `users` table if it doesn’t exist
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    givennames TEXT NOT NULL,
    lastname TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    license_image_id TEXT NOT NULL
);
