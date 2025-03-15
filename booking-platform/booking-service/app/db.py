import psycopg2
from pymongo import MongoClient
import os

# create a connection to cockroachdb database 'booking'
cockroach_conn = psycopg2.connect(
    database="booking",
    user="root",
    host=os.getenv('COCKROACHDB_HOST'),
    port=os.getenv('COCKROACHDB_PORT')
)

# create a connection to mongo client
mongo_client = MongoClient(
    host=os.getenv('MONGODB_HOST'),
    port=int(os.getenv('MONGODB_PORT'))
)

# extract the database 'booking_db'
mongo_db = mongo_client["booking_db"]