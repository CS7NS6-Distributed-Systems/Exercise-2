#!/bin/bash
set -e

sleep 20
# Wait for the database to be ready
echo "Waiting for CockroachDB to be ready..."
for i in {1..30}; do
    if nc -z $COCKROACHDB_HOST $COCKROACHDB_PORT; then
        echo "CockroachDB is ready!"
        break
    fi
    echo "Waiting for CockroachDB... ($i/30)"
    sleep 2
done

# Run the OSM import script in the background
echo "Starting OSM data import in the background..."
python -m app.osm_import &

# Start the Flask application
echo "Starting the Flask application..."
gunicorn --bind 0.0.0.0:5000 app.app:app