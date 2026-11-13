"""Los fragmentos conservan filtros, permisos y formularios sin cargar la cabecera."""

from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from notificaciones.models import Notificacion, Novedad, PlazoReporte

from .models import Envio


class PanelesInteractivosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            "interfaz_admin", email="admin@example.invalid", password="SoloParaPruebas42!"
        )
        cls.user = User.objects.create_user("interfaz_propia")
        cls.other = User.objects.create_user("interfaz_ajena")
        cls.plazo = PlazoReporte.objects.create(
            titulo="Entrega compartida", fecha_limite=timezone.now() + timedelta(days=1)
        )
        cls.propia = Envio.objects.create(
            usuario=cls.user,
            nombre="Informe de mi equipo",
            proyecto="LEM",
            tipo_evidencia="Documento",
            link_evidencia="https://www.sena.edu.co",
            plazo=cls.plazo,
        )
        cls.ajena = Envio.objects.create(
            usuario=cls.other, nombre="Archivo de otro equipo", proyecto="GIVIT", tipo_evidencia="Documento"
        )
        cls.aviso = Notificacion.objects.create(
            usuario=cls.user, tipo="novedad", titulo="Aviso personal de investigación", mensaje="Contenido privado"
        )
        Notificacion.objects.create(
            usuario=cls.other, tipo="novedad", titulo="Aviso de otra cuenta", mensaje="Mensaje privado de otro equipo"
        )
        Novedad.objects.create(titulo="Publicación de ejemplo", contenido="Información de investigación")

    def setUp(self):
        self.client.force_login(self.admin)

    def fragmento(self, route, **kwargs):
        return self.client.get(reverse(route, **kwargs), HTTP_X_WORKSPACE_FRAGMENT="1")

    def test_all_nine_interactive_panels_support_full_page_and_fragment(self):
        rutas = [
            ("admin_personalizado:dashboard", {}),
            ("admin_personalizado:gestionar_usuarios", {}),
            ("reportes", {}),
            ("evidencias_list", {}),
            ("notificaciones:bandeja", {}),
            ("notificaciones:mis_plazos", {}),
            ("notificaciones:plazos_admin", {}),
            ("notificaciones:novedades_admin", {}),
            ("notificaciones:seguimiento_plazo", {"pk": self.plazo.pk}),
        ]
        for ruta, kwargs in rutas:
            with self.subTest(ruta=ruta):
                full = self.client.get(reverse(ruta, kwargs=kwargs))
                response = self.fragmento(ruta, kwargs=kwargs)
                self.assertEqual((full.status_code, response.status_code), (200, 200))
                self.assertContains(full, '<html lang="es">')
                self.assertNotContains(response, "<html")
                self.assertNotContains(response, 'id="main-navigation"')
                self.assertNotContains(response, "data-notifications-summary")
                self.assertContains(response, "data-live-region=")
                self.assertLess(len(response.content), len(full.content))
                self.assertEqual(response["X-Workspace-Fragment"], "1")
                self.assertIn("X-Workspace-Fragment", response["Vary"])
                self.assertIn("X-Workspace-Fragment", full["Vary"])
                self.assertIn("no-store", response["Cache-Control"])

    def test_query_parameter_or_unknown_header_never_replaces_full_navigation(self):
        for headers in [{}, {"HTTP_X_WORKSPACE_FRAGMENT": "true"}, {"HTTP_X_WORKSPACE_FRAGMENT": "other"}]:
            response = self.client.get(reverse("evidencias_list"), {"base_panel": "ui/base_fragmento.html"}, **headers)
            self.assertContains(response, '<html lang="es">')
            self.assertNotIn("X-Workspace-Fragment", response)

    def test_scoped_evidence_and_report_filters_are_identical_without_foreign_rows(self):
        self.client.force_login(self.user)
        for ruta in ["evidencias_list", "reportes"]:
            with self.subTest(ruta=ruta):
                url = reverse(ruta)
                params = {"proyecto": "LEM", "estado": "pendiente"}
                full = self.client.get(url, params)
                response = self.client.get(url, params, HTTP_X_WORKSPACE_FRAGMENT="1")
                self.assertEqual(response.context["total_envios"], full.context["total_envios"])
                self.assertEqual(response.context["total_envios"], 1)
                self.assertNotContains(response, self.ajena.nombre)
                if ruta == "evidencias_list":
                    self.assertEqual([e.pk for e in response.context["envios"]], [self.propia.pk])
                else:
                    self.assertEqual(response.context["download_query"], full.context["download_query"])
        response = self.client.get(reverse("reportes"), {"start": "2026-13"}, HTTP_X_WORKSPACE_FRAGMENT="1")
        self.assertContains(response, "Revisa los filtros")
        self.assertEqual(response.context["total_envios"], 0)

    def test_fragment_request_cannot_bypass_login_or_administration_role(self):
        self.client.logout()
        response = self.fragmento("evidencias_list")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))
        self.client.force_login(self.user)
        for ruta in [
            "admin_personalizado:gestionar_usuarios",
            "admin_personalizado:dashboard",
            "notificaciones:novedades_admin",
            "notificaciones:plazos_admin",
        ]:
            url = reverse(ruta)
            full = self.client.get(url)
            response = self.client.get(url, HTTP_X_WORKSPACE_FRAGMENT="1")
            self.assertEqual(response.status_code, full.status_code)
            self.assertNotContains(response, "data-live-region=", status_code=response.status_code)
        response = self.fragmento("notificaciones:bandeja")
        self.assertContains(response, self.aviso.titulo)
        self.assertNotContains(response, "Aviso de otra cuenta")

    def test_native_roles_and_observation_forms_still_have_csrf_and_current_version(self):
        response = self.fragmento("admin_personalizado:gestionar_usuarios")
        self.assertContains(response, "data-account-actions")
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        response = self.fragmento("evidencias_list")
        self.assertContains(response, "data-observation-form")
        self.assertContains(response, 'name="version" value="1"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.admin)
        self.assertEqual(
            csrf.post(
                reverse("actualizar_observaciones", args=[self.propia.pk]),
                {"observaciones": "No guardar"},
                HTTP_X_WORKSPACE_FRAGMENT="1",
            ).status_code,
            403,
        )
        self.propia.refresh_from_db()
        self.assertFalse(self.propia.observaciones)

    def test_fragments_skip_header_queries_and_share_existing_inbox_count(self):
        self.client.force_login(self.user)
        for ruta, ahorro in [("evidencias_list", 2), ("reportes", 2), ("notificaciones:bandeja", 1)]:
            with self.subTest(ruta=ruta):
                with CaptureQueriesContext(connection) as completas:
                    self.client.get(reverse(ruta))
                with CaptureQueriesContext(connection) as parciales:
                    self.fragmento(ruta)

                def conteo(qs):
                    return sum(
                        "notificaciones_notificacion" in q["sql"] and q["sql"].lstrip().startswith("SELECT") for q in qs
                    )

                self.assertEqual(conteo(completas) - conteo(parciales), ahorro)

    def test_read_request_never_marks_a_notice_as_read(self):
        self.client.force_login(self.user)
        self.fragmento("notificaciones:bandeja")
        self.aviso.refresh_from_db()
        self.assertIsNone(self.aviso.leida_en)


class FiltrosDirectorioTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            "filtro_usuarios_admin", email="admin@example.invalid", password="SoloPruebas42!"
        )
        self.member = User.objects.create_user("filtro_instructor", first_name="Valentina")
        self.member.groups.set([Group.objects.get(name="instructor")])
        self.client.force_login(self.admin)
        self.url = reverse("admin_personalizado:gestionar_usuarios")

    def test_invalid_role_or_state_does_not_raise_500_or_expand_the_directory(self):
        for filtros in [
            {"rol": "²"},
            {"rol": "9" * 5000},
            {"rol": "-1"},
            {"rol": "0"},
            {"rol": "99999999"},
            {"rol": "texto"},
            {"estado": "inventado"},
            {"q": "x" * 101},
        ]:
            for header in [{}, {"HTTP_X_WORKSPACE_FRAGMENT": "1"}]:
                with self.subTest(filtros={k: v[:30] for k, v in filtros.items()}, parcial=bool(header)):
                    response = self.client.get(self.url, filtros, **header)
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.context["filtros_form"].errors)
                    self.assertEqual(response.context["usuarios"].paginator.count, 0)
                    self.assertContains(response, "No se muestran cuentas hasta corregir los filtros.")
                    self.assertNotContains(response, "Valentina")

    def test_valid_role_state_and_search_preserve_historical_route_and_choices(self):
        params = {"rol": str(Group.objects.get(name="instructor").pk), "estado": "activo", "q": "Valentina"}
        for ruta in ["admin_personalizado:gestionar_usuarios", "admin_personalizado:usuarios"]:
            response = self.client.get(reverse(ruta), params, HTTP_X_WORKSPACE_FRAGMENT="1")
            self.assertEqual([u.pk for u in response.context["usuarios"]], [self.member.pk])
            self.assertEqual(response.context["rol"], params["rol"])
            self.assertFalse(response.context["filtros_form"].errors)
