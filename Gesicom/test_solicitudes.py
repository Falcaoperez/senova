"""Reintentos de alta sin duplicar registros, adjuntos ni movimientos."""

import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from notificaciones.models import PlazoReporte

from .models import Envio, SolicitudEnvio
from .services import registrar_evidencia
from .solicitudes import crear_solicitud, verificar_solicitud


class SolicitudesTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory(prefix="gesicom-solicitud-")
        self.addCleanup(self.media.cleanup)
        self.config = override_settings(MEDIA_ROOT=self.media.name)
        self.config.enable()
        self.addCleanup(self.config.disable)
        self.user = User.objects.create_user("solicitud_autor")
        self.other = User.objects.create_user("solicitud_otro")
        self.client.force_login(self.user)

    def datos(self, **extra):
        return {
            "nombre": "Informe de investigación",
            "proyecto": "LEM",
            "linkArchivo": "https://www.sena.edu.co",
            **extra,
        }

    def test_signed_form_replay_redirects_to_original_record(self):
        response = self.client.get(reverse("evidencia"))
        token = response.context["form"]["solicitud"].value()
        self.assertTrue(token)
        datos = self.datos(solicitud=token)
        primero = self.client.post(reverse("evidencia"), datos)
        segundo = self.client.post(reverse("evidencia"), datos)
        self.assertEqual((primero.status_code, segundo.status_code), (302, 302))
        self.assertEqual(primero.url, segundo.url)
        self.assertEqual(Envio.objects.count(), 1)
        self.assertEqual(SolicitudEnvio.objects.count(), 1)
        self.assertEqual(Envio.objects.get().historial.count(), 1)

    def test_deadline_replay_still_works_after_delivery_or_archiving(self):
        plazo = PlazoReporte.objects.create(
            titulo="Entrega", proyecto="LEM", fecha_limite=timezone.now() + timedelta(days=1)
        )
        token = crear_solicitud(self.user)
        payload = self.datos(solicitud=token, plazo=plazo.pk)
        primero = self.client.post(reverse("evidencia"), payload)
        self.assertEqual(primero.status_code, 302)
        plazo.activo = False
        plazo.save(update_fields=["activo"])
        segundo = self.client.post(reverse("evidencia"), payload)
        self.assertEqual(segundo.status_code, 302)
        self.assertEqual(primero.url, segundo.url)
        self.assertEqual(Envio.objects.count(), 1)

    def test_replay_does_not_overwrite_original_or_require_reupload(self):
        token = crear_solicitud(self.user)
        primero = self.client.post(
            reverse("evidencia"),
            self.datos(
                solicitud=token, linkArchivo="", archivo=SimpleUploadedFile("informe.txt", b"Contenido original")
            ),
        )
        segundo = self.client.post(reverse("evidencia"), {"solicitud": token, "nombre": "No sobrescribir"})
        self.assertEqual((primero.status_code, segundo.status_code), (302, 302))
        self.assertEqual(primero.url, segundo.url)
        self.assertEqual(Envio.objects.get().nombre, "Informe de investigación")
        self.assertEqual(len([p for p in Path(self.media.name).rglob("*") if p.is_file()]), 1)

    def test_token_is_bound_to_account_and_invalid_or_expired_tokens_do_not_save(self):
        token = crear_solicitud(self.other)
        for valor in [token, "firma-invalida"]:
            response = self.client.post(reverse("evidencia"), self.datos(solicitud=valor))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)
        with patch("django.core.signing.time") as reloj:
            reloj.time.return_value = 1_800_000_000
            token = crear_solicitud(self.user)
            reloj.time.return_value = 1_800_086_401
            with self.assertRaises(ValidationError):
                verificar_solicitud(token, self.user)
        self.assertFalse(Envio.objects.exists())
        self.assertFalse(SolicitudEnvio.objects.exists())

    def test_deleted_original_is_not_resurrected(self):
        token = crear_solicitud(self.user)
        self.client.post(reverse("evidencia"), self.datos(solicitud=token))
        Envio.objects.get().delete()
        response = self.client.post(reverse("evidencia"), self.datos(solicitud=token))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "su registro no está disponible")
        self.assertFalse(Envio.objects.exists())
        self.assertIsNone(SolicitudEnvio.objects.get().envio_id)

    def test_request_cannot_be_reused_by_another_account_or_reveal_reassigned_record(self):
        codigo = uuid.uuid4()
        envio = registrar_evidencia(self.user, self.datos(solicitud=codigo))
        with self.assertRaises(PermissionDenied):
            registrar_evidencia(self.other, self.datos(solicitud=codigo))
        Envio.objects.filter(pk=envio.pk).update(usuario=self.other)
        with self.assertRaises(ValidationError):
            registrar_evidencia(self.user, self.datos(solicitud=codigo))
        self.assertEqual(Envio.objects.count(), 1)

    def test_failure_rolls_back_receipt_file_and_allows_retry(self):
        codigo = uuid.uuid4()
        with (
            patch("Gesicom.services.registrar_movimiento", side_effect=IntegrityError),
            self.assertRaises(IntegrityError),
        ):
            registrar_evidencia(
                self.user, self.datos(solicitud=codigo, archivo=SimpleUploadedFile("informe.txt", b"Texto"))
            )
        self.assertFalse(SolicitudEnvio.objects.exists())
        self.assertFalse(Envio.objects.exists())
        self.assertFalse([p for p in Path(self.media.name).rglob("*") if p.is_file()])
        registrar_evidencia(self.user, self.datos(solicitud=codigo))
        self.assertEqual(SolicitudEnvio.objects.count(), 1)
        self.assertEqual(Envio.objects.count(), 1)

    def test_separate_forms_and_legacy_clients_can_create_distinct_records(self):
        for _ in range(2):
            self.client.post(reverse("evidencia"), self.datos(solicitud=crear_solicitud(self.user)))
        self.client.post(reverse("evidencia"), self.datos())
        self.assertEqual(Envio.objects.count(), 3)
        self.assertEqual(SolicitudEnvio.objects.count(), 2)

    def test_missing_correction_target_never_creates_a_new_evidence(self):
        response = self.client.post(reverse("corregir_evidencia", args=[0]), self.datos())
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Envio.objects.exists())


class SolicitudesConcurrentesTests(TransactionTestCase):
    def test_two_simultaneous_posts_keep_one_file_and_one_evidence(self):
        if connection.vendor != "mysql":
            self.skipTest("Requiere bloqueos de MySQL.")
        with tempfile.TemporaryDirectory(prefix="gesicom-doble-") as media, override_settings(MEDIA_ROOT=media):
            usuario = User.objects.create_user("solicitud_simultanea")
            codigo = uuid.uuid4()

            def enviar(_):
                close_old_connections()
                try:
                    return registrar_evidencia(
                        User.objects.get(pk=usuario.pk),
                        {
                            "solicitud": codigo,
                            "nombre": "Único registro",
                            "proyecto": "LEM",
                            "archivo": SimpleUploadedFile("adjunto.txt", b"Contenido"),
                            "evidencias": ["Documento"],
                        },
                    ).pk
                finally:
                    close_old_connections()

            with ThreadPoolExecutor(max_workers=2) as executor:
                resultados = list(executor.map(enviar, range(2)))
            self.assertEqual(resultados[0], resultados[1])
            self.assertEqual(Envio.objects.count(), 1)
            self.assertEqual(Envio.objects.get().historial.count(), 1)
            self.assertEqual(SolicitudEnvio.objects.count(), 1)
            self.assertEqual(len([p for p in Path(media).rglob("*") if p.is_file()]), 1)
