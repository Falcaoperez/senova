from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from notificaciones.models import Notificacion

from .models import Envio
from .services import corregir_evidencia, observar_evidencia


class AdminEvidenciasTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser(
            "adminregistros", email="root@example.invalid", password="ClaveLocal42!"
        )
        self.user = User.objects.create_user("autorregistro", email="autor@example.invalid")
        self.envio = Envio.objects.create(
            usuario=self.user,
            nombre="Documento original",
            tipo_evidencia="Documento",
            proyecto="LEM",
            link_evidencia="https://example.com/original",
        )
        self.url = reverse("admin:Gesicom_envio_change", args=[self.envio.pk])
        self.client.force_login(self.root)

    def payload(self, **changes):
        data = {
            "usuario": self.user.pk,
            "nombre": "Documento actualizado",
            "tipo_evidencia": "Documento",
            "proyecto": "LEM",
            "link_evidencia": "https://example.com/nuevo",
            "version_actual": self.envio.version,
            "_save": "Guardar",
        }
        data.update(changes)
        return data

    def test_native_edit_advances_version_and_registers_history(self):
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 302)
        self.envio.refresh_from_db()
        self.assertEqual((self.envio.nombre, self.envio.version), ("Documento actualizado", 2))
        self.assertEqual(self.envio.historial.get().actor, self.root)
        self.assertEqual(self.envio.historial.get().accion, "administracion")

    def test_native_stale_edit_cannot_overwrite_recent_review(self):
        observar_evidencia(self.root, self.envio.pk, "Observación más reciente", version=1)
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "La evidencia cambió mientras la consultabas.")
        self.envio.refresh_from_db()
        self.assertEqual(self.envio.nombre, "Documento original")
        self.assertEqual(self.envio.observaciones, "Observación más reciente")
        self.assertEqual(self.envio.version, 2)

    def test_native_review_notifies_owner_and_history_is_read_only(self):
        response = self.client.post(self.url, self.payload(aprobada="on"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notificacion.objects.filter(usuario=self.user, envio=self.envio).count(), 1)
        history = self.envio.historial.get()
        self.assertEqual(history.accion, "revision")
        response = self.client.post(
            reverse("admin:Gesicom_movimientoevidencia_change", args=[history.pk]), {"detalle": "No modificar"}
        )
        self.assertEqual(response.status_code, 403)
        history.refresh_from_db()
        self.assertNotEqual(history.detalle, "No modificar")

    def test_native_file_upload_is_cleaned_if_the_history_cannot_be_saved(self):
        with TemporaryDirectory(prefix="gesicom-admin-") as media, self.settings(MEDIA_ROOT=media):
            payload = self.payload(archivo_evidencia=SimpleUploadedFile("nuevo.pdf", b"%PDF-1.4"))
            with (
                patch("Gesicom.admin.registrar_movimiento", side_effect=IntegrityError),
                self.assertRaises(IntegrityError),
            ):
                self.client.post(self.url, payload)
            self.assertFalse([p for p in Path(media).rglob("*") if p.is_file()])
            self.envio.refresh_from_db()
            self.assertEqual(self.envio.version, 1)

    def test_native_reviewer_receives_correction_at_an_authorized_admin_link(self):
        revisor = User.objects.create_user("revisornativo", email="revisor@example.invalid", is_staff=True)
        revisor.user_permissions.add(Permission.objects.get(content_type__app_label="Gesicom", codename="change_envio"))
        self.client.force_login(revisor)
        response = self.client.post(self.url, self.payload(rechazada="on"))
        self.assertEqual(response.status_code, 302)
        corregir_evidencia(
            self.user,
            self.envio.pk,
            {
                "version": 2,
                "nombre": "Corregida por el autor",
                "proyecto": "LEM",
                "evidencias": ["Documento"],
                "linkArchivo": "https://example.com/corregida",
                "motivo": "Adjunto corregido",
            },
        )
        notice = Notificacion.objects.get(usuario=revisor, envio=self.envio)
        self.assertEqual(notice.enlace, self.url)
        self.assertEqual(self.client.get(notice.enlace).status_code, 200)
