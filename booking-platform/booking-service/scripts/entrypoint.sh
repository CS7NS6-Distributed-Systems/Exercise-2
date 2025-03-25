#!/bin/bash
set -e

# Log that the container is starting
echo "Starting booking service container..."

# Run gunicorn
exec gunicorn --bind 0.0.0.0:5000 app:app 