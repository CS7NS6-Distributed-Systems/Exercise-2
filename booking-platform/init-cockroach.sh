#!/bin/sh
# Start CockroachDB
/cockroach/cockroach start-single-node --insecure &

# Wait for CockroachDB to be ready
sleep 10

# Run initialization SQL
# /cockroach/cockroach sql --insecure < /docker-entrypoint-initdb.d/init.sql
# Check if booking database exists
DB_EXISTS=$(/cockroach/cockroach sql --insecure -e "SHOW DATABASES;" | grep -c booking)

if [ $DB_EXISTS -eq 0 ]; then
  # If booking database doesn't exist, restore from backup
  /cockroach/cockroach sql --insecure -e "RESTORE FROM LATEST IN 'nodelocal://self/1/backup';"


else
  echo "Booking database already exists, skipping restore."
fi

# Keep container running
wait