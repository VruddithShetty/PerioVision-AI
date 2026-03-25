import os
import pymongo
from pymongo import MongoClient

class MongoDBConnection:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDBConnection, cls).__new__(cls)
            mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
            
            # Attempt to connect to real MongoDB
            try:
                client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
                client.server_info() # Force connection check
                cls._instance.client = client
                print("Connected to real MongoDB instance.")
            except pymongo.errors.ServerSelectionTimeoutError:
                print("Could not connect to MongoDB. Falling back to mongomock in-memory database for testing.")
                import mongomock
                cls._instance.client = mongomock.MongoClient()
                
            cls._instance.db = cls._instance.client["dental_prediction_db"]
        return cls._instance

    @classmethod
    def get_db(cls):
        return cls().db

    @classmethod
    def get_client(cls):
        return cls().client
