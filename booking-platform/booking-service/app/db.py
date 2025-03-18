import psycopg2
from psycopg2 import pool
from pymongo import MongoClient
import redis
import os

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

# cockroach connection pools
cockroach_pool = pool.SimpleConnectionPool(
    1, 10,
    dbname=os.getenv("COCKROACHDB_DATABASE", "booking"),
    user=os.getenv("COCKROACHDB_USER", "root"),
    password=os.getenv("COCKROACHDB_PASSWORD", ""),
    host=os.getenv("COCKROACHDB_HOST", "cockroachdb"),
    port=os.getenv("COCKROACHDB_PORT", "26257"),
)

# function to get a cockroach connection from pool
def get_cockroach_connection():
    return cockroach_pool.getconn()

# function to release the cockroach connection to pool
def release_cockroach_connection(conn):
    try:
        if conn:
            cockroach_pool.putconn(conn)
    except psycopg2.DatabaseError as e:
        print(f"Error releasing CockroachDB connection: {e}")