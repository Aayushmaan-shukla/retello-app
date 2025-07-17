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

    # Compare-phones microservice URL (defaults to same base as MICRO_URL)
    COMPARE_PHONES_URL: str = os.getenv("COMPARE_PHONES_URL", "https://api-microretello.enpointe.io/compare-phones")

    # [NEW] Added on 2024-03-21: Streaming-related settings
    STREAMING_CHUNK_SIZE: int = int(os.getenv("STREAMING_CHUNK_SIZE", "1024"))  # Size of each chunk in bytes
    STREAMING_TIMEOUT: int = int(os.getenv("STREAMING_TIMEOUT", "300"))  # Timeout in seconds for streaming responses

    # Gupshup WhatsApp API Configuration
    GUPSHUP_API_KEY: str = os.getenv("GUPSHUP_API_KEY", "")
    GUPSHUP_BASE_URL: str = os.getenv("GUPSHUP_BASE_URL", "")
    GUPSHUP_APP_NAME: str = os.getenv("GUPSHUP_APP_NAME", "RetelloWA")
    GUPSHUP_APP_ID: str = os.getenv("GUPSHUP_APP_ID", "")
    GUPSHUP_WABA_ID: str = os.getenv("GUPSHUP_WABA_ID", "")
    # Updated with actual WhatsApp Business phone number
    GUPSHUP_SOURCE_PHONE: str = os.getenv("GUPSHUP_SOURCE_PHONE", "")  # Your WhatsApp Business number
    
    # Gupshup Authentication Template ID (from curl command)
    GUPSHUP_AUTH_TEMPLATE_ID: str = os.getenv("GUPSHUP_AUTH_TEMPLATE_ID", "")
    
    # OTP Configuration
    OTP_EXPIRY_MINUTES: int = int(os.getenv("OTP_EXPIRY_MINUTES", "5"))
    OTP_MAX_ATTEMPTS: int = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
    OTP_RATE_LIMIT_PER_HOUR: int = int(os.getenv("OTP_RATE_LIMIT_PER_HOUR", "10"))  # Increased for testing
    OTP_LENGTH: int = int(os.getenv("OTP_LENGTH", "6"))
    
    # Gupshup Limits (from dashboard)
    GUPSHUP_DAILY_LIMIT: int = int(os.getenv("GUPSHUP_DAILY_LIMIT", "250"))  # 250 customers/24 hrs
    
    # Invite System Configuration
    INVITE_MAX_GENERATION_LIMIT: int = int(os.getenv("INVITE_MAX_GENERATION_LIMIT", "10"))  # Max invites per user
    INVITE_CODE_LENGTH: int = int(os.getenv("INVITE_CODE_LENGTH", "12"))  # Length of invite codes
    INVITE_DEFAULT_MAX_USES: int = int(os.getenv("INVITE_DEFAULT_MAX_USES", "1"))  # Default uses per invite
    INVITE_GUEST_TOKEN_EXPIRY_HOURS: int = int(os.getenv("INVITE_GUEST_TOKEN_EXPIRY_HOURS", "24"))  # Guest token expiry

    # CORS
    BACKEND_CORS_ORIGINS: list = [
        "http://localhost:3000",
        "http://192.168.0.61:3000",
        "http://localhost:4100",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:4100",
        "https://api-retello.enpointe.io",
        "https://api-uat-retello.enpointe.io",
        "https://api-uat-microretello.enpointe.io",
        "https://retello.enpointe.io",
        "https://early.retello.ai",
        "https://api-early.retello.ai"
    ]

    class Config:
        case_sensitive = True

settings = Settings() 
