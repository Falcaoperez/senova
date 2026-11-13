"""Los reportes y sus descargas representan la misma consulta autorizada."""

import csv
import datetime
import io

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from ..models import Envio


def csv_filas(response):
    contenido = b"".join(response.streaming_content) if response.streaming else response.content
    return list(csv.reader(io.StringIO(contenido.decode("utf-8-sig"))))


class ReportesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("reporte_personal", first_name="Laura", last_name="Pérez")
        cls.other = User.objects.create_user("reporte_ajeno", first_name="Laura", last_name="Pérez")
        cls.admin = User.objects.create_superuser("reporte_admin", "reporte@example.invalid", "ReporteLocal42!")
        cls.historico = Envio.objects.create(
            usuario=cls.user,
            nombre="Informe histórico",
            proyecto="LEM",
            tipo_evidencia="Documento",
            fecha_envio=datetime.date(2024, 2, 29),
            aprobada=True,
        )
        cls.reciente = Envio.objects.create(
            usuario=cls.user,
            nombre="Informe en revisión",
            proyecto="GIVIT",
            tipo_evidencia="Informe Final",
            fecha_envio=datetime.date(2024, 12, 1),
        )
        cls.ajeno = Envio.objects.create(
            usuario=cls.other,
            nombre="Registro privado",
            proyecto="LEM",
            tipo_evidencia="Documento",
            fecha_envio=datetime.date(2024, 2, 15),
            rechazada=True,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_historical_window_ends_in_selected_period_in_chart_and_csv(self):
        filtros = {"start": "2024-01", "end": "2024-03", "quarters": "4"}
        response = self.client.get(reverse("reportes"), filtros)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["trimestres_labels_json"][-1], "Q1 2024")
        self.assertEqual(response.context["datos_trimestrales_nuevas_json"], [0, 0, 0, 1])
        self.assertEqual(response.context["datos_trimestrales_aprobadas_json"], [0, 0, 0, 1])
        exportado = self.client.get(reverse("reportes_trimestrales_csv"), filtros)
        filas = csv_filas(exportado)
        self.assertEqual(filas[-1], ["Q1 2024", "1", "1"])
        self.assertEqual([f[0] for f in filas[1:]], response.context["trimestres_labels_json"])
        self.assertEqual([int(f[1]) for f in filas[1:]], response.context["datos_trimestrales_nuevas_json"])

    def test_quarterly_download_uses_one_aggregation_regardless_of_window_size(self):
        for n in [1, 12]:
            with CaptureQueriesContext(connection) as consultas:
                response = self.client.get(reverse("reportes_trimestrales_csv"), {"quarters": n, "end": "2024-12"})
                filas = csv_filas(response)
            self.assertEqual(len(filas), n + 1)
            self.assertLessEqual(len(consultas), 9)

    def test_form_defaults_match_four_quarters_without_extra_parameters(self):
        response = self.client.get(reverse("reportes"))
        self.assertEqual(response.context["filtros_form"]["quarters"].value(), "4")
        self.assertEqual(len(response.context["serie_trimestral"]), 4)
        self.assertContains(response, 'value="4" selected')

    def test_search_project_and_state_are_retained_by_form_and_download_links(self):
        filtros = {"q": "Informe", "proyecto": "GIVIT", "estado": "pendiente", "start": "2024-01", "end": "2024-12"}
        response = self.client.get(reverse("reportes"), filtros)
        self.assertEqual(response.context["total_envios"], 1)
        self.assertContains(response, 'name="q"')
        self.assertEqual(response.context["filtros_form"]["estado"].value(), "pendiente")
        for campo, valor in filtros.items():
            self.assertIn(f"{campo}={valor}", response.context["download_query"])
        exportado = self.client.get(reverse("reportes_csv"), filtros)
        filas = csv_filas(exportado)
        self.assertEqual(len(filas), 2)
        self.assertEqual(filas[1][1], self.reciente.nombre)
        self.assertEqual(filas[1][6], "En revisión")

    def test_invalid_filters_show_errors_and_never_expand_an_export(self):
        invalidos = [
            {"start": "2024-13"},
            {"end": "2024-2"},
            {"start": "2025-01", "end": "2024-01"},
            {"quarters": "24"},
            {"quarters": "oops"},
            {"proyecto": "INVENTADO"},
            {"estado": "invalid"},
            {"q": "x" * 101},
            {"plazo": "no"},
            {"usuario": "-1"},
            {"order": "password"},
        ]
        for filtros in invalidos:
            with self.subTest(filtros=filtros):
                for nombre in ["reportes", "evidencias_list"]:
                    response = self.client.get(reverse(nombre), filtros)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.context["total_envios"], 0)
                    self.assertContains(response, "Revisa los filtros")
                    if nombre == "reportes":
                        self.assertTrue(response.context["download_query"])
                for nombre in ["reportes_csv", "reportes_trimestrales_csv"]:
                    response = self.client.get(reverse(nombre), filtros)
                    self.assertEqual(response.status_code, 400)
                    self.assertFalse(response.streaming)
                    self.assertNotIn("Content-Disposition", response)

    def test_invalid_hidden_identifiers_do_not_expose_foreign_evidence(self):
        response = self.client.get(reverse("reportes"), {"usuario": self.other.pk})
        self.assertEqual(response.context["total_envios"], 0)
        self.assertNotContains(response, self.ajeno.nombre)
        self.assertEqual(len(csv_filas(self.client.get(reverse("reportes_csv"), {"usuario": self.other.pk}))), 1)

    def test_personal_charts_and_csv_exclude_other_people(self):
        response = self.client.get(reverse("reportes"), {"end": "2024-12"})
        self.assertEqual(response.context["total_envios"], 2)
        self.assertEqual(response.context["usuarios_resumen"][0]["usuario"], self.user.username)
        self.assertEqual(len(response.context["usuarios_resumen"]), 1)
        filas = csv_filas(self.client.get(reverse("reportes_csv")))
        self.assertEqual(len(filas), 3)
        self.assertNotIn(self.ajeno.nombre, [f[1] for f in filas[1:]])

    def test_reviewers_can_report_team_with_same_named_users_kept_separate(self):
        self.user.groups.add(Group.objects.get(name="coordinador"))
        response = self.client.get(reverse("reportes"))
        self.assertEqual(response.context["total_envios"], 3)
        self.assertEqual(len(response.context["usuarios_resumen"]), 2)
        self.assertEqual({f["id"] for f in response.context["usuarios_resumen"]}, {self.user.pk, self.other.pk})

    def test_legacy_projects_and_unassigned_rows_are_included_in_chart_totals(self):
        Envio.objects.create(
            usuario=self.user, nombre="Proyecto anterior", proyecto="LEGADO", tipo_evidencia="Documento"
        )
        Envio.objects.create(usuario=self.user, nombre="Sin proyecto", proyecto="", tipo_evidencia="Documento")
        response = self.client.get(reverse("reportes"))
        self.assertEqual(sum(response.context["categorias_data_json"]), response.context["total_envios"])
        self.assertIn("Sin proyecto", response.context["categorias_labels_json"])
        for proyecto, nombre in [("LEGADO", "Proyecto anterior"), ("__sin_proyecto", "Sin proyecto")]:
            response = self.client.get(reverse("reportes_csv"), {"proyecto": proyecto})
            self.assertEqual(csv_filas(response)[1][1], nombre)

    def test_deleted_owner_does_not_break_authorized_team_summary_or_csv(self):
        Envio.objects.create(usuario=None, nombre="Archivo sin autor", proyecto="LEM", tipo_evidencia="Documento")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("reportes"))
        self.assertIn("Cuenta no disponible", [f["nombre"] for f in response.context["usuarios_resumen"]])
        filas = csv_filas(self.client.get(reverse("reportes_csv"), {"q": "Archivo sin autor"}))
        self.assertEqual(filas[1][7], "")

    def test_csv_streaming_unicode_formula_protection_and_order(self):
        Envio.objects.create(
            usuario=self.user,
            nombre="=HYPERLINK(1)",
            proyecto="LEM",
            tipo_evidencia="Documento",
            observaciones="@SUM(1,2)\nMás información",
        )
        response = self.client.get(reverse("reportes_csv"), {"q": "HYPERLINK"})
        self.assertTrue(response.streaming)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("no-store", response["Cache-Control"])
        filas = csv_filas(response)
        self.assertEqual(
            filas[0][:6], ["fecha_envio", "nombre", "proyecto", "tipo_evidencia", "link_evidencia", "observaciones"]
        )
        self.assertEqual(filas[1][1], "'=HYPERLINK(1)")
        self.assertEqual(filas[1][5], "'@SUM(1,2) Más información")
        filas = csv_filas(self.client.get(reverse("reportes_csv"), {"order": "nombre", "dir": "asc"}))
        nombres = [f[1] for f in filas[1:]]
        self.assertEqual(nombres[0], "'=HYPERLINK(1)")
        self.assertEqual(nombres[1:], sorted(nombres[1:]))

    def test_very_early_and_late_valid_months_do_not_overflow(self):
        for filtros in [{"start": "1000-01", "end": "1000-01", "quarters": "12"}, {"end": "9999-12", "quarters": "12"}]:
            response = self.client.get(reverse("reportes"), filtros)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.context["filtros_form"].errors)

    def test_accessible_tables_exist_without_loading_charts(self):
        response = self.client.get(reverse("reportes"), {"end": "2024-12"})
        for nombre in ["quarter-table", "project-table", "people-table", "state-table"]:
            self.assertContains(response, f'id="{nombre}"', count=1)
        self.assertContains(response, 'class="chart-data" open', count=4)
        self.assertContains(response, "Q4 2024")
