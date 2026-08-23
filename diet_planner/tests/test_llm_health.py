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
                            post=lambda url, payload, headers: calls.append(url))

        self.assertFalse(sent)
        self.assertEqual(calls, [])

    def test_posts_the_message_to_the_configured_webhook(self):
        calls = []

        sent = notify_slack('prod LLM is down',
                            webhook_url='https://hooks.slack.test/abc',
                            post=lambda url, payload, headers: calls.append((url, payload)))

        self.assertTrue(sent)
        self.assertEqual(len(calls), 1)
        url, payload = calls[0]
        self.assertEqual(url, 'https://hooks.slack.test/abc')
        self.assertIn('prod LLM is down', payload['text'])

    def test_swallows_a_slack_failure_rather_than_masking_the_outage(self):
        def broken(url, payload, headers):
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
                     post=lambda url, payload, headers: calls.append(payload),
                     stdout=StringIO(), stderr=StringIO())

        self.assertEqual(calls, [])

    def test_alerts_and_fails_the_job_when_the_llm_is_down(self):
        calls = []

        def denied(prompt):
            raise PermissionError('403 Lightning dunning decision is deny')

        with self.assertRaises(CommandError):
            call_command('check_llm_health', generate=denied,
                         post=lambda url, payload, headers: calls.append(payload),
                         stdout=StringIO(), stderr=StringIO())

        self.assertEqual(len(calls), 1)
        self.assertIn('Lightning dunning', calls[0]['text'])


class NotifySlackBotTokenTest(TestCase):
    """Delivery via chat.postMessage, reusing the bot credentials that already
    exist for slack_bot — no incoming webhook to create."""

    def test_posts_to_chat_postmessage_with_the_bot_token(self):
        calls = []

        sent = notify_slack('prod LLM is down', bot_token='xoxb-test',
                            channel='C0B6L3',
                            post=lambda url, payload, headers: (
                                calls.append((url, payload, headers)) or {'ok': True}))

        self.assertTrue(sent)
        url, payload, headers = calls[0]
        self.assertEqual(url, 'https://slack.com/api/chat.postMessage')
        self.assertEqual(payload['channel'], 'C0B6L3')
        self.assertIn('prod LLM is down', payload['text'])
        self.assertEqual(headers['Authorization'], 'Bearer xoxb-test')

    def test_treats_an_ok_false_body_as_undelivered(self):
        # Slack answers HTTP 200 with {"ok": false} when the bot is not in the
        # channel. Trusting the status code would report a phantom delivery.
        with self.assertLogs('diet_planner.services.llm_health', 'WARNING'):
            sent = notify_slack('prod LLM is down', bot_token='xoxb-test',
                                channel='C0B6L3',
                                post=lambda url, payload, headers: {
                                    'ok': False, 'error': 'not_in_channel'})

        self.assertFalse(sent)

    def test_prefers_the_bot_token_over_a_webhook_when_both_are_set(self):
        calls = []

        notify_slack('prod LLM is down', webhook_url='https://hooks.slack.test/abc',
                     bot_token='xoxb-test', channel='C0B6L3',
                     post=lambda url, payload, headers: (
                         calls.append(url) or {'ok': True}))

        self.assertEqual(calls, ['https://slack.com/api/chat.postMessage'])

    @override_settings(SLACK_BOT_TOKEN='xoxb-test',
                       LLM_HEALTH_SLACK_CHANNEL='C0B6L3',
                       LLM_HEALTH_SLACK_WEBHOOK_URL='')
    def test_command_alerts_through_the_bot_token(self):
        calls = []

        def denied(prompt):
            raise PermissionError('403 Lightning dunning decision is deny')

        with self.assertRaises(CommandError):
            call_command('check_llm_health', generate=denied,
                         post=lambda url, payload, headers: (
                             calls.append((url, payload)) or {'ok': True}),
                         stdout=StringIO(), stderr=StringIO())

        self.assertEqual(len(calls), 1)
        url, payload = calls[0]
        self.assertEqual(url, 'https://slack.com/api/chat.postMessage')
        self.assertEqual(payload['channel'], 'C0B6L3')
