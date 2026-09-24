from datetime import date
from unittest.mock import MagicMock

from django.test import TestCase, override_settings
from slack_sdk.errors import SlackApiError

from social.models import SocialPost
from social.slack import MISSED_NOTE, SlackDrafts, draft_blocks, status_line

TODAY = date(2026, 9, 6)


def _client(replies=None, bot_id='UBOT'):
    client = MagicMock()
    client.auth_test.return_value = {'user_id': bot_id}
    client.chat_postMessage.return_value = {'ts': '1700000000.000100'}
    client.chat_update.return_value = {'ok': True}
    client.conversations_replies.return_value = {'messages': replies or []}
    return client


def _post(**kw):
    defaults = dict(kind='deals', iso_week='2026-W37', scheduled_for='2026-09-07',
                    caption='Cibule je v akci.', group_variant='Stavím appku…',
                    image=b'PNG', slack_channel='C123', slack_ts='1700000000.000100')
    defaults.update(kw)
    post = SocialPost.objects.create(**defaults)
    post.refresh_from_db()   # dates as the jobs see them, not the strings above
    return post


def _slack_api_error(status=500, error='internal_error'):
    response = MagicMock()
    response.status_code = status
    response.data = {'ok': False, 'error': error}
    return SlackApiError(message=error, response=response)


@override_settings(SOCIAL_SLACK_CHANNEL='C123', SLACK_BOT_TOKEN='xoxb-test', SOCIAL_SLACK_MENTION='UOWNER')
class DraftBlocksTests(TestCase):
    def _types(self, post):
        return [b['type'] for b in draft_blocks(post, today=TODAY)]

    def test_draft_card_has_header_image_caption_status_and_buttons(self):
        post = _post()
        blocks = draft_blocks(post, today=TODAY)
        self.assertEqual([b['type'] for b in blocks], ['header', 'image', 'section', 'context', 'actions'])
        self.assertEqual(blocks[0]['text']['text'], '🛒 Akce · pondělí 7. 9. · Facebook')
        self.assertIn(f'/api/social/card/{post.pk}/', blocks[1]['image_url'])
        self.assertEqual(blocks[2]['text']['text'], 'Cibule je v akci.')
        self.assertEqual(blocks[3]['elements'][0]['text'],
                         '⏳ Čeká na schválení · do pondělí 7. 9. 9:00 · <@UOWNER>')
        self.assertEqual([e['action_id'] for e in blocks[4]['elements']], ['social_approve', 'social_reject'])
        self.assertEqual({e['value'] for e in blocks[4]['elements']}, {str(post.pk)})
        self.assertEqual([e['text']['text'] for e in blocks[4]['elements']], ['✅ Schválit', '❌ Zamítnout'])

    def test_recipe_header_names_both_channels(self):
        post = _post(kind='recipe', scheduled_for='2026-09-09')
        self.assertEqual(draft_blocks(post, today=TODAY)[0]['text']['text'],
                         '🍲 Recept · středa 9. 9. · Facebook + Pinterest')

    def test_showcase_label(self):
        post = _post(kind='showcase', scheduled_for='2026-09-11')
        self.assertEqual(draft_blocks(post, today=TODAY)[0]['text']['text'],
                         '📅 Ukázka jídelníčku · pátek 11. 9. · Facebook')

    def test_no_image_block_without_image(self):
        self.assertNotIn('image', self._types(_post(image=None)))

    def test_mention_omitted_when_unset(self):
        with override_settings(SOCIAL_SLACK_MENTION=''):
            self.assertEqual(status_line(_post(), today=TODAY), '⏳ Čeká na schválení · do pondělí 7. 9. 9:00')

    def test_missed_draft_says_so_and_keeps_buttons(self):
        post = _post(error=MISSED_NOTE)
        self.assertEqual(status_line(post, today=date(2026, 9, 7)),
                         '⏳ Nestihlo se · schval a půjde ven při dalším běhu (po/st/pá 9:00) · <@UOWNER>')
        self.assertIn('actions', self._types(post))

    def test_draft_without_caption_asks_for_override_and_keeps_buttons(self):
        post = _post(caption='', error='caption failed validation: number 9,90')
        self.assertEqual(status_line(post, today=TODAY),
                         '⚠️ Text neprošel kontrolou — odpověz v threadu `caption: …` a pak Schválit · <@UOWNER>')
        blocks = draft_blocks(post, today=TODAY)
        self.assertIn('actions', [b['type'] for b in blocks])
        self.assertIn('number 9,90', blocks[2]['text']['text'])

    def test_approved_has_no_buttons_and_names_publish_day(self):
        post = _post(status='approved', approved_by='UHUMAN')
        self.assertEqual(status_line(post, today=TODAY), '✅ Schváleno (<@UHUMAN>) · jde ven pondělí 7. 9. 9:00')
        self.assertNotIn('actions', self._types(post))

    def test_approved_after_its_day_goes_out_next_run(self):
        post = _post(status='approved', approved_by='UHUMAN')
        self.assertEqual(status_line(post, today=date(2026, 9, 8)),
                         '✅ Schváleno (<@UHUMAN>) · jde ven při dalším běhu (po/st/pá 9:00)')

    def test_approved_without_caption_waits_for_override(self):
        post = _post(status='approved', approved_by='UHUMAN', caption='')
        self.assertEqual(status_line(post, today=TODAY),
                         '⚠️ Schváleno, ale text neprošel kontrolou — odpověz v threadu `caption: …`, '
                         'publikuje se při dalším běhu')

    def test_rejected_by_button_vs_by_gate(self):
        self.assertEqual(status_line(_post(status='rejected', approved_by='UHUMAN'), today=TODAY),
                         '❌ Zamítnuto (<@UHUMAN>)')
        self.assertEqual(status_line(_post(status='rejected', error='6 of 8 offers expired before publish day',
                                           iso_week='2026-W38'), today=TODAY),
                         '🚫 Nepublikováno — 6 of 8 offers expired before publish day')

    def test_published_links_facebook_and_pinterest(self):
        post = _post(kind='recipe', status='published', facebook_post_id='111_999', pinterest_pin_id='pin42')
        self.assertEqual(status_line(post, today=TODAY),
                         '🚀 Publikováno · https://www.facebook.com/111_999 · pinterest: pin42')
        self.assertEqual(status_line(_post(status='published', facebook_post_id='111_999'), today=TODAY),
                         '🚀 Publikováno · https://www.facebook.com/111_999')

    def test_failed_and_skipped(self):
        self.assertEqual(status_line(_post(status='failed', error='facebook: 400 bad token'), today=TODAY),
                         '⚠️ Publikování selhalo — facebook: 400 bad token')
        self.assertEqual(status_line(_post(status='skipped', error='no deals', iso_week='2026-W38'), today=TODAY),
                         '⏭️ Přeskočeno — no deals')

    def test_caption_is_mrkdwn_escaped(self):
        blocks = draft_blocks(_post(caption='Ovoce & zelenina <akce>'), today=TODAY)
        self.assertEqual(blocks[2]['text']['text'], 'Ovoce &amp; zelenina &lt;akce&gt;')


@override_settings(SOCIAL_SLACK_CHANNEL='C123', SLACK_BOT_TOKEN='xoxb-test')
class PostDraftTests(TestCase):
    def test_posts_blocks_with_fallback_text_then_group_reply_and_stores_ts(self):
        client = _client()
        post = _post(slack_ts='', slack_channel='')
        SlackDrafts(client=client).post_draft(post, today=TODAY)
        post.refresh_from_db()
        self.assertEqual((post.slack_ts, post.slack_channel), ('1700000000.000100', 'C123'))
        parent = client.chat_postMessage.call_args_list[0].kwargs
        self.assertEqual(parent['channel'], 'C123')
        self.assertEqual(parent['blocks'][0]['type'], 'header')
        self.assertIn('Cibule je v akci.', parent['text'])
        self.assertNotIn('thread_ts', parent)
        group = client.chat_postMessage.call_args_list[1].kwargs
        self.assertEqual(group['thread_ts'], '1700000000.000100')
        self.assertIn('Stavím appku', group['text'])
        client.files_upload_v2.assert_not_called()

    def test_group_reply_failure_leaves_ts_empty_and_propagates(self):
        client = _client()
        client.chat_postMessage.side_effect = [{'ts': '1700000000.000100'}, _slack_api_error()]
        post = _post(slack_ts='', slack_channel='')
        with self.assertRaises(SlackApiError):
            SlackDrafts(client=client).post_draft(post)
        post.refresh_from_db()
        self.assertEqual((post.slack_ts, post.slack_channel), ('', ''))

    def test_no_group_reply_when_group_variant_empty(self):
        client = _client()
        SlackDrafts(client=client).post_draft(_post(slack_ts='', slack_channel='', group_variant=''))
        self.assertEqual(client.chat_postMessage.call_count, 1)


@override_settings(SOCIAL_SLACK_CHANNEL='C123', SLACK_BOT_TOKEN='xoxb-test')
class UpdateCardTests(TestCase):
    def test_update_card_edits_the_message_in_place(self):
        client = _client()
        post = _post(status='published', facebook_post_id='111_999')
        SlackDrafts(client=client).update_card(post, today=TODAY)
        kw = client.chat_update.call_args.kwargs
        self.assertEqual((kw['channel'], kw['ts']), ('C123', '1700000000.000100'))
        self.assertIn('Publikováno', kw['blocks'][-1]['elements'][0]['text'])
        self.assertNotIn('actions', [b['type'] for b in kw['blocks']])
        self.assertIn('Akce', kw['text'])

    def test_update_card_swallows_slack_errors_and_skips_rows_without_message(self):
        client = _client()
        client.chat_update.side_effect = _slack_api_error()
        SlackDrafts(client=client).update_card(_post(), today=TODAY)          # must not raise
        client.chat_update.reset_mock()
        SlackDrafts(client=client).update_card(_post(slack_ts='', iso_week='2026-W40'), today=TODAY)
        client.chat_update.assert_not_called()


@override_settings(SOCIAL_SLACK_CHANNEL='C123', SLACK_BOT_TOKEN='xoxb-test')
class CaptionOverrideTests(TestCase):
    def test_last_human_caption_reply_wins(self):
        client = _client(replies=[{'ts': '1', 'text': 'parent', 'user': 'UBOT'},
                                  {'ts': '2', 'text': 'caption: první verze', 'user': 'UHUMAN'},
                                  {'ts': '3', 'text': 'Caption:  Cibule je tenhle týden v akci v Lidlu.', 'user': 'UHUMAN'},
                                  {'ts': '4', 'text': 'nice', 'user': 'UHUMAN'}])
        self.assertEqual(SlackDrafts(client=client).caption_override(_post()),
                         'Cibule je tenhle týden v akci v Lidlu.')

    def test_bot_caption_reply_is_ignored_and_none_when_absent(self):
        client = _client(replies=[{'ts': '2', 'text': 'caption: lidský návrh', 'user': 'UHUMAN'},
                                  {'ts': '3', 'text': 'caption: bot návrh', 'user': 'UBOT'}])
        self.assertEqual(SlackDrafts(client=client).caption_override(_post()), 'lidský návrh')
        self.assertIsNone(SlackDrafts(client=_client()).caption_override(_post(iso_week='2026-W38')))

    def test_reply_posts_in_thread(self):
        client = _client()
        SlackDrafts(client=client).reply(_post(), 'Published: https://facebook.com/x')
        kwargs = client.chat_postMessage.call_args.kwargs
        self.assertEqual(kwargs['thread_ts'], '1700000000.000100')
        self.assertEqual(kwargs['channel'], 'C123')

    def test_reply_swallows_slack_api_error(self):
        client = _client()
        client.chat_postMessage.side_effect = _slack_api_error()
        SlackDrafts(client=client).reply(_post(), 'Published: https://facebook.com/x')   # must not raise

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
        SlackDrafts(client=_client())
