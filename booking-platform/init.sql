-- Create the database if it doesn't exist
CREATE DATABASE IF NOT EXISTS booking;

-- Ensure we are using the correct database
SET DATABASE = booking;

-- Create `users` table if it doesn't exist
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    givennames TEXT NOT NULL,
    lastname TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    license_image_id TEXT NOT NULL
);

-- Create regions table
CREATE TABLE IF NOT EXISTS regions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    country TEXT,
    code TEXT,
    UNIQUE(name, country)
);

-- Create roads table (metadata without geometry)
CREATE TABLE IF NOT EXISTS roads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    osm_id BIGINT UNIQUE,
    name TEXT,
    road_type TEXT,
    country TEXT,
    region_id UUID REFERENCES regions(id),
    tags JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create road_segments table
CREATE TABLE IF NOT EXISTS road_segments (
    segment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    road_id UUID REFERENCES roads(id),
    osm_way_id BIGINT UNIQUE,
    geometry TEXT, -- GeoJSON format for segment geometry
    length_meters FLOAT,
    start_node_id BIGINT,
    end_node_id BIGINT,
    tags JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS roads_name_idx ON roads(name);
CREATE INDEX IF NOT EXISTS roads_road_type_idx ON roads(road_type);
CREATE INDEX IF NOT EXISTS roads_region_id_idx ON roads(region_id);

CREATE INDEX IF NOT EXISTS road_segments_road_id_idx ON road_segments(road_id);
CREATE INDEX IF NOT EXISTS road_segments_geometry_idx ON road_segments(geometry);