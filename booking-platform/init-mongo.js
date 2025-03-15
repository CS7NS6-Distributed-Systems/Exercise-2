// Connect to the default "admin" database
db = db.getSiblingDB("booking_db");

// Create users collection (if it doesn't exist)
db.createCollection("users");

// Ensure username is unique
db.users.createIndex({ "username": 1 }, { unique: true });
