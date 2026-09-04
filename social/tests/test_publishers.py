import base64
from unittest.mock import MagicMock

import requests
from django.test import SimpleTestCase, override_settings

from social.publishers import PublishError, get_publisher
from social.publishers.facebook import publish as publish_facebook
from social.publishers.pinterest import publish as publish_pinterest


def _response(status=200, payload=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload or {}
    resp.text = str(payload)
    return resp


def _bad_json_response(status=200, text='<html>not json</html>'):
    resp = MagicMock()
    resp.status_code = status
    resp.json.side_effect = ValueError('no json object could be decoded')
    resp.text = text
    return resp


@override_settings(FB_PAGE_ID='111', FB_PAGE_ACCESS_TOKEN='EAAtoken')
class FacebookTests(SimpleTestCase):
    def test_posts_photo_with_caption_and_link(self):
        post = MagicMock(return_value=_response(200, {'id': '999', 'post_id': '111_999'}))
        result = publish_facebook(caption='Cibule v akci.', link='https://eatalnicek.eu/?utm_source=facebook',
                                  image=b'PNG', post_fn=post)
        self.assertEqual(result, '111_999')
        url = post.call_args.args[0]
        self.assertEqual(url, 'https://graph.facebook.com/v24.0/111/photos')
        data = post.call_args.kwargs['data']
        self.assertEqual(data['message'], 'Cibule v akci.\n\nhttps://eatalnicek.eu/?utm_source=facebook')
        self.assertEqual(data['caption'], data['message'])
        self.assertEqual(data['access_token'], 'EAAtoken')
        self.assertEqual(data['published'], 'true')
        self.assertEqual(post.call_args.kwargs['files']['source'][1], b'PNG')
        self.assertEqual(post.call_args.kwargs['timeout'], 60)

    def test_error_response_raises_publish_error_with_platform_message(self):
        post = MagicMock(return_value=_response(400, {'error': {'message': 'Invalid OAuth access token'}}))
        with self.assertRaises(PublishError) as ctx:
            publish_facebook(caption='x', link='https://e', image=b'PNG', post_fn=post)
        self.assertIn('Invalid OAuth access token', str(ctx.exception))

    def test_200_with_error_dict_raises(self):
        post = MagicMock(return_value=_response(200, {'error': {'message': 'Duplicate post'}}))
        with self.assertRaises(PublishError) as ctx:
            publish_facebook(caption='x', link='https://e', image=b'PNG', post_fn=post)
        self.assertIn('Duplicate post', str(ctx.exception))

    def test_error_as_plain_string_raises_without_attributeerror(self):
        post = MagicMock(return_value=_response(200, {'error': 'Something went wrong'}))
        with self.assertRaises(PublishError) as ctx:
            publish_facebook(caption='x', link='https://e', image=b'PNG', post_fn=post)
        self.assertIn('Something went wrong', str(ctx.exception))

    def test_200_with_empty_body_raises_no_post_id(self):
        post = MagicMock(return_value=_response(200, {}))
        with self.assertRaises(PublishError) as ctx:
            publish_facebook(caption='x', link='https://e', image=b'PNG', post_fn=post)
        self.assertIn('no post id', str(ctx.exception))

    def test_non_json_body_raises(self):
        post = MagicMock(return_value=_bad_json_response(502, '<html>Bad Gateway</html>'))
        with self.assertRaises(PublishError):
            publish_facebook(caption='x', link='https://e', image=b'PNG', post_fn=post)

    def test_request_exception_raises_publish_error(self):
        post = MagicMock(side_effect=requests.RequestException('boom'))
        with self.assertRaises(PublishError):
            publish_facebook(caption='x', link='https://e', image=b'PNG', post_fn=post)
        post.assert_called_once()

    @override_settings(FB_PAGE_ACCESS_TOKEN='')
    def test_missing_credentials_raise_before_any_request(self):
        post = MagicMock()
        with self.assertRaises(PublishError) as ctx:
            publish_facebook(caption='x', link='https://e', image=b'PNG', post_fn=post)
        self.assertIn('FB_PAGE_ACCESS_TOKEN', str(ctx.exception))
        post.assert_not_called()

    @override_settings(FB_PAGE_ID='')
    def test_missing_page_id_alone_raises_before_any_request(self):
        post = MagicMock()
        with self.assertRaises(PublishError):
            publish_facebook(caption='x', link='https://e', image=b'PNG', post_fn=post)
        post.assert_not_called()


@override_settings(FB_PAGE_ID='111', FB_PAGE_ACCESS_TOKEN='EAAtoken')
class FacebookErrorWithoutMessageTests(SimpleTestCase):
    def test_error_dict_without_message_falls_back_to_body(self):
        post = MagicMock(return_value=_response(400, {'error': {'code': 190, 'type': 'OAuthException'}}))
        with self.assertRaises(PublishError) as ctx:
            publish_facebook(caption='x', link='https://e', image=b'PNG', post_fn=post)
        self.assertIn('OAuthException', str(ctx.exception))
        self.assertNotIn('None', str(ctx.exception))


@override_settings(PINTEREST_ACCESS_TOKEN='pina', PINTEREST_BOARD_ID='123456789')
class PinterestTests(SimpleTestCase):
    def test_creates_pin_with_base64_image(self):
        post = MagicMock(return_value=_response(201, {'id': 'pin42'}))
        result = publish_pinterest(caption='Svíčková má 420 kcal.', link='https://eatalnicek.eu/recepty/1/x/?utm_source=pinterest',
                                   image=b'PNG', title='Svíčková', post_fn=post)
        self.assertEqual(result, 'pin42')
        self.assertEqual(post.call_args.args[0], 'https://api.pinterest.com/v5/pins')
        body = post.call_args.kwargs['json']
        self.assertEqual(body['board_id'], '123456789')
        self.assertEqual(body['title'], 'Svíčková')
        self.assertEqual(body['description'], 'Svíčková má 420 kcal.')
        self.assertEqual(body['link'], 'https://eatalnicek.eu/recepty/1/x/?utm_source=pinterest')
        self.assertEqual(body['alt_text'], 'Svíčková')
        self.assertEqual(body['media_source']['source_type'], 'image_base64')
        self.assertEqual(body['media_source']['data'], base64.b64encode(b'PNG').decode())
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer pina')
        self.assertEqual(post.call_args.kwargs['timeout'], 60)

    def test_error_response_raises(self):
        post = MagicMock(return_value=_response(401, {'code': 2, 'message': 'Authentication failed.'}))
        with self.assertRaises(PublishError) as ctx:
            publish_pinterest(caption='x', link='https://e', image=b'PNG', title='t', post_fn=post)
        self.assertIn('Authentication failed', str(ctx.exception))

    def test_long_caption_truncated_at_sentence_boundary(self):
        caption = ('X' * 500) + '. ' + ('Y' * 398)  # 900 chars total
        post = MagicMock(return_value=_response(201, {'id': 'pin1'}))
        publish_pinterest(caption=caption, link='https://e', image=b'PNG', title='t', post_fn=post)
        description = post.call_args.kwargs['json']['description']
        self.assertLessEqual(len(description), 800)
        self.assertTrue(description.endswith('…'))
        self.assertEqual(description[-2], '.')

    def test_json_list_body_raises(self):
        post = MagicMock(return_value=_response(201, ['unexpected']))
        with self.assertRaises(PublishError):
            publish_pinterest(caption='x', link='https://e', image=b'PNG', title='t', post_fn=post)

    def test_non_json_body_raises(self):
        post = MagicMock(return_value=_bad_json_response(500, '<html>oops</html>'))
        with self.assertRaises(PublishError):
            publish_pinterest(caption='x', link='https://e', image=b'PNG', title='t', post_fn=post)

    def test_request_exception_raises_publish_error(self):
        post = MagicMock(side_effect=requests.RequestException('boom'))
        with self.assertRaises(PublishError):
            publish_pinterest(caption='x', link='https://e', image=b'PNG', title='t', post_fn=post)
        post.assert_called_once()


class RegistryTests(SimpleTestCase):
    def test_get_publisher_knows_both_channels(self):
        self.assertIs(get_publisher('facebook'), publish_facebook)
        self.assertIs(get_publisher('pinterest'), publish_pinterest)
        with self.assertRaises(KeyError):
            get_publisher('tiktok')
