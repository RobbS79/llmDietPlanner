"""
Utility functions for email verification token generation.
"""
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.conf import settings
from typing import Tuple, Dict


def generate_email_verification_token(user) -> Tuple[str, str]:
    """
    Generate email verification token and UID for a user.
    
    Args:
        user: User instance
        
    Returns:
        Tuple of (uid, token) strings
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return uid, token


def verify_email_token(user, uid: str, token: str) -> bool:
    """
    Verify email verification token for a user.
    
    Args:
        user: User instance
        uid: Base64 encoded user ID
        token: Verification token
        
    Returns:
        True if token is valid, False otherwise
    """
    try:
        from django.utils.http import urlsafe_base64_decode
        from django.utils.encoding import force_str
        
        user_id = force_str(urlsafe_base64_decode(uid))
        if str(user.pk) != user_id:
            return False
        
        return default_token_generator.check_token(user, token)
    except (TypeError, ValueError, OverflowError):
        return False


def get_password_reset_email_content(username: str, reset_url: str) -> Dict[str, str]:
    """
    Generate email content for password reset email.
    """
    subject = 'Reset your password'
    from_email = f"Vařto <{settings.DEFAULT_FROM_EMAIL}>"

    text_content = f'''Hello {username},

We received a request to reset your password for your Vařto account.

Click the following link to set a new password:

{reset_url}

This link will expire in 24 hours.

If you did not request a password reset, please ignore this email. Your password will remain unchanged.

Best regards,
Vařto Team'''

    html_content = f'''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background-color: #f8f9fa; padding: 30px; border-radius: 8px;">
        <h1 style="color: #2c3e50; margin-top: 0;">Reset Your Password</h1>
        <p>Hello {username},</p>
        <p>We received a request to reset your password for your Vařto account.</p>
        <p>Click the button below to set a new password:</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_url}" style="display: inline-block; padding: 12px 30px; background-color: #4F46E5; color: #ffffff; text-decoration: none; border-radius: 5px; font-weight: bold;">Reset Password</a>
        </div>
        <p style="font-size: 14px; color: #666;">Or copy and paste this link into your browser:</p>
        <p style="font-size: 12px; color: #999; word-break: break-all; background-color: #f1f1f1; padding: 10px; border-radius: 4px;">{reset_url}</p>
        <p style="font-size: 14px; color: #666;"><strong>This link will expire in 24 hours.</strong></p>
        <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
        <p style="font-size: 12px; color: #999;">If you did not request a password reset, please ignore this email.</p>
        <p style="margin-top: 30px;">Best regards,<br><strong>Vařto Team</strong></p>
    </div>
</body>
</html>'''

    return {
        'subject': subject,
        'text_content': text_content,
        'html_content': html_content,
        'from_email': from_email,
    }


def get_verification_email_content(username: str, verification_url: str) -> Dict[str, str]:
    """
    Generate email content (text and HTML) for verification email.
    
    Args:
        username: User's username
        verification_url: Full URL for email verification
        
    Returns:
        Dictionary with 'subject', 'text_content', 'html_content', and 'from_email' keys
    """
    subject = 'Ověřte svou e-mailovou adresu'
    from_email = f"Vařto <{settings.DEFAULT_FROM_EMAIL}>"

    # Plain text version
    text_content = f'''Dobrý den {username},

děkujeme za registraci ve Vařto!

Kliknutím na následující odkaz potvrdíte svou e-mailovou adresu a aktivujete svůj účet:

{verification_url}

Platnost odkazu vyprší za 24 hodin.

Pokud jste si účet nezakládali, tento e-mail prosím ignorujte.

S pozdravem,
tým Vařto'''

    # HTML version (more professional, less likely to be marked as spam)
    html_content = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background-color: #f8f9fa; padding: 30px; border-radius: 8px;">
        <h1 style="color: #2c3e50; margin-top: 0;">Vítejte ve Vařto!</h1>

        <p>Dobrý den {username},</p>

        <p>děkujeme za registraci ve Vařto!</p>

        <p>Kliknutím na tlačítko níže potvrdíte svou e-mailovou adresu a aktivujete svůj účet:</p>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{verification_url}" style="display: inline-block; padding: 12px 30px; background-color: #047857; color: #ffffff; text-decoration: none; border-radius: 5px; font-weight: bold;">Ověřit e-mail</a>
        </div>

        <p style="font-size: 14px; color: #666;">Nebo zkopírujte tento odkaz do prohlížeče:</p>
        <p style="font-size: 12px; color: #999; word-break: break-all; background-color: #f1f1f1; padding: 10px; border-radius: 4px;">{verification_url}</p>

        <p style="font-size: 14px; color: #666;"><strong>Platnost odkazu vyprší za 24 hodin.</strong></p>

        <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">

        <p style="font-size: 12px; color: #999;">Pokud jste si účet nezakládali, tento e-mail prosím ignorujte.</p>

        <p style="margin-top: 30px;">S pozdravem,<br><strong>tým Vařto</strong></p>
    </div>
</body>
</html>'''
    
    return {
        'subject': subject,
        'text_content': text_content,
        'html_content': html_content,
        'from_email': from_email
    }

