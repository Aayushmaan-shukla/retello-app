from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from core.email import send_test_email
from core.email_simple import send_test_email_simple
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/email", tags=["email"])


class TestEmailRequest(BaseModel):
    email: EmailStr


@router.post("/test")
def send_test_email_endpoint(request: TestEmailRequest):
    """
    Send a test email to verify SMTP configuration
    """
    try:
        # Try the simple method first
        success = send_test_email_simple(request.email)
        if success:
            return {"message": f"Test email sent successfully to {request.email}", "method": "simple"}
        else:
            # Fallback to the original method
            send_test_email(request.email)
            return {"message": f"Test email sent successfully to {request.email}", "method": "emails_library"}
    except Exception as e:
        logger.error(f"Failed to send test email: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send test email: {str(e)}"
        )
