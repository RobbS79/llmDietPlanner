"""
DRF serializers for login_app.

Includes serializers for:
- User model (basic responses)
- UserDetails for dj-rest-auth (with profile data)
"""
from rest_framework import serializers
from django.contrib.auth.models import User

try:
    from dj_rest_auth.serializers import UserDetailsSerializer as BaseUserDetailsSerializer
    DJ_REST_AUTH_AVAILABLE = True
except ImportError:
    DJ_REST_AUTH_AVAILABLE = False
    BaseUserDetailsSerializer = None


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model (for responses)."""

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'is_active', 'date_joined']
        read_only_fields = ['id', 'is_active', 'date_joined']


if DJ_REST_AUTH_AVAILABLE:
    class UserDetailsSerializer(BaseUserDetailsSerializer):
        """
        Extended user serializer with profile data for dj-rest-auth.

        This serializer is used by dj-rest-auth for the user endpoint
        and is included in the login/social auth responses.
        """
        free_generations_remaining = serializers.IntegerField(
            source='profile.free_generations_remaining',
            read_only=True,
            default=10
        )
        total_generations = serializers.IntegerField(
            source='profile.total_generations',
            read_only=True,
            default=0
        )
        primary_auth_provider = serializers.CharField(
            source='profile.primary_auth_provider',
            read_only=True,
            default='email'
        )
        email_verified = serializers.BooleanField(
            source='profile.email_verified',
            read_only=True,
            default=False
        )

        class Meta(BaseUserDetailsSerializer.Meta):
            fields = BaseUserDetailsSerializer.Meta.fields + (
                'free_generations_remaining',
                'total_generations',
                'primary_auth_provider',
                'email_verified',
            )




