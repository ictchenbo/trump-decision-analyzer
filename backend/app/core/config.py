from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseSettings):
    MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    DB_NAME: str = os.getenv("DB_NAME", "trump_decision_analyzer")
    PORT: int = int(os.getenv("PORT", 8000))
    API_PREFIX: str = "/api/v1"

settings = Settings()
