import io
import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Group, User
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from database.seguridad.perfiles import (
    CRUD,
    DDL,
    Perfil,
    generar_sql,
    identificador,
    perfiles_desde_entorno,
    plan_publico,
)
from scripts.preparar_mysql import comprobar_dedicacion
from SENNOVA.database_security import concesiones_minimas, inspeccionar_conexion
from SENNOVA.db_config import opciones_mysql

ENTORNO = {
    "DB_NAME": "centro_sena",
    "DB_USER": "app_dedicada",
    "DB_PASSWORD": "clave-exclusiva-app",
    "DB_MIGRATION_USER": "migrador_dedicado",
    "DB_MIGRATION_PASSWORD": "clave-exclusiva-migraciones",
    "DB_TEST_USER": "pruebas_dedicadas",
    "DB_TEST_PASSWORD": "clave-exclusiva-pruebas",
}
GRANT = "GRANT SELECT, INSERT, UPDATE, DELETE ON `centro\\_sena`.* TO `app_dedicada`@`%`"
USAGE = "GRANT USAGE ON *.* TO `app_dedicada`@`%`"


class PerfilesMySQLTests(SimpleTestCase):
    def test_perfiles_separan_cuentas_esquemas_y_no_publican_password(self):
        perfiles = perfiles_desde_entorno(ENTORNO, pruebas=True)
        self.assertEqual([p.permisos for p in perfiles], [CRUD, DDL, DDL])
        self.assertEqual([p.esquema for p in perfiles], ["centro_sena", "centro_sena", "test_centro_sena"])
        for clave in (ENTORNO[k] for k in ENTORNO if "PASSWORD" in k):
            self.assertNotIn(clave, repr(perfiles))
            self.assertNotIn(clave, json.dumps(plan_publico(perfiles)))

    def test_rechaza_nombres_del_sistema_inyecciones_y_nombres_que_truncan(self):
        for valor in [
            "mysql",
            "sys",
            "performance_schema",
            "information_schema",
            "x`.*",
            "x;DROP",
            "x%",
            "",
            "área",
            "x" * 65,
        ]:
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                identificador(valor)
        for valor in ["root", "x" * 33]:
            with self.assertRaises(ValueError):
                identificador(valor, cuenta=True)
        self.assertEqual(perfiles_desde_entorno({**ENTORNO, "DB_NAME": "x" * 64})[0].esquema, "x" * 64)

    def test_no_prepara_cuentas_compartidas_password_repetida_o_placeholder(self):
        for cambio in [
            {"DB_MIGRATION_USER": ENTORNO["DB_USER"].upper()},
            {"DB_MIGRATION_PASSWORD": ENTORNO["DB_PASSWORD"]},
            {"DB_TEST_USER": ENTORNO["DB_USER"]},
            {"DB_PASSWORD": "replace-password"},
            {"DB_PASSWORD": "con\nsalto"},
            {"DB_PASSWORD": ""},
            {"DB_NAME": "x" * 60},
        ]:
            with self.subTest(cambio=list(cambio)), self.assertRaises(ValueError):
                perfiles_desde_entorno({**ENTORNO, **cambio}, pruebas=True)

    def test_sql_acota_privilegios_fija_tls_y_escapa_password_y_comodines(self):
        perfiles = perfiles_desde_entorno({**ENTORNO, "DB_PASSWORD": "privada'\\fin"}, pruebas=True)
        sql = generar_sql(perfiles)
        self.assertTrue(sql.startswith("SET SESSION sql_mode='NO_BACKSLASH_ESCAPES';"))
        self.assertIn("IDENTIFIED BY 'privada''\\fin' REQUIRE SSL", sql)
        self.assertIn("IF(@@GLOBAL.partial_revokes, '`centro_sena`.*', '`centro\\_sena`.*')", sql)
        self.assertIn("'`test\\_centro\\_sena`.*'", sql)
        self.assertNotIn("GRANT ALL", sql)
        self.assertNotIn("WITH GRANT OPTION", sql)
        self.assertNotIn(" ON *.*", sql)
        self.assertNotIn("FLUSH PRIVILEGES", sql)

    def test_generador_no_acepta_permisos_administrativos_inyectados(self):
        with self.assertRaises(ValueError):
            generar_sql([Perfil("operador", "centro", ("CREATE USER",), "privada")])

    @patch("scripts.preparar_mysql.ejecutar_sql")
    def test_preflight_rechaza_roles_globales_otros_hosts_y_esquemas_sin_escribir(self, ejecutar):
        perfiles = perfiles_desde_entorno(ENTORNO)
        for campo in [
            "globales",
            "roles",
            "roles_obligatorios",
            "proxy",
            "otros_hosts",
            "otros_esquemas",
            "otras_tablas",
            "otras_columnas",
        ]:
            ejecutar.reset_mock()
            ejecutar.return_value = json.dumps({campo: 1, "existe": 1})
            with self.subTest(campo=campo), self.assertRaises(ValueError):
                comprobar_dedicacion(perfiles, "mysql-local")
            self.assertEqual(ejecutar.call_count, 1)
            consulta = ejecutar.call_args.args[0]
            self.assertNotIn("ALTER USER", consulta)
            self.assertNotIn("REVOKE", consulta)


class ConexionMySQLTests(SimpleTestCase):
    def opciones(self, valores=None):
        valores = valores or {}
        return opciones_mysql(lambda clave, default=None: valores.get(clave, default))

    def test_exige_tls_y_deshabilita_cargas_y_sentencias_encadenadas(self):
        opciones = self.opciones()
        self.assertEqual(opciones["ssl_mode"], "REQUIRED")
        self.assertIs(opciones["local_infile"], False)
        self.assertIs(opciones["multi_statements"], False)

    def test_rechaza_tls_opcional_o_verificacion_sin_ca(self):
        for modo in ["DISABLED", "PREFERRED", "", "VERIFY_CA", "VERIFY_IDENTITY"]:
            with self.subTest(modo=modo), self.assertRaises(ImproperlyConfigured):
                self.opciones({"DB_SSL_MODE": modo})

    def test_ca_debe_existir_y_se_configura_sin_rebajar_modo(self):
        with TemporaryDirectory() as carpeta:
            path = Path(carpeta, "ca.pem")
            valores = {"DB_SSL_MODE": "VERIFY_IDENTITY", "DB_SSL_CA": str(path), "DB_HOST": "db.example.invalid"}
            with self.assertRaises(ImproperlyConfigured):
                self.opciones(valores)
            path.write_text("certificado-de-prueba")
            opciones = self.opciones(valores)
            self.assertEqual(opciones["ssl_mode"], "VERIFY_IDENTITY")
            self.assertEqual(opciones["ssl"], {"ca": str(path)})

    def test_identidad_rechaza_ip_incluso_abreviada_y_socket_local(self):
        with TemporaryDirectory() as carpeta:
            ca = Path(carpeta, "ca.pem")
            ca.write_text("certificado-de-prueba")
            for host in [
                "",
                "localhost",
                "LOCALHOST",
                "127.0.0.1",
                "::1",
                "[::1]",
                "127.1",
                "2130706433",
                "0x7f000001",
            ]:
                with self.subTest(host=host), self.assertRaises(ImproperlyConfigured):
                    self.opciones({"DB_SSL_MODE": "VERIFY_IDENTITY", "DB_SSL_CA": str(ca), "DB_HOST": host})


class DiagnosticoMySQLTests(SimpleTestCase):
    def conexion(self):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            ("app_dedicada@%", "centro_sena", 1, "STRICT_TRANS_TABLES", "InnoDB", 0, "NONE", "", 0),
            ("Ssl_cipher", "TLS_AES_256_GCM_SHA384"),
            (0,),
        ]
        cursor.fetchall.return_value = [(USAGE,), (GRANT,)]
        contexto = MagicMock()
        contexto.__enter__.return_value = cursor
        db = SimpleNamespace(
            vendor="mysql",
            cursor=lambda: contexto,
            connection=SimpleNamespace(client_flag=0),
            settings_dict={"USER": "app_dedicada", "OPTIONS": {"ssl_mode": "REQUIRED"}},
        )
        return db, cursor

    def test_acepta_crud_exacto_con_uso_global_sin_permisos(self):
        self.assertTrue(concesiones_minimas([USAGE, GRANT], "centro_sena"))
        self.assertTrue(concesiones_minimas([GRANT.replace("\\_", "_")], "centro_sena", partial_revokes=True))

    def test_rechaza_comodines_roles_concesiones_globales_tablas_y_grant_option(self):
        for concesion in [
            GRANT.replace("\\_", "_"),
            GRANT.replace("centro\\_sena", "otro"),
            GRANT.replace("`centro\\_sena`.*", "*.*"),
            GRANT.replace("`centro\\_sena`.*", "`centro\\_sena`.`tabla`"),
            GRANT.replace("SELECT, INSERT, UPDATE, DELETE", "ALL PRIVILEGES"),
            GRANT + " WITH GRANT OPTION",
            "GRANT `rol`@`%` TO `app_dedicada`@`%`",
        ]:
            with self.subTest(concesion=concesion):
                self.assertFalse(concesiones_minimas([GRANT, concesion], "centro_sena"))
        self.assertFalse(concesiones_minimas([USAGE], "centro_sena"))
        self.assertFalse(concesiones_minimas([GRANT], None))
        self.assertFalse(concesiones_minimas([GRANT], ""))

    def test_diagnostico_usa_metadatos_y_no_devuelve_sql_usuarios_ni_esquemas(self):
        db, cursor = self.conexion()
        informe = inspeccionar_conexion(db)
        self.assertTrue(informe["correcto"])
        self.assertEqual(len(informe["controles"]), 4)
        for consulta in cursor.execute.call_args_list:
            self.assertTrue(consulta.args[0].startswith(("SELECT ", "SHOW ")))
        salida = json.dumps(informe)
        for secreto in ["app_dedicada", "centro_sena", "GRANT", "TLS_AES"]:
            self.assertNotIn(secreto, salida)
        self.assertIn("no verifica la identidad", salida)

    def test_roles_activos_obligatorios_y_cuenta_distinta_requieren_revision(self):
        for indice, valor in [(0, "otra@%"), (6, "rol@%"), (7, "rol_obligatorio@%")]:
            db, cursor = self.conexion()
            datos = ["app_dedicada@%", "centro_sena", 1, "STRICT_TRANS_TABLES", "InnoDB", 0, "NONE", "", 0]
            datos[indice] = valor
            cursor.fetchone.side_effect = [tuple(datos), ("Ssl_cipher", "TLS_AES"), (0,)]
            informe = inspeccionar_conexion(db)
            self.assertEqual(informe["estado"], "revisar")
            self.assertFalse(informe["controles"][0]["correcto"])

    def test_sin_tls_cargas_habilitadas_o_integridad_rebajada_no_aprueba(self):
        from MySQLdb.constants import CLIENT

        for tipo in ["tls", "multi", "local", "servidor_local", "fk", "modo", "motor", "tablas"]:
            db, cursor = self.conexion()
            datos = ["app_dedicada@%", "centro_sena", 1, "STRICT_TRANS_TABLES", "InnoDB", 0, "NONE", "", 0]
            if tipo in {"fk", "modo", "motor", "servidor_local"}:
                indice, valor = {"fk": (2, 0), "modo": (3, ""), "motor": (4, "MyISAM"), "servidor_local": (8, 1)}[tipo]
                datos[indice] = valor
            if tipo in {"multi", "local"}:
                db.connection.client_flag = CLIENT.MULTI_STATEMENTS if tipo == "multi" else CLIENT.LOCAL_FILES
            cursor.fetchone.side_effect = [
                tuple(datos),
                ("Ssl_cipher", "" if tipo == "tls" else "TLS_AES"),
                (1 if tipo == "tablas" else 0,),
            ]
            with self.subTest(tipo=tipo):
                self.assertEqual(inspeccionar_conexion(db)["estado"], "revisar")

    def test_error_mysql_no_expone_detalle_y_otro_motor_no_se_consulta(self):
        db, _ = self.conexion()
        db.cursor = MagicMock(side_effect=OperationalError("host y credencial privados"))
        self.assertEqual(inspeccionar_conexion(db)["estado"], "no_disponible")
        db.vendor = "sqlite"
        db.cursor.reset_mock()
        self.assertEqual(inspeccionar_conexion(db)["estado"], "no_disponible")
        db.cursor.assert_not_called()

    @patch("ADMIN.management.commands.comprobar_base_datos.inspeccionar_conexion")
    def test_comando_json_y_modo_estricto_se_detienen_si_falta_verificacion(self, inspeccionar):
        inspeccionar.return_value = {"estado": "no_disponible", "correcto": False, "controles": []}
        salida = io.StringIO()
        with self.assertRaises(CommandError):
            call_command("comprobar_base_datos", "--estricto", "--json", stdout=salida)
        self.assertEqual(json.loads(salida.getvalue()), inspeccionar.return_value)
        inspeccionar.return_value = {"estado": "correcto", "correcto": True, "controles": []}
        call_command("comprobar_base_datos", "--estricto", stdout=io.StringIO())


@patch("ADMIN.views.inspeccionar_conexion")
class PantallaBaseDatosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("sql_administrador")
        cls.admin.groups.add(Group.objects.get_or_create(name="administrador")[0])
        cls.root = User.objects.create_superuser("sql_super", "sql@example.invalid", "clave-exclusiva-pruebas")
        cls.staff = User.objects.create_user("sql_personal", is_staff=True)
        cls.usuario = User.objects.create_user("sql_usuario")
        cls.url = reverse("admin_personalizado:base_datos")

    def informe(self):
        return {
            "estado": "correcto",
            "correcto": True,
            "controles": [
                {
                    "codigo": "permisos",
                    "titulo": "Permisos de ejecución",
                    "detalle": "Solo registros.",
                    "correcto": True,
                }
            ],
        }

    def test_anonymous_staff_y_usuario_sin_rol_no_consultan_metadatos(self, inspeccionar):
        for usuario in [None, self.staff, self.usuario]:
            if usuario:
                self.client.force_login(usuario)
            response = self.client.get(self.url)
            self.assertIn(response.status_code, [302, 403])
            inspeccionar.assert_not_called()

    def test_admin_y_superuser_consultan_estado_sin_cache(self, inspeccionar):
        inspeccionar.return_value = self.informe()
        for usuario in [self.admin, self.root]:
            self.client.force_login(usuario)
            response = self.client.get(self.url)
            self.assertContains(response, "Controles comprobados")
            self.assertContains(response, "Volver a comprobar")
            self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(inspeccionar.call_count, 2)

    def test_ningun_post_puede_alterar_los_perfiles(self, inspeccionar):
        self.client.force_login(self.root)
        self.assertEqual(self.client.post(self.url, {"grant": "ALL"}).status_code, 405)
        inspeccionar.assert_not_called()

    def test_revisar_y_no_disponible_no_se_presentan_como_correctos(self, inspeccionar):
        self.client.force_login(self.admin)
        informe = deepcopy(self.informe())
        informe.update(estado="revisar", correcto=False)
        informe["controles"][0]["correcto"] = False
        inspeccionar.return_value = informe
        self.assertContains(self.client.get(self.url), "Hay controles por revisar")
        inspeccionar.return_value = {"estado": "no_disponible", "correcto": False, "controles": []}
        self.assertContains(self.client.get(self.url), "No se pudo completar la consulta")

    def test_consulta_parcial_conserva_estado_y_acceso_desde_permisos(self, inspeccionar):
        self.client.force_login(self.admin)
        inspeccionar.return_value = self.informe()
        response = self.client.get(self.url, HTTP_X_WORKSPACE_FRAGMENT="1")
        self.assertContains(response, "Permisos de ejecución")
        self.assertEqual(response["X-Workspace-Fragment"], "1")
        self.assertNotContains(response, "<!DOCTYPE html>")
        self.assertContains(self.client.get(reverse("admin_personalizado:permisos")), self.url)
