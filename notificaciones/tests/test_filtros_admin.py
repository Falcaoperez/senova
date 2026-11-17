"""Filtros administrativos y exportación acotada del seguimiento de plazos."""

import csv
import datetime
import io
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import Group, Permission, User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from Gesicom.models import Envio

from ..models import PlazoReporte
from ..selectors import seguimiento_filtrado


def filas(response):
    contenido = b"".join(response.streaming_content) if response.streaming else response.content
    return list(csv.reader(io.StringIO(contenido.decode("utf-8-sig"))))


class FiltrosAdministracionPlazosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("plazos_operador", password="PruebaPlazosLocal42!")
        cls.admin.groups.add(Group.objects.get(name="administrador"))
        cls.grupo = Group.objects.get(name="instructor")
        cls.usuarios = [
            User.objects.create_user(f"reporte_seguro_{i}", email=f"seguro{i}@example.invalid") for i in range(3)
        ]
        for usuario in cls.usuarios:
            usuario.groups.add(cls.grupo)
        cls.inactivo = User.objects.create_user("reporte_inactivo", is_active=False)
        cls.inactivo.groups.add(cls.grupo)
        cls.ajeno = User.objects.create_user("reporte_ajeno")
        ahora = timezone.now()
        cls.plazo = PlazoReporte.objects.create(
            titulo="Entrega segura", proyecto="LEM", fecha_limite=ahora + datetime.timedelta(days=2)
        )
        cls.plazo.grupos.add(cls.grupo)
        cls.vencido = PlazoReporte.objects.create(
            titulo="Entrega vencida", proyecto="LEM", fecha_limite=ahora - datetime.timedelta(days=1)
        )
        cls.archivado = PlazoReporte.objects.create(
            titulo="Entrega archivada", proyecto="GIVIT", activo=False, fecha_limite=ahora - datetime.timedelta(days=1)
        )
        cls.sin_proyecto = PlazoReporte.objects.create(
            titulo="Entrega transversal", fecha_limite=ahora + datetime.timedelta(days=1)
        )
        cls.puntual = Envio.objects.create(
            usuario=cls.usuarios[0],
            plazo=cls.plazo,
            nombre="Puntual",
            limite_aplicado=ahora + datetime.timedelta(hours=1),
        )
        Envio.objects.create(
            usuario=cls.usuarios[1],
            plazo=cls.plazo,
            nombre="Tardía",
            limite_aplicado=ahora - datetime.timedelta(hours=1),
        )
        Envio.objects.create(usuario=cls.ajeno, plazo=cls.plazo, nombre="Ajena")
        cls.lista = reverse("notificaciones:plazos_admin")
        cls.seguimiento = reverse("notificaciones:seguimiento_plazo", args=[cls.plazo.pk])
        cls.csv = reverse("notificaciones:seguimiento_csv", args=[cls.plazo.pk])

    def setUp(self):
        self.client.force_login(self.admin)

    def test_estado_desconocido_no_exporta_todos_los_destinatarios(self):
        response = self.client.get(self.csv, {"estado": "estado-inexistente"})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response["Content-Type"].startswith("text/html"))
        self.assertNotContains(response, self.usuarios[0].email, status_code=400)

    def test_estado_desconocido_no_amplia_la_lista(self):
        response = self.client.get(self.seguimiento, {"estado": "estado-inexistente"})
        self.assertEqual(response.context["destinatarios"].paginator.count, 0)
        self.assertIsNone(response.context["url_exportar"])
        self.assertContains(response, "Revisa los filtros")

    def test_filtros_invalidos_del_listado_no_muestran_plazos(self):
        for params in [
            {"estado": "otro"},
            {"proyecto": "inexistente"},
            {"q": "Entrega" + "x" * 100},
            {"q": "Entrega\0"},
        ]:
            response = self.client.get(self.lista, params)
            self.assertEqual(response.context["plazos"].paginator.count, 0)
            self.assertContains(response, "Revisa los filtros")

    def test_opcion_sin_proyecto_distingue_de_todos_los_proyectos(self):
        response = self.client.get(self.lista, {"proyecto": "sin_proyecto"})
        self.assertEqual([p.pk for p in response.context["plazos"]], [self.sin_proyecto.pk])
        self.assertContains(response, "Sin proyecto específico")
        self.assertEqual(self.client.get(self.lista).context["plazos"].paginator.count, 4)

    def test_estados_del_listado_conservan_el_alcance(self):
        for estado, esperado in [
            ("programado", {self.plazo.pk, self.sin_proyecto.pk}),
            ("vencido", {self.vencido.pk}),
            ("archivado", {self.archivado.pk}),
        ]:
            response = self.client.get(self.lista, {"estado": estado})
            self.assertSetEqual({p.pk for p in response.context["plazos"]}, esperado)
        self.assertEqual(
            self.client.get(self.lista, {"q": "  segura  ", "proyecto": "LEM"}).context["plazos"].paginator.count, 1
        )

    def test_lista_y_csv_comparten_busqueda_y_estado(self):
        esperados = {
            "": self.usuarios,
            "pendiente": self.usuarios[2:],
            "entregado": self.usuarios[:2],
            "a_tiempo": self.usuarios[:1],
            "tardia": self.usuarios[1:2],
        }
        for estado, usuarios in esperados.items():
            params = {"q": "  reporte_seguro_  ", "estado": estado}
            pagina = self.client.get(self.seguimiento, params)
            datos = filas(self.client.get(self.csv, params))
            self.assertSetEqual({p.pk for p in pagina.context["destinatarios"]}, {u.pk for u in usuarios})
            self.assertSetEqual({fila[0] for fila in datos[1:]}, {u.username for u in usuarios})
            self.assertEqual(len(datos[0]), 6)

    def test_invalidos_no_generan_archivo_y_ocultan_la_descarga(self):
        for params in [{"q": "reporte" + "x" * 100}, {"q": "reporte\0"}]:
            self.assertEqual(self.client.get(self.csv, params).status_code, 400)
            self.assertIsNone(self.client.get(self.seguimiento, params).context["url_exportar"])

    def test_parametros_ajenos_no_se_copian_al_enlace_de_descarga(self):
        response = self.client.get(
            self.seguimiento,
            {
                "q": "reporte_seguro",
                "estado": "pendiente",
                "page": "2",
                "next": "https://example.invalid",
                "password": "dato-ajeno",
            },
        )
        self.assertEqual(
            parse_qs(urlsplit(response.context["url_exportar"]).query),
            {"q": ["reporte_seguro"], "estado": ["pendiente"]},
        )
        self.assertContains(response, "Exportar resultados CSV", count=1)

    def test_respuesta_parcial_conserva_errores_y_enlace_actualizado(self):
        response = self.client.get(self.seguimiento, {"estado": "otro"}, HTTP_X_WORKSPACE_FRAGMENT="1")
        self.assertEqual(response["X-Workspace-Fragment"], "1")
        self.assertContains(response, "Revisa los filtros")
        self.assertNotContains(response, "Exportar resultados CSV")
        response = self.client.get(self.seguimiento, {"estado": "pendiente"}, HTTP_X_WORKSPACE_FRAGMENT="1")
        self.assertIn("estado=pendiente", response.context["url_exportar"])

    def test_metodos_de_lectura_y_permisos_por_rol(self):
        for url in [self.lista, self.seguimiento, self.csv]:
            self.assertEqual(self.client.head(url).status_code, 200)
            self.assertEqual(self.client.post(url).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get(self.csv).status_code, 302)
        for rol in ["usuario", "instructor", "investigador", "coordinador", "dinamizador"]:
            self.ajeno.groups.set([Group.objects.get(name=rol)])
            self.client.force_login(self.ajeno)
            self.assertEqual(self.client.get(self.csv).status_code, 403)
        self.ajeno.is_staff = True
        self.ajeno.save(update_fields=["is_staff"])
        self.ajeno.user_permissions.add(Permission.objects.get(codename="view_user", content_type__app_label="auth"))
        self.assertEqual(self.client.get(self.csv).status_code, 403)
        self.ajeno.is_superuser = True
        self.ajeno.save(update_fields=["is_superuser"])
        self.assertEqual(self.client.get(self.csv).status_code, 200)

    def test_retirar_rol_bloquea_la_siguiente_descarga(self):
        self.admin.groups.clear()
        self.assertEqual(self.client.get(self.csv).status_code, 403)

    def test_consulta_no_carga_hashes_ni_genera_lecturas_por_persona(self):
        with CaptureQueriesContext(connection) as consultas:
            usuarios = list(seguimiento_filtrado(self.plazo, {}))
            for usuario in usuarios:
                usuario.get_full_name()
                usuario.email
                usuario.ultima_entrega
        self.assertEqual(len(consultas), 1)
        self.assertTrue(all("password" in usuario.get_deferred_fields() for usuario in usuarios))
        self.assertTrue(all(connection.ops.quote_name("password") not in c["sql"] for c in consultas))

    def test_fecha_del_csv_es_colombia_con_otra_zona_activada(self):
        Envio.objects.filter(pk=self.puntual.pk).update(
            registrado_en=datetime.datetime(2026, 11, 14, 4, 59, tzinfo=datetime.UTC)
        )
        with timezone.override("Asia/Tokyo"):
            datos = filas(self.client.get(self.csv, {"q": self.usuarios[0].username}))
        self.assertEqual(datos[1][4], "2026-11-13 23:59:00")

    def test_csv_conserva_unicode_y_neutraliza_formulas(self):
        usuario = User.objects.create_user("=reporte_formula", first_name="+Luz", last_name='Gómez, "Ana"')
        usuario.groups.add(self.grupo)
        response = self.client.get(self.csv, {"q": "reporte_formula"})
        self.assertIn("no-store", response["Cache-Control"])
        datos = filas(response)
        self.assertEqual(datos[1][0], "'=reporte_formula")
        self.assertEqual(datos[1][1], '\'+Luz Gómez, "Ana"')

    def test_csv_vacio_y_comillas_sql_como_datos(self):
        self.assertEqual(len(filas(self.client.get(self.csv, {"q": "' OR 1=1 --"}))), 1)


class EscalaExportacionSeguimientoTests(TestCase):
    def test_lotes_sql_limites_y_altas_posteriores_al_corte(self):
        from ..exportaciones import filas_seguimiento

        grupo = Group.objects.get(name="instructor")
        plazo = PlazoReporte.objects.create(titulo="Exportación de escala", fecha_limite=timezone.now())
        plazo.grupos.add(grupo)
        User.objects.bulk_create([User(username=f"escala_plazos_{1200 - i:04}", password="!") for i in range(1200)])
        usuarios = list(User.objects.filter(username__startswith="escala_plazos_").order_by("pk"))
        User.groups.through.objects.bulk_create(
            [User.groups.through(user_id=u.pk, group_id=grupo.pk) for u in usuarios]
        )
        with CaptureQueriesContext(connection) as iniciales:
            generador = filas_seguimiento(seguimiento_filtrado(plazo, {"q": "escala_plazos_"}))
            next(generador)
            primera = next(generador)
        nuevo = User.objects.create_user("escala_plazos_nuevo")
        nuevo.groups.add(grupo)
        User.objects.filter(pk=usuarios[0].pk).update(username="escala_plazos_zz_renombrado")
        with CaptureQueriesContext(connection) as restantes:
            datos = [primera, *generador]
        consultas = [*iniciales, *restantes]
        self.assertEqual([fila[0] for fila in datos], [u.username for u in usuarios])
        self.assertEqual(len(datos), 1200)
        self.assertEqual(len(consultas), 4)
        lecturas = [
            c["sql"]
            for c in consultas
            if "FROM " + connection.ops.quote_name("auth_user") in c["sql"] and "MAX(" not in c["sql"]
        ]
        self.assertEqual(len(lecturas), 3)
        self.assertTrue(all("LIMIT 500" in sql and "OFFSET" not in sql for sql in lecturas))
        self.assertTrue(all(connection.ops.quote_name("password") not in c["sql"] for c in consultas))
        print("ESCALA CSV seguimiento / 1200 destinatarios: 4 consultas, lotes SQL de 500 y sin OFFSET ni hashes.")
