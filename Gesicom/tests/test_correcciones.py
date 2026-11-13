"""Regresiones de propiedad, versiones, archivos y trazabilidad de evidencias."""

import importlib
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from notificaciones.models import CorreoPendiente, Notificacion, PlazoReporte, PreferenciasNotificacion

from ..forms import EvidenciaForm
from ..models import Envio
from ..services import corregir_evidencia, observar_evidencia, registrar_evidencia, revisar_evidencia


class CorreccionesTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp(prefix="gesicom-evidencias-")
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()
        self.addCleanup(shutil.rmtree, self.media)
        self.addCleanup(self.override.disable)
        self.user = User.objects.create_user("autor", email="autor@example.invalid")
        self.other = User.objects.create_user("otroautor", email="otro@example.invalid")
        self.reviewer = User.objects.create_user("revisor", email="revisor@example.invalid")
        self.reviewer.groups.add(Group.objects.get(name="administrador"))
        self.client.force_login(self.user)
        self.envio = registrar_evidencia(self.user, self.data())
        self.url = reverse("corregir_evidencia", args=[self.envio.pk])

    def data(self, **changes):
        data = {
            "nombre": "Informe del equipo",
            "proyecto": "LEM",
            "evidencias": ["Informe Final"],
            "linkArchivo": "https://example.com/original",
            "motivo": "Actualicé el informe",
            "version": 1,
        }
        data.update(changes)
        return data

    def test_creation_redirect_prevents_refreshing_the_post(self):
        response = self.client.post(reverse("evidencia"), self.data(nombre="Nuevo informe"))
        nuevo = Envio.objects.get(nombre="Nuevo informe")
        self.assertRedirects(response, reverse("ver_evidencia", args=[nuevo.pk]))
        self.client.get(response.url)
        self.client.get(response.url)
        self.assertEqual(Envio.objects.filter(nombre="Nuevo informe").count(), 1)
        self.assertEqual(nuevo.historial.get().accion, "registro")

    def test_correction_returns_to_review_and_preserves_delivery_and_feedback(self):
        plazo = PlazoReporte.objects.create(
            titulo="Entrega original", proyecto="LEM", fecha_limite=timezone.now() - timedelta(days=2)
        )
        otro_plazo = PlazoReporte.objects.create(
            titulo="Intento de cambio", fecha_limite=timezone.now() + timedelta(days=3)
        )
        self.envio.plazo = plazo
        self.envio.limite_aplicado = plazo.fecha_limite
        self.envio.observaciones = "Falta el anexo de resultados"
        self.envio.save()
        envio, _ = revisar_evidencia(self.reviewer, self.envio.pk, False, version=1)
        original = (envio.registrado_en, envio.fecha_envio, envio.limite_aplicado, envio.plazo_id)
        response = self.client.post(
            self.url,
            self.data(
                version=2,
                nombre="Informe corregido",
                plazo=otro_plazo.pk,
                observaciones="No debe reemplazar la observación del revisor",
            ),
        )
        self.assertRedirects(response, reverse("ver_evidencia", args=[envio.pk]))
        envio.refresh_from_db()
        self.assertEqual((envio.registrado_en, envio.fecha_envio, envio.limite_aplicado, envio.plazo_id), original)
        self.assertTrue(envio.entrega_tardia)
        self.assertEqual(envio.estado, "pendiente")
        self.assertEqual(envio.version, 3)
        self.assertEqual(envio.observaciones, "Falta el anexo de resultados")
        self.assertEqual(envio.historial.first().detalle, "Actualicé el informe")
        self.assertEqual(Notificacion.objects.filter(usuario=self.reviewer, envio=envio).count(), 1)

    def test_only_owner_can_correct_even_when_another_user_is_reviewer(self):
        for actor in [self.other, self.reviewer]:
            self.client.force_login(actor)
            self.assertEqual(self.client.get(self.url).status_code, 404)
            self.assertEqual(self.client.post(self.url, self.data()).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_approved_evidence_is_immutable_to_owner(self):
        revisar_evidencia(self.reviewer, self.envio.pk, True)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.data(version=2)).status_code, 403)
        self.envio.refresh_from_db()
        self.assertEqual(self.envio.version, 2)

    def test_stale_correction_is_rejected_without_losing_typed_values(self):
        corregir_evidencia(self.user, self.envio.pk, self.data(nombre="Primera corrección"))
        response = self.client.post(self.url, self.data(nombre="Edición de otra pestaña"))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.context["form"]["nombre"].value(), "Edición de otra pestaña")
        self.envio.refresh_from_db()
        self.assertEqual(self.envio.nombre, "Primera corrección")
        self.assertEqual(self.envio.historial.count(), 2)

    def test_stale_review_or_observation_cannot_overwrite_a_correction(self):
        corregir_evidencia(self.user, self.envio.pk, self.data())
        self.client.force_login(self.reviewer)
        response = self.client.post(reverse("set_aprobada", args=[self.envio.pk]), {"valor": "1", "version": 1})
        self.assertEqual(response.status_code, 409)
        response = self.client.post(
            reverse("actualizar_observaciones", args=[self.envio.pk]), {"observaciones": "Desactualizada", "version": 1}
        )
        self.assertEqual(response.status_code, 409)
        self.envio.refresh_from_db()
        self.assertFalse(self.envio.aprobada)
        self.assertFalse(self.envio.observaciones)
        self.assertEqual(self.envio.version, 2)

    def test_repeated_review_is_idempotent_and_current_forms_include_versions(self):
        revisar_evidencia(self.reviewer, self.envio.pk, True)
        revisar_evidencia(self.reviewer, self.envio.pk, True)
        self.envio.refresh_from_db()
        self.assertEqual(self.envio.version, 2)
        self.assertEqual(self.envio.historial.filter(accion="revision").count(), 1)
        self.assertEqual(Notificacion.objects.filter(usuario=self.user, envio=self.envio).count(), 1)
        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("evidencias_list"))
        self.assertContains(response, 'name="version" value="2"', count=2)

    def test_correction_does_not_notify_a_former_reviewer_and_respects_email_preferences(self):
        revisar_evidencia(self.reviewer, self.envio.pk, False)
        PreferenciasNotificacion.objects.create(usuario=self.reviewer, correo_evidencias=False)
        corregir_evidencia(self.user, self.envio.pk, self.data(version=2))
        notification = Notificacion.objects.get(usuario=self.reviewer, envio=self.envio)
        self.assertFalse(CorreoPendiente.objects.filter(notificacion=notification).exists())
        self.reviewer.groups.clear()
        corregir_evidencia(self.user, self.envio.pk, self.data(version=3))
        self.assertEqual(Notificacion.objects.filter(usuario=self.reviewer, envio=self.envio).count(), 1)
        with self.assertRaises(PermissionDenied):
            revisar_evidencia(self.reviewer, self.envio.pk, True)

    def test_file_replacement_removal_and_rollback_do_not_leave_new_orphans(self):
        original = SimpleUploadedFile("original.pdf", b"%PDF-1.4 original")
        envio = registrar_evidencia(self.user, self.data(archivo=original, linkArchivo=""))
        anterior = Path(envio.archivo_evidencia.path)
        replacement = SimpleUploadedFile("nuevo.pdf", b"%PDF-1.4 nuevo")
        with self.captureOnCommitCallbacks(execute=True):
            envio = corregir_evidencia(self.user, envio.pk, self.data(archivo=replacement, linkArchivo="", version=1))
        self.assertFalse(anterior.exists())
        actual = Path(envio.archivo_evidencia.path)
        with self.captureOnCommitCallbacks(execute=True):
            corregir_evidencia(self.user, envio.pk, self.data(version=2, eliminar_archivo=True))
        self.assertFalse(actual.exists())
        names = set(Path(self.media).rglob("*"))
        with (
            patch("Gesicom.services.registrar_movimiento", side_effect=IntegrityError),
            self.assertRaises(IntegrityError),
        ):
            registrar_evidencia(self.user, self.data(archivo=SimpleUploadedFile("fallo.pdf", b"%PDF-1.4 fallo")))
        self.assertEqual({p for p in Path(self.media).rglob("*") if p.is_file()}, {p for p in names if p.is_file()})

    def test_shared_file_is_not_deleted_while_referenced_by_another_record(self):
        envio = registrar_evidencia(self.user, self.data(archivo=SimpleUploadedFile("compartido.pdf", b"%PDF-1.4")))
        otro = Envio.objects.create(
            usuario=self.other, tipo_evidencia="Documento", archivo_evidencia=envio.archivo_evidencia.name
        )
        with self.captureOnCommitCallbacks(execute=True):
            corregir_evidencia(self.user, envio.pk, self.data(eliminar_archivo=True))
        self.assertTrue(Path(otro.archivo_evidencia.path).exists())

    def test_correction_validates_files_links_limits_and_requires_an_attachment(self):
        for changes in [
            {"nombre": "x" * 81},
            {"linkArchivo": "javascript:alert(1)"},
            {"linkArchivo": "ftp://example.com/f"},
            {"linkArchivo": "", "eliminar_archivo": True},
            {"version": ""},
            {"motivo": ""},
        ]:
            form = EvidenciaForm(self.data(**changes), usuario=self.user, envio=self.envio)
            self.assertFalse(form.is_valid(), changes)
        form = EvidenciaForm(
            self.data(), {"archivo": SimpleUploadedFile("ejecutable.exe", b"bad")}, usuario=self.user, envio=self.envio
        )
        self.assertFalse(form.is_valid())
        archivo = SimpleUploadedFile("grande.pdf", b"0")
        archivo.size = 10 * 1024 * 1024 + 1
        form = EvidenciaForm(self.data(), {"archivo": archivo}, usuario=self.user, envio=self.envio)
        self.assertFalse(form.is_valid())

    def test_history_is_private_paginated_and_escapes_notes(self):
        observar_evidencia(self.reviewer, self.envio.pk, "<script>alert('x')</script>", version=1)
        for i in range(22):
            observar_evidencia(self.reviewer, self.envio.pk, f"Nota {i}")
        response = self.client.get(reverse("ver_evidencia", args=[self.envio.pk]))
        self.assertEqual(response.context["historial"].paginator.count, 24)
        self.assertEqual(len(response.context["historial"]), 20)
        self.assertNotContains(response, "<script>alert(")
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("ver_evidencia", args=[self.envio.pk])).status_code, 404)

    def test_expired_observation_session_returns_json_login_instead_of_html(self):
        self.client.logout()
        response = self.client.post(
            reverse("actualizar_observaciones", args=[self.envio.pk]),
            {"observaciones": "No guardar"},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["login_url"], reverse("login"))

    def test_backfill_preserves_records_and_marks_unknown_past_as_historical(self):
        envio = Envio.objects.create(usuario=None, nombre="Preexistente", tipo_evidencia="Documento", aprobada=True)
        envio.refresh_from_db()
        original = (envio.fecha_envio, envio.registrado_en, envio.aprobada, envio.archivo_evidencia.name)
        migration = importlib.import_module("Gesicom.migrations.0013_envio_actualizado_en_envio_version_and_more")
        migration.incorporar_historial(apps, SimpleNamespace(connection=connection))
        envio.refresh_from_db()
        self.assertEqual(
            (envio.fecha_envio, envio.registrado_en, envio.aprobada, envio.archivo_evidencia.name), original
        )
        history = envio.historial.get()
        self.assertEqual((history.accion, history.actor_id, history.estado), ("historico", None, "aprobada"))
        self.assertEqual(self.envio.historial.count(), 1)

    def test_correction_preserves_unclassified_or_legacy_project_in_form_and_service(self):
        for proyecto in ["", "Proyecto anterior"]:
            with self.subTest(proyecto=proyecto):
                Envio.objects.filter(pk=self.envio.pk).update(proyecto=proyecto)
                self.envio.refresh_from_db()
                response = self.client.get(self.url)
                self.assertEqual(response.context["form"]["proyecto"].value(), proyecto)
                response = self.client.post(self.url, self.data(proyecto=proyecto, version=self.envio.version))
                self.assertEqual(response.status_code, 302)
                self.envio.refresh_from_db()
                self.assertEqual(self.envio.proyecto, proyecto)

    def test_correction_keeps_original_project_after_deadline_reclassification(self):
        plazo = PlazoReporte.objects.create(titulo="Plazo reclasificado", proyecto="GIVIT", fecha_limite=timezone.now())
        self.envio.plazo = plazo
        self.envio.limite_aplicado = plazo.fecha_limite
        self.envio.save()
        response = self.client.post(self.url, self.data())
        self.assertEqual(response.status_code, 302)
        self.envio.refresh_from_db()
        self.assertEqual(self.envio.proyecto, "LEM")
        response = self.client.post(self.url, self.data(proyecto="ACAF", version=2))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "El proyecto debe coincidir")
        self.envio.refresh_from_db()
        self.assertEqual((self.envio.proyecto, self.envio.version), ("LEM", 2))
