#!/usr/bin/env python
"""
Script to create a Django superuser programmatically.
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'llm_diet_planner_project.settings')
django.setup()

from django.contrib.auth.models import User

def create_superuser(username='admin', email='admin@example.com', password='admin123'):
    """Create a superuser if it doesn't exist."""
    if User.objects.filter(username=username).exists():
        print(f"Superuser '{username}' already exists!")
        user = User.objects.get(username=username)
        if not user.is_superuser:
            user.is_superuser = True
            user.is_staff = True
            user.save()
            print(f"Updated user '{username}' to superuser.")
        else:
            print(f"User '{username}' is already a superuser.")
        return user
    else:
        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password
        )
        print(f"Superuser '{username}' created successfully!")
        print(f"Email: {email}")
        print(f"Password: {password}")
        return user

if __name__ == '__main__':
    # Default credentials (you can modify these)
    username = sys.argv[1] if len(sys.argv) > 1 else 'admin'
    email = sys.argv[2] if len(sys.argv) > 2 else 'admin@example.com'
    password = sys.argv[3] if len(sys.argv) > 3 else 'admin123'
    
    print("Creating superuser...")
    create_superuser(username, email, password)
    print("\nYou can now log in to Django admin at: http://localhost:8000/admin/")

