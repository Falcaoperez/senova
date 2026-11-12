from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Envio

User = get_user_model()


class ArchivosProtegidosTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        override = override_settings(MEDIA_ROOT=self.directory.name)
        override.enable()
        self.addCleanup(override.disable)
        self.owner = User.objects.create_user("fileowner", email="fileowner@example.com")
        self.other = User.objects.create_user("fileother", email="fileother@example.com")
        self.envio = Envio.objects.create(
            usuario=self.owner,
            nombre="Archivo privado",
            proyecto="LEM",
            tipo_evidencia="Documento",
            archivo_evidencia=SimpleUploadedFile("privado.txt", b"Contenido privado"),
        )

    def test_anonymous_and_other_users_cannot_download(self):
        url = reverse("archivo_evidencia", args=[self.envio.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(self.envio.archivo_evidencia.url).status_code, 404)

    def test_owner_and_reviewer_can_read_and_download(self):
        url = reverse("archivo_evidencia", args=[self.envio.pk])
        self.client.force_login(self.owner)
        response = self.client.get(url)
        self.assertEqual(b"".join(response.streaming_content), b"Contenido privado")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertIn("inline", response["Content-Disposition"])
        response = self.client.get(url, {"descargar": "1"})
        self.assertIn("attachment", response["Content-Disposition"])
        b"".join(response.streaming_content)
        self.other.groups.add(Group.objects.get(name="coordinador"))
        self.client.force_login(self.other)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)

    def test_reset_endpoints_are_csrf_protected(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("verificar_pin"), {"email": "fileowner@example.com", "codigo": "123456"})
        self.assertEqual(response.status_code, 403)
        response = client.post(
            reverse("restablecer_password"), {"password": "UnaClave42!", "password_confirm": "UnaClave42!"}
        )
        self.assertEqual(response.status_code, 403)

    def test_untrusted_csv_content_is_not_a_formula(self):
        Envio.objects.create(
            usuario=self.owner,
            nombre='=HYPERLINK("https://example.com")',
            proyecto="LEM",
            tipo_evidencia="Documento",
            observaciones=" @SUM(1+1)",
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("reportes_csv"))
        import csv
        import io

        contenido = b"".join(response.streaming_content).decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(contenido)))
        row = next(row for row in rows if row[1].startswith("'="))
        self.assertTrue(row[5].startswith("' @"))
