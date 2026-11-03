from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from login_app.email_rules import is_disposable, normalise_email


class EmailRulesTest(SimpleTestCase):
    def test_gmail_dots_and_plus_collapse(self):
        self.assertEqual(normalise_email('J.An+uvarto@GMail.com'), 'jan@gmail.com')
        self.assertEqual(normalise_email('jan@googlemail.com'), 'jan@gmail.com')

    def test_other_domains_keep_dots_but_drop_plus(self):
        self.assertEqual(normalise_email('J.An+x@Seznam.cz'), 'j.an@seznam.cz')

    def test_disposable(self):
        self.assertTrue(is_disposable('a@mailinator.com'))
        self.assertTrue(is_disposable('a@10minutemail.com'))
        self.assertFalse(is_disposable('a@seznam.cz'))


class RegistrationRulesTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def _register(self, username, email):
        return self.client.post('/api/auth/register/', {
            'username': username, 'email': email,
            'password': 'heslo1234', 'passwordConfirm': 'heslo1234'}, format='json')

    def test_alias_of_existing_gmail_is_rejected(self):
        get_user_model().objects.create(username='first', email='jan@gmail.com')
        resp = self._register('second', 'j.an+2@gmail.com')
        self.assertEqual(resp.status_code, 400)

    def test_disposable_is_rejected(self):
        resp = self._register('throwaway', 'x@mailinator.com')
        self.assertEqual(resp.status_code, 400)

    def test_stored_email_is_kept_as_typed(self):
        resp = self._register('typed', 'Pepa.Novak+x@Seznam.cz')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(get_user_model().objects.get(username='typed').email, 'Pepa.Novak+x@seznam.cz')  # local part and +tag kept; the existing schema lowercases the domain

    def test_sixth_signup_in_a_day_is_throttled(self):
        for i in range(5):
            self.assertNotEqual(self._register(f'u{i}', f'u{i}@seznam.cz').status_code, 429)
        self.assertEqual(self._register('u6', 'u6@seznam.cz').status_code, 429)
