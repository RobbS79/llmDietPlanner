"""The LLM outage canary.

Four Gemini outages (2026-07-27 credits, 08-06 account denial, 08-07 retired
model, 08-23 billing dunning) were each found by accident, because nothing
periodically asks the only question that matters: can prod generate right now?
These cover the probe and its alert path.
"""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from diet_planner.services.llm_health import notify_slack, probe_llm


class ProbeLlmTest(TestCase):
    def test_reports_healthy_when_the_model_answers(self):
        result = probe_llm(generate=lambda prompt: 'ok')

        self.assertTrue(result.ok)
        self.assertEqual(result.error_type, '')

    def test_reports_unhealthy_and_keeps_the_error_when_the_call_raises(self):
        def denied(prompt):
            raise PermissionError(
                '403 Lightning dunning decision is deny for project: '
                'projects/922038889178')

        result = probe_llm(generate=denied)

        self.assertFalse(result.ok)
        self.assertEqual(result.error_type, 'PermissionError')
        self.assertIn('Lightning dunning', result.detail)

    def test_reports_unhealthy_when_the_call_succeeds_but_returns_nothing(self):
        result = probe_llm(generate=lambda prompt: '   ')

        self.assertFalse(result.ok)
        self.assertEqual(result.error_type, 'EmptyResponse')


class NotifySlackTest(TestCase):
    def test_does_not_post_when_no_webhook_is_configured(self):
        calls = []

        sent = notify_slack('prod LLM is down', webhook_url='',
                            post=lambda url, payload: calls.append(url))

        self.assertFalse(sent)
        self.assertEqual(calls, [])

    def test_posts_the_message_to_the_configured_webhook(self):
        calls = []

        sent = notify_slack('prod LLM is down',
                            webhook_url='https://hooks.slack.test/abc',
                            post=lambda url, payload: calls.append((url, payload)))

        self.assertTrue(sent)
        self.assertEqual(len(calls), 1)
        url, payload = calls[0]
        self.assertEqual(url, 'https://hooks.slack.test/abc')
        self.assertIn('prod LLM is down', payload['text'])

    def test_swallows_a_slack_failure_rather_than_masking_the_outage(self):
        def broken(url, payload):
            raise OSError('slack unreachable')

        with self.assertLogs('diet_planner.services.llm_health', 'WARNING'):
            sent = notify_slack('prod LLM is down',
                                webhook_url='https://hooks.slack.test/abc',
                                post=broken)

        self.assertFalse(sent)


@override_settings(LLM_HEALTH_SLACK_WEBHOOK_URL='https://hooks.slack.test/abc')
class CheckLlmHealthCommandTest(TestCase):
    def test_stays_quiet_and_succeeds_when_the_llm_is_healthy(self):
        calls = []

        call_command('check_llm_health',
                     generate=lambda prompt: 'ok',
                     post=lambda url, payload: calls.append(payload),
                     stdout=StringIO(), stderr=StringIO())

        self.assertEqual(calls, [])

    def test_alerts_and_fails_the_job_when_the_llm_is_down(self):
        calls = []

        def denied(prompt):
            raise PermissionError('403 Lightning dunning decision is deny')

        with self.assertRaises(CommandError):
            call_command('check_llm_health', generate=denied,
                         post=lambda url, payload: calls.append(payload),
                         stdout=StringIO(), stderr=StringIO())

        self.assertEqual(len(calls), 1)
        self.assertIn('Lightning dunning', calls[0]['text'])
