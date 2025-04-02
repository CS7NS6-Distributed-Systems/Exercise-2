-- Create the database if it doesn't exist
CREATE DATABASE IF NOT EXISTS booking;

-- Ensure we are using the correct database
SET DATABASE = booking_test;

-- Create `users` table if it doesn't exist
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    givennames TEXT NOT NULL,
    lastname TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    license_image_id TEXT NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE
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
    hourly_capacity INTEGER NOT NULL DEFAULT 100,
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

-- Create road_booking_slots table (renamed from booking_segment_slots)
CREATE TABLE IF NOT EXISTS road_booking_slots (
    road_booking_slot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    road_id UUID NOT NULL REFERENCES roads(id),
    slot_time TIMESTAMP NOT NULL,
    capacity INTEGER NOT NULL,
    available_capacity INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (available_capacity >= 0),
    CHECK (capacity >= available_capacity)
);

-- Create bookings table
CREATE TABLE IF NOT EXISTS bookings (
    booking_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    booking_timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create booking_lines table (replacing booking_segments)
CREATE TABLE IF NOT EXISTS booking_lines (
    booking_line_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL REFERENCES bookings(booking_id),
    road_booking_slot_id UUID NOT NULL REFERENCES road_booking_slots(road_booking_slot_id),
    quantity INTEGER NOT NULL,
    CHECK (quantity > 0)
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS road_booking_slots_road_id_idx ON road_booking_slots(road_id);
CREATE INDEX IF NOT EXISTS road_booking_slots_time_idx ON road_booking_slots(slot_time);
CREATE INDEX IF NOT EXISTS road_booking_slots_availability_idx ON road_booking_slots(available_capacity);

CREATE INDEX IF NOT EXISTS bookings_user_id_idx ON bookings(user_id);
CREATE INDEX IF NOT EXISTS bookings_time_idx ON bookings(booking_timestamp);

CREATE INDEX IF NOT EXISTS booking_lines_booking_id_idx ON booking_lines(booking_id);
CREATE INDEX IF NOT EXISTS booking_lines_slot_id_idx ON booking_lines(road_booking_slot_id);
