from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import EmailStr, validator
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "Retello"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"
    
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "localhost")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "retello")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")

    @validator("DATABASE_URL", pre=True)
    def assemble_db_connection(cls, v: Optional[str], values: dict) -> str:
        if v and isinstance(v, str):
            return v
        return f"postgresql://{values.get('POSTGRES_USER')}:{values.get('POSTGRES_PASSWORD')}@{values.get('POSTGRES_SERVER')}:{values.get('POSTGRES_PORT')}/{values.get('POSTGRES_DB')}"

    JWT_SECRET: str = os.getenv("JWT_SECRET", "your-secret-key")
    JWT_ALGORITHM: str = "HS256"
    
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    MICRO_URL: str = os.getenv("MICRO_URL", "https://api-microretello.enpointe.io/ask")
    
    # Why-this-phone microservice URL (defaults to same base as MICRO_URL)
    WHY_THIS_PHONE_URL: str = os.getenv("WHY_THIS_PHONE_URL", "https://api-microretello.enpointe.io/why-this-phone")
    
    # Get-more-phones microservice URL (defaults to same base as MICRO_URL)
    GET_MORE_PHONES_URL: str = os.getenv("GET_MORE_PHONES_URL", "https://api-microretello.enpointe.io/get-more-phones")

    # [NEW] Added on 2024-03-21: Streaming-related settings
    STREAMING_CHUNK_SIZE: int = int(os.getenv("STREAMING_CHUNK_SIZE", "1024"))  # Size of each chunk in bytes
    STREAMING_TIMEOUT: int = int(os.getenv("STREAMING_TIMEOUT", "300"))  # Timeout in seconds for streaming responses

    # CORS
    BACKEND_CORS_ORIGINS: list = [
        "http://localhost:3000",
        "http://192.168.0.61:3000",
        "http://localhost:4100",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:4100",
        "https://api-retello.enpointe.io",
        "https://retello-uat.enpointe.io",
        "https://retello.enpointe.io",
        "https://early.retello.ai",
        "https://api-early.retello.ai"
    ]

    class Config:
        case_sensitive = True

settings = Settings() 
