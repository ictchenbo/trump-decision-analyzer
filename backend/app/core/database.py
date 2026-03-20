from pymongo import MongoClient
from .config import settings
import logging

logger = logging.getLogger(__name__)

class Database:
    client: MongoClient = None
    db = None

    def connect(self):
        try:
            self.client = MongoClient(settings.MONGODB_URL)
            self.db = self.client[settings.DB_NAME]
            logger.info("Successfully connected to MongoDB (sync)")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    def disconnect(self):
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")

db = Database()
