from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Import models to ensure they're registered with SQLAlchemy
from app.models.user import User
from app.models.session import Session
from app.models.chat import Chat
#from app.models.otp_verification import OTPVerification

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 