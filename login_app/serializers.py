"""
DRF serializers for login_app (if needed for additional functionality).
"""
from rest_framework import serializers
from django.contrib.auth.models import User


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model (for responses)."""
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'is_active', 'date_joined']
        read_only_fields = ['id', 'is_active', 'date_joined']




