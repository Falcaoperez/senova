from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Group


class AuthFlowTests(TestCase):
    def setUp(self):
        Group.objects.get_or_create(name='usuario')

    def test_register_and_login(self):
        resp = self.client.post(reverse('register'), {
            'username': 'demo',
            'email': 'demo@example.com',
            'password1': 'Abcdef1!',
            'password2': 'Abcdef1!',
        })
        self.assertEqual(resp.status_code, 302)
        # Redirige al rol usuario por defecto
        self.assertIn('/usuario', resp.url)

        # Logout y login
        self.client.get(reverse('logout'))
        resp = self.client.post(reverse('login'), {
            'username': 'demo',
            'password': 'Abcdef1!',
            'remember': 'on',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith('/usuario') or resp.url.startswith('/home'))
