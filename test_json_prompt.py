#!/usr/bin/env python
"""
Quick test script to generate and display the LLM JSON prompt structure.
This doesn't require Node.js or the React frontend.

Usage:
    source venv/bin/activate
    python test_json_prompt.py [goal_id]
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'llm_diet_planner_project.settings')

try:
    import django
    import django.db.utils
    django.setup()
except ImportError:
    print("Error: Django not found. Please activate the virtual environment:")
    print("  source venv/bin/activate")
    sys.exit(1)

from diet_planner.models import DietaryGoal
from diet_planner.tasks import build_llm_prompt_json
import json

def main():
    # Check if any goals exist
    try:
        goals = DietaryGoal.objects.all()
    except django.db.utils.OperationalError as e:
        if 'no such table' in str(e):
            print("Error: Database tables don't exist yet.")
            print("\nPlease run migrations first:")
            print("  python manage.py migrate")
            print("\nIf migrations don't exist, create them:")
            print("  python manage.py makemigrations")
            print("  python manage.py migrate")
            return
        raise
    
    if not goals.exists():
        print("No dietary goals found in database.")
        print("\nTo create a test goal, run:")
        print("  python manage.py shell")
        print("\nThen in the shell:")
        print("""
from django.contrib.auth.models import User
from diet_planner.models import DietaryGoal

user, _ = User.objects.get_or_create(username='testuser', defaults={'email': 'test@test.com'})
goal = DietaryGoal.objects.create(
    user=user,
    prompt="I want to lose 5kg in 2 months while maintaining muscle mass",
    dietary_restrictions="No gluten, lactose intolerant",
    country="CZ",
    city="Prague",
    currency="CZK",
    language_code="cs"
)
print(f"Created goal ID: {goal.id}")
        """)
        return
    
    # Show all goals
    print("Found {} dietary goal(s):\n".format(goals.count()))
    for goal in goals:
        print("  ID: {} | User: {} | Status: {}".format(goal.id, goal.user.username, goal.status))
        print("  Country: {} | City: {}".format(goal.country, goal.city))
        print()
    
    # Ask which goal to display (or use first one)
    if len(sys.argv) > 1:
        goal_id = int(sys.argv[1])
    else:
        goal_id = goals.first().id
        print("Using goal ID: {}\n".format(goal_id))
    
    try:
        goal = DietaryGoal.objects.get(id=goal_id)
        
        # Build JSON prompt
        llm_prompt_json = build_llm_prompt_json(goal)
        
        # Display formatted JSON
        print("=" * 80)
        print("LLM PROMPT JSON STRUCTURE")
        print("=" * 80)
        print(json.dumps(llm_prompt_json, indent=2, ensure_ascii=False))
        print("=" * 80)
        
        # Also save to file
        output_file = 'llm_prompt_goal_{}.json'.format(goal_id)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(llm_prompt_json, f, indent=2, ensure_ascii=False)
        print("\nSaved to: {}".format(output_file))
        
    except DietaryGoal.DoesNotExist:
        print("Error: Goal with ID {} not found.".format(goal_id))
        print("Available goal IDs: {}".format([g.id for g in goals]))

if __name__ == '__main__':
    main()

