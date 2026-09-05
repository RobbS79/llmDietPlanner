from unittest.mock import MagicMock

from django.test import TestCase, override_settings
from slack_sdk.errors import SlackApiError

from social.models import SocialPost
from social.slack import Decision, SlackDrafts, draft_text


def _client(reactions=None, replies=None, bot_id='UBOT'):
    client = MagicMock()
    client.auth_test.return_value = {'user_id': bot_id}
    client.chat_postMessage.return_value = {'ts': '1700000000.000100'}
    client.files_upload_v2.return_value = {'file': {'id': 'F1'}}
    client.reactions_get.return_value = {'message': {'reactions': reactions or []}}
    client.conversations_replies.return_value = {'messages': replies or []}
    return client


def _post(**kw):
    defaults = dict(kind='deals', iso_week='2026-W37', scheduled_for='2026-09-07',
                    caption='Cibule je v akci.', group_variant='Stavím appku…',
                    image=b'PNG', slack_channel='C123', slack_ts='1700000000.000100')
    defaults.update(kw)
    return SocialPost.objects.create(**defaults)


def _slack_api_error(status=500, error='internal_error'):
    response = MagicMock()
    response.status_code = status
    response.data = {'ok': False, 'error': error}
    return SlackApiError(message=error, response=response)


@override_settings(SOCIAL_SLACK_CHANNEL='C123', SLACK_BOT_TOKEN='xoxb-test')
class PostDraftTests(TestCase):
    def test_posts_message_then_uploads_card_in_thread_and_stores_ts(self):
        client = _client()
        post = _post(slack_ts='', slack_channel='')
        SlackDrafts(client=client).post_draft(post)
        post.refresh_from_db()
        self.assertEqual(post.slack_ts, '1700000000.000100')
        self.assertEqual(post.slack_channel, 'C123')
        text = client.chat_postMessage.call_args_list[0].kwargs['text']
        self.assertIn('2026-09-07', text)
        self.assertIn('deals', text)
        self.assertIn('Cibule je v akci.', text)
        self.assertIn('✅', text)
        upload = client.files_upload_v2.call_args.kwargs
        self.assertEqual(upload['thread_ts'], '1700000000.000100')
        self.assertEqual(upload['content'], b'PNG')
        group_reply = [c for c in client.chat_postMessage.call_args_list
                       if 'Pro skupiny' in c.kwargs.get('text', '')]
        self.assertEqual(len(group_reply), 1)
        self.assertIn('Stavím appku', group_reply[0].kwargs['text'])

    def test_draft_text_marks_failed_caption(self):
        post = _post(caption='', error='caption failed validation: number 9,90')
        self.assertIn('caption:', draft_text(post))
        self.assertIn('failed validation', draft_text(post))

    def test_caption_is_html_escaped(self):
        post = _post(caption='Ovoce & zelenina <akce>')
        text = draft_text(post)
        self.assertIn('Ovoce &amp; zelenina &lt;akce&gt;', text)
        self.assertNotIn('Ovoce & zelenina <akce>', text)

    def test_upload_failure_leaves_ts_empty_and_propagates(self):
        client = _client()
        client.files_upload_v2.side_effect = _slack_api_error()
        post = _post(slack_ts='', slack_channel='')
        with self.assertRaises(SlackApiError):
            SlackDrafts(client=client).post_draft(post)
        post.refresh_from_db()
        self.assertEqual(post.slack_ts, '')
        self.assertEqual(post.slack_channel, '')

    def test_no_upload_when_image_is_none(self):
        client = _client()
        post = _post(slack_ts='', slack_channel='', image=None)
        SlackDrafts(client=client).post_draft(post)
        client.files_upload_v2.assert_not_called()

    def test_no_group_reply_when_group_variant_empty(self):
        client = _client()
        post = _post(slack_ts='', slack_channel='', group_variant='')
        SlackDrafts(client=client).post_draft(post)
        # only the parent chat_postMessage call, no group-variant reply
        self.assertEqual(client.chat_postMessage.call_count, 1)


@override_settings(SOCIAL_SLACK_CHANNEL='C123', SLACK_BOT_TOKEN='xoxb-test')
class ReadDecisionTests(TestCase):
    def test_no_reaction_is_pending(self):
        post = _post()
        d = SlackDrafts(client=_client()).read_decision(post)
        self.assertEqual(d, Decision('pending', '', None))

    def test_missing_reactions_key_is_pending(self):
        client = _client()
        client.reactions_get.return_value = {'message': {}}
        d = SlackDrafts(client=client).read_decision(_post())
        self.assertEqual(d.status, 'pending')

    def test_checkmark_from_human_approves(self):
        client = _client(reactions=[{'name': 'white_check_mark', 'users': ['UHUMAN'], 'count': 1}])
        d = SlackDrafts(client=client).read_decision(_post())
        self.assertEqual(d.status, 'approved')
        self.assertEqual(d.approved_by, 'UHUMAN')

    def test_heavy_check_mark_alias_approves(self):
        client = _client(reactions=[{'name': 'heavy_check_mark', 'users': ['UHUMAN'], 'count': 1}])
        d = SlackDrafts(client=client).read_decision(_post())
        self.assertEqual(d.status, 'approved')

    def test_bot_reaction_is_ignored(self):
        client = _client(reactions=[{'name': 'white_check_mark', 'users': ['UBOT'], 'count': 1}])
        self.assertEqual(SlackDrafts(client=client).read_decision(_post()).status, 'pending')

    def test_bot_only_reject_is_pending(self):
        client = _client(reactions=[{'name': 'x', 'users': ['UBOT'], 'count': 1}])
        self.assertEqual(SlackDrafts(client=client).read_decision(_post()).status, 'pending')

    def test_cross_rejects_even_with_checkmark(self):
        client = _client(reactions=[{'name': 'white_check_mark', 'users': ['UHUMAN'], 'count': 1},
                                    {'name': 'x', 'users': ['UHUMAN'], 'count': 1}])
        self.assertEqual(SlackDrafts(client=client).read_decision(_post()).status, 'rejected')

    def test_last_caption_reply_overrides(self):
        client = _client(
            reactions=[{'name': 'white_check_mark', 'users': ['UHUMAN'], 'count': 1}],
            replies=[{'ts': '1', 'text': 'parent', 'user': 'UBOT'},
                     {'ts': '2', 'text': 'caption: první verze', 'user': 'UHUMAN'},
                     {'ts': '3', 'text': 'Caption:  Cibule je tenhle týden v akci v Lidlu.', 'user': 'UHUMAN'},
                     {'ts': '4', 'text': 'nice', 'user': 'UHUMAN'}])
        d = SlackDrafts(client=client).read_decision(_post())
        self.assertEqual(d.caption_override, 'Cibule je tenhle týden v akci v Lidlu.')

    def test_bot_caption_reply_after_human_is_ignored(self):
        client = _client(
            replies=[{'ts': '1', 'text': 'parent', 'user': 'UBOT'},
                     {'ts': '2', 'text': 'caption: lidský návrh', 'user': 'UHUMAN'},
                     {'ts': '3', 'text': 'caption: bot návrh', 'user': 'UBOT'}])
        d = SlackDrafts(client=client).read_decision(_post())
        self.assertEqual(d.caption_override, 'lidský návrh')

    def test_reply_posts_in_thread(self):
        client = _client()
        SlackDrafts(client=client).reply(_post(), 'Published: https://facebook.com/x')
        kwargs = client.chat_postMessage.call_args.kwargs
        self.assertEqual(kwargs['thread_ts'], '1700000000.000100')
        self.assertEqual(kwargs['channel'], 'C123')

    def test_reply_swallows_slack_api_error(self):
        client = _client()
        client.chat_postMessage.side_effect = _slack_api_error()
        # must not raise
        SlackDrafts(client=client).reply(_post(), 'Published: https://facebook.com/x')

    def test_reply_channel_posts_without_thread(self):
        client = _client()
        SlackDrafts(client=client).reply_channel('Skipped this week: no deals')
        kwargs = client.chat_postMessage.call_args.kwargs
        self.assertEqual(kwargs['channel'], 'C123')
        self.assertNotIn('thread_ts', kwargs)


class UnconfiguredTests(TestCase):
    @override_settings(SOCIAL_SLACK_CHANNEL='', SLACK_BOT_TOKEN='')
    def test_missing_config_raises_clear_error(self):
        from social.slack import SlackNotConfigured
        with self.assertRaises(SlackNotConfigured):
            SlackDrafts()

    @override_settings(SOCIAL_SLACK_CHANNEL='', SLACK_BOT_TOKEN='xoxb-test')
    def test_missing_channel_raises_even_with_client_injected(self):
        from social.slack import SlackNotConfigured
        with self.assertRaises(SlackNotConfigured):
            SlackDrafts(client=_client())

    @override_settings(SOCIAL_SLACK_CHANNEL='C123', SLACK_BOT_TOKEN='')
    def test_missing_token_is_fine_when_client_injected(self):
        # no exception: the token check is skipped when a client is injected
        SlackDrafts(client=_client())
