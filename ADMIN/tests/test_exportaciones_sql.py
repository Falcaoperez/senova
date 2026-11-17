"""El historial completo se descarga con SQL acotado y un orden estable."""

import datetime
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from cuentas.models import RegistroSeguridad

from ..auditoria import filas_auditoria, registros_filtrados
from ..forms import FiltrosAuditoriaForm


class CSVAuditoriaSQLTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = User.objects.create_user("csv_historial", first_name="Lucía", email="privado@example.invalid")
        RegistroSeguridad.objects.bulk_create(
            [
                RegistroSeguridad(actor=cls.actor, accion="admin:perfil", ruta=f"/csv-historial/{i:04}/")
                for i in range(1200)
            ],
            batch_size=500,
        )
        cls.instante = datetime.datetime(2026, 11, 18, 4, 59, 59, tzinfo=datetime.UTC)
        ids = list(RegistroSeguridad.objects.order_by("pk").values_list("pk", flat=True))
        RegistroSeguridad.objects.update(creado_en=cls.instante)
        RegistroSeguridad.objects.filter(pk__in=ids[::3]).update(creado_en=cls.instante - datetime.timedelta(days=1))

    def consulta(self):
        return registros_filtrados(FiltrosAuditoriaForm({"q": "csv-historial"}))

    def test_mil_doscientos_eventos_con_empates_y_fechas_fuera_del_orden_de_id(self):
        esperado = list(self.consulta().values_list("ruta", flat=True))
        with CaptureQueriesContext(connection) as consultas:
            filas = list(filas_auditoria(self.consulta()))
        self.assertEqual([f[6] for f in filas[1:]], esperado)
        self.assertEqual(len(consultas), 4)
        lecturas = [c["sql"] for c in consultas if "MAX(" not in c["sql"]]
        self.assertEqual(len(lecturas), 3)
        self.assertTrue(all("LIMIT 500" in sql and "OFFSET" not in sql for sql in lecturas))
        for consulta in consultas:
            for campo in ("password", "email", "last_login", "is_superuser"):
                self.assertNotIn(connection.ops.quote_name(campo), consulta["sql"])
        print("ESCALA CSV auditoría / 1200 eventos: 4 consultas y lotes SQL de 500 sin OFFSET ni credenciales.")

    def test_eventos_creados_durante_la_descarga_no_alargan_el_archivo(self):
        esperadas = list(self.consulta().values_list("ruta", flat=True))
        generador = filas_auditoria(self.consulta())
        next(generador)
        primera = next(generador)
        nuevo = RegistroSeguridad.objects.create(accion="admin:perfil", ruta="/csv-historial/nuevo/")
        RegistroSeguridad.objects.filter(pk=nuevo.pk).update(creado_en=self.instante - datetime.timedelta(days=2))
        self.assertEqual([f[6] for f in [primera, *generador]], esperadas)

    def test_actor_eliminado_entre_lotes_no_elimina_eventos_ni_consulta_cuenta_por_fila(self):
        generador = filas_auditoria(self.consulta())
        next(generador)
        primera = next(generador)
        self.actor.delete()
        with CaptureQueriesContext(connection) as consultas:
            filas = [primera, *generador]
        self.assertEqual(len(filas), 1200)
        self.assertTrue(all(f[1] == "Sin cuenta asociada" and f[2] == "" for f in filas[500:]))
        self.assertEqual(len(consultas), 2)

    def test_fecha_explicita_de_colombia_y_filtros_sin_resultados(self):
        with timezone.override(ZoneInfo("Asia/Tokyo")):
            filas = list(filas_auditoria(self.consulta()))
        self.assertEqual(filas[1][0], "2026-11-17 23:59:59 -0500")
        self.assertEqual(
            len(list(filas_auditoria(registros_filtrados(FiltrosAuditoriaForm({"q": "sin resultados"}))))), 1
        )
