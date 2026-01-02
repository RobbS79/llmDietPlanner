#!/usr/bin/env python
"""
Quick script to create a test dietary goal for testing the JSON prompt.
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'llm_diet_planner_project.settings')

try:
    import django
    django.setup()
    
    from django.contrib.auth.models import User
    from diet_planner.models import DietaryGoal
    
    # Get or create a test user
    user, created = User.objects.get_or_create(
        username='testuser',
        defaults={'email': 'test@test.com'}
    )
    if created:
        user.set_password('testpass123')
        user.save()
        print("Created test user: testuser")
    else:
        print("Using existing test user: testuser")
    
    # Create a test goal
    goal = DietaryGoal.objects.create(
        user=user,
        prompt="I want to lose 5kg in 2 months while maintaining muscle mass. I prefer healthy meals with lots of vegetables.",
        dietary_restrictions="No gluten, lactose intolerant, vegetarian",
        country="CZ",
        city="Prague",
        currency="CZK",
        language_code="cs"
    )
    
    print("\n" + "=" * 80)
    print("SUCCESS! Created test dietary goal")
    print("=" * 80)
    print("Goal ID: {}".format(goal.id))
    print("User: {}".format(goal.user.username))
    print("Country: {} | City: {}".format(goal.country, goal.city))
    print("Status: {}".format(goal.status))
    print("\nNow you can:")
    print("1. View JSON: python test_json_prompt.py {}".format(goal.id))
    print("2. Or access via API: http://localhost:8000/api/goals/{}/prompt-debug/".format(goal.id))
    print("=" * 80)
    
except ImportError:
    print("Error: Django not found. Please activate the virtual environment:")
    print("  source venv/bin/activate")
    sys.exit(1)
except Exception as e:
    print("Error: {}".format(e))
    import traceback
    traceback.print_exc()
    sys.exit(1)

