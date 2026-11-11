from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse


class AuthFlowTests(TestCase):
    def setUp(self):
        Group.objects.get_or_create(name="usuario")

    def test_register_and_login(self):
        resp = self.client.post(
            reverse("register"),
            {
                "username": "demo",
                "email": "demo@example.com",
                "password1": "Abcdef1!",
                "password2": "Abcdef1!",
            },
        )
        self.assertEqual(resp.status_code, 302)
        # Redirige al rol usuario por defecto
        self.assertEqual(resp.url, "/login/?created=1")

        # Logout y login
        self.client.get(reverse("logout"))
        resp = self.client.post(
            reverse("login"),
            {
                "username": "demo",
                "password": "Abcdef1!",
                "remember": "on",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith("/usuario") or resp.url.startswith("/home"))

    def test_long_password_and_confirmation(self):
        data = {"username": "longpass", "email": "long@example.com", "password1": "LongPassword42!", "password2": ""}
        response = self.client.post(reverse("register"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="longpass").exists())
        data["password2"] = data["password1"]
        self.assertEqual(self.client.post(reverse("register"), data).status_code, 302)
        self.assertTrue(self.client.login(username="longpass", password=data["password1"]))
