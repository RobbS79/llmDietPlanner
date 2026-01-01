"""
Celery tasks for login_app.
Handles async email sending for user verification.
"""
from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.urls import reverse
from django.contrib.auth.models import User
from .utils import get_verification_email_content
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_verification_email_task(self, user_id: int, uid: str, token: str, base_url: str = None):
    """
    Async Celery task to send email verification email.
    
    Args:
        user_id: ID of the user to send email to
        uid: Base64 encoded user ID for verification link
        token: Verification token
        base_url: Base URL for building verification link (optional)
        
    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        user = User.objects.get(id=user_id)
        
        # Build verification URL
        if base_url:
            verification_url = f"{base_url}/api/auth/verify-email/?uid={uid}&token={token}"
        else:
            # Fallback: try to build URL (may not work in all contexts)
            try:
                verify_path = reverse('login_app:verify-email')
                verification_url = f"{settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'localhost'}{verify_path}?uid={uid}&token={token}"
            except Exception:
                verification_url = f"/api/auth/verify-email/?uid={uid}&token={token}"
        
        # Get email content (text and HTML)
        email_content = get_verification_email_content(user.username, verification_url)
        
        # Send email with both text and HTML versions
        msg = EmailMultiAlternatives(
            subject=email_content['subject'],
            body=email_content['text_content'],
            from_email=email_content['from_email'],
            to=[user.email]
        )
        msg.attach_alternative(email_content['html_content'], "text/html")
        msg.send(fail_silently=False)  # Raise exception if email fails so Celery can retry
        
        logger.info(f"Verification email sent successfully to {user.email}")
        return True
        
    except User.DoesNotExist:
        logger.error(f"User with id {user_id} not found for email verification")
        return False
    except Exception as exc:
        logger.error(f"Failed to send verification email to user {user_id}: {str(exc)}")
        # Retry the task with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

