"""Auditoría privada, filtros de Colombia y exportación sin ampliar permisos."""

import csv
import datetime
import io

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from cuentas.models import RegistroSeguridad

from ..auditoria import codigo_http, etiqueta_accion, filas_auditoria, registros_filtrados
from ..forms import FiltrosAuditoriaForm
from ..selectors import centro_operaciones


def utc(value):
    return datetime.datetime.fromisoformat(value).replace(tzinfo=datetime.UTC)


def contenido(response):
    return b"".join(response.streaming_content) if response.streaming else response.content


def filas(response):
    return list(csv.reader(io.StringIO(contenido(response).decode("utf-8-sig"))))


class AuditoriaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("auditoria_operadora", first_name="Valeria", last_name="Gómez")
        cls.admin.groups.add(Group.objects.get(name="administrador"))
        cls.other = User.objects.create_user("auditoria_equipo", email="no-exportar@example.invalid")
        cls.root = User.objects.create_superuser("auditoria_supervisor", email="supervisor@example.invalid")
        cls.eventos = []
        for accion, fecha, actor, ruta in [
            ("login:302", "2026-11-13T05:00:00", cls.other, "/login/"),
            ("verificar_pin:400", "2026-11-14T04:59:59", cls.other, "/api/verificar_pin/"),
            ("admin:roles", "2026-11-14T05:00:00", cls.admin, "/administrador/usuario/45/"),
            ("login:429", "2026-11-13T04:59:59", None, "/login/"),
            (
                "notificaciones:crear_plazo:200",
                "2026-11-12T14:00:00",
                cls.admin,
                "/notificaciones/administracion/plazos/",
            ),
            ("mantenimiento:credenciales", "2026-11-11T14:00:00", None, "/mantenimiento/"),
        ]:
            evento = RegistroSeguridad.objects.create(actor=actor, accion=accion, ruta=ruta, direccion_ip="203.0.113.7")
            RegistroSeguridad.objects.filter(pk=evento.pk).update(creado_en=utc(fecha))
            cls.eventos.append(evento)

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse("admin_personalizado:actividad")
        self.export = reverse("admin_personalizado:actividad_csv")

    def test_anonymous_users_must_login_for_page_and_file(self):
        self.client.logout()
        for url in [self.url, self.export]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith(reverse("login")))

    def test_other_roles_and_staff_without_administrator_role_are_denied(self):
        for rol in ["usuario", "instructor", "investigador", "coordinador", "dinamizador"]:
            self.other.groups.set([Group.objects.get(name=rol)])
            self.client.force_login(self.other)
            for url in [self.url, self.export]:
                response = self.client.get(url, HTTP_X_WORKSPACE_FRAGMENT="1")
                self.assertEqual(response.status_code, 403)
                self.assertNotContains(response, "203.0.113.7", status_code=403)
        self.other.groups.clear()
        self.other.is_staff = True
        self.other.save(update_fields=["is_staff"])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_superuser_can_read_without_business_role(self):
        self.client.force_login(self.root)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(len(filas(self.client.get(self.export))), 7)

    def test_removing_administrator_role_revokes_next_page_and_export(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.admin.groups.clear()
        for url in [self.url, self.export]:
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_default_history_orders_recent_events_and_handles_deleted_actor(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["pagina"].paginator.count, 6)
        self.assertEqual([r["pk"] for r in response.context["registros"]][:3], [e.pk for e in self.eventos[2::-1]])
        self.assertContains(response, "HTTP 302")
        self.assertContains(response, "Registro interno")
        self.other.delete()
        self.assertContains(self.client.get(self.url), "Sin cuenta asociada")

    def test_history_export_queries_only_actor_identity_without_extra_queries(self):
        RegistroSeguridad.objects.bulk_create(
            [RegistroSeguridad(actor=self.other, accion="login:302", ruta="/login/") for _ in range(250)]
        )
        with CaptureQueriesContext(connection) as consultas:
            resultado = list(filas_auditoria(registros_filtrados(FiltrosAuditoriaForm({}))))
        self.assertEqual(len(resultado), 257)
        self.assertEqual(len(consultas), 1)
        sql = consultas[0]["sql"].lower()
        for campo in ["password", "email", "is_superuser", "last_login"]:
            self.assertNotIn(connection.ops.quote_name(campo), sql)
        self.assertTrue(any(fila[2] == self.other.username for fila in resultado[1:]))

    def test_dashboard_activity_and_recent_members_do_not_load_credentials(self):
        with CaptureQueriesContext(connection) as consultas:
            contexto = centro_operaciones("30")
            miembros = list(contexto["usuarios_recientes"])
            for miembro in miembros:
                miembro.get_full_name()
                list(miembro.groups.all())
        self.assertTrue(contexto["actividad_reciente"])
        self.assertTrue(miembros)
        for miembro in miembros:
            self.assertTrue({"password", "email", "is_superuser"}.issubset(miembro.get_deferred_fields()))
        for consulta in consultas:
            self.assertNotIn(connection.ops.quote_name("password"), consulta["sql"].lower())

    def test_search_matches_actor_name_username_action_and_path(self):
        for q, esperado in [("Gómez", 2), ("auditoria_equipo", 2), ("verificar_pin", 1), ("/mantenimiento/", 1)]:
            params = {"q": q}
            response = self.client.get(self.url, params)
            self.assertEqual(response.context["pagina"].paginator.count, esperado)
            self.assertEqual(len(filas(self.client.get(self.export, params))) - 1, esperado)

    def test_dates_include_complete_colombian_days(self):
        params = {"desde": "2026-11-13", "hasta": "2026-11-13"}
        response = self.client.get(self.url, params)
        self.assertEqual({r["pk"] for r in response.context["registros"]}, {e.pk for e in self.eventos[:2]})
        data = filas(self.client.get(self.export, params))
        self.assertEqual(len(data), 3)
        self.assertEqual(data[1][0], "2026-11-13 23:59:59 -0500")
        self.assertEqual(data[2][0], "2026-11-13 00:00:00 -0500")

    def test_open_date_ranges_and_supported_year_boundaries(self):
        for params, total in [
            ({"desde": "2026-11-14"}, 1),
            ({"hasta": "2026-11-11"}, 1),
            ({"desde": "1000-01-01", "hasta": "9998-12-31"}, 6),
        ]:
            response = self.client.get(self.url, params)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["pagina"].paginator.count, total)

    def test_invalid_filters_hide_results_and_reject_file_without_attachment(self):
        for params in [
            {"q": "x" * 101},
            {"estado": "otro"},
            {"desde": "2026-13-01"},
            {"hasta": "2026-02-30"},
            {"desde": "2026-1-01"},
            {"desde": "２０２６-11-13"},
            {"desde": "0999-01-01"},
            {"hasta": "9999-12-31"},
            {"desde": "2026-11-14", "hasta": "2026-11-13"},
        ]:
            with self.subTest(params=params):
                response = self.client.get(self.url, params)
                self.assertTrue(response.context["filtros_form"].errors)
                self.assertEqual(response.context["registros"], [])
                self.assertIsNone(response.context["url_exportar"])
                response = self.client.get(self.export, params)
                self.assertEqual(response.status_code, 400)
                self.assertNotIn("Content-Disposition", response)
                self.assertContains(response, "Volver a actividad", status_code=400)

    def test_http_filters_do_not_confuse_redirects_with_internal_changes(self):
        for estado, total in [("http", 4), ("incidencias", 2), ("internos", 2)]:
            params = {"estado": estado}
            response = self.client.get(self.url, params)
            self.assertEqual(response.context["pagina"].paginator.count, total)
            self.assertEqual(len(filas(self.client.get(self.export, params))) - 1, total)
        response = self.client.get(self.url, {"estado": "incidencias"})
        self.assertNotContains(response, "HTTP 302")

    def test_http_filter_and_display_agree_on_legacy_malformed_actions(self):
        for action in ["valor:400\n", "valor:４００", "valor:099", "valor:999", "valor:2000", "valor:200", "valor:103"]:
            record = RegistroSeguridad.objects.create(accion=action)
            response = self.client.get(self.url, {"estado": "http"})
            shown = {r["pk"] for r in response.context["registros"]}
            self.assertEqual(record.pk in shown, bool(codigo_http(action)))
        self.assertEqual(etiqueta_accion("notificaciones:preferencias:302"), "Comunicaciones y plazos")

    def test_html_escapes_actor_route_and_action(self):
        self.other.first_name = '<img src=x onerror="alert(1)">'
        self.other.save(update_fields=["first_name"])
        RegistroSeguridad.objects.create(
            actor=self.other, accion="<script>alert(2)</script>", ruta="javascript:alert(3)"
        )
        response = self.client.get(self.url)
        self.assertContains(response, "&lt;img")
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert(2)</script>")
        self.assertNotContains(response, 'href="javascript:')

    def test_csv_is_private_unicode_and_escapes_formulas_without_exporting_email_or_hash(self):
        self.other.first_name = "=1+1"
        self.other.set_password("NoPublicarClave42!")
        self.other.save(update_fields=["first_name", "password"])
        response = self.client.get(self.export, {"q": "auditoria_equipo", "page": "99", "password": "no-incluir"})
        data = contenido(response)
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("actividad-gesicom.csv", response["Content-Disposition"])
        text = data.decode("utf-8-sig")
        self.assertIn("'=1+1", text)
        self.assertNotIn(self.other.email, text)
        self.assertNotIn(self.other.password, text)
        self.assertNotIn("no-incluir", text)

    def test_pagination_is_stable_and_export_includes_all_pages_without_n_plus_one(self):
        RegistroSeguridad.objects.bulk_create(
            [
                RegistroSeguridad(actor=self.other, accion="admin:perfil", ruta=f"/prueba-paginada/{i}/")
                for i in range(120)
            ]
        )
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url, {"q": "prueba-paginada"})
        self.assertEqual(len(response.context["registros"]), 25)
        self.assertEqual(response.context["pagina"].paginator.count, 120)
        self.assertLessEqual(len(queries), 9)
        first = {r["pk"] for r in response.context["registros"]}
        second = self.client.get(self.url, {"q": "prueba-paginada", "page": 2})
        self.assertFalse(first.intersection(r["pk"] for r in second.context["registros"]))
        with CaptureQueriesContext(connection) as queries:
            data = filas(self.client.get(self.export, {"q": "prueba-paginada"}))
        self.assertEqual(len(data), 121)
        self.assertEqual(sum("FROM `cuentas_registroseguridad`" in q["sql"] for q in queries), 1)
        self.assertLessEqual(len(queries), 6)

    def test_full_and_fragment_share_results_and_keep_private_headers(self):
        params = {"estado": "incidencias"}
        full = self.client.get(self.url, params)
        part = self.client.get(self.url, params, HTTP_X_WORKSPACE_FRAGMENT="1")
        self.assertEqual([r["pk"] for r in full.context["registros"]], [r["pk"] for r in part.context["registros"]])
        self.assertContains(full, "css/audit.css")
        self.assertNotContains(part, "<html")
        self.assertIn("no-store", part["Cache-Control"])
        self.assertIn("X-Workspace-Fragment", part["Vary"])

    def test_reading_does_not_create_events_and_endpoints_accept_only_safe_methods(self):
        before = RegistroSeguridad.objects.count()
        self.client.get(self.url)
        filas(self.client.get(self.export))
        self.assertEqual(self.client.head(self.url).status_code, 200)
        self.assertEqual(self.client.head(self.export).status_code, 200)
        self.assertEqual(RegistroSeguridad.objects.count(), before)
        for url in [self.url, self.export]:
            self.assertEqual(self.client.post(url).status_code, 405)

    def test_dashboard_links_to_history_and_download_url_keeps_only_filter_fields(self):
        dashboard = self.client.get(reverse("admin_personalizado:dashboard"))
        self.assertContains(dashboard, 'href="' + self.url + '"')
        response = self.client.get(self.url, {"q": "Gómez", "page": "999", "token": "no-publicar"})
        url = response.context["url_exportar"]
        self.assertIn("q=G%C3%B3mez", url)
        self.assertNotIn("page", url)
        self.assertNotIn("token", url)
