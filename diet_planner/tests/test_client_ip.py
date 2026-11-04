from unittest import mock

from django.test import RequestFactory, SimpleTestCase
from rest_framework.request import Request

from diet_planner import client_ip as client_ip_mod
from diet_planner.client_ip import client_ip
from diet_planner.throttles import DiscoverDayThrottle
from diet_planner.views_discover import _ident


def _raw(**meta):
    return RequestFactory().post('/api/discover/', **meta)


class ClientIpTest(SimpleTestCase):
    def test_forged_leading_xff_does_not_change_identity(self):
        a = _raw(HTTP_DO_CONNECTING_IP='203.0.113.7', HTTP_X_FORWARDED_FOR='1.1.1.1, 203.0.113.7')
        b = _raw(HTTP_DO_CONNECTING_IP='203.0.113.7', HTTP_X_FORWARDED_FOR='9.9.9.9, 203.0.113.7')
        self.assertEqual(client_ip(a), '203.0.113.7')
        self.assertEqual(client_ip(a), client_ip(b))
        self.assertEqual(_ident(a), _ident(b))

    def test_order_do_then_cf_then_rightmost_xff_then_remote(self):
        self.assertEqual(client_ip(_raw(HTTP_CF_CONNECTING_IP='198.51.100.2',
                                        HTTP_X_FORWARDED_FOR='1.1.1.1, 10.0.0.5')), '198.51.100.2')
        self.assertEqual(client_ip(_raw(HTTP_X_FORWARDED_FOR='1.1.1.1, 10.0.0.5')), '10.0.0.5')
        self.assertEqual(client_ip(_raw(REMOTE_ADDR='192.0.2.9')), '192.0.2.9')

    def test_invalid_value_falls_through(self):
        req = _raw(HTTP_DO_CONNECTING_IP='not-an-ip', HTTP_CF_CONNECTING_IP=' 2001:db8::1 ')
        self.assertEqual(client_ip(req), '2001:db8::1')
        req = _raw(HTTP_DO_CONNECTING_IP='', HTTP_X_FORWARDED_FOR='1.1.1.1, garbage',
                   REMOTE_ADDR='192.0.2.9')
        self.assertEqual(client_ip(req), '192.0.2.9')

    def test_unknown_when_nothing_parses(self):
        self.assertEqual(client_ip(_raw(REMOTE_ADDR='')), 'unknown')

    def test_throttle_uses_helper(self):
        a = Request(_raw(HTTP_DO_CONNECTING_IP='203.0.113.7', HTTP_X_FORWARDED_FOR='1.1.1.1'))
        b = Request(_raw(HTTP_DO_CONNECTING_IP='203.0.113.7', HTTP_X_FORWARDED_FOR='2.2.2.2'))
        t = DiscoverDayThrottle()
        self.assertEqual(t.get_cache_key(a, view=None), t.get_cache_key(b, view=None))
        self.assertIn('203.0.113.7', t.get_cache_key(a, view=None))
        with mock.patch('diet_planner.throttles.client_ip', return_value='7.7.7.7') as helper:
            self.assertIn('7.7.7.7', t.get_cache_key(a, view=None))
        helper.assert_called_once()

    def test_source_logged_once_per_process(self):
        with mock.patch.object(client_ip_mod, '_logged', False), \
             mock.patch.object(client_ip_mod.logger, 'info') as info:
            client_ip(_raw(HTTP_DO_CONNECTING_IP='203.0.113.7'))
            client_ip(_raw(HTTP_DO_CONNECTING_IP='203.0.113.8'))
        info.assert_called_once()
        self.assertIn('HTTP_DO_CONNECTING_IP', info.call_args.args[1])
