"""La preparación local conserva secretos y limita el inicio rápido a SQLite."""

import contextlib
import io
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from scripts import configurar_entorno


class EntornoDesarrolloTests(SimpleTestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory(prefix="gesicom con espacios ")
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)

    def test_una_configuracion_existente_se_conserva_exactamente(self):
        archivo = self.raiz / ".env"
        contenido = b'# Privado\nDB_ENGINE=mysql\nDB_PASSWORD="clave de prueba con espacios"\n'
        archivo.write_bytes(contenido)
        self.assertFalse(configurar_entorno.crear_configuracion_local(self.raiz))
        self.assertEqual(archivo.read_bytes(), contenido)

    def test_la_configuracion_nueva_tiene_secreto_propio_y_correo_solo_local(self):
        self.assertTrue(configurar_entorno.crear_configuracion_local(self.raiz))
        archivo = self.raiz / ".env"
        valores = dict(linea.split("=", 1) for linea in archivo.read_text().splitlines() if "=" in linea)
        self.assertEqual(valores["DB_ENGINE"], "sqlite")
        self.assertEqual(valores["REDIS_URL"], "")
        self.assertEqual(valores["EMAIL_BACKEND"], "django.core.mail.backends.console.EmailBackend")
        self.assertGreaterEqual(len(valores["DJANGO_SECRET_KEY"]), 40)
        otra = self.raiz / "otra copia"
        otra.mkdir()
        configurar_entorno.crear_configuracion_local(otra)
        self.assertNotEqual(archivo.read_text(), (otra / ".env").read_text())
        if os.name != "nt":
            self.assertEqual(archivo.stat().st_mode & 0o777, 0o600)

    @patch("scripts.configurar_entorno.ejecutar")
    @patch("scripts.configurar_entorno.crear_entorno")
    def test_preparar_un_proyecto_existente_no_migra_ni_crea_cuentas(self, crear, ejecutar):
        archivo = self.raiz / ".env"
        contenido = "DB_ENGINE=mysql\nDJANGO_DEBUG=False\n"
        archivo.write_text(contenido)
        crear.return_value = self.raiz / ".venv" / "bin" / "python"
        with contextlib.redirect_stdout(io.StringIO()):
            configurar_entorno.preparar(self.raiz, inicio_rapido=True)
        self.assertEqual(archivo.read_text(), contenido)
        self.assertEqual(ejecutar.call_count, 2)
        instalar, comprobar = [llamada.args[0] for llamada in ejecutar.call_args_list]
        self.assertIn("--require-virtualenv", instalar)
        self.assertIn(self.raiz / "requirements-dev.txt", instalar)
        self.assertEqual(comprobar[-1], "check")
        self.assertNotIn(self.raiz / "manage.py", comprobar)

    @patch("scripts.configurar_entorno.ejecutar")
    @patch("scripts.configurar_entorno.crear_entorno")
    def test_el_inicio_nuevo_no_usa_conexiones_heredadas_del_proceso(self, crear, ejecutar):
        crear.return_value = self.raiz / ".venv" / "bin" / "python"
        heredadas = {
            "DB_ENGINE": "mysql",
            "REDIS_URL": "redis://servidor.example.invalid:6379/0",
            "EMAIL_BACKEND": "SENNOVA.email_backend.SMTPBackend",
            "DJANGO_SETTINGS_MODULE": "configuracion_externa",
        }
        with patch.dict(os.environ, heredadas), contextlib.redirect_stdout(io.StringIO()):
            configurar_entorno.preparar(self.raiz, inicio_rapido=True)
            self.assertEqual(os.environ["DB_ENGINE"], "mysql")
        comandos = [c for c in ejecutar.call_args_list if self.raiz / "manage.py" in c.args[0]]
        self.assertEqual(len(comandos), 4)
        for llamada in comandos:
            entorno = llamada.kwargs["entorno"]
            self.assertEqual(entorno["DB_ENGINE"], "sqlite")
            self.assertEqual(entorno["REDIS_URL"], "")
            self.assertEqual(entorno["EMAIL_BACKEND"], "django.core.mail.backends.console.EmailBackend")
            self.assertEqual(entorno["DJANGO_SETTINGS_MODULE"], "SENNOVA.settings")
            self.assertEqual(llamada.args[1], self.raiz)
        self.assertTrue(any("crear_usuarios_revision" in c.args[0] for c in comandos))

    def test_un_directorio_incompleto_no_se_borra_ni_se_reemplaza(self):
        carpeta = self.raiz / ".venv"
        carpeta.mkdir()
        marcador = carpeta / "conservar.txt"
        marcador.write_text("Datos previos")
        with self.assertRaisesRegex(RuntimeError, "incompleto"):
            configurar_entorno.crear_entorno(self.raiz)
        self.assertEqual(marcador.read_text(), "Datos previos")

    def preparar_estructura(self):
        carpeta = self.raiz / ".venv"
        python = configurar_entorno.python_del_entorno(self.raiz)
        python.parent.mkdir(parents=True)
        python.touch()
        (carpeta / "pyvenv.cfg").write_text("version = 3.12.0\n")
        return carpeta, python

    @patch("scripts.configurar_entorno.subprocess.check_output")
    def test_no_se_instalan_paquetes_en_un_python_global_o_de_otra_version(self, salida):
        carpeta, _ = self.preparar_estructura()
        for version, prefix, base in [
            ([3, 11], str(carpeta), "/python-base"),
            ([3, 12], "/python-global", "/python-global"),
        ]:
            with self.subTest(version=version, prefix=prefix):
                salida.return_value = json.dumps({"version": version, "prefix": prefix, "base": base})
                with self.assertRaisesRegex(RuntimeError, "aislado"):
                    configurar_entorno.crear_entorno(self.raiz)

    @patch("scripts.configurar_entorno.venv.EnvBuilder")
    @patch("scripts.configurar_entorno.subprocess.check_output")
    def test_un_entorno_aislado_existente_se_reutiliza(self, salida, builder):
        carpeta, python = self.preparar_estructura()
        salida.return_value = json.dumps({"version": [3, 12], "prefix": str(carpeta), "base": "/python-base"})
        self.assertEqual(configurar_entorno.crear_entorno(self.raiz), python)
        builder.assert_not_called()

    @patch("scripts.configurar_entorno.preparar")
    def test_otra_version_falla_antes_de_crear_archivos_o_instalar(self, preparar):
        with (
            patch("scripts.configurar_entorno.sys.version_info", (3, 11, 0)),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(configurar_entorno.main([]), 2)
        preparar.assert_not_called()
