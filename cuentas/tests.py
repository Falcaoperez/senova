import datetime
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core import mail
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .correos import procesar_correos_seguridad
from .models import PasswordResetToken


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", RATE_LIMITS_ENABLED=False)
class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("resetuser", email="reset@example.com", password="Anterior42!")
        cache.clear()

    def solicitar(self, client=None):
        client = client or self.client
        response = client.post(reverse("olvide_password"), {"email": "RESET@example.com"})
        self.assertEqual(response.status_code, 200)
        procesar_correos_seguridad()
        pin = re.search(r"\b\d{6}\b", mail.outbox[-1].body).group()
        return pin

    def verificar(self, pin, client=None):
        return (client or self.client).post(reverse("verificar_pin"), {"email": self.user.email, "codigo": pin})

    def test_pin_is_six_digits_hashed_and_prior_code_is_invalidated(self):
        old = PasswordResetToken.crear_para_usuario(self.user)
        pin = self.solicitar()
        self.assertEqual(len(pin), 6)
        old.refresh_from_db()
        self.assertTrue(old.utilizado)
        request = PasswordResetToken.objects.filter(usuario=self.user, utilizado=False).get()
        self.assertNotEqual(pin, request.token)
        self.assertTrue(check_password(pin, request.token))
        self.assertIn(pin, mail.outbox[-1].alternatives[0].content)
        self.assertLess(request.expira_en - timezone.now(), datetime.timedelta(minutes=11))

    def test_verify_then_change_password_and_reuse_is_forbidden(self):
        pin = self.solicitar()
        self.assertEqual(self.client.get(reverse("password_reset_new")).status_code, 302)
        data = {"password": "NuevaSegura42!", "password_confirm": "NuevaSegura42!"}
        self.assertEqual(self.client.post(reverse("restablecer_password"), data).status_code, 403)
        self.assertEqual(self.verificar(pin).status_code, 200)
        self.assertEqual(self.client.get(reverse("password_reset_new")).status_code, 200)
        self.assertEqual(self.client.post(reverse("restablecer_password"), data).status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(data["password"]))
        self.assertEqual(self.client.post(reverse("restablecer_password"), data).status_code, 403)
        self.assertEqual(self.verificar(pin).status_code, 400)

    def test_verification_is_bound_to_the_session(self):
        pin = self.solicitar()
        self.assertEqual(self.verificar(pin).status_code, 200)
        attacker = Client()
        data = {"email": self.user.email, "codigo": pin, "password": "OtraClave42!", "password_confirm": "OtraClave42!"}
        self.assertEqual(attacker.post(reverse("restablecer_password"), data).status_code, 403)
        self.assertEqual(attacker.get(reverse("password_reset_new")).status_code, 302)

    def test_wrong_attempts_lock_pin(self):
        pin = self.solicitar()
        wrong = "999999" if pin != "999999" else "000000"
        for _ in range(5):
            self.assertEqual(self.verificar(wrong).status_code, 400)
        self.assertEqual(self.verificar(pin).status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Anterior42!"))

    def test_expired_pin_and_weak_password(self):
        pin = self.solicitar()
        token = PasswordResetToken.objects.get(usuario=self.user, utilizado=False)
        token.expira_en = timezone.now() - datetime.timedelta(seconds=1)
        token.save()
        self.assertEqual(self.verificar(pin).status_code, 400)
        pin = self.solicitar()
        self.assertEqual(self.verificar(pin).status_code, 200)
        self.assertEqual(
            self.client.post(
                reverse("restablecer_password"), {"password": "short", "password_confirm": "short"}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                reverse("restablecer_password"), {"password": "NuevaSegura42!", "password_confirm": "Distinta42!"}
            ).status_code,
            400,
        )

    def test_new_request_invalidates_verified_session(self):
        pin = self.solicitar()
        self.verificar(pin)
        self.solicitar()
        self.assertEqual(self.client.get(reverse("password_reset_new")).status_code, 302)

    @patch("cuentas.correos.EmailMultiAlternatives.send", side_effect=RuntimeError("SMTP unavailable"))
    def test_mail_failure_remains_generic_and_is_retried_outside_the_request(self, send):
        response = self.client.post(reverse("olvide_password"), {"email": self.user.email})
        unknown = self.client.post(reverse("olvide_password"), {"email": "unknown@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), unknown.json())
        send.assert_not_called()
        self.assertEqual(procesar_correos_seguridad(), 0)
        self.assertTrue(PasswordResetToken.objects.filter(utilizado=False).exists())
        self.assertNotIn("SMTP unavailable", response.content.decode())

    def test_unknown_email_has_same_success_message(self):
        response = self.client.post(reverse("olvide_password"), {"email": self.user.email})
        unknown = self.client.post(reverse("olvide_password"), {"email": "unknown@example.com"})
        self.assertEqual(response.json(), unknown.json())
        procesar_correos_seguridad()
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(RATE_LIMITS_ENABLED=True)
    def test_recovery_is_limited_by_account(self):
        for _ in range(3):
            self.assertEqual(self.client.post(reverse("olvide_password"), {"email": self.user.email}).status_code, 200)
        response = self.client.post(reverse("olvide_password"), {"email": self.user.email})
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)

    @override_settings(RATE_LIMITS_ENABLED=True)
    def test_forwarded_header_does_not_bypass_account_limit(self):
        for i in range(3):
            self.client.post(
                reverse("olvide_password"), {"email": self.user.email}, HTTP_X_FORWARDED_FOR=f"203.0.113.{i}"
            )
        response = self.client.post(
            reverse("olvide_password"), {"email": self.user.email}, HTTP_X_FORWARDED_FOR="203.0.113.99"
        )
        self.assertEqual(response.status_code, 429)

    def test_mail_uniqueness_is_enforced_in_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            get_user_model().objects.create_user("duplicate", email="RESET@example.com")

    def test_debug_tokens_not_exposed(self):
        self.assertEqual(self.client.get("/api/debug-tokens/").status_code, 404)
