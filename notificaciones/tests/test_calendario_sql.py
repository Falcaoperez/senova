"""La descarga iCalendar conserva el alcance con lecturas SQL acotadas."""

import datetime

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from Gesicom.models import Envio

from ..icalendar import lineas_calendario
from ..models import PlazoReporte
from ..selectors import agenda_filtrada
from .test_calendario import lineas


class CalendarioSQLTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("calendario_sql_personal")
        cls.other = User.objects.create_user("calendario_sql_otro", email="no-exportar@example.invalid")
        cls.team = Group.objects.create(name="Equipo de descarga SQL")
        cls.user.groups.add(cls.team)
        cls.ahora = datetime.datetime(2026, 11, 10, 12, tzinfo=datetime.UTC)
        cls.fecha = datetime.datetime(2026, 11, 20, 14, tzinfo=datetime.UTC)
        PlazoReporte.objects.bulk_create(
            [
                PlazoReporte(
                    titulo=f"Plazo SQL {i:04}",
                    descripcion="Información de revisión; Bogotá, prueba con saltos.\nSegunda línea.",
                    proyecto="LEM" if i % 2 else "GIVIT",
                    fecha_limite=cls.fecha + datetime.timedelta(days=i % 3),
                    creado_por=cls.other,
                )
                for i in range(1200)
            ],
            batch_size=500,
        )
        PlazoReporte.grupos.through.objects.bulk_create(
            [
                PlazoReporte.grupos.through(plazoreporte_id=pk, group_id=cls.team.pk)
                for pk in PlazoReporte.objects.values_list("pk", flat=True)
            ],
            batch_size=500,
        )

    def consulta(self, **datos):
        return agenda_filtrada(self.user, datos)

    def exportar(self, consulta=None):
        return lineas_calendario(
            self.consulta() if consulta is None else consulta, "https://gesicom.example.invalid", self.ahora
        )

    @staticmethod
    def titulos(lineas):
        return [linea.removeprefix("SUMMARY:") for linea in lineas if linea.startswith("SUMMARY:")]

    @staticmethod
    def primer_evento(generador):
        resultado = []
        for linea in generador:
            resultado.append(linea)
            if linea == "END:VEVENT":
                return resultado
        raise AssertionError("La descarga debe contener un primer evento.")

    def test_1200_plazos_con_empates_se_ordenan_con_lecturas_de_500(self):
        esperados = list(self.consulta().order_by("fecha_limite", "pk").values_list("titulo", flat=True))
        with CaptureQueriesContext(connection) as consultas:
            resultado = list(self.exportar())
        self.assertEqual(self.titulos(resultado), esperados)
        self.assertEqual(len({linea for linea in resultado if linea.startswith("UID:")}), 1200)
        self.assertEqual(len(consultas), 4)
        lecturas = [c["sql"] for c in consultas if "MAX(" not in c["sql"]]
        self.assertEqual(len(lecturas), 3)
        self.assertTrue(all("LIMIT 500" in sql and "OFFSET" not in sql for sql in lecturas))
        print("ESCALA iCalendar / 1200 plazos: 4 consultas, tres lecturas SQL de hasta 500 filas y sin OFFSET.")

    def test_solo_se_cargan_campos_del_evento_y_sus_estados_de_entrega(self):
        with CaptureQueriesContext(connection) as consultas:
            resultado = list(self.exportar())
        self.assertEqual(resultado.count("BEGIN:VEVENT"), 1200)
        for consulta in consultas:
            sql = consulta["sql"]
            seleccion = sql.split(" FROM ", 1)[0]
            for campo in ("creado_por_id", "recordatorio_horas", "version", "activo"):
                self.assertNotIn(connection.ops.quote_name(campo), seleccion)
            for campo in ("password", "email", "last_login", "observaciones", "archivo_evidencia"):
                self.assertNotIn(connection.ops.quote_name(campo), sql)

    def test_descarga_http_conserva_filtros_y_todos_los_resultados_entre_lotes(self):
        self.client.force_login(self.user)
        datos = {"mes": "2026-11", "proyecto": "LEM", "q": "Plazo SQL"}
        esperados = list(self.consulta(**datos).order_by("fecha_limite", "pk").values_list("titulo", flat=True))
        with CaptureQueriesContext(connection) as consultas:
            response = self.client.get(reverse("notificaciones:calendario_ics"), datos)
            resultado = lineas(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/calendar; charset=utf-8")
        self.assertIn("mis-plazos-2026-11.ics", response["Content-Disposition"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.titulos(resultado), esperados)
        self.assertEqual(len(esperados), 600)
        tabla = "FROM " + connection.ops.quote_name(PlazoReporte._meta.db_table)
        lecturas = [c["sql"] for c in consultas if tabla in c["sql"] and "MAX(" not in c["sql"]]
        self.assertEqual(len(lecturas), 2)
        self.assertTrue(all("LIMIT 500" in sql and "OFFSET" not in sql for sql in lecturas))

    def test_resultado_vacio_y_ultimo_lote_exacto_conservan_un_archivo_completo(self):
        with CaptureQueriesContext(connection) as consultas:
            resultado = list(self.exportar(self.consulta().filter(pk__lt=0)))
        self.assertEqual(len(consultas), 1)
        self.assertEqual(resultado[0], "BEGIN:VCALENDAR")
        self.assertEqual(resultado[-1], "END:VCALENDAR")
        self.assertNotIn("BEGIN:VEVENT", resultado)
        ids = list(self.consulta().order_by("fecha_limite", "pk").values_list("pk", flat=True)[:1000])
        consulta = self.consulta().filter(pk__in=ids)
        with CaptureQueriesContext(connection) as consultas:
            resultado = list(self.exportar(consulta))
        self.assertEqual(resultado.count("BEGIN:VEVENT"), 1000)
        self.assertEqual(len({linea for linea in resultado if linea.startswith("UID:")}), 1000)
        self.assertEqual(resultado[-1], "END:VCALENDAR")
        self.assertEqual(len(consultas), 4)
        self.assertTrue(all("LIMIT 500" in c["sql"] for c in consultas if "MAX(" not in c["sql"]))

    def test_altas_despues_del_primer_evento_no_se_anaden_a_la_descarga(self):
        esperados = list(self.consulta().order_by("fecha_limite", "pk").values_list("titulo", flat=True))
        generador = self.exportar()
        principio = self.primer_evento(generador)
        for dias in (-10, 10):
            PlazoReporte.objects.create(
                titulo=f"Alta posterior {dias}", fecha_limite=self.fecha + datetime.timedelta(days=dias)
            )
        self.assertEqual(self.titulos([*principio, *generador]), esperados)

    def test_siguientes_lotes_excluyen_plazos_eliminados_o_archivados(self):
        filas = list(self.consulta().order_by("fecha_limite", "pk").values_list("pk", "titulo"))
        generador = self.exportar()
        principio = self.primer_evento(generador)
        eliminar, archivar = filas[550][0], filas[800][0]
        PlazoReporte.objects.filter(pk=eliminar).delete()
        PlazoReporte.objects.filter(pk=archivar).update(activo=False)
        resultado = self.titulos([*principio, *generador])
        self.assertEqual(resultado, [titulo for pk, titulo in filas if pk not in {eliminar, archivar}])

    def test_retirar_el_grupo_impide_leer_los_siguientes_lotes_incluso_con_precarga(self):
        user = User.objects.prefetch_related("groups").get(pk=self.user.pk)
        consulta = agenda_filtrada(user, {})
        primeros = list(consulta.order_by("fecha_limite", "pk").values_list("titulo", flat=True)[:500])
        generador = self.exportar(consulta)
        principio = self.primer_evento(generador)
        self.team.user_set.remove(self.user)
        self.assertEqual(self.titulos([*principio, *generador]), primeros)

    def test_estados_fechas_y_revision_se_conservan_sin_consultas_por_evento(self):
        plazos = list(self.consulta().order_by("pk")[:3])
        for indice in (0, 1):
            Envio.objects.create(
                usuario=self.user,
                plazo=plazos[indice],
                registrado_en=self.fecha + datetime.timedelta(days=indice),
                limite_aplicado=self.fecha,
                proyecto=plazos[indice].proyecto,
                nombre="Entrega de revisión",
            )
        vencido = PlazoReporte.objects.create(
            titulo="Vencido de revisión",
            fecha_limite=self.ahora - datetime.timedelta(hours=1),
            revision=3,
            actualizado_en=self.ahora - datetime.timedelta(days=1),
        )
        estados = ["Entregado", "Entregado fuera de plazo", "Pendiente", "Vencido sin entrega"]
        for plazo, estado in zip([*plazos, vencido], estados, strict=True):
            with self.subTest(estado=estado):
                with CaptureQueriesContext(connection) as consultas:
                    resultado = list(self.exportar(self.consulta(plazo=plazo.pk)))
                self.assertEqual(len(consultas), 2)
                self.assertTrue(any("Estado: " + estado in linea for linea in resultado))
                self.assertIn("DTSTAMP:20261110T120000Z", resultado)
                self.assertIn("SEQUENCE:" + str(plazo.revision), resultado)
                if plazo.pk == vencido.pk:
                    self.assertIn("LAST-MODIFIED:20261109T120000Z", resultado)
