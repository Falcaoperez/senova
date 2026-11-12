"""Cumplimiento, ediciones concurrentes y recordatorios con destinatarios actuales."""

import csv
import io
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from Gesicom.models import Envio
from Gesicom.selectors import _panel_context

from .forms import PlazoReporteForm
from .models import CorreoPendiente, Notificacion, PlazoReporte, PreferenciasNotificacion
from .plazos import ConflictoPlazo, archivar_plazo, guardar_plazo, recordar_pendientes
from .selectors import resumen_agenda, resumen_seguimiento, seguimiento_destinatarios
from .services import anunciar_plazo, procesar_correos, sincronizar_plazos

User = get_user_model()
PASSWORD = "PruebaSeguimiento29!"


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SeguimientoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("agenda_admin", "agenda_admin@example.invalid", PASSWORD)
        cls.grupo = Group.objects.get(name="instructor")
        cls.otro_grupo = Group.objects.get(name="investigador")
        cls.usuarios = [User.objects.create_user(f"agenda_{i}", f"agenda_{i}@example.invalid") for i in range(4)]
        for user in cls.usuarios[:3]:
            user.groups.add(cls.grupo)
        cls.plazo = PlazoReporte.objects.create(
            titulo="Reporte de investigación",
            proyecto="LEM",
            descripcion="Entrega mensual",
            fecha_limite=timezone.now() + timedelta(days=2),
            creado_por=cls.admin,
        )
        cls.plazo.grupos.add(cls.grupo)

    def setUp(self):
        self.client.force_login(self.admin)

    def entrega(self, usuario, *, tardia=False):
        return Envio.objects.create(
            usuario=usuario,
            nombre="Informe",
            proyecto="LEM",
            tipo_evidencia="Documento",
            plazo=self.plazo,
            limite_aplicado=timezone.now() + timedelta(hours=-1 if tardia else 1),
        )

    def datos(self, **cambios):
        plazo = PlazoReporte.objects.get(pk=self.plazo.pk)
        datos = {
            field: getattr(plazo, field)
            for field in ["titulo", "descripcion", "proyecto", "fecha_limite", "recordatorio_horas", "activo"]
        }
        datos.update(grupos=list(plazo.grupos.all()), revision_actual=plazo.revision)
        datos.update(cambios)
        return datos

    def payload(self, **cambios):
        datos = self.datos(**cambios)
        datos["grupos"] = [grupo.pk for grupo in datos["grupos"]]
        datos["fecha_limite"] = timezone.localtime(datos["fecha_limite"]).strftime("%Y-%m-%dT%H:%M")
        return datos

    def test_follow_up_uses_current_audience_and_original_delivery_limit(self):
        puntual = self.entrega(self.usuarios[0])
        tarde = self.entrega(self.usuarios[1], tardia=True)
        self.entrega(self.usuarios[3])  # La cuenta ya no pertenece al grupo destinatario.
        PlazoReporte.objects.filter(pk=self.plazo.pk).update(fecha_limite=timezone.now() + timedelta(days=10))
        self.assertEqual(
            resumen_seguimiento(self.plazo),
            {
                "total": 3,
                "entregados": 2,
                "a_tiempo": 1,
                "tardios": 1,
                "pendientes": 1,
                "sin_recordatorio": 1,
            },
        )
        filas = {p.pk: p for p in seguimiento_destinatarios(self.plazo)}
        self.assertTrue(filas[self.usuarios[0].pk].a_tiempo)
        self.assertFalse(filas[self.usuarios[1].pk].a_tiempo)
        puntual.refresh_from_db()
        tarde.refresh_from_db()
        self.assertFalse(puntual.entrega_tardia)
        self.assertTrue(tarde.entrega_tardia)

    def test_filters_and_csv_only_export_matching_current_recipients(self):
        self.entrega(self.usuarios[0])
        user = self.usuarios[2]
        user.first_name = "=SUM(1,2)"
        user.save(update_fields=["first_name"])
        response = self.client.get(
            reverse("notificaciones:seguimiento_csv", args=[self.plazo.pk]), {"estado": "pendiente", "q": user.username}
        )
        contenido = b"".join(response.streaming_content).decode("utf-8-sig")
        filas = list(csv.reader(io.StringIO(contenido)))
        self.assertEqual(len(filas), 2)
        self.assertEqual(filas[1][0], user.username)
        self.assertEqual(filas[1][1], "'=SUM(1,2)")
        self.assertEqual(response["Cache-Control"], "no-store")
        response = self.client.get(
            reverse("notificaciones:seguimiento_plazo", args=[self.plazo.pk]), {"estado": "pendiente"}
        )
        self.assertEqual(response.context["destinatarios"].paginator.count, 2)
        self.assertEqual(response.context["seguimiento"]["total"], 3)

    def test_non_administrators_cannot_read_or_change_follow_up(self):
        self.client.force_login(self.usuarios[0])
        for name in ["seguimiento_plazo", "seguimiento_csv"]:
            self.assertEqual(self.client.get(reverse("notificaciones:" + name, args=[self.plazo.pk])).status_code, 403)
        for name in ["recordar_pendientes", "archivar_plazo"]:
            self.assertEqual(
                self.client.post(
                    reverse("notificaciones:" + name, args=[self.plazo.pk]),
                    {"revision_actual": 1, "contrasena_actual": PASSWORD},
                ).status_code,
                403,
            )

    def test_manual_reminder_is_once_per_recipient_and_revision_and_keeps_automatic_schedule(self):
        self.entrega(self.usuarios[0])
        PreferenciasNotificacion.objects.create(usuario=self.usuarios[1], correo_plazos=False)
        self.assertEqual(recordar_pendientes(self.admin, self.plazo.pk, 1), 2)
        self.assertEqual(recordar_pendientes(self.admin, self.plazo.pk, 1), 0)
        self.assertEqual(Notificacion.objects.filter(tipo="seguimiento").count(), 2)
        self.assertEqual(CorreoPendiente.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(sincronizar_plazos(self.plazo.fecha_limite - timedelta(hours=1)), 2)
        nuevo, _, _ = guardar_plazo(self.admin, self.datos(descripcion="Indicaciones actualizadas"), pk=self.plazo.pk)
        self.assertEqual(recordar_pendientes(self.admin, self.plazo.pk, nuevo.revision), 2)
        self.assertEqual(Notificacion.objects.filter(tipo="seguimiento").count(), 4)

    def test_password_and_revision_are_required_for_manual_actions(self):
        url = reverse("notificaciones:recordar_pendientes", args=[self.plazo.pk])
        cliente_csrf = Client(enforce_csrf_checks=True)
        cliente_csrf.force_login(self.admin)
        self.assertEqual(cliente_csrf.post(url, {"revision_actual": 1, "contrasena_actual": PASSWORD}).status_code, 403)
        for payload in [{}, {"revision_actual": 1}, {"revision_actual": 0, "contrasena_actual": PASSWORD}]:
            self.client.post(url, payload)
            self.assertFalse(Notificacion.objects.exists())
        self.client.post(url, {"revision_actual": 1, "contrasena_actual": PASSWORD})
        self.assertEqual(Notificacion.objects.count(), 3)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_members_of_multiple_assigned_groups_are_counted_once(self):
        self.usuarios[0].groups.add(self.otro_grupo)
        self.plazo.grupos.add(self.otro_grupo)
        self.assertEqual(resumen_seguimiento(self.plazo)["total"], 3)
        self.assertEqual(resumen_agenda(self.usuarios[0])["total"], 1)
        self.assertEqual(recordar_pendientes(self.admin, self.plazo.pk, 1), 3)

    def test_empty_audience_has_an_accessible_zero_progress_state(self):
        vacio = Group.objects.create(name="agenda_sin_destinatarios")
        self.plazo.grupos.set([vacio])
        response = self.client.get(reverse("notificaciones:seguimiento_plazo", args=[self.plazo.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["seguimiento"]["total"], 0)
        self.assertContains(response, "0%")
        self.assertContains(response, "No hay destinatarios")
        self.assertEqual(recordar_pendientes(self.admin, self.plazo.pk, 1), 0)

    @override_settings(RATE_LIMITS_ENABLED=True)
    @patch("SENNOVA.middleware.time")
    def test_password_confirmation_attempts_are_limited_per_account(self, reloj):
        reloj.time.return_value = 1_800_000_123
        cache.clear()
        url = reverse("notificaciones:recordar_pendientes", args=[self.plazo.pk])
        for _ in range(20):
            self.assertEqual(self.client.post(url, {"contrasena_actual": "incorrecta"}).status_code, 302)
        self.assertEqual(self.client.post(url, {"contrasena_actual": "incorrecta"}).status_code, 429)
        self.assertFalse(Notificacion.objects.exists())

    def test_noop_save_preserves_seconds_version_and_queue(self):
        anunciar_plazo(self.plazo)
        form = PlazoReporteForm(self.payload(), instance=self.plazo)
        self.assertTrue(form.is_valid(), form.errors)
        guardado, total, cambio = guardar_plazo(self.admin, form.cleaned_data, pk=self.plazo.pk)
        self.assertFalse(cambio)
        self.assertEqual(total, 0)
        self.assertEqual(guardado.fecha_limite, self.plazo.fecha_limite)
        self.assertEqual((guardado.version, guardado.revision), (1, 1))
        self.assertEqual(CorreoPendiente.objects.filter(estado="pendiente").count(), 3)

    def test_audience_change_cancels_old_mail_and_notifies_only_current_members(self):
        anunciar_plazo(self.plazo)
        self.usuarios[3].groups.add(self.otro_grupo)
        plazo, total, _ = guardar_plazo(self.admin, self.datos(grupos=[self.otro_grupo]), pk=self.plazo.pk)
        self.assertEqual((plazo.version, plazo.revision, total), (2, 2, 1))
        self.assertEqual(CorreoPendiente.objects.filter(estado="cancelado").count(), 3)
        self.assertEqual(procesar_correos(), 1)
        self.assertEqual(mail.outbox[0].to, [self.usuarios[3].email])

    def test_stale_edit_does_not_overwrite_data_or_queue(self):
        datos_antiguos = self.payload(titulo="Título obsoleto")
        guardar_plazo(self.admin, self.datos(titulo="Título vigente"), pk=self.plazo.pk)
        response = self.client.post(reverse("notificaciones:editar_plazo", args=[self.plazo.pk]), datos_antiguos)
        self.assertEqual(response.status_code, 409)
        self.plazo.refresh_from_db()
        self.assertEqual(self.plazo.titulo, "Título vigente")
        self.assertEqual(Notificacion.objects.count(), 3)
        with self.assertRaises(ConflictoPlazo):
            guardar_plazo(self.admin, self.datos(revision_actual=1, titulo="No sobrescribir"), pk=self.plazo.pk)

    def test_expired_deadline_can_be_archived_without_changing_delivery_history(self):
        envio = self.entrega(self.usuarios[0], tardia=True)
        original = (envio.registrado_en, envio.limite_aplicado)
        PlazoReporte.objects.filter(pk=self.plazo.pk).update(fecha_limite=timezone.now() - timedelta(days=2))
        self.plazo.refresh_from_db()
        anunciar_plazo(self.plazo)
        form = PlazoReporteForm(self.payload(activo=False), instance=self.plazo)
        self.assertTrue(form.is_valid(), form.errors)
        guardado, _, _ = guardar_plazo(self.admin, form.cleaned_data, pk=self.plazo.pk)
        self.assertFalse(guardado.activo)
        self.assertEqual(procesar_correos(), 0)
        envio.refresh_from_db()
        self.assertEqual((envio.registrado_en, envio.limite_aplicado), original)
        self.assertEqual(resumen_agenda(self.usuarios[0])["total"], 0)

    def test_archiving_cancels_queue_and_blocks_new_reminders(self):
        anunciar_plazo(self.plazo)
        response = self.client.post(
            reverse("notificaciones:archivar_plazo", args=[self.plazo.pk]),
            {"revision_actual": 1, "contrasena_actual": PASSWORD},
        )
        self.assertEqual(
            response.status_code, 302, response.context["adminform"].form.errors if response.status_code == 200 else ""
        )
        self.plazo.refresh_from_db()
        self.assertFalse(self.plazo.activo)
        self.assertEqual(CorreoPendiente.objects.filter(estado="cancelado").count(), 3)
        self.assertEqual(procesar_correos(), 0)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(archivar_plazo(self.admin, self.plazo.pk, self.plazo.revision).revision, 2)

    def test_native_admin_uses_same_revision_and_does_not_announce_noop(self):
        url = reverse("admin:notificaciones_plazoreporte_change", args=[self.plazo.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, {**self.payload(titulo="Título desde Django"), "_save": "Guardar"})
        self.assertEqual(
            response.status_code, 302, response.context["adminform"].form.errors if response.status_code == 200 else ""
        )
        self.plazo.refresh_from_db()
        self.assertEqual((self.plazo.revision, self.plazo.version), (2, 2))
        self.assertEqual(Notificacion.objects.count(), 3)
        self.assertEqual(self.client.post(url, {**self.payload(), "_save": "Guardar"}).status_code, 302)
        self.plazo.refresh_from_db()
        self.assertEqual(self.plazo.revision, 2)
        self.assertEqual(Notificacion.objects.count(), 3)

    def test_native_staff_can_create_with_explicit_permission(self):
        staff = User.objects.create_user("agenda_editor", is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename="add_plazoreporte"))
        self.client.force_login(staff)
        response = self.client.post(
            reverse("admin:notificaciones_plazoreporte_add"),
            {**self.payload(titulo="Nuevo plazo nativo"), "_save": "Guardar"},
        )
        self.assertEqual(
            response.status_code, 302, response.context["adminform"].form.errors if response.status_code == 200 else ""
        )
        creado = PlazoReporte.objects.get(titulo="Nuevo plazo nativo")
        self.assertEqual(creado.creado_por, staff)
        self.assertEqual(creado.grupos.get(), self.grupo)
        self.assertEqual(Notificacion.objects.filter(plazo=creado).count(), 3)

    def test_personal_dashboard_prioritizes_overdue_and_scopes_corrections(self):
        self.entrega(self.usuarios[0])
        vencido = PlazoReporte.objects.create(titulo="Entrega vencida", fecha_limite=timezone.now() - timedelta(days=1))
        vencido.grupos.add(self.grupo)
        Envio.objects.create(usuario=self.usuarios[0], nombre="Corregir", rechazada=True)
        Envio.objects.create(usuario=self.usuarios[1], nombre="Privado", rechazada=True)
        context = _panel_context(self.usuarios[0], "instructor")
        self.assertEqual(list(context["proximos_plazos"]), [vencido])
        self.assertEqual(context["agenda"]["vencidos"], 1)
        self.assertEqual(context["mis_correcciones"], 1)
        self.assertFalse(any(envio.usuario == self.usuarios[1] for envio in context["recientes"]))
        self.client.force_login(self.usuarios[0])
        self.assertContains(self.client.get(reverse("role_instructor")), "Entrega vencida")

    def test_deadline_and_author_scopes_do_not_expose_other_users_evidence(self):
        propio = self.entrega(self.usuarios[0])
        ajeno = self.entrega(self.usuarios[1])
        self.client.force_login(self.usuarios[0])
        response = self.client.get(reverse("evidencias_list"), {"plazo": self.plazo.pk, "usuario": self.usuarios[1].pk})
        self.assertEqual(response.context["envios"].paginator.count, 0)
        response = self.client.get(reverse("evidencias_list"), {"plazo": self.plazo.pk})
        self.assertEqual([e.pk for e in response.context["envios"]], [propio.pk])
        self.client.force_login(self.admin)
        response = self.client.get(reverse("evidencias_list"), {"plazo": self.plazo.pk, "usuario": self.usuarios[1].pk})
        self.assertEqual([e.pk for e in response.context["envios"]], [ajeno.pk])
