"""Resumen acotado, aislamiento y coste compartido entre bandeja y cabecera."""

import json
from datetime import timedelta

from django.contrib.auth.models import AnonymousUser, User
from django.db import connection
from django.test import Client, RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from cuentas.models import SesionUsuario

from ..models import Notificacion
from ..resumen import resumen_de_peticion
from ..views import resumen


class ResumenTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("resumen_propio")
        self.other = User.objects.create_user("resumen_ajeno")
        self.client.force_login(self.user)
        self.url = reverse("notificaciones:resumen")
        self.aviso = Notificacion.objects.create(
            usuario=self.user, tipo="novedad", titulo="Convocatoria", mensaje="Contenido privado no expuesto"
        )
        Notificacion.objects.create(
            usuario=self.other, tipo="novedad", titulo="Aviso de otra cuenta", mensaje="Otro contenido privado"
        )

    def request(self, **params):
        request = RequestFactory().get(self.url, params)
        request.user = self.user
        return request

    def test_counter_keeps_previous_contract_and_does_not_load_recent_notices(self):
        with self.assertNumQueries(1):
            response = resumen(self.request())
        self.assertEqual(json.loads(response.content), {"pendientes": 1})
        with self.assertNumQueries(1):
            response = resumen(self.request(detalle="otro"))
        self.assertEqual(json.loads(response.content), {"pendientes": 1})

    def test_detail_uses_two_queries_and_exposes_only_four_own_recent_notices(self):
        ahora = timezone.now()
        nuevos = [
            Notificacion.objects.create(
                usuario=self.user, tipo="novedad", titulo=f"Actualización {i}", mensaje="No exponer", creada_en=ahora
            )
            for i in range(5)
        ]
        with self.assertNumQueries(2):
            response = resumen(self.request(detalle="1", usuario=self.other.pk))
        data = json.loads(response.content)
        self.assertEqual(data["pendientes"], 6)
        self.assertEqual([n["id"] for n in data["recientes"]], [n.pk for n in nuevos[::-1][:4]])
        self.assertEqual(set(data["recientes"][0]), {"id", "titulo", "fecha", "leida", "abrir_url"})
        self.assertNotIn("mensaje", response.content.decode())
        self.assertNotIn("Aviso de otra cuenta", response.content.decode())
        self.assertEqual(data["recientes"][0]["abrir_url"], reverse("notificaciones:abrir", args=[nuevos[-1].pk]))

    def test_one_request_reuses_counter_and_recent_notices_but_another_reloads(self):
        request = self.request()
        with self.assertNumQueries(1):
            self.assertEqual(resumen_de_peticion(request)["pendientes"], 1)
        with self.assertNumQueries(1):
            self.assertEqual(len(resumen_de_peticion(request, recientes=True)["recientes"]), 1)
        with self.assertNumQueries(0):
            self.assertEqual(resumen_de_peticion(request, recientes=True)["pendientes"], 1)
        Notificacion.objects.create(usuario=self.user, tipo="novedad", titulo="Nueva", mensaje="Contenido")
        with self.assertNumQueries(2):
            nuevo = resumen_de_peticion(self.request(), recientes=True)
        self.assertEqual(nuevo["pendientes"], 2)
        request.user = self.other
        with self.assertNumQueries(2):
            ajeno = resumen_de_peticion(request, recientes=True)
        self.assertEqual([n.titulo for n in ajeno["recientes"]], ["Aviso de otra cuenta"])

    def test_guest_or_inactive_account_cannot_obtain_a_summary(self):
        request = self.request()
        for usuario in [AnonymousUser(), User(pk=self.user.pk, is_active=False)]:
            request.user = usuario
            with self.assertNumQueries(0):
                self.assertEqual(resumen_de_peticion(request, recientes=True), {"pendientes": 0, "recientes": []})
        self.client.logout()
        response = self.client.get(self.url, {"detalle": "1"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["login_url"], reverse("login"))
        self.assertIn("no-store", response["Cache-Control"])

    def test_endpoint_is_read_only_and_opening_still_requires_post_and_csrf(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.assertEqual(self.client.head(self.url).status_code, 200)
        response = self.client.get(self.url, {"detalle": "1"})
        self.assertFalse(response.json()["recientes"][0]["leida"])
        self.assertIn("no-store", response["Cache-Control"])
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.user)
        target = reverse("notificaciones:abrir", args=[self.aviso.pk])
        self.assertEqual(csrf.post(target).status_code, 403)
        csrf.get(reverse("evidencias_list"))
        token = csrf.cookies["csrftoken"].value
        self.assertEqual(csrf.post(target, HTTP_X_CSRFTOKEN=token).status_code, 302)
        response = self.client.get(self.url, {"detalle": "1"})
        self.assertEqual(response.json()["pendientes"], 0)
        self.assertTrue(response.json()["recientes"][0]["leida"])

    @override_settings(SESSION_IDLE_TIMEOUT=1800)
    def test_detailed_polling_does_not_extend_idle_session_and_expiry_is_json(self):
        key = self.client.session.session_key
        anterior = timezone.now() - timedelta(minutes=2)
        SesionUsuario.objects.filter(sesion_id=key).update(ultimo_uso=anterior)
        self.assertEqual(self.client.get(self.url, {"detalle": "1"}).status_code, 200)
        self.assertEqual(SesionUsuario.objects.get(sesion_id=key).ultimo_uso, anterior)
        SesionUsuario.objects.filter(sesion_id=key).update(ultimo_uso=timezone.now() - timedelta(minutes=31))
        response = self.client.get(self.url, {"detalle": "1"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["login_url"], reverse("login"))

    def test_inbox_and_header_share_the_unread_count_query_and_escape_titles(self):
        Notificacion.objects.filter(pk=self.aviso.pk).update(titulo="<img src=x onerror=alert(1)>")
        with CaptureQueriesContext(connection) as consultas:
            response = self.client.get(reverse("notificaciones:bandeja"))
        conteos = [
            q["sql"]
            for q in consultas
            if "COUNT(" in q["sql"] and "notificaciones_notificacion" in q["sql"] and "leida_en" in q["sql"]
        ]
        self.assertEqual(len(conteos), 1)
        self.assertEqual(response.context["sin_leer"], response.context["ui_notificaciones_pendientes"])
        self.assertContains(response, "&lt;img src=x onerror=alert(1)&gt;")
        self.assertNotContains(response, "<img src=x onerror=alert(1)>")
        self.assertContains(response, "data-notification-template")
        self.assertContains(response, 'method="post"')

    def test_large_unread_count_keeps_accessible_total_and_small_visual_badge(self):
        Notificacion.objects.bulk_create(
            [
                Notificacion(usuario=self.user, tipo="novedad", titulo=f"Aviso {i}", mensaje="Mensaje")
                for i in range(100)
            ]
        )
        response = self.client.get(reverse("evidencias_list"))
        self.assertContains(response, 'aria-label="Notificaciones: 101 sin leer"')
        self.assertContains(response, "99+")
        response = self.client.get(self.url, {"detalle": "1"})
        self.assertEqual(response.json()["pendientes"], 101)
        self.assertEqual(len(response.json()["recientes"]), 4)
