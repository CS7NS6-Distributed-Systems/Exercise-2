#!/bin/sh
# Start CockroachDB
/cockroach/cockroach start-single-node --insecure &

# Wait for CockroachDB to be ready
sleep 10

# Run initialization SQL
/cockroach/cockroach sql --insecure < /docker-entrypoint-initdb.d/init.sql


# Keep container running
wait