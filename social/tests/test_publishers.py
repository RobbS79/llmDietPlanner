import base64
from unittest.mock import MagicMock

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


@override_settings(FB_PAGE_ID='111', FB_PAGE_ACCESS_TOKEN='EAAtoken')
class FacebookTests(SimpleTestCase):
    def test_posts_photo_with_caption_and_link(self):
        post = MagicMock(return_value=_response(200, {'id': '999', 'post_id': '111_999'}))
        result = publish_facebook(caption='Cibule v akci.', link='https://eatalnicek.eu/?utm_source=facebook',
                                  image=b'PNG', post_fn=post)
        self.assertEqual(result, '111_999')
        url = post.call_args.args[0]
        self.assertEqual(url, 'https://graph.facebook.com/v21.0/111/photos')
        data = post.call_args.kwargs['data']
        self.assertEqual(data['message'], 'Cibule v akci.\n\nhttps://eatalnicek.eu/?utm_source=facebook')
        self.assertEqual(data['access_token'], 'EAAtoken')
        self.assertEqual(data['published'], 'true')
        self.assertEqual(post.call_args.kwargs['files']['source'][1], b'PNG')

    def test_error_response_raises_publish_error_with_platform_message(self):
        post = MagicMock(return_value=_response(400, {'error': {'message': 'Invalid OAuth access token'}}))
        with self.assertRaises(PublishError) as ctx:
            publish_facebook(caption='x', link='https://e', image=b'PNG', post_fn=post)
        self.assertIn('Invalid OAuth access token', str(ctx.exception))

    @override_settings(FB_PAGE_ACCESS_TOKEN='')
    def test_missing_credentials_raise_before_any_request(self):
        post = MagicMock()
        with self.assertRaises(PublishError) as ctx:
            publish_facebook(caption='x', link='https://e', image=b'PNG', post_fn=post)
        self.assertIn('FB_PAGE_ACCESS_TOKEN', str(ctx.exception))
        post.assert_not_called()


@override_settings(PINTEREST_ACCESS_TOKEN='pina', PINTEREST_BOARD_ID='board1')
class PinterestTests(SimpleTestCase):
    def test_creates_pin_with_base64_image(self):
        post = MagicMock(return_value=_response(201, {'id': 'pin42'}))
        result = publish_pinterest(caption='Svíčková má 420 kcal.', link='https://eatalnicek.eu/recepty/1/x/?utm_source=pinterest',
                                   image=b'PNG', title='Svíčková', post_fn=post)
        self.assertEqual(result, 'pin42')
        self.assertEqual(post.call_args.args[0], 'https://api.pinterest.com/v5/pins')
        body = post.call_args.kwargs['json']
        self.assertEqual(body['board_id'], 'board1')
        self.assertEqual(body['title'], 'Svíčková')
        self.assertEqual(body['description'], 'Svíčková má 420 kcal.')
        self.assertEqual(body['link'], 'https://eatalnicek.eu/recepty/1/x/?utm_source=pinterest')
        self.assertEqual(body['media_source']['source_type'], 'image_base64')
        self.assertEqual(body['media_source']['data'], base64.b64encode(b'PNG').decode())
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer pina')

    def test_error_response_raises(self):
        post = MagicMock(return_value=_response(401, {'code': 2, 'message': 'Authentication failed.'}))
        with self.assertRaises(PublishError) as ctx:
            publish_pinterest(caption='x', link='https://e', image=b'PNG', title='t', post_fn=post)
        self.assertIn('Authentication failed', str(ctx.exception))


class RegistryTests(SimpleTestCase):
    def test_get_publisher_knows_both_channels(self):
        self.assertIs(get_publisher('facebook'), publish_facebook)
        self.assertIs(get_publisher('pinterest'), publish_pinterest)
        with self.assertRaises(KeyError):
            get_publisher('tiktok')
