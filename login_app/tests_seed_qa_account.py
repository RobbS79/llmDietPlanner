"""Tests for the seed_qa_account management command.

The command provisions a stable QA user for post-deploy prod verification
(/qa-prod). It is gated on DO-secret env vars and idempotent, mirroring the
superuser bootstrap in start.sh. Credentials must NEVER be committed.
"""
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from unittest import mock


class SeedQaAccountCommandTest(TestCase):
    def _run(self, env):
        out = StringIO()
        with mock.patch.dict("os.environ", env, clear=False):
            call_command("seed_qa_account", stdout=out)
        return out.getvalue()

    def test_noop_when_credentials_unset(self):
        env = {"QA_TEST_USERNAME": "", "QA_TEST_PASSWORD": ""}
        output = self._run(env)
        self.assertEqual(User.objects.filter(username="qa_bot").count(), 0)
        self.assertIn("skipping", output.lower())

    def test_creates_active_user_when_set(self):
        env = {
            "QA_TEST_USERNAME": "qa_bot",
            "QA_TEST_PASSWORD": "qa-strong-pw-123",
            "QA_TEST_EMAIL": "qa@example.com",
        }
        output = self._run(env)
        user = User.objects.get(username="qa_bot")
        self.assertTrue(user.is_active)
        self.assertEqual(user.email, "qa@example.com")
        self.assertTrue(user.check_password("qa-strong-pw-123"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertIn("created", output.lower())

    def test_idempotent_resets_password_on_rerun(self):
        env = {"QA_TEST_USERNAME": "qa_bot", "QA_TEST_PASSWORD": "first-pw-123"}
        self._run(env)
        env["QA_TEST_PASSWORD"] = "second-pw-456"
        output = self._run(env)
        self.assertEqual(User.objects.filter(username="qa_bot").count(), 1)
        user = User.objects.get(username="qa_bot")
        self.assertTrue(user.check_password("second-pw-456"))
        self.assertIn("reset", output.lower())
