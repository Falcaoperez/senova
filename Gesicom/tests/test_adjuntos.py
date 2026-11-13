"""Formatos reales, adjuntos privados, vistas limitadas y retirada tras confirmar SQL."""

import io
import struct
import tempfile
import zipfile
import zlib
from pathlib import Path

from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from ..adjuntos import MAX_TEXTO_VISTA, validar_archivo_evidencia
from ..models import Envio


def imagen_png():
    salida = io.BytesIO()
    Image.new("RGB", (2, 2), "green").save(salida, format="PNG")
    return salida.getvalue()


def documento_zip(partes):
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as archivo:
        for nombre, contenido in partes.items():
            archivo.writestr(nombre, contenido)
    return salida.getvalue()


class FormatosAdjuntosTests(TestCase):
    def test_known_formats_and_windows_text_encodings_are_accepted(self):
        office = {"docx": "word/document.xml", "xlsx": "xl/workbook.xml", "pptx": "ppt/presentation.xml"}
        ejemplos = {
            "informe.PDF": b"%PDF-1.7\ncontenido",
            "captura.PNG": imagen_png(),
            "informe.doc": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 504,
            "notas.txt": "Información pública del proyecto".encode(),
            "comprimido.zip": documento_zip({"documento.txt": "Contenido"}),
            "archivo.rar": b"Rar!\x1a\x07\x01\x00" + b"archivo",
        }
        for extension, parte in office.items():
            ejemplos[f"documento.{extension}"] = documento_zip(
                {"[Content_Types].xml": "<Types/>", parte: "<document/>"}
            )
        for nombre, contenido in ejemplos.items():
            with self.subTest(nombre=nombre):
                archivo = SimpleUploadedFile(nombre, contenido)
                validar_archivo_evidencia(archivo)
                self.assertFalse(archivo.closed)
                self.assertEqual(archivo.tell(), 0)
                self.assertEqual(archivo.read(), contenido)
        for codec in ["utf-8-sig", "utf-16", "utf-32", "cp1252"]:
            validar_archivo_evidencia(SimpleUploadedFile("notas.txt", "Investigación y formación".encode(codec)))

    def test_renamed_binary_html_or_other_formats_are_rejected(self):
        for nombre, contenido in [
            ("texto.pdf", b"<html>contenido</html>"),
            ("foto.png", b"<svg onload=alert(1)>"),
            ("foto.jpg", imagen_png()),
            ("documento.doc", b"Texto con extension falsa"),
            ("documento.docx", documento_zip({"falso.txt": "contenido"})),
            ("comprimido.zip", b"PK no es un zip"),
            ("comprimido.rar", b"falso"),
            ("binario.txt", b"MZ\0\x01\x02"),
            ("script.html", b"<html>"),
            ("vacio.pdf", b""),
        ]:
            with self.subTest(nombre=nombre), self.assertRaises(ValidationError):
                validar_archivo_evidencia(SimpleUploadedFile(nombre, contenido))

    def test_size_and_image_resolution_limits_are_enforced_before_large_decoding(self):
        grande = SimpleUploadedFile("grande.pdf", b"%PDF-1.7")
        grande.size = 10 * 1024 * 1024 + 1
        with self.assertRaisesMessage(ValidationError, "10 MB"):
            validar_archivo_evidencia(grande)
        png = imagen_png()
        ihdr = struct.pack(">IIBBBBB", 5001, 5000, 8, 2, 0, 0, 0)
        png = png[:16] + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr)) + png[33:]
        with self.assertRaisesMessage(ValidationError, "25 millones"):
            validar_archivo_evidencia(SimpleUploadedFile("resolucion.png", png))

    def test_stream_position_is_preserved_and_bad_crc_is_rejected(self):
        archivo = SimpleUploadedFile("imagen.png", imagen_png())
        archivo.read(7)
        validar_archivo_evidencia(archivo)
        self.assertEqual(archivo.tell(), 7)
        corrupto = imagen_png()[:-9] + b"x" * 9
        with self.assertRaises(ValidationError):
            validar_archivo_evidencia(SimpleUploadedFile("corrupto.png", corrupto))

    def test_office_directory_limits_are_checked_without_unzipping(self):
        contenido = bytearray(documento_zip({"[Content_Types].xml": "<Types/>", "word/document.xml": "<document/>"}))
        posicion = contenido.rfind(b"PK\x05\x06")
        struct.pack_into("<HH", contenido, posicion + 8, 5001, 5001)
        with self.assertRaises(ValidationError):
            validar_archivo_evidencia(SimpleUploadedFile("demasiadas_partes.docx", bytes(contenido)))


class AdjuntosPrivadosTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory(prefix="gesicom-adjuntos-")
        self.addCleanup(self.media.cleanup)
        self.config = override_settings(MEDIA_ROOT=self.media.name)
        self.config.enable()
        self.addCleanup(self.config.disable)
        self.user = User.objects.create_user("adjunto_autor")
        self.other = User.objects.create_user("adjunto_ajeno")
        self.client.force_login(self.user)

    def envio(self, nombre="documento.txt", contenido=b"Contenido"):
        return Envio.objects.create(
            usuario=self.user,
            nombre="Soporte privado",
            proyecto="LEM",
            tipo_evidencia="Documento",
            archivo_evidencia=SimpleUploadedFile(nombre, contenido),
        )

    def test_native_viewer_can_read_file_but_public_evidence_scope_does_not_expand(self):
        envio = self.envio()
        staff = User.objects.create_user("adjunto_personal", is_staff=True)
        staff.user_permissions.add(Permission.objects.get(content_type__app_label="Gesicom", codename="view_envio"))
        self.client.force_login(staff)
        response = self.client.get(reverse("archivo_evidencia", args=[envio.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"Contenido")
        response = self.client.get(envio.archivo_evidencia.url)
        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)
        self.assertEqual(self.client.get(reverse("ver_evidencia", args=[envio.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("admin:Gesicom_envio_change", args=[envio.pk])).status_code, 200)
        staff.user_permissions.clear()
        self.assertEqual(self.client.get(reverse("archivo_evidencia", args=[envio.pk])).status_code, 404)

    def test_staff_without_evidence_permission_cannot_open_foreign_files(self):
        envio = self.envio()
        self.other.is_staff = True
        self.other.save(update_fields=["is_staff"])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("archivo_evidencia", args=[envio.pk])).status_code, 404)
        self.assertEqual(self.client.get(envio.archivo_evidencia.url).status_code, 404)

    def test_shared_path_chooses_an_authorized_reference_instead_of_crashing(self):
        envio = self.envio()
        Envio.objects.create(
            usuario=self.user,
            nombre="Referencia compartida",
            tipo_evidencia="Documento",
            archivo_evidencia=envio.archivo_evidencia.name,
        )
        response = self.client.get(envio.archivo_evidencia.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"Contenido")

    def test_missing_file_keeps_detail_history_and_does_not_offer_broken_preview(self):
        envio = self.envio()
        Path(envio.archivo_evidencia.path).unlink()
        response = self.client.get(reverse("ver_evidencia", args=[envio.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "El adjunto no está disponible")
        self.assertFalse(response.context["archivo_disponible"])
        self.assertIsNone(response.context["archivo_url"])
        self.assertTrue(Envio.objects.filter(pk=envio.pk).exists())
        self.assertEqual(self.client.get(reverse("archivo_evidencia", args=[envio.pk])).status_code, 404)
        response = self.client.get(reverse("corregir_evidencia", args=[envio.pk]))
        self.assertContains(response, "El archivo no está disponible. Puedes sustituirlo o retirarlo.")
        self.assertNotContains(response, "Consultar adjunto")

    def test_text_preview_is_bounded_and_download_retains_all_bytes(self):
        data = ("Investigación y formación\n" * 5000).encode()
        envio = self.envio(contenido=data)
        response = self.client.get(reverse("archivo_evidencia", args=[envio.pk]), {"vista": "texto"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Preview-Truncated"], "1")
        self.assertLessEqual(len(response.content), MAX_TEXTO_VISTA)
        self.assertNotIn("�", response.content.decode())
        response = self.client.get(reverse("archivo_evidencia", args=[envio.pk]), {"descargar": "1"})
        self.assertEqual(b"".join(response.streaming_content), data)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("no-store", response["Cache-Control"])

    def test_text_preview_decodes_legacy_unicode_and_windows_text(self):
        for codec in ["utf-16", "utf-32", "cp1252"]:
            with self.subTest(codec=codec):
                envio = self.envio(contenido="Información del proyecto".encode(codec))
                response = self.client.get(reverse("archivo_evidencia", args=[envio.pk]), {"vista": "texto"})
                self.assertEqual(response.content.decode(), "Información del proyecto")
                self.assertEqual(response["X-Preview-Truncated"], "0")

    def test_mislabeled_legacy_file_is_forced_to_download(self):
        envio = self.envio("renombrado.pdf", b"<html><script>alert(1)</script></html>")
        response = self.client.get(reverse("archivo_evidencia", args=[envio.pk]))
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(response["Content-Type"], "application/octet-stream")
        b"".join(response.streaming_content)
        self.assertEqual(
            self.client.get(reverse("archivo_evidencia", args=[envio.pk]), {"vista": "texto"}).status_code, 404
        )

    def test_retired_file_is_deleted_only_after_commit_and_last_reference(self):
        envio = self.envio()
        path = Path(envio.archivo_evidencia.path)
        other = Envio.objects.create(
            usuario=self.other,
            nombre="Mismo soporte",
            tipo_evidencia="Documento",
            archivo_evidencia=envio.archivo_evidencia.name,
        )
        with self.captureOnCommitCallbacks(execute=True):
            envio.delete()
            self.assertTrue(path.exists())
        self.assertTrue(path.exists())
        with self.captureOnCommitCallbacks(execute=True):
            other.delete()
            self.assertTrue(path.exists())
        self.assertFalse(path.exists())

    def test_rollback_of_delete_preserves_the_file(self):
        envio = self.envio()
        path = Path(envio.archivo_evidencia.path)
        pk = envio.pk
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    envio.delete()
                    raise RuntimeError("Deshacer prueba")
            except RuntimeError:
                pass
        self.assertTrue(Envio.objects.filter(pk=pk).exists())
        self.assertTrue(path.exists())

    def test_deleting_user_retires_unreferenced_attachments(self):
        envio = self.envio()
        path = Path(envio.archivo_evidencia.path)
        with self.captureOnCommitCallbacks(execute=True):
            self.user.delete()
        self.assertFalse(path.exists())

    def test_more_than_one_uploaded_file_is_rejected(self):
        response = self.client.post(
            reverse("evidencia"),
            {
                "nombre": "Dos adjuntos",
                "proyecto": "LEM",
                "archivo": SimpleUploadedFile("uno.txt", b"Uno"),
                "otro": SimpleUploadedFile("dos.txt", b"Dos"),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Envio.objects.exists())
