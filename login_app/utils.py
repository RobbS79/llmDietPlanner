"""
Utility functions for email verification token generation.
"""
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from typing import Tuple


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

