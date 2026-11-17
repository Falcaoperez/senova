"""Los CSV conservan su orden y permisos con lecturas SQL de tamaño limitado."""

import datetime
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from notificaciones.models import PlazoReporte

from ..models import Envio
from ..reportes import filas_evidencias
from ..selectors import _filtros


class CSVReportesSQLTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("csv_orden_personal", email="privado@example.invalid")
        cls.other = User.objects.create_user("csv_orden_ajeno")
        cls.instante = datetime.datetime(2026, 11, 18, 4, 59, 59, tzinfo=datetime.UTC)
        cls.plazo = PlazoReporte.objects.create(
            titulo="Límite de revisión", descripcion="No cargar esta descripción" * 100, fecha_limite=cls.instante
        )
        Envio.objects.bulk_create(
            [
                Envio(
                    usuario=cls.user,
                    nombre=["Árbol", "arbol", "ÁRBOL"][i % 3] if i < 900 else f"Informe {i:04}",
                    proyecto=["LEM", "GIVIT", ""][i % 3],
                    tipo_evidencia="Documento" if i < 900 else "Informe Final",
                    fecha_envio=datetime.date(2026, 11, 17) + datetime.timedelta(days=i % 2),
                    registrado_en=cls.instante,
                    limite_aplicado=cls.instante - datetime.timedelta(seconds=1),
                    plazo=cls.plazo if i % 2 else None,
                    link_evidencia=f"https://example.invalid/csv/{i:04}",
                )
                for i in range(1200)
            ],
            batch_size=500,
        )

    def solicitud(self, datos=None):
        request = RequestFactory().get("/reportes/csv/", datos or {})
        request.user = self.user
        self.assertTrue(_filtros(request).is_valid())
        return request

    def test_lecturas_sql_acotadas_respetan_los_ocho_ordenes_con_empates(self):
        for campo in ("fecha_envio", "nombre", "proyecto", "tipo_evidencia"):
            for direccion in ("asc", "desc"):
                with self.subTest(campo=campo, direccion=direccion):
                    request = self.solicitud({"order": campo, "dir": direccion})
                    prefijo = "" if direccion == "asc" else "-"
                    esperados = list(
                        Envio.objects.filter(usuario=self.user)
                        .order_by(prefijo + campo, prefijo + "pk")
                        .values_list("link_evidencia", flat=True)
                    )
                    with CaptureQueriesContext(connection) as consultas:
                        filas = list(filas_evidencias(request))
                    self.assertEqual([f[4] for f in filas[1:]], esperados)
                    self.assertEqual(len(consultas), 4)
                    lecturas = [c["sql"] for c in consultas if "MAX(" not in c["sql"]]
                    self.assertEqual(len(lecturas), 3)
                    self.assertTrue(all("LIMIT 500" in sql and "OFFSET" not in sql for sql in lecturas))
        print("ESCALA CSV reportes / 1200 evidencias: 4 consultas, ocho órdenes y lotes SQL de 500.")

    def test_sql_no_carga_credenciales_ni_campos_ajenos_al_archivo(self):
        request = self.solicitud()
        with CaptureQueriesContext(connection) as consultas:
            filas = list(filas_evidencias(request))
        self.assertEqual(len(filas), 1201)
        for consulta in consultas:
            for campo in ("password", "email", "last_login", "is_superuser", "descripcion", "archivo_evidencia"):
                self.assertNotIn(connection.ops.quote_name(campo), consulta["sql"])

    def test_altas_posteriores_al_corte_no_se_incluyen_aunque_cambien_de_posicion(self):
        request = self.solicitud({"order": "nombre", "dir": "asc"})
        esperados = list(
            Envio.objects.filter(usuario=self.user).order_by("nombre", "pk").values_list("link_evidencia", flat=True)
        )
        generador = filas_evidencias(request)
        next(generador)
        primera = next(generador)
        for nombre in ("000 antes", "ZZZ después"):
            Envio.objects.create(usuario=self.user, nombre=nombre, tipo_evidencia="Documento")
        self.assertEqual([f[4] for f in [primera, *generador]], esperados)

    def test_eliminar_una_fila_pendiente_no_salta_otras_filas(self):
        request = self.solicitud({"order": "nombre", "dir": "desc"})
        esperados = list(
            Envio.objects.filter(usuario=self.user).order_by("-nombre", "-pk").values_list("pk", "link_evidencia")
        )
        generador = filas_evidencias(request)
        next(generador)
        primera = next(generador)
        eliminado, _ = esperados[700]
        Envio.objects.filter(pk=eliminado).delete()
        self.assertEqual([f[4] for f in [primera, *generador]], [link for pk, link in esperados if pk != eliminado])

    def test_filtros_personales_no_incluyen_evidencias_de_otras_cuentas(self):
        Envio.objects.create(usuario=self.other, nombre="Árbol privado", proyecto="LEM", tipo_evidencia="Documento")
        request = self.solicitud({"proyecto": "LEM", "q": "rbol", "estado": "pendiente", "order": "nombre"})
        filas = list(filas_evidencias(request))
        esperados = Envio.objects.filter(usuario=self.user, proyecto="LEM", nombre__icontains="rbol").count()
        self.assertEqual(len(filas), esperados + 1)
        self.assertNotIn("Árbol privado", [f[1] for f in filas[1:]])
        self.assertEqual(list(filas_evidencias(self.solicitud({"usuario": self.other.pk})))[1:], [])

    def test_columnas_de_colombia_no_dependen_del_huso_activo(self):
        request = self.solicitud({"plazo": self.plazo.pk})
        with timezone.override(ZoneInfo("Asia/Tokyo")):
            filas = list(filas_evidencias(request))
        self.assertEqual(len(filas), 601)
        self.assertTrue(all(f[8] == "2026-11-17 23:59:59" and f[10] == "2026-11-17 23:59:58" for f in filas[1:]))
        self.assertTrue(all(f[9] == self.plazo.titulo and f[11] == "Sí" for f in filas[1:]))

    def test_resultado_vacio_y_ultima_pagina_exacta_no_pierden_filas(self):
        self.assertEqual(len(list(filas_evidencias(self.solicitud({"q": "sin coincidencias"})))), 1)
        conservar = list(Envio.objects.filter(usuario=self.user).order_by("pk").values_list("pk", flat=True)[:1000])
        Envio.objects.filter(usuario=self.user).exclude(pk__in=conservar).delete()
        filas = list(filas_evidencias(self.solicitud()))
        self.assertEqual(len(filas), 1001)
        self.assertEqual(len({f[4] for f in filas[1:]}), 1000)
