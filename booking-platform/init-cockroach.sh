#!/bin/sh
set -e

# Create the backup directory if it doesn't exist
mkdir -p /cockroach/cockroach-data/extern/1/backup

# Start CockroachDB
exec /cockroach/cockroach start-single-node --insecure "$@" 