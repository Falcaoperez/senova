from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .correos import encolar_pin, procesar_correos_seguridad
from .models import CorreoSeguridad, PasswordResetToken, SesionUsuario

User = get_user_model()


class SesionesYPerfilTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("seguro", email="seguro@example.invalid", password="ClaveActual42!")
        self.other = User.objects.create_user("otra", email="otra@example.invalid", password="OtraClave42!")
        self.client.force_login(self.user)
        self.second = Client()
        self.second.force_login(self.user)
        self.external = Client()
        self.external.force_login(self.other)

    def payload(self, **updates):
        data = {
            "username": self.user.username,
            "nombre": "Ana",
            "apellido": "Pérez",
            "correo": self.user.email,
            "contrasena": "",
        }
        data.update(updates)
        return data

    def test_sessions_are_registered_at_login_without_a_subsequent_request(self):
        self.assertEqual(SesionUsuario.objects.filter(usuario=self.user).count(), 2)

    def test_switching_accounts_creates_a_registered_session_for_the_new_user(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("centro_seguridad")).status_code, 200)
        self.assertEqual(SesionUsuario.objects.get(sesion_id=self.client.session.session_key).usuario_id, self.other.pk)

    def test_sessions_from_before_the_security_upgrade_require_a_fresh_login(self):
        from .sesiones import CLAVE_VERSION

        session = self.client.session
        del session[CLAVE_VERSION]
        session.save()
        response = self.client.get(reverse("centro_seguridad"))
        self.assertRedirects(response, reverse("login"))
        self.assertEqual(self.client.get(reverse("editar_perfil")).status_code, 302)

    def test_security_page_contains_only_own_sessions_without_session_keys(self):
        response = self.client.get(reverse("centro_seguridad"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["sesiones"].paginator.count, 2)
        self.assertContains(response, "Sesión actual")
        self.assertNotContains(response, self.client.session.session_key)
        self.assertNotContains(response, self.second.session.session_key)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_names_can_be_corrected_without_reauth_but_email_and_username_cannot(self):
        self.assertEqual(self.client.post(reverse("editar_perfil"), self.payload()).status_code, 302)
        for change in ({"correo": "nueva@example.invalid"}, {"username": "otro-nombre"}):
            response = self.client.post(reverse("editar_perfil"), self.payload(**change))
            self.assertTrue(response.context["form"].errors)
            self.user.refresh_from_db()
            self.assertEqual(self.user.email, "seguro@example.invalid")
            self.assertEqual(self.user.username, "seguro")

    def test_password_change_requires_current_password_and_confirmation(self):
        for extra in (
            {},
            {"contrasena_actual": "incorrecta"},
            {"contrasena_actual": "ClaveActual42!", "confirmar_contrasena": "distinta"},
        ):
            response = self.client.post(reverse("editar_perfil"), self.payload(contrasena="NuevaSegura42!", **extra))
            self.assertTrue(response.context["form"].errors)
            self.user.refresh_from_db()
            self.assertTrue(self.user.check_password("ClaveActual42!"))

    def test_change_password_closes_other_cached_sessions_and_keeps_current(self):
        self.user.email = self.user.email.upper()
        self.user.save()
        response = self.client.post(
            reverse("editar_perfil"),
            self.payload(
                contrasena="NuevaSegura42!", confirmar_contrasena="NuevaSegura42!", contrasena_actual="ClaveActual42!"
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.second.get(reverse("editar_perfil")).status_code, 302)
        self.assertEqual(self.client.get(reverse("editar_perfil")).status_code, 200)
        self.assertEqual(CorreoSeguridad.objects.filter(tipo="cambio").count(), 1)

    def test_email_change_invalidates_reset_and_alerts_old_and_new_addresses(self):
        token = PasswordResetToken.crear_para_usuario(self.user)
        encolar_pin(token)
        self.assertEqual(
            self.client.post(
                reverse("editar_perfil"),
                self.payload(correo="nueva@example.invalid", contrasena_actual="ClaveActual42!"),
            ).status_code,
            302,
        )
        token.refresh_from_db()
        self.assertTrue(token.utilizado)
        self.assertEqual(
            set(CorreoSeguridad.objects.filter(tipo="cambio").values_list("destinatario", flat=True)),
            {"seguro@example.invalid", "nueva@example.invalid"},
        )
        self.assertEqual(CorreoSeguridad.objects.get(tipo="pin").contenido_cifrado, "")

    def test_cannot_revoke_foreign_session_or_use_get(self):
        own = SesionUsuario.objects.get(sesion_id=self.second.session.session_key)
        external = SesionUsuario.objects.get(sesion_id=self.external.session.session_key)
        self.assertEqual(self.client.get(reverse("revocar_sesion", args=[own.pk])).status_code, 405)
        self.assertEqual(
            self.client.post(
                reverse("revocar_sesion", args=[external.pk]), {"contrasena_actual": "ClaveActual42!"}
            ).status_code,
            404,
        )
        self.assertEqual(self.external.get(reverse("editar_perfil")).status_code, 200)

    def test_revoke_requires_password_and_clears_both_session_stores(self):
        own = SesionUsuario.objects.get(sesion_id=self.second.session.session_key)
        url = reverse("revocar_sesion", args=[own.pk])
        self.assertEqual(self.client.post(url, {"contrasena_actual": "incorrecta"}).status_code, 400)
        self.assertEqual(self.second.get(reverse("editar_perfil")).status_code, 200)
        self.assertEqual(self.client.post(url, {"contrasena_actual": "ClaveActual42!"}).status_code, 302)
        self.assertEqual(self.second.get(reverse("editar_perfil")).status_code, 302)
        self.assertEqual(self.client.get(reverse("editar_perfil")).status_code, 200)

    def test_close_others_preserves_current_and_other_users(self):
        response = self.client.post(reverse("cerrar_otras_sesiones"), {"contrasena_actual": "ClaveActual42!"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.second.get(reverse("editar_perfil")).status_code, 302)
        self.assertEqual(self.client.get(reverse("editar_perfil")).status_code, 200)
        self.assertEqual(self.external.get(reverse("editar_perfil")).status_code, 200)

    def test_logout_is_post_and_csrf_protected(self):
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertEqual(self.client.get(reverse("editar_perfil")).status_code, 200)
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.user)
        self.assertEqual(protected.post(reverse("logout")).status_code, 403)
        self.assertEqual(self.client.post(reverse("logout")).status_code, 302)
        self.assertEqual(self.client.get(reverse("editar_perfil")).status_code, 302)

    def test_session_revocation_is_csrf_protected(self):
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.user)
        own = SesionUsuario.objects.get(sesion_id=self.second.session.session_key)
        for url in (reverse("revocar_sesion", args=[own.pk]), reverse("cerrar_otras_sesiones")):
            self.assertEqual(protected.post(url, {"contrasena_actual": "ClaveActual42!"}).status_code, 403)

    def test_mail_status_never_renders_credentials(self):
        self.user.is_superuser = True
        self.user.save()
        with override_settings(
            EMAIL_HOST_PASSWORD="private-mail-password-do-not-render",
            EMAIL_OAUTH2_ACCESS_TOKEN="private-oauth-token-do-not-render",
        ):
            response = self.client.get(reverse("admin_personalizado:dashboard"))
        self.assertContains(response, "Estado del correo")
        self.assertNotContains(response, "private-mail-password-do-not-render")
        self.assertNotContains(response, "private-oauth-token-do-not-render")

    @override_settings(SESSION_IDLE_TIMEOUT=1800)
    def test_inactivity_expires_the_session(self):
        SesionUsuario.objects.filter(sesion_id=self.client.session.session_key).update(
            ultimo_uso=timezone.now() - timedelta(minutes=31)
        )
        response = self.client.get(reverse("centro_seguridad"))
        self.assertRedirects(response, reverse("login"))
        self.assertEqual(self.client.get(reverse("editar_perfil")).status_code, 302)

    @override_settings(SESSION_IDLE_TIMEOUT=1800)
    def test_background_notifications_do_not_keep_an_inactive_session_alive(self):
        key = self.client.session.session_key
        previous = timezone.now() - timedelta(minutes=2)
        SesionUsuario.objects.filter(sesion_id=key).update(ultimo_uso=previous)
        self.assertEqual(self.client.get(reverse("notificaciones:resumen")).status_code, 200)
        self.assertEqual(SesionUsuario.objects.get(sesion_id=key).ultimo_uso, previous)
        SesionUsuario.objects.filter(sesion_id=key).update(ultimo_uso=timezone.now() - timedelta(minutes=31))
        response = self.client.get(reverse("notificaciones:resumen"))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["login_url"], reverse("login"))


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ColaSeguridadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("pinqueue", email="pinqueue@example.invalid", password="ClaveAnterior42!")

    def crear(self):
        solicitud = PasswordResetToken.crear_para_usuario(self.user)
        return solicitud, encolar_pin(solicitud)

    def test_request_queues_encrypted_pin_without_opening_smtp(self):
        with patch("cuentas.correos.get_connection") as connect:
            response = self.client.post(reverse("olvide_password"), {"email": self.user.email})
        self.assertEqual(response.status_code, 200)
        connect.assert_not_called()
        correo = CorreoSeguridad.objects.get()
        self.assertNotEqual(correo.contenido_cifrado, "")
        self.assertEqual(procesar_correos_seguridad(), 1)
        correo.refresh_from_db()
        self.assertEqual(correo.contenido_cifrado, "")
        self.assertEqual(correo.estado, "enviado")
        self.assertEqual(len(mail.outbox), 1)

    def test_delivered_pin_matches_hash_and_is_not_sent_twice(self):
        solicitud, correo = self.crear()
        self.assertNotEqual(correo.contenido_cifrado, solicitud.pin_para_envio)
        self.assertEqual(procesar_correos_seguridad(), 1)
        self.assertIn(solicitud.pin_para_envio, mail.outbox[0].body)
        self.assertEqual(procesar_correos_seguridad(), 0)

    def test_expired_used_inactive_and_changed_email_never_send(self):
        for state in ("expired", "used", "inactive", "email"):
            self.user.is_active = True
            self.user.email = "pinqueue@example.invalid"
            self.user.save()
            solicitud, correo = self.crear()
            if state == "expired":
                solicitud.expira_en = timezone.now() - timedelta(seconds=1)
            if state == "used":
                solicitud.utilizado = True
            if state == "inactive":
                self.user.is_active = False
                self.user.save()
            if state == "email":
                self.user.email = "other@example.invalid"
                self.user.save()
            solicitud.save()
            self.assertEqual(procesar_correos_seguridad(), 0)
            correo.refresh_from_db()
            self.assertEqual(correo.estado, "cancelado")
            self.assertEqual(correo.contenido_cifrado, "")
        self.assertEqual(len(mail.outbox), 0)

    def test_corrupted_ciphertext_is_cancelled_without_exposing_details(self):
        solicitud, correo = self.crear()
        correo.contenido_cifrado = "no-es-un-cifrado-valido"
        correo.save()
        self.assertEqual(procesar_correos_seguridad(), 0)
        correo.refresh_from_db()
        solicitud.refresh_from_db()
        self.assertEqual(correo.estado, "cancelado")
        self.assertEqual(correo.contenido_cifrado, "")
        self.assertTrue(solicitud.utilizado)

    def test_ciphertext_cannot_be_moved_between_reset_requests(self):
        solicitud, correo = self.crear()
        other = User.objects.create_user("anotherpin", email="anotherpin@example.invalid")
        other_request = PasswordResetToken.crear_para_usuario(other)
        other_mail = encolar_pin(other_request)
        correo.contenido_cifrado = other_mail.contenido_cifrado
        correo.save()
        self.assertEqual(procesar_correos_seguridad(), 1)
        correo.refresh_from_db()
        self.assertEqual(correo.estado, "cancelado")
        self.assertEqual(mail.outbox[0].to, [other.email])

    def test_old_key_is_accepted_during_rotation(self):
        solicitud, correo = self.crear()
        from django.conf import settings

        old_key = settings.SECRET_KEY
        with override_settings(SECRET_KEY="nueva-clave-privada-de-pruebas-" * 3, SECRET_KEY_FALLBACKS=[old_key]):
            self.assertEqual(procesar_correos_seguridad(), 1)
        self.assertIn(solicitud.pin_para_envio, mail.outbox[0].body)

    def test_native_account_changes_invalidate_existing_recovery_requests(self):
        for field, value in (("email", "changed@example.invalid"), ("password", "!changed-password")):
            self.user.refresh_from_db()
            solicitud, _ = self.crear()
            self.assertTrue(solicitud.es_valido())
            User.objects.filter(pk=self.user.pk).update(**{field: value})
            fresh = PasswordResetToken.objects.select_related("usuario").get(pk=solicitud.pk)
            self.assertFalse(fresh.es_valido())
            self.assertEqual(procesar_correos_seguridad(), 0)

    @patch("cuentas.correos.EmailMultiAlternatives.send", side_effect=RuntimeError("secret-provider-detail"))
    def test_three_failures_invalidate_pin_and_erase_ciphertext(self, send):
        solicitud, correo = self.crear()
        for _ in range(3):
            self.assertEqual(procesar_correos_seguridad(), 0)
            correo.refresh_from_db()
            correo.proximo_intento = timezone.now()
            correo.save()
        correo.refresh_from_db()
        solicitud.refresh_from_db()
        self.assertEqual(correo.intentos, 3)
        self.assertEqual(correo.estado, "error")
        self.assertEqual(correo.contenido_cifrado, "")
        self.assertTrue(solicitud.utilizado)
        self.assertNotIn("secret-provider-detail", correo.ultimo_error)

    def test_reset_invalidates_authenticated_sessions_and_queues_alert(self):
        logged = Client()
        logged.force_login(self.user)
        solicitud, _ = self.crear()
        procesar_correos_seguridad()
        self.assertEqual(
            self.client.post(
                reverse("verificar_pin"), {"email": self.user.email, "codigo": solicitud.pin_para_envio}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                reverse("restablecer_password"),
                {"password": "ClaveNuevaSegura42!", "password_confirm": "ClaveNuevaSegura42!"},
            ).status_code,
            200,
        )
        self.assertEqual(logged.get(reverse("editar_perfil")).status_code, 302)
        self.assertEqual(CorreoSeguridad.objects.filter(tipo="cambio", estado="pendiente").count(), 1)
