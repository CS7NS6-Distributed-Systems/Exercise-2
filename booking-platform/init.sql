-- Create the database if it doesn't exist
CREATE DATABASE IF NOT EXISTS booking;

-- Ensure we are using the correct database
SET DATABASE = booking;

-- Create `users` table if it doesn't exist
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    givennames TEXT NOT NULL,
    lastname TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    license_image_id TEXT NOT NULL
);

-- Create roads table
CREATE TABLE IF NOT EXISTS osm_roads (
    id BIGINT PRIMARY KEY,
    name TEXT,
    road_type TEXT,
    country TEXT,
    region TEXT,
    geometry TEXT, -- GeoJSON format for road geometry
    tags JSONB,    -- Additional OSM tags as JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Replace GIN indexes with B-tree indexes which work for text columns
CREATE INDEX IF NOT EXISTS osm_roads_geometry_idx ON osm_roads(geometry);
CREATE INDEX IF NOT EXISTS osm_roads_road_type_idx ON osm_roads(road_type);
CREATE INDEX IF NOT EXISTS osm_roads_country_region_idx ON osm_roads(country, region);