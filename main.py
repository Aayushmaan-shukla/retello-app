from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1 import auth, user, session, chat, chat_name
from app.core.logging_config import setup_logging
import logging

# Initialize logging
loggers = setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# [MODIFIED] Updated on 2024-03-21: Enhanced CORS settings for streaming support and pagination
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Content-Type", 
        "Content-Length", 
        "Transfer-Encoding",  # For streaming support
        "X-Total-Count",      # For pagination metadata
        "X-Page-Size",        # For pagination metadata
        "X-Page-Offset",      # For pagination metadata
        "X-Has-More"          # For pagination metadata
    ]
)

logger.info("Application startup: Initializing routes")
# Include routers
app.include_router(auth.router, prefix=settings.API_V1_STR)
#app.include_router(otp_auth.router, prefix=settings.API_V1_STR)  # Add OTP auth router
#app.include_router(gupshup_test.router, prefix=settings.API_V1_STR)  # Add Gupshup test router
app.include_router(user.router, prefix=settings.API_V1_STR)
app.include_router(session.router, prefix=settings.API_V1_STR)
app.include_router(chat.router, prefix=settings.API_V1_STR)
app.include_router(chat_name.router, prefix=settings.API_V1_STR)
logger.info("Application startup: Routes initialized successfully")

@app.get("/")
def root():
    logger.debug("Root endpoint accessed")
    return {"message": "IF YOU SEE THIS, THE SERVER IS RUNNING"} 