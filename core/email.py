import logging
from pathlib import Path
from typing import Dict, Any
from emails import Message
from emails.template import JinjaTemplate
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def send_email(
    email_to: str,
    subject_template: str = "",
    html_template: str = "",
    environment: Dict[str, Any] = {},
) -> None:
    assert settings.EMAILS_FROM_EMAIL, "no provided configuration for email variables"
    
    try:
        logger.info(f"Attempting to send email to: {email_to}")
        logger.info(f"SMTP Host: {settings.SMTP_HOST}, Port: {settings.SMTP_PORT}")
        
        message = Message(
            subject=JinjaTemplate(subject_template),
            html=JinjaTemplate(html_template),
            mail_from=(settings.EMAILS_FROM_NAME, settings.EMAILS_FROM_EMAIL),
        )
        
        smtp_options = {"host": settings.SMTP_HOST, "port": settings.SMTP_PORT}
        if settings.SMTP_TLS:
            smtp_options["tls"] = True
        if settings.SMTP_USER:
            smtp_options["user"] = settings.SMTP_USER
        if settings.SMTP_PASSWORD:
            smtp_options["password"] = settings.SMTP_PASSWORD
            
        logger.info(f"SMTP options: {dict(smtp_options, password='***' if smtp_options.get('password') else None)}")
        
        response = message.send(to=email_to, render=environment, smtp=smtp_options)
        logger.info(f"Email send result: {response}")
        
        if hasattr(response, 'status_code'):
            if response.status_code not in [200, 250]:
                raise Exception(f"SMTP server returned status code: {response.status_code}")
        
    except Exception as e:
        logger.error(f"Failed to send email to {email_to}: {str(e)}")
        logger.exception("Email sending exception details")
        raise e


def send_test_email(email_to: str) -> None:
    subject = f"{settings.PROJECT_NAME} - Test email"
    html_content = f"""
    <p>Test email from {settings.PROJECT_NAME}</p>
    <p>This is a test email to verify SMTP configuration.</p>
    """
    send_email(
        email_to=email_to,
        subject_template=subject,
        html_template=html_content,
    )


def send_verification_email(email_to: str, verification_link: str, user_name: str = "") -> None:
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
            .header {{
                text-align: center;
                margin-bottom: 30px;
            }}
            .logo {{
                font-size: 28px;
                font-weight: bold;
                color: #333;
                margin-bottom: 10px;
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
            .button:hover {{
                background-color: #0056b3;
            }}
            .footer {{
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #eee;
                font-size: 12px;
                color: #666;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">{settings.PROJECT_NAME}</div>
                <h2>Welcome{", " + user_name if user_name else ""}!</h2>
            </div>
            
            <p>Thank you for registering with {settings.PROJECT_NAME}. To complete your registration and activate your account, please verify your email address by clicking the button below:</p>
            
            <div style="text-align: center;">
                <a href="{verification_link}" class="button">Verify Email Address</a>
            </div>
            
            <p>If the button doesn't work, you can also copy and paste the following link into your browser:</p>
            <p style="word-break: break-all; background-color: #f8f9fa; padding: 10px; border-radius: 5px;">
                {verification_link}
            </p>
            
            <p><strong>Important:</strong> This verification link will expire in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours for security reasons.</p>
            
            <p>If you didn't create an account with {settings.PROJECT_NAME}, please ignore this email.</p>
            
            <div class="footer">
                <p>This is an automated email from {settings.PROJECT_NAME}. Please do not reply to this email.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    send_email(
        email_to=email_to,
        subject_template=subject,
        html_template=html_content,
    )


def send_password_reset_email(email_to: str, reset_link: str, user_name: str = "") -> None:
    subject = f"{settings.PROJECT_NAME} - Password Reset"
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Password Reset</title>
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
            .header {{
                text-align: center;
                margin-bottom: 30px;
            }}
            .logo {{
                font-size: 28px;
                font-weight: bold;
                color: #333;
                margin-bottom: 10px;
            }}
            .button {{
                display: inline-block;
                padding: 15px 30px;
                background-color: #dc3545;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin: 20px 0;
                font-weight: bold;
            }}
            .button:hover {{
                background-color: #c82333;
            }}
            .footer {{
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #eee;
                font-size: 12px;
                color: #666;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">{settings.PROJECT_NAME}</div>
                <h2>Password Reset Request</h2>
            </div>
            
            <p>Hello{" " + user_name if user_name else ""},</p>
            
            <p>We received a request to reset your password for your {settings.PROJECT_NAME} account. Click the button below to reset your password:</p>
            
            <div style="text-align: center;">
                <a href="{reset_link}" class="button">Reset Password</a>
            </div>
            
            <p>If the button doesn't work, you can also copy and paste the following link into your browser:</p>
            <p style="word-break: break-all; background-color: #f8f9fa; padding: 10px; border-radius: 5px;">
                {reset_link}
            </p>
            
            <p><strong>Important:</strong> This password reset link will expire in 24 hours for security reasons.</p>
            
            <p>If you didn't request a password reset, please ignore this email. Your password will remain unchanged.</p>
            
            <div class="footer">
                <p>This is an automated email from {settings.PROJECT_NAME}. Please do not reply to this email.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    send_email(
        email_to=email_to,
        subject_template=subject,
        html_template=html_content,
    )
