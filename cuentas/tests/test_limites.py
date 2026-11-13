from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(RATE_LIMITS_ENABLED=True)
class LimitesIdentidadTests(TestCase):
    def setUp(self):
        cache.clear()
        # El límite usa ventanas fijas. La prueba no debe cruzar una por tardar
        # más en un runner; aislar solo el reloj del middleware, no el de la caché.
        self.reloj_patch = patch("SENNOVA.middleware.time")
        self.reloj = self.reloj_patch.start()
        self.reloj.time.return_value = 1_800_000_123
        self.addCleanup(self.reloj_patch.stop)
        self.user = get_user_model().objects.create_user(
            "aliaslogin", email="alias@example.invalid", password="ClaveSegura42!"
        )

    def test_username_and_email_share_the_login_limit(self):
        for i in range(10):
            identifier = self.user.username if i % 2 else self.user.email
            response = self.client.post(reverse("login"), {"username": identifier, "password": "incorrecta"})
            self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("login_root"), {"username": self.user.email, "password": "ClaveSegura42!"})
        self.assertEqual(response.status_code, 429)
        self.assertTrue(response["Content-Type"].startswith("text/html"))
        self.assertContains(response, "Vuelve a intentarlo", status_code=429)

    def test_reset_limits_keep_json_for_the_pin_form(self):
        for _ in range(3):
            self.client.post(reverse("olvide_password"), {"email": self.user.email})
        response = self.client.post(reverse("olvide_password"), {"email": self.user.email})
        self.assertEqual(response.status_code, 429)
        self.assertIn("error", response.json())

    def test_profile_password_guesses_are_limited(self):
        self.client.force_login(self.user)
        payload = {
            "username": self.user.username,
            "nombre": "Ana",
            "apellido": "Pérez",
            "correo": "change@example.invalid",
            "contrasena_actual": "incorrecta",
        }
        for _ in range(10):
            self.assertEqual(self.client.post(reverse("editar_perfil"), payload).status_code, 200)
        self.assertEqual(self.client.post(reverse("editar_perfil"), payload).status_code, 429)

    def test_login_window_resets_at_its_boundary_and_reports_retry_after(self):
        self.reloj.time.return_value = 1_800_000_599
        for _ in range(10):
            self.client.post(reverse("login"), {"username": self.user.username, "password": "incorrecta"})
        response = self.client.post(reverse("login"), {"username": self.user.email, "password": "ClaveSegura42!"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "1")
        self.reloj.time.return_value = 1_800_000_600
        response = self.client.post(reverse("login"), {"username": self.user.email, "password": "ClaveSegura42!"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)
