from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from Gesicom.models import Envio

from ..models import (
    CorreoPendiente,
    Notificacion,
    Novedad,
    PlazoReporte,
    PreferenciasNotificacion,
)
from ..services import (
    anunciar_plazo,
    procesar_correos,
    publicar_novedad,
    sincronizar_plazos,
)

User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class NotificationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("noticeadmin", email="admin@example.com")
        self.admin.groups.set([Group.objects.get(name="administrador")])
        self.user = User.objects.create_user("noticeuser", email="member@example.com")
        self.user.groups.set([Group.objects.get(name="instructor")])
        self.other = User.objects.create_user("noticeother", email="other@example.com")

    def novedad(self):
        novedad = Novedad.objects.create(
            titulo="Jornada de innovación", contenido="Tenemos una nueva jornada.", creada_por=self.admin
        )
        novedad.grupos.add(Group.objects.get(name="instructor"))
        return novedad

    def plazo(self, hours=2):
        deadline = PlazoReporte.objects.create(
            titulo="Informe mensual",
            proyecto="LEM",
            fecha_limite=timezone.now() + timedelta(hours=hours),
            recordatorio_horas=24,
            creado_por=self.admin,
        )
        deadline.grupos.add(Group.objects.get(name="instructor"))
        return deadline

    def test_news_audience_and_idempotence(self):
        novedad = self.novedad()
        self.assertEqual(publicar_novedad(novedad), 1)
        self.assertEqual(publicar_novedad(novedad), 0)
        self.assertEqual(Notificacion.objects.get().usuario, self.user)
        self.assertEqual(CorreoPendiente.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(procesar_correos(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertEqual(procesar_correos(), 0)

    def test_deadline_reminder_expiry_and_delivered_report(self):
        deadline = self.plazo()
        anunciar_plazo(deadline)
        self.assertEqual(sincronizar_plazos(), 1)
        self.assertEqual(sincronizar_plazos(), 0)
        self.assertEqual(sincronizar_plazos(deadline.fecha_limite + timedelta(seconds=1)), 1)
        self.assertEqual(sincronizar_plazos(deadline.fecha_limite + timedelta(hours=1)), 0)
        self.assertEqual(Notificacion.objects.filter(usuario=self.user).count(), 3)
        next_deadline = self.plazo()
        Envio.objects.create(
            usuario=self.user,
            nombre="Informe entregado",
            proyecto="LEM",
            tipo_evidencia="Informe Final",
            plazo=next_deadline,
        )
        self.assertEqual(sincronizar_plazos(next_deadline.fecha_limite + timedelta(seconds=1)), 0)

    def test_preferences_are_respected_before_and_after_queueing(self):
        publicar_novedad(self.novedad())
        PreferenciasNotificacion.objects.create(usuario=self.user, correo_novedades=False)
        self.assertEqual(procesar_correos(), 0)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(Notificacion.objects.filter(usuario=self.user).count(), 1)
        other_news = self.novedad()
        publicar_novedad(other_news)
        self.assertEqual(CorreoPendiente.objects.count(), 1)

    @patch("notificaciones.services.EmailMultiAlternatives.send", side_effect=RuntimeError("Secret provider details"))
    def test_smtp_failure_retries_without_exposing_details(self, send):
        publicar_novedad(self.novedad())
        self.assertEqual(procesar_correos(), 0)
        queue = CorreoPendiente.objects.get()
        self.assertEqual(queue.intentos, 1)
        self.assertEqual(queue.estado, "pendiente")
        self.assertGreater(queue.proximo_intento, timezone.now())
        self.assertNotIn("Secret provider details", queue.ultimo_error)
        self.assertEqual(procesar_correos(), 0)

    def test_notifications_can_only_be_opened_by_the_owner(self):
        publicar_novedad(self.novedad())
        notice = Notificacion.objects.get()
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse("notificaciones:abrir", args=[notice.pk])).status_code, 404)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("notificaciones:abrir", args=[notice.pk])).status_code, 405)
        self.assertEqual(self.client.post(reverse("notificaciones:abrir", args=[notice.pk])).status_code, 302)
        notice.refresh_from_db()
        self.assertIsNotNone(notice.leida_en)

    def test_admin_pages_and_authorization(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("notificaciones:novedades_admin")).status_code, 403)
        self.client.force_login(self.admin)
        for name in ["novedades_admin", "crear_novedad", "plazos_admin", "crear_plazo"]:
            self.assertEqual(self.client.get(reverse("notificaciones:" + name)).status_code, 200)
        response = self.client.post(
            reverse("notificaciones:crear_novedad"),
            {
                "titulo": "Nueva actividad",
                "contenido": "Información del equipo",
                "grupos": [Group.objects.get(name="instructor").pk],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notificacion.objects.filter(usuario=self.user).count(), 1)

    def test_evidence_must_match_the_assigned_deadline(self):
        deadline = self.plazo()
        self.client.force_login(self.other)
        response = self.client.post(
            reverse("evidencia"),
            {"nombre": "No autorizado", "proyecto": "LEM", "plazo": deadline.pk, "linkArchivo": "https://example.com"},
        )
        self.assertFalse(response.context["exito"])
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("evidencia"),
            {
                "nombre": "Proyecto distinto",
                "proyecto": "GIVIT",
                "plazo": deadline.pk,
                "linkArchivo": "https://example.com",
            },
        )
        self.assertFalse(response.context["exito"])
        response = self.client.post(
            reverse("evidencia"),
            {
                "nombre": "Reporte correcto",
                "proyecto": "LEM",
                "plazo": deadline.pk,
                "linkArchivo": "https://example.com",
            },
        )
        self.assertEqual(response.status_code, 302)
        envio = Envio.objects.get(nombre="Reporte correcto")
        self.assertEqual(envio.plazo, deadline)
        self.assertEqual(envio.limite_aplicado, deadline.fecha_limite)

    def test_review_notifies_owner_once_for_unchanged_state(self):
        envio = Envio.objects.create(
            usuario=self.user, nombre="Para revisión", proyecto="LEM", tipo_evidencia="Documento"
        )
        self.client.force_login(self.admin)
        url = reverse("set_aprobada", args=[envio.pk])
        self.client.post(url, {"valor": "1"})
        self.client.post(url, {"valor": "1"})
        self.assertEqual(Notificacion.objects.filter(usuario=self.user, tipo="evidencia").count(), 1)

    def test_late_submission_keeps_the_deadline_and_is_identified(self):
        deadline = self.plazo(hours=-1)
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("evidencia"),
            {"nombre": "Entrega tardía", "proyecto": "LEM", "plazo": deadline.pk, "linkArchivo": "https://example.com"},
        )
        self.assertEqual(response.status_code, 302)
        envio = Envio.objects.get(nombre="Entrega tardía")
        self.assertTrue(envio.entrega_tardia)
        deadline.fecha_limite = timezone.now() + timedelta(days=1)
        deadline.save()
        envio.refresh_from_db()
        self.assertTrue(envio.entrega_tardia)
        response = self.client.get(reverse("notificaciones:mis_plazos"))
        self.assertContains(response, "Entregado fuera de plazo")
