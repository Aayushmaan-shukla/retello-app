from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1 import auth, user, session, chat
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

# [MODIFIED] Updated on 2024-03-21: Enhanced CORS settings for streaming support
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type", "Content-Length", "Transfer-Encoding"]  # Added for streaming support
)

logger.info("Application startup: Initializing routes")
# Include routers
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(user.router, prefix=settings.API_V1_STR)
app.include_router(session.router, prefix=settings.API_V1_STR)
app.include_router(chat.router, prefix=settings.API_V1_STR)
logger.info("Application startup: Routes initialized successfully")

@app.get("/")
def root():
    logger.debug("Root endpoint accessed")
    return {"message": "Hello World"} 