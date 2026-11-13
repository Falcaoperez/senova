"""Filtros estrictos y cambios de lectura sin ampliar el alcance de una cuenta."""

import datetime

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from ..models import Notificacion, PreferenciasNotificacion


class BandejaInteractivaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("bandeja_interactiva")
        PreferenciasNotificacion.objects.create(usuario=self.user)
        self.client.force_login(self.user)
        self.aviso = Notificacion.objects.create(
            usuario=self.user, tipo="novedad", titulo="Aviso de investigación", mensaje="Información del equipo"
        )
        self.other = User.objects.create_user("bandeja_interactiva_ajena")
        self.ajeno = Notificacion.objects.create(
            usuario=self.other, tipo="novedad", titulo="Aviso privado ajeno", mensaje="No divulgar"
        )
        self.url = reverse("notificaciones:bandeja")
        self.read = reverse("notificaciones:lectura", args=[self.aviso.pk])
        self.bulk = reverse("notificaciones:lectura_seleccion")
        self.all = reverse("notificaciones:marcar_todas")

    def api(self, url, data):
        return self.client.post(url, data, HTTP_X_INBOX_ACTION="1", HTTP_ACCEPT="application/json")

    def test_invalid_filter_cannot_mark_the_whole_inbox_as_read(self):
        self.client.post(reverse("notificaciones:marcar_todas"), {"alcance": "filtradas", "tipo": "tipo-inexistente"})
        self.aviso.refresh_from_db()
        self.assertIsNone(self.aviso.leida_en)

    def test_invalid_filters_hide_results_and_never_change_timestamps(self):
        for params in [
            {"q": "x" * 101},
            {"tipo": "inexistente"},
            {"estado": "otro"},
            {"aviso": "²"},
            {"aviso": "-1"},
            {"aviso": "1.0"},
            {"aviso": "9" * 5000},
            {"desde": "2026-02-30"},
            {"hasta": "2026-13-01"},
            {"desde": "2026-1-01"},
            {"desde": "0999-01-01"},
            {"hasta": "9999-12-31"},
            {"desde": "2026-11-14", "hasta": "2026-11-13"},
        ]:
            with self.subTest(params={k: v[:30] for k, v in params.items()}):
                response = self.client.get(self.url, params, HTTP_X_WORKSPACE_FRAGMENT="1")
                self.assertTrue(response.context["filtros_form"].errors)
                self.assertEqual(response.context["avisos"].paginator.count, 0)
                self.assertNotContains(response, self.aviso.titulo)
                self.assertContains(response, "No se muestran ni marcan resultados")
                response = self.api(self.all, {"alcance": "filtradas", **params})
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.json())
                self.aviso.refresh_from_db()
                self.assertIsNone(self.aviso.leida_en)

    def test_unknown_scope_cannot_fall_back_to_the_whole_inbox(self):
        self.assertEqual(self.api(self.all, {"alcance": "incorrecto"}).status_code, 400)
        self.aviso.refresh_from_db()
        self.assertIsNone(self.aviso.leida_en)

    def test_date_filter_and_mark_all_share_colombian_day_boundaries(self):
        records = []
        for stamp in ["2026-11-13T04:59:59", "2026-11-13T05:00:00", "2026-11-14T04:59:59", "2026-11-14T05:00:00"]:
            records.append(
                Notificacion.objects.create(
                    usuario=self.user,
                    tipo="recordatorio",
                    titulo="Rango verificado",
                    mensaje="Fecha",
                    creada_en=datetime.datetime.fromisoformat(stamp).replace(tzinfo=datetime.UTC),
                )
            )
        params = {"q": "Rango verificado", "desde": "2026-11-13", "hasta": "2026-11-13", "tipo": "recordatorio"}
        response = self.client.get(self.url, params)
        self.assertEqual({a.pk for a in response.context["avisos"]}, {r.pk for r in records[1:3]})
        response = self.api(self.all, {"alcance": "filtradas", **params})
        self.assertEqual(response.json()["actualizados"], 2)
        for i, record in enumerate(records):
            record.refresh_from_db()
            self.assertEqual(record.leida_en is not None, i in [1, 2])
        self.aviso.refresh_from_db()
        self.ajeno.refresh_from_db()
        self.assertIsNone(self.aviso.leida_en)
        self.assertIsNone(self.ajeno.leida_en)

    def test_open_date_ranges_and_supported_years_render_without_overflow(self):
        for params in [
            {"desde": "1000-01-01"},
            {"hasta": "9998-12-31"},
            {"desde": "1000-01-01", "hasta": "9998-12-31"},
        ]:
            response = self.client.get(self.url, params)
            self.assertFalse(response.context["filtros_form"].errors)
            self.assertEqual(response.context["avisos"].paginator.count, 1)

    def test_single_read_and_unread_api_preserve_first_read_and_do_not_queue_flash_messages(self):
        response = self.api(self.read, {"accion": "leida"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["actualizados"], 1)
        self.assertEqual(list(get_messages(response.wsgi_request)), [])
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])
        self.aviso.refresh_from_db()
        primera = self.aviso.leida_en
        self.assertEqual(self.api(self.read, {"accion": "leida"}).json()["actualizados"], 0)
        self.aviso.refresh_from_db()
        self.assertEqual(self.aviso.leida_en, primera)
        self.assertEqual(self.api(self.read, {"accion": "pendiente"}).json()["actualizados"], 1)
        self.assertEqual(self.api(self.read, {"accion": "pendiente"}).json()["actualizados"], 0)
        self.aviso.refresh_from_db()
        self.assertIsNone(self.aviso.leida_en)

    def test_invalid_selection_api_returns_error_without_changing_notifications(self):
        for payload in [
            {"accion": "borrar", "avisos": [self.aviso.pk]},
            {"accion": "leida", "avisos": [self.aviso.pk] * 101},
            {"accion": "leida", "avisos": ["²"]},
            {"accion": "leida"},
        ]:
            self.assertEqual(self.api(self.bulk, payload).status_code, 400)
            self.aviso.refresh_from_db()
            self.assertIsNone(self.aviso.leida_en)

    def test_mixed_owner_batch_is_atomic_and_does_not_disclose_foreign_data(self):
        response = self.api(self.bulk, {"avisos": [self.aviso.pk, self.ajeno.pk], "accion": "leida"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(set(response.json()), {"error"})
        self.assertNotContains(response, self.ajeno.titulo, status_code=404)
        for aviso in [self.aviso, self.ajeno]:
            aviso.refresh_from_db()
            self.assertIsNone(aviso.leida_en)

    def test_batch_updates_only_selected_owner_records(self):
        second = Notificacion.objects.create(usuario=self.user, tipo="evidencia", titulo="Revisión", mensaje="Equipo")
        response = self.api(self.bulk, {"avisos": [self.aviso.pk, second.pk], "accion": "leida"})
        self.assertEqual(response.json()["actualizados"], 2)
        self.assertEqual(Notificacion.objects.filter(usuario=self.user, leida_en__isnull=False).count(), 2)
        self.ajeno.refresh_from_db()
        self.assertIsNone(self.ajeno.leida_en)

    def test_legacy_all_scope_and_native_return_keep_existing_behavior(self):
        response = self.client.post(self.all, {"next": self.url + "?tipo=novedad"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.url + "?tipo=novedad")
        self.aviso.refresh_from_db()
        self.assertIsNotNone(self.aviso.leida_en)
        response = self.client.post(self.read, {"accion": "pendiente", "next": "https://example.invalid"})
        self.assertEqual(response.url, self.url)

    def test_only_exact_header_enables_json_and_csrf_is_still_required(self):
        response = self.client.post(self.read, {"accion": "leida"}, HTTP_X_INBOX_ACTION="true")
        self.assertEqual(response.status_code, 302)
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.user)
        for url in [self.read, self.bulk, self.all]:
            self.assertEqual(secure.post(url, {"accion": "pendiente"}, HTTP_X_INBOX_ACTION="1").status_code, 403)

    def test_api_and_filtered_page_require_login_and_keep_personal_scope_for_superuser(self):
        self.user.is_staff = self.user.is_superuser = True
        self.user.save(update_fields=["is_staff", "is_superuser"])
        response = self.client.get(self.url, {"usuario": self.other.pk})
        self.assertEqual([a.pk for a in response.context["avisos"]], [self.aviso.pk])
        self.assertNotContains(response, self.ajeno.titulo)
        self.client.logout()
        self.assertEqual(self.api(self.read, {"accion": "leida"}).status_code, 302)

    def test_get_and_head_do_not_change_read_state_and_post_to_inbox_is_rejected(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.head(self.url).status_code, 200)
        for url in [self.read, self.bulk, self.all]:
            self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.aviso.refresh_from_db()
        self.assertIsNone(self.aviso.leida_en)

    def test_complete_and_fragment_responses_share_strict_filters_and_private_headers(self):
        params = {"tipo": "novedad", "estado": "pendiente"}
        full = self.client.get(self.url, params)
        part = self.client.get(self.url, params, HTTP_X_WORKSPACE_FRAGMENT="1")
        self.assertEqual([a.pk for a in full.context["avisos"]], [a.pk for a in part.context["avisos"]])
        self.assertNotContains(part, "<html")
        self.assertContains(full, "js/inbox.js")
        self.assertIn("X-Workspace-Fragment", part["Vary"])
        self.assertIn("no-store", part["Cache-Control"])

    def test_large_filtered_update_and_page_avoid_one_query_per_notice(self):
        Notificacion.objects.bulk_create(
            [
                Notificacion(usuario=self.user, tipo="novedad", titulo=f"Carga bandeja {i}", mensaje="Equipo")
                for i in range(250)
            ]
        )
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url, {"q": "Carga bandeja"})
        self.assertEqual(len(response.context["avisos"]), 20)
        self.assertEqual(response.context["avisos"].paginator.count, 250)
        self.assertLessEqual(len(queries), 9)
        with CaptureQueriesContext(connection) as queries:
            response = self.api(self.all, {"alcance": "filtradas", "q": "Carga bandeja"})
        self.assertEqual(response.json()["actualizados"], 250)
        self.assertEqual(sum(q["sql"].lstrip().startswith("UPDATE `notificaciones_notificacion`") for q in queries), 1)
        self.assertLessEqual(len(queries), 6)
