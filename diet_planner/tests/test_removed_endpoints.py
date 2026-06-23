"""Pantry-toggle PATCH and price-feedback endpoints are removed."""
from django.test import TestCase
from django.urls import NoReverseMatch, reverse


class RemovedEndpoints(TestCase):
    def test_price_feedback_route_gone(self):
        with self.assertRaises(NoReverseMatch):
            reverse("diet_planner:goal-price-feedback", kwargs={"goal_id": 1})

    def test_price_feedback_view_class_gone(self):
        from diet_planner import views
        self.assertFalse(
            hasattr(views, "PriceFeedbackView"),
            "PriceFeedbackView should be removed from views",
        )
