"""
Custom social account adapter for handling account linking and user creation.

This adapter customizes django-allauth's behavior for social authentication:
- Links social accounts to existing email accounts automatically
- Sets users as active immediately (trusts OAuth provider email verification)
- Generates unique usernames when provider doesn't provide one
"""
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth.models import User
import logging

logger = logging.getLogger(__name__)


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter that:
    - Links social accounts to existing email accounts
    - Sets users as active immediately (trusts provider email verification)
    - Generates unique usernames
    """

    def save_user(self, request, sociallogin, form=None):
        """
        Save user and mark as active (skip email verification).

        Social auth users from trusted providers (Google, Facebook) have
        already verified their email with the provider, so we trust that
        verification and activate the account immediately.
        
        Handles both new user creation and linking to existing accounts.
        """
        # Check if user already exists (this happens when linking accounts)
        user = sociallogin.user
        is_new_user = user.pk is None
        
        user = super().save_user(request, sociallogin, form)
        user.is_active = True
        user.save(update_fields=['is_active'])

        # Update profile with provider info
        if hasattr(user, 'profile'):
            # Only set primary_auth_provider if this is a new user or user hasn't set one
            # For existing users, keep their original auth provider but mark email as verified
            profile = user.profile
            update_fields = ['email_verified']
            
            if is_new_user or profile.primary_auth_provider == 'email':
                profile.primary_auth_provider = sociallogin.account.provider
                update_fields.append('primary_auth_provider')
            
            profile.email_verified = True
            profile.save(update_fields=update_fields)
            
            action = "Created" if is_new_user else "Linked"
            logger.info(f"{action} user {user.username} via {sociallogin.account.provider}")
        else:
            # Profile should exist due to signal, but handle edge case
            logger.warning(f"User {user.username} has no profile after social login")
        
        return user

    def populate_user(self, request, sociallogin, data):
        """
        Populate user with data from social provider.

        Ensures username is unique by appending numbers if needed.
        """
        user = super().populate_user(request, sociallogin, data)

        # Ensure unique username
        if not user.username or User.objects.filter(username=user.username).exists():
            email = data.get('email', '')
            base = email.split('@')[0] if email else 'user'
            # Clean the base username (remove special characters)
            base = ''.join(c for c in base if c.isalnum() or c == '_')
            if not base:
                base = 'user'

            username = base[:150]  # Max username length
            counter = 1
            while User.objects.filter(username=username).exists():
                suffix = str(counter)
                # Ensure we don't exceed max length
                username = f"{base[:150 - len(suffix) - 1]}{suffix}"
                counter += 1
            user.username = username

        return user

    def is_auto_signup_allowed(self, request, sociallogin):
        """
        Allow automatic signup for social accounts.

        This is called to determine whether the user should be automatically
        signed up (without showing a signup form) when using social auth.
        """
        return True
    
    def pre_social_login(self, request, sociallogin):
        """
        Called before a social account is logged in or created.
        
        This method handles automatic account linking when a user with the same
        email already exists. The email-based linking is enabled via
        SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT setting.
        """
        # Let allauth handle the linking automatically if configured
        # This method can be used for additional custom logic if needed
        if sociallogin.is_existing:
            logger.info(f"Linking existing user to {sociallogin.account.provider}")
        else:
            email = sociallogin.account.extra_data.get('email', '')
            if email:
                try:
                    existing_user = User.objects.get(email=email)
                    # The linking will be handled automatically by allauth
                    # due to SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
                    logger.info(f"Will link {sociallogin.account.provider} account to existing user: {existing_user.username}")
                except User.DoesNotExist:
                    pass  # New user, will be created
                except User.MultipleObjectsReturned:
                    logger.warning(f"Multiple users found with email {email}, using first one for linking")
