import os

from gridfs import GridFS
from pymongo import MongoClient


MONGO_URI = (
    os.getenv("MONGO_URI")
    or os.getenv("MONGODB_URI")
    or "mongodb://localhost:27017"
)
MONGO_DB_NAME = (
    os.getenv("MONGO_DB_NAME")
    or os.getenv("MONGODB_DB_NAME")
    or "cui_campusbot"
)

client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
fs = GridFS(db)

