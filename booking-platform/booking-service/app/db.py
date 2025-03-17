import psycopg2
from pymongo import MongoClient
import redis
import os
import time

# Retry logic for CockroachDB connection
MAX_RETRIES = 5
RETRY_DELAY = 5  # 5 seconds between retries

for attempt in range(MAX_RETRIES):
    try:
        cockroach_conn = psycopg2.connect(
            dbname=os.getenv('COCKROACHDB_DATABASE', 'booking'),
            user=os.getenv('COCKROACHDB_USER', 'root'),
            password=os.getenv('COCKROACHDB_PASSWORD', ''),
            host=os.getenv('COCKROACHDB_HOST', 'cockroachdb'),
            port=os.getenv('COCKROACHDB_PORT', '26257')
        )
        print("Connected to CockroachDB")
        break
    except psycopg2.OperationalError as e:
        print(f"Waiting for CockroachDB to be ready... ({attempt+1}/{MAX_RETRIES})")
        time.sleep(RETRY_DELAY)
else:
    raise Exception("Failed to connect to CockroachDB after multiple attempts")

# create a connection to mongo client
mongo_client = MongoClient(
    host=os.getenv("MONGODB_HOST"),
    port=int(os.getenv("MONGODB_PORT"))
)

# extract the database "booking_db"
mongo_db = mongo_client["booking_db"]

# create a connection to redis client
redis_client = redis.StrictRedis(
    host=os.getenv("REDIS_HOST"),
    port=int(os.getenv("REDIS_PORT")),
    decode_responses=True
)