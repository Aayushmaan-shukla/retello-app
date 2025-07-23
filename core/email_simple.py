import smtplib
import ssl
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


def send_email_simple(
    email_to: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None
) -> bool:
    """
    Send email using Python's built-in smtplib
    Returns True if successful, False otherwise
    """
    try:
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_EMAIL}>"
        msg["To"] = email_to

        # Create the HTML part
        html_part = MIMEText(html_content, "html")
        msg.attach(html_part)

        # If text content is provided, add it
        if text_content:
            text_part = MIMEText(text_content, "plain")
            msg.attach(text_part)

        # Create SMTP session
        logger.info(f"Connecting to SMTP server: {settings.SMTP_HOST}:{settings.SMTP_PORT}")
        
        # Gmail specific configuration
        if settings.SMTP_HOST == "smtp.gmail.com":
            if settings.SMTP_PORT == 465:
                # Use SSL for port 465
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=context)
            else:
                # Use TLS for port 587 (default)
                context = ssl.create_default_context()
                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
                server.starttls(context=context)
        else:
            # Generic configuration for other providers
            if settings.SMTP_TLS and settings.SMTP_PORT != 465:
                # Use TLS
                context = ssl.create_default_context()
                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
                server.starttls(context=context)
            elif settings.SMTP_PORT == 465:
                # Use SSL for port 465
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=context)
            else:
                # Use plain connection
                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)

        # Login if credentials are provided
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            logger.info(f"Logging in as: {settings.SMTP_USER}")
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

        # Send email
        logger.info(f"Sending email to: {email_to}")
        text = msg.as_string()
        server.sendmail(settings.EMAILS_FROM_EMAIL, email_to, text)
        server.quit()
        
        logger.info("Email sent successfully!")
        return True

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP Authentication failed: {e}")
        logger.error("Check your email credentials (username/password)")
        return False
    except smtplib.SMTPConnectError as e:
        logger.error(f"SMTP Connection failed: {e}")
        logger.error("Check your SMTP host and port settings")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP Error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending email: {e}")
        logger.exception("Full exception details")
        return False


def send_test_email_simple(email_to: str) -> bool:
    """Send a test email using the simple SMTP method"""
    subject = f"{settings.PROJECT_NAME} - Test Email"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Email</title>
    </head>
    <body>
        <h2>Test Email from {settings.PROJECT_NAME}</h2>
        <p>This is a test email to verify your SMTP configuration is working correctly.</p>
        <p>If you received this email, your email setup is working! 🎉</p>
        <hr>
        <p><small>This is an automated test email from {settings.PROJECT_NAME}</small></p>
    </body>
    </html>
    """
    
    text_content = f"""
    Test Email from {settings.PROJECT_NAME}
    
    This is a test email to verify your SMTP configuration is working correctly.
    If you received this email, your email setup is working!
    
    This is an automated test email from {settings.PROJECT_NAME}
    """
    
    return send_email_simple(email_to, subject, html_content, text_content)


def send_verification_email_simple(email_to: str, verification_link: str, user_name: str = "") -> bool:
    """Send verification email using the simple SMTP method"""
    subject = f"{settings.PROJECT_NAME} - Email Verification"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Email Verification</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                margin: 0;
                padding: 20px;
                background-color: #f4f4f4;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background-color: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 0 20px rgba(0,0,0,0.1);
            }}
            .button {{
                display: inline-block;
                padding: 15px 30px;
                background-color: #007bff;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin: 20px 0;
                font-weight: bold;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>{settings.PROJECT_NAME}</h1>
            <h2>Welcome{f", {user_name}" if user_name else ""}!</h2>
            
            <p>Thank you for registering with {settings.PROJECT_NAME}. Please verify your email address by clicking the button below:</p>
            
            <div style="text-align: center;">
                <a href="{verification_link}" class="button">Verify Email Address</a>
            </div>
            
            <p>Or copy and paste this link into your browser:</p>
            <p style="word-break: break-all; background-color: #f8f9fa; padding: 10px; border-radius: 5px;">
                {verification_link}
            </p>
            
            <p><strong>Note:</strong> This link expires in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours.</p>
            
            <hr>
            <p><small>This is an automated email from {settings.PROJECT_NAME}. Please do not reply.</small></p>
        </div>
    </body>
    </html>
    """
    
    text_content = f"""
    Welcome to {settings.PROJECT_NAME}!
    
    Thank you for registering{f", {user_name}" if user_name else ""}. 
    
    Please verify your email address by visiting this link:
    {verification_link}
    
    This verification link will expire in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours.
    
    If you didn't create an account, please ignore this email.
    
    ---
    This is an automated email from {settings.PROJECT_NAME}. Please do not reply.
    """
    
    return send_email_simple(email_to, subject, html_content, text_content)
