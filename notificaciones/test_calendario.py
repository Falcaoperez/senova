"""Agenda mensual privada, límites de calendario y exportación RFC 5545."""

import datetime
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from Gesicom.models import Envio

from .calendario import limites_mes
from .forms import FiltrosAgendaForm
from .icalendar import base_publica, escapar_texto, plegar_linea
from .models import Notificacion, PlazoReporte

UTC = datetime.UTC


def utc(value):
    return datetime.datetime.fromisoformat(value).replace(tzinfo=UTC)


def contenido(response):
    return b"".join(response.streaming_content) if response.streaming else response.content


def lineas(response):
    data = contenido(response)
    assert data.endswith(b"\r\n")
    assert all(len(line) <= 75 for line in data.split(b"\r\n"))
    return data.replace(b"\r\n ", b"").decode("utf-8").split("\r\n")


class CalendarioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("agenda_calendario")
        cls.other = User.objects.create_user("agenda_calendario_otro")
        cls.team = Group.objects.create(name="Equipo de calendario")
        cls.other_team = Group.objects.create(name="Otro equipo de calendario")
        cls.user.groups.add(cls.team)
        cls.other.groups.add(cls.other_team)
        cls.own = PlazoReporte.objects.create(
            titulo="Agenda personal de investigación", proyecto="LEM", fecha_limite=utc("2026-11-13T14:30:00")
        )
        cls.own.grupos.add(cls.team)
        cls.shared = PlazoReporte.objects.create(
            titulo="Entrega para todos", proyecto="GIVIT", fecha_limite=utc("2026-12-01T04:59:00")
        )
        cls.next = PlazoReporte.objects.create(titulo="Inicio de diciembre", fecha_limite=utc("2026-12-01T05:00:00"))
        cls.previous = PlazoReporte.objects.create(
            titulo="Último minuto de octubre", fecha_limite=utc("2026-11-01T04:59:00")
        )
        cls.foreign = PlazoReporte.objects.create(
            titulo="Agenda exclusiva de otro equipo", fecha_limite=utc("2026-11-14T14:00:00")
        )
        cls.foreign.grupos.add(cls.other_team)
        cls.archived = PlazoReporte.objects.create(
            titulo="Plazo archivado de mi equipo", activo=False, fecha_limite=utc("2026-11-15T14:00:00")
        )
        cls.archived.grupos.add(cls.team)

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("notificaciones:mis_plazos")
        self.ics = reverse("notificaciones:calendario_ics")

    def test_default_list_preserves_all_months_and_existing_actions(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["vista"], "lista")
        self.assertEqual(response.context["plazos"].paginator.count, 4)
        self.assertEqual(response.context["mes"], "")
        self.assertContains(response, "Enviar reporte")
        self.assertContains(response, "Descargar plazos (.ics)")
        self.assertNotContains(response, self.foreign.titulo)
        self.assertNotContains(response, self.archived.titulo)

    def test_month_uses_colombian_midnight_in_list_grid_and_export(self):
        params = {"vista": "calendario", "mes": "2026-11"}
        response = self.client.get(self.url, params)
        self.assertEqual(response.context["total_calendario"], 2)
        dias = response.context["dias_calendario"]
        self.assertEqual(len(dias), 42)
        por_fecha = {d["fecha"]: [p.pk for p in d["plazos"]] for d in dias}
        self.assertEqual(por_fecha[datetime.date(2026, 11, 13)], [self.own.pk])
        self.assertEqual(por_fecha[datetime.date(2026, 11, 30)], [self.shared.pk])
        self.assertNotContains(response, self.next.titulo)
        self.assertNotContains(response, self.previous.titulo)
        self.assertContains(response, "23:59")
        response = self.client.get(self.url, {"mes": "2026-11"})
        self.assertEqual({p.pk for p in response.context["plazos"]}, {self.own.pk, self.shared.pk})
        exported = lineas(self.client.get(self.ics, params))
        self.assertIn("DTSTART:20261201T045900Z", exported)
        self.assertNotIn("DTSTART:20261201T050000Z", exported)

    def test_calendar_without_month_redirects_to_explicit_current_month(self):
        with patch("notificaciones.forms.timezone") as reloj:
            reloj.localdate.return_value = datetime.date(2026, 11, 13)
            response = self.client.get(self.url, {"vista": "calendario"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("mes=2026-11", response.url)
        self.assertIn("vista=calendario", response.url)
        response = self.client.get(response.url)
        self.assertContains(response, "Noviembre 2026")

    def test_missing_or_invalid_filters_never_broaden_calendar_or_download(self):
        invalidos = [
            {"mes": "2026-13"},
            {"mes": "2026-1"},
            {"mes": "2026-00"},
            {"mes": "0000-01"},
            {"mes": "0999-01"},
            {"mes": "9999-12"},
            {"mes": "x" * 100},
            {"vista": "calendario", "mes": ""},
            {"vista": "otra"},
            {"estado": "otro"},
            {"proyecto": "INVENTADO"},
            {"q": "x" * 101},
            {"plazo": "²"},
            {"plazo": "-1"},
            {"plazo": "9" * 5000},
        ]
        for params in invalidos:
            with self.subTest(params={k: v[:25] for k, v in params.items()}):
                response = self.client.get(self.url, params)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["filtros_form"].errors)
                self.assertNotContains(response, self.own.titulo)
                self.assertIsNone(response.context["url_exportar"])
                export = self.client.get(self.ics, params)
                self.assertEqual(export.status_code, 400)
                self.assertFalse(export.streaming)
                self.assertNotIn("Content-Disposition", export)
                self.assertContains(export, "Volver a mis plazos", status_code=400)

    def test_search_project_and_status_are_shared_by_all_representations(self):
        params = {"q": "personal", "proyecto": "LEM", "mes": "2026-11"}
        for vista in ["lista", "calendario"]:
            response = self.client.get(self.url, {**params, "vista": vista})
            self.assertContains(response, self.own.titulo)
            self.assertNotContains(response, self.shared.titulo)
        exported = lineas(self.client.get(self.ics, params))
        self.assertEqual(exported.count("BEGIN:VEVENT"), 1)
        self.assertIn("SUMMARY:" + self.own.titulo, exported)

    def test_foreign_identifier_and_query_user_cannot_export_other_groups(self):
        for params in [{"plazo": self.foreign.pk}, {"plazo": self.foreign.pk, "usuario": self.other.pk}]:
            response = self.client.get(self.url, params)
            self.assertEqual(response.context["plazos"].paginator.count, 0)
            exported = lineas(self.client.get(self.ics, params))
            self.assertNotIn("BEGIN:VEVENT", exported)
            self.assertFalse(any(self.foreign.titulo in line for line in exported))
        exported = lineas(self.client.get(self.ics, {"usuario": self.other.pk}))
        self.assertNotIn("SUMMARY:" + self.foreign.titulo, exported)

    def test_current_group_membership_and_archiving_are_checked_on_each_export(self):
        self.assertIn("SUMMARY:" + self.own.titulo, lineas(self.client.get(self.ics)))
        self.user.groups.remove(self.team)
        self.assertNotIn("SUMMARY:" + self.own.titulo, lineas(self.client.get(self.ics)))
        self.user.groups.add(self.team)
        PlazoReporte.objects.filter(pk=self.own.pk).update(activo=False)
        self.assertNotIn("SUMMARY:" + self.own.titulo, lineas(self.client.get(self.ics)))

    def test_calendar_keeps_personal_scope_even_for_a_superuser(self):
        self.user.is_staff = self.user.is_superuser = True
        self.user.save(update_fields=["is_staff", "is_superuser"])
        data = lineas(self.client.get(self.ics, {"mes": "2026-11"}))
        self.assertIn("SUMMARY:" + self.own.titulo, data)
        self.assertNotIn("SUMMARY:" + self.foreign.titulo, data)

    def test_pending_and_overdue_filters_match_list_and_file(self):
        ahora = datetime.datetime.now(UTC)
        futuro = PlazoReporte.objects.create(
            titulo="Estado actual próximo", fecha_limite=ahora + datetime.timedelta(days=1)
        )
        vencido = PlazoReporte.objects.create(
            titulo="Estado actual vencido", fecha_limite=ahora - datetime.timedelta(days=1)
        )
        for estado, esperado in [("pendiente", futuro), ("vencido", vencido)]:
            params = {"q": "Estado actual", "estado": estado}
            response = self.client.get(self.url, params)
            self.assertEqual([p.pk for p in response.context["plazos"]], [esperado.pk])
            data = lineas(self.client.get(self.ics, params))
            self.assertEqual(data.count("BEGIN:VEVENT"), 1)
            self.assertIn("SUMMARY:" + esperado.titulo, data)

    def test_delivery_and_late_status_keep_original_deadline_snapshot(self):
        envio = Envio.objects.create(
            usuario=self.user,
            nombre="Entrega tardía",
            proyecto="LEM",
            tipo_evidencia="Documento",
            plazo=self.own,
            registrado_en=utc("2026-11-13T16:00:00"),
            limite_aplicado=utc("2026-11-13T14:30:00"),
        )
        PlazoReporte.objects.filter(pk=self.own.pk).update(fecha_limite=utc("2026-11-15T14:00:00"))
        params = {"estado": "tardia", "mes": "2026-11"}
        response = self.client.get(self.url, {**params, "vista": "calendario"})
        self.assertEqual(response.context["total_calendario"], 1)
        self.assertContains(response, "Entregado fuera de plazo")
        self.assertIn("Estado: Entregado fuera de plazo", "\n".join(lineas(self.client.get(self.ics, params))))
        envio.refresh_from_db()
        self.assertTrue(envio.entrega_tardia)

    def test_selected_deadline_shows_full_instructions_and_existing_evidence_link(self):
        descripcion = "Indicaciones del equipo. " * 15 + "Último requisito completo."
        PlazoReporte.objects.filter(pk=self.own.pk).update(descripcion=descripcion)
        response = self.client.get(self.url, {"plazo": self.own.pk, "mes": "2026-11"})
        self.assertContains(response, "Último requisito completo.")
        Envio.objects.create(usuario=self.user, nombre="Informe entregado", tipo_evidencia="Documento", plazo=self.own)
        response = self.client.get(self.url, {"plazo": self.own.pk})
        self.assertContains(response, f"plazo={self.own.pk}&amp;usuario={self.user.pk}")

    def test_calendar_works_at_supported_year_boundaries(self):
        for mes in ["1000-01", "9998-12"]:
            response = self.client.get(self.url, {"vista": "calendario", "mes": mes})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.context["dias_calendario"]), 42)
            self.assertIsNone(
                response.context["mes_anterior"] if mes == "1000-01" else response.context["mes_siguiente"]
            )

    def test_calendar_full_and_fragment_keep_same_events_and_private_headers(self):
        params = {"vista": "calendario", "mes": "2026-11"}
        full = self.client.get(self.url, params)
        partial = self.client.get(self.url, params, HTTP_X_WORKSPACE_FRAGMENT="1")
        self.assertEqual(full.context["total_calendario"], partial.context["total_calendario"])
        self.assertContains(partial, "calendar-grid")
        self.assertNotContains(partial, "<html")
        self.assertIn("no-store", partial["Cache-Control"])
        self.assertIn("X-Workspace-Fragment", partial["Vary"])
        self.assertContains(full, "css/calendar.css")

    def test_calendar_does_not_duplicate_events_for_multiple_matching_groups(self):
        self.user.groups.add(self.other_team)
        self.own.grupos.add(self.other_team)
        exported = lineas(self.client.get(self.ics, {"mes": "2026-11"}))
        self.assertEqual(exported.count("SUMMARY:" + self.own.titulo), 1)

    def test_export_is_read_only_and_requires_login(self):
        before = Notificacion.objects.count()
        response = self.client.post(self.ics)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(self.client.head(self.ics).status_code, 200)
        self.assertEqual(Notificacion.objects.count(), before)
        self.client.logout()
        for url in [self.url, self.ics]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith(reverse("login")))

    @override_settings(
        PUBLIC_BASE_URL="https://gesicom.example.invalid", ALLOWED_HOSTS=["testserver", "forged.example.invalid"]
    )
    def test_download_uses_trusted_base_and_stable_uid_across_revisions(self):
        params = {"plazo": self.own.pk}
        first = lineas(self.client.get(self.ics, params))
        PlazoReporte.objects.filter(pk=self.own.pk).update(revision=2, actualizado_en=utc("2026-11-13T18:00:00"))
        second = lineas(self.client.get(self.ics, params, HTTP_HOST="forged.example.invalid"))
        self.assertEqual(
            [linea for linea in first if linea.startswith("UID:")],
            [linea for linea in second if linea.startswith("UID:")],
        )
        self.assertIn("SEQUENCE:2", second)
        self.assertIn("LAST-MODIFIED:20261113T180000Z", second)
        self.assertIn(f"URL:https://gesicom.example.invalid/notificaciones/plazos/?plazo={self.own.pk}", second)
        self.assertFalse(any("forged.example.invalid" in linea for linea in second))

    def test_attachment_is_unicode_private_and_does_not_add_invitations_or_alarms(self):
        response = self.client.get(self.ics, {"mes": "2026-11"})
        self.assertTrue(response.streaming)
        self.assertEqual(response["Content-Type"], "text/calendar; charset=utf-8")
        self.assertIn("mis-plazos-2026-11.ics", response["Content-Disposition"])
        self.assertIn("no-store", response["Cache-Control"])
        data = lineas(response)
        self.assertEqual(data[0], "BEGIN:VCALENDAR")
        self.assertIn("VERSION:2.0", data)
        self.assertIn("TRANSP:TRANSPARENT", data)
        self.assertFalse(
            any(linea.startswith(("ATTENDEE:", "ORGANIZER:", "ATTACH:", "BEGIN:VALARM")) for linea in data)
        )

    def test_text_cannot_inject_calendar_components_or_recipients(self):
        PlazoReporte.objects.filter(pk=self.own.pk).update(
            titulo="Título\r\nATTENDEE:mailto:persona@example.invalid",
            descripcion="Texto; con, comas\\\nBEGIN:VEVENT\r\nSUMMARY:Inyectado\x00",
        )
        data = lineas(self.client.get(self.ics, {"plazo": self.own.pk}))
        self.assertEqual(data.count("BEGIN:VEVENT"), 1)
        self.assertEqual(data.count("END:VEVENT"), 1)
        self.assertFalse(any(linea.startswith("ATTENDEE:") for linea in data))
        self.assertTrue(any(linea.startswith("SUMMARY:Título\\nATTENDEE:") for linea in data))
        self.assertTrue(any("Texto\\; con\\, comas\\\\\\nBEGIN:VEVENT" in linea for linea in data))
        self.assertNotIn("\x00", "\n".join(data))

    def test_export_includes_every_page_with_one_query_for_events(self):
        PlazoReporte.objects.bulk_create(
            [PlazoReporte(titulo=f"Entrega de prueba {i}", fecha_limite=utc("2026-11-20T14:00:00")) for i in range(240)]
        )
        response = self.client.get(self.url, {"mes": "2026-11"})
        self.assertEqual(len(response.context["plazos"]), 20)
        with CaptureQueriesContext(connection) as queries:
            data = lineas(self.client.get(self.ics, {"mes": "2026-11"}))
        self.assertEqual(data.count("BEGIN:VEVENT"), 242)
        self.assertEqual(sum("FROM `notificaciones_plazoreporte`" in q["sql"] for q in queries), 1)
        self.assertLessEqual(len(queries), 6)
        self.assertEqual(len({linea for linea in data if linea.startswith("UID:")}), 242)

    def test_calendar_is_bounded_and_export_keeps_results_beyond_preview_limit(self):
        PlazoReporte.objects.bulk_create(
            [PlazoReporte(titulo=f"Tope mensual {i}", fecha_limite=utc("2026-11-21T14:00:00")) for i in range(510)]
        )
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url, {"vista": "calendario", "mes": "2026-11", "q": "Tope mensual"})
        self.assertTrue(response.context["calendario_truncado"])
        self.assertEqual(response.context["total_calendario"], 500)
        self.assertEqual(sum(len(d["plazos"]) for d in response.context["dias_calendario"]), 500)
        self.assertLessEqual(len(queries), 8)
        data = lineas(self.client.get(self.ics, {"mes": "2026-11", "q": "Tope mensual"}))
        self.assertEqual(data.count("BEGIN:VEVENT"), 510)


class FormatoCalendarioTests(TestCase):
    def test_utf8_lines_fold_at_75_octets_without_splitting_a_character(self):
        for text in [
            "SUMMARY:" + "á" * 150,
            "DESCRIPTION:" + "Investigación 🧪; formación, resultados " * 30,
            "UID:" + "x" * 180,
        ]:
            data = "".join(plegar_linea(text)).encode("utf-8")
            self.assertTrue(all(len(linea) <= 75 for linea in data.split(b"\r\n")))
            self.assertEqual(data.replace(b"\r\n ", b"").decode().removesuffix("\r\n"), text)
        self.assertEqual(escapar_texto("a\r\nb;c,d\\e"), "a\\nb\\;c\\,d\\\\e")

    def test_invalid_public_base_is_not_included_as_a_calendar_url(self):
        for base in [
            "javascript:alert(1)",
            "https://user:password@example.invalid",
            "https://example.invalid\nATTENDEE:a",
            "https://example.invalid:bad",
            "https://example.invalid/?token=secret",
            "https://example.invalid\\host",
        ]:
            with self.subTest(base=base), override_settings(PUBLIC_BASE_URL=base):
                self.assertIsNone(base_publica())

    def test_month_bounds_and_query_url_use_only_known_validated_fields(self):
        form = FiltrosAgendaForm(
            {"vista": "calendario", "mes": "2026-11", "q": "innovación", "usuario": "otro", "password": "no-incluir"}
        )
        self.assertTrue(form.is_valid())
        self.assertNotIn("usuario", form.consulta_url())
        self.assertNotIn("password", form.consulta_url())
        inicio, fin = limites_mes(form.fecha_mes())
        self.assertEqual(inicio.astimezone(UTC), utc("2026-11-01T05:00:00"))
        self.assertEqual(fin.astimezone(UTC), utc("2026-12-01T05:00:00"))
