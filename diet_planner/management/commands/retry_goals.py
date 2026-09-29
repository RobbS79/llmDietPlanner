from django.core.management.base import BaseCommand
from diet_planner.models import DietaryGoal, DietaryPlan
from diet_planner.tasks import generate_meal_pool_task


class Command(BaseCommand):
    help = "Retry failed dietary goals by ID"

    def add_arguments(self, parser):
        parser.add_argument("goal_ids", nargs="+", type=int)

    def handle(self, *args, **options):
        for goal_id in options["goal_ids"]:
            try:
                goal = DietaryGoal.objects.get(id=goal_id)
                self.stdout.write(f"Goal {goal_id}: status={goal.status}")
                if (goal.status == DietaryGoal.StatusChoices.COMPLETED
                        or DietaryPlan.objects.filter(dietary_goal=goal).exists()):
                    self.stdout.write(self.style.WARNING(
                        f"Goal {goal_id}: already has a plan, skipping"))
                    continue
                if not any(goal.pool_counts().values()):
                    self.stdout.write(self.style.WARNING(
                        f"Goal {goal_id}: legacy goal (no pool counts), cannot regenerate, skipping"))
                    continue
                goal.status = DietaryGoal.StatusChoices.PENDING
                goal.error_message = ""
                goal.save(update_fields=["status", "error_message"])
                task = generate_meal_pool_task.delay(goal_id)
                goal.celery_task_id = task.id
                goal.save(update_fields=["celery_task_id"])
                self.stdout.write(self.style.SUCCESS(
                    f"Goal {goal_id}: reset to pending, task {task.id} dispatched"
                ))
            except DietaryGoal.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Goal {goal_id}: not found"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Goal {goal_id}: {e}"))
