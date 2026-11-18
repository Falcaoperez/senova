"""Centro de seguridad personal: orden, estado, filtros y datos mínimos."""

import datetime
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.db import connection
from django.test import Client, RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from ..models import SesionUsuario
from ..seguridad import _contexto


class PanelSesionesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("sesiones_panel", password="SoloPruebasPanel42!")
        cls.other = User.objects.create_user("sesiones_panel_ajena")

    def setUp(self):
        self.url = reverse("centro_seguridad")
        self.client.force_login(self.user)
        self.second = Client()
        self.second.force_login(self.user)
        self.external = Client()
        self.external.force_login(self.other)
        self.actual = SesionUsuario.objects.get(sesion_id=self.client.session.session_key)
        self.otra = SesionUsuario.objects.get(sesion_id=self.second.session.session_key)
        self.ahora = timezone.now()

    def solicitud(self, **params):
        request = RequestFactory().get(self.url, params)
        request.user = self.user
        request.session = SimpleNamespace(session_key=self.actual.sesion_id)
        return request

    def agregar(self, total):
        claves = [f"{i:032x}" for i in range(total)]
        Session.objects.bulk_create(
            [
                Session(
                    session_key=clave,
                    session_data="contenido-no-necesario",
                    expire_date=self.ahora + datetime.timedelta(days=1),
                )
                for clave in claves
            ]
        )
        SesionUsuario.objects.bulk_create(
            [SesionUsuario(usuario=self.user, sesion_id=clave, ultimo_uso=self.ahora) for clave in claves]
        )

    def test_sesion_actual_aparece_primero_con_mas_de_una_pagina(self):
        self.agregar(25)
        SesionUsuario.objects.filter(pk=self.actual.pk).update(ultimo_uso=self.ahora - datetime.timedelta(seconds=30))
        pagina = _contexto(self.solicitud())["sesiones"]
        self.assertEqual(pagina[0].pk, self.actual.pk)
        self.assertTrue(pagina[0].es_actual)
        self.assertEqual(pagina.paginator.count, 27)
        self.assertEqual(len(pagina), 20)

    def test_filtros_distinguen_actual_y_otras_sin_ampliar_el_alcance(self):
        for estado, esperado in [("actual", {self.actual.pk}), ("otras", {self.otra.pk})]:
            with self.subTest(estado=estado):
                pagina = _contexto(self.solicitud(estado=estado))["sesiones"]
                self.assertSetEqual({s.pk for s in pagina}, esperado)

    def test_filtro_desconocido_muestra_error_y_ninguna_sesion(self):
        response = self.client.get(self.url, {"estado": "desconocido"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["filtros_form"].errors)
        self.assertEqual(response.context["sesiones"].paginator.count, 0)
        self.assertContains(response, "Revisa el filtro de sesiones")
        self.assertNotContains(response, 'class="session-entry')

    def test_consulta_de_mil_doscientas_sesiones_solo_lee_metadatos_de_la_pagina(self):
        self.agregar(1200)
        with CaptureQueriesContext(connection) as consultas:
            pagina = _contexto(self.solicitud())["sesiones"]
            datos = [(s.dispositivo, s.es_actual, s.es_inactiva) for s in pagina]
        self.assertEqual(len(datos), 20)
        self.assertEqual(pagina.paginator.count, 1202)
        self.assertEqual(len(consultas), 2)
        self.assertIn("LIMIT 20", consultas[1]["sql"])
        for consulta in consultas:
            for campo in ("session_data", "password", "email", "is_superuser"):
                self.assertNotIn(connection.ops.quote_name(campo), consulta["sql"])
        self.assertTrue(all({"usuario_id", "sesion_id"}.issubset(s.get_deferred_fields()) for s in pagina))
        print("ESCALA centro de seguridad / 1202 sesiones: 2 consultas, 20 metadatos y sin contenido de sesión.")

    @override_settings(SESSION_IDLE_TIMEOUT=1800)
    def test_inactividad_usa_el_mismo_limite_estricto_que_el_middleware(self):
        corte = self.ahora - datetime.timedelta(seconds=1800)
        SesionUsuario.objects.filter(pk=self.otra.pk).update(ultimo_uso=corte)
        with patch("cuentas.seguridad.timezone.now", return_value=self.ahora):
            self.assertFalse(_contexto(self.solicitud(estado="otras"))["sesiones"][0].es_inactiva)
        SesionUsuario.objects.filter(pk=self.otra.pk).update(ultimo_uso=corte - datetime.timedelta(microseconds=1))
        with patch("cuentas.seguridad.timezone.now", return_value=self.ahora):
            self.assertTrue(_contexto(self.solicitud(estado="otras"))["sesiones"][0].es_inactiva)

    @override_settings(SESSION_IDLE_TIMEOUT=0)
    def test_sin_limite_de_inactividad_no_se_marca_como_caducada(self):
        SesionUsuario.objects.filter(pk=self.otra.pk).update(ultimo_uso=self.ahora - datetime.timedelta(days=10))
        self.assertFalse(_contexto(self.solicitud(estado="otras"))["sesiones"][0].es_inactiva)

    def test_sesiones_expiradas_y_de_otra_cuenta_no_aparecen(self):
        Session.objects.filter(pk=self.otra.sesion_id).update(expire_date=self.ahora - datetime.timedelta(seconds=1))
        pagina = _contexto(self.solicitud())["sesiones"]
        self.assertEqual([s.pk for s in pagina], [self.actual.pk])

    def test_empates_tienen_orden_estable_y_paginacion_sin_repeticiones(self):
        self.agregar(25)
        primera = _contexto(self.solicitud(estado="otras"))["sesiones"]
        segunda = _contexto(self.solicitud(estado="otras", page=2))["sesiones"]
        esperados = list(
            SesionUsuario.objects.filter(usuario=self.user)
            .exclude(pk=self.actual.pk)
            .order_by("-ultimo_uso", "-pk")
            .values_list("pk", flat=True)
        )
        self.assertEqual([s.pk for s in [*primera, *segunda]], esperados)

    def test_paginacion_solo_conserva_el_filtro_validado(self):
        self.agregar(25)
        response = self.client.get(self.url, {"estado": "otras", "token": "no-copiar-este-valor"})
        self.assertContains(response, self.url + "?estado=otras&amp;page=2")
        self.assertNotContains(response, "no-copiar-este-valor")
        self.assertNotContains(response, self.actual.sesion_id)
        self.assertNotContains(response, self.otra.sesion_id)

    def test_horarios_de_colombia_no_cambian_con_otro_huso_activo(self):
        instante = datetime.datetime(2026, 11, 17, 4, 59, tzinfo=datetime.UTC)
        SesionUsuario.objects.filter(pk=self.otra.pk).update(ultimo_uso=instante)
        with timezone.override("Asia/Tokyo"):
            response = self.client.get(self.url, {"estado": "otras"})
        self.assertContains(response, 'datetime="2026-11-16T23:59:00-05:00"')

    def test_pagina_solo_admite_lectura_y_requiere_autenticacion(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.head(self.url).status_code, 200)
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_error_de_contrasena_conserva_estilos_sin_rellenar_el_secreto(self):
        response = self.client.post(
            reverse("revocar_sesion", args=[self.otra.pk]), {"contrasena_actual": "incorrecta-no-mostrar"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "css/security.css", status_code=400)
        self.assertContains(response, "Confirma tu contraseña actual", status_code=400)
        self.assertNotContains(response, "incorrecta-no-mostrar", status_code=400)
