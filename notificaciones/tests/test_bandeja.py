"""Aislamiento de bandejas y comprobaciones de pertinencia antes del envío."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from Gesicom.models import Envio

from ..acceso import enlace_seguro
from ..bandeja import cambiar_lectura, regreso_bandeja
from ..models import CorreoPendiente, Notificacion, Novedad, PlazoReporte
from ..services import anunciar_plazo, procesar_correos, publicar_novedad, sincronizar_plazos

User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class BandejaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("bandeja_propia", "propia@example.invalid")
        self.other = User.objects.create_user("bandeja_ajena", "ajena@example.invalid")
        self.client.force_login(self.user)
        self.propia = Notificacion.objects.create(
            usuario=self.user, tipo="novedad", titulo="Convocatoria", mensaje="Innovación y formación"
        )
        self.leida = Notificacion.objects.create(
            usuario=self.user,
            tipo="evidencia",
            titulo="Evidencia revisada",
            mensaje="Observación",
            leida_en=timezone.now(),
        )
        self.ajena = Notificacion.objects.create(
            usuario=self.other, tipo="novedad", titulo="Convocatoria privada", mensaje="No mostrar"
        )

    def test_search_type_and_read_state_always_respect_owner(self):
        response = self.client.get(
            reverse("notificaciones:bandeja"), {"q": "Innovación", "tipo": "novedad", "estado": "pendiente"}
        )
        self.assertEqual([a.pk for a in response.context["avisos"]], [self.propia.pk])
        self.assertEqual(response.context["sin_leer"], 1)
        response = self.client.get(reverse("notificaciones:bandeja"), {"estado": "leida"})
        self.assertEqual([a.pk for a in response.context["avisos"]], [self.leida.pk])
        response = self.client.get(reverse("notificaciones:bandeja"), {"aviso": self.ajena.pk})
        self.assertEqual(response.context["avisos"].paginator.count, 0)

    def test_batch_change_is_atomic_if_any_id_belongs_to_someone_else(self):
        response = self.client.post(
            reverse("notificaciones:lectura_seleccion"), {"avisos": [self.propia.pk, self.ajena.pk], "accion": "leida"}
        )
        self.assertEqual(response.status_code, 404)
        self.propia.refresh_from_db()
        self.ajena.refresh_from_db()
        self.assertIsNone(self.propia.leida_en)
        self.assertIsNone(self.ajena.leida_en)

    def test_selection_is_bounded_and_requires_a_valid_action(self):
        for payload in [
            {"avisos": [self.propia.pk] * 101, "accion": "leida"},
            {"avisos": ["999999999999999999999999"], "accion": "leida"},
            {"avisos": ["x"], "accion": "leida"},
            {"avisos": [self.propia.pk], "accion": "borrar"},
            {"accion": "leida"},
        ]:
            response = self.client.post(reverse("notificaciones:lectura_seleccion"), payload)
            self.assertEqual(response.status_code, 302)
        self.propia.refresh_from_db()
        self.assertIsNone(self.propia.leida_en)

    def test_read_and_unread_preserve_first_read_timestamp_and_filters(self):
        target = reverse("notificaciones:bandeja") + "?q=Convocatoria&estado=pendiente"
        url = reverse("notificaciones:lectura", args=[self.propia.pk])
        response = self.client.post(url, {"accion": "leida", "next": target})
        self.assertRedirects(response, target)
        self.propia.refresh_from_db()
        primera = self.propia.leida_en
        self.assertEqual(cambiar_lectura(self.user, [str(self.propia.pk)], "leida"), 0)
        self.propia.refresh_from_db()
        self.assertEqual(self.propia.leida_en, primera)
        self.client.post(url, {"accion": "pendiente", "next": "https://attacker.invalid"})
        self.propia.refresh_from_db()
        self.assertIsNone(self.propia.leida_en)

    def test_mark_filtered_results_does_not_change_other_results_or_accounts(self):
        self.client.post(
            reverse("notificaciones:marcar_todas"), {"alcance": "filtradas", "tipo": "novedad", "q": "Convocatoria"}
        )
        self.propia.refresh_from_db()
        self.ajena.refresh_from_db()
        self.assertIsNotNone(self.propia.leida_en)
        self.assertIsNone(self.ajena.leida_en)
        self.assertTrue(Notificacion.objects.filter(pk=self.leida.pk, leida_en__isnull=False).exists())

    def test_post_actions_require_csrf(self):
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.user)
        for name, args in [("lectura", [self.propia.pk]), ("lectura_seleccion", []), ("marcar_todas", [])]:
            self.assertEqual(
                secure.post(reverse("notificaciones:" + name, args=args), {"accion": "leida"}).status_code, 403
            )

    def test_safe_return_accepts_only_the_same_inbox_path(self):
        bandeja = reverse("notificaciones:bandeja")
        for target in [
            "//attacker.invalid",
            "/\\attacker.invalid",
            "https://attacker.invalid",
            "/administracion/",
            bandeja + "\n",
        ]:
            self.assertEqual(regreso_bandeja(target), bandeja)
        self.assertEqual(regreso_bandeja(bandeja + "?tipo=novedad&page=2"), bandeja + "?tipo=novedad&page=2")

    def test_deleted_evidence_opens_inbox_instead_of_a_broken_destination(self):
        self.assertRedirects(
            self.client.post(reverse("notificaciones:abrir", args=[self.leida.pk])), reverse("notificaciones:bandeja")
        )

    def test_revoked_deadline_and_archived_notice_do_not_open_upload_form(self):
        plazo = PlazoReporte.objects.create(titulo="Asignación", fecha_limite=timezone.now() + timedelta(days=1))
        aviso = Notificacion.objects.create(
            usuario=self.user, plazo=plazo, tipo="apertura", titulo="Reporte", mensaje="Entregar"
        )
        plazo.grupos.add(Group.objects.get(name="instructor"))
        response = self.client.post(reverse("notificaciones:abrir", args=[aviso.pk]), follow=True)
        self.assertContains(response, "ya no está asignado")
        plazo.activo = False
        plazo.save(update_fields=["activo"])
        response = self.client.post(reverse("notificaciones:abrir", args=[aviso.pk]), follow=True)
        self.assertContains(response, "fue archivado")

    def test_notification_links_reject_unsafe_url_forms(self):
        for value in [
            "javascript:alert(1)",
            "//attacker.invalid",
            "/\\attacker.invalid",
            "https://user:password@example.com/",
            "https://example.com/\nnext",
            "http://[invalid/",
        ]:
            self.assertIsNone(enlace_seguro(value), value)
        self.assertEqual(enlace_seguro("https://example.com/news?q=sena"), "https://example.com/news?q=sena")
        self.assertEqual(enlace_seguro("/notificaciones/?estado=pendiente"), "/notificaciones/?estado=pendiente")

    def test_news_with_deleted_author_or_unsafe_legacy_link_render_safely(self):
        admin = User.objects.create_superuser("noticias_admin", "noticias@example.invalid", "PruebaNoticia29!")
        Novedad.objects.create(titulo="Archivo histórico", contenido="Autor eliminado", enlace="javascript:alert(1)")
        self.client.force_login(admin)
        response = self.client.get(reverse("notificaciones:novedades_admin"), {"q": "histórico"})
        self.assertContains(response, "Cuenta no disponible")
        self.assertNotContains(response, 'href="javascript:')


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PertinenciaColaTests(TestCase):
    def setUp(self):
        self.grupo = Group.objects.get(name="instructor")
        self.user = User.objects.create_user("cola_actual", "cola_actual@example.invalid")
        self.user.groups.add(self.grupo)
        self.plazo = PlazoReporte.objects.create(titulo="Entrega", fecha_limite=timezone.now() + timedelta(hours=2))
        self.plazo.grupos.add(self.grupo)

    def news(self):
        novedad = Novedad.objects.create(titulo="Nueva publicación", contenido="Contenido")
        novedad.grupos.add(self.grupo)
        publicar_novedad(novedad)
        return novedad

    def test_delivered_report_cancels_already_queued_reminder(self):
        sincronizar_plazos()
        Envio.objects.create(usuario=self.user, nombre="Ya entregado", plazo=self.plazo)
        self.assertEqual(procesar_correos(), 0)
        self.assertEqual(CorreoPendiente.objects.get().estado, "cancelado")
        self.assertEqual(len(mail.outbox), 0)

    def test_changed_deadline_version_cancels_stale_opening_mail(self):
        anunciar_plazo(self.plazo)
        PlazoReporte.objects.filter(pk=self.plazo.pk).update(version=2)
        self.assertEqual(procesar_correos(), 0)
        self.assertEqual(CorreoPendiente.objects.get().estado, "cancelado")

    def test_inactive_user_is_rechecked_after_queueing(self):
        self.news()
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(procesar_correos(), 0)
        self.assertEqual(CorreoPendiente.objects.get().estado, "cancelado")

    def test_changed_audience_is_rechecked_after_queueing(self):
        self.news()
        self.user.groups.clear()
        self.assertEqual(procesar_correos(), 0)
        self.assertEqual(CorreoPendiente.objects.get().estado, "cancelado")

    def test_deleted_queue_row_is_never_recreated_by_a_worker(self):
        noticia = self.news()

        def enviar(*args, **kwargs):
            noticia.delete()
            return 1

        with patch("notificaciones.services.EmailMultiAlternatives.send", side_effect=enviar):
            self.assertEqual(procesar_correos(), 1)
        self.assertFalse(CorreoPendiente.objects.exists())
        self.assertFalse(Notificacion.objects.exists())

    def test_cancellation_during_transport_failure_is_not_retried(self):
        self.news()

        def fallar(*args, **kwargs):
            CorreoPendiente.objects.update(estado="cancelado")
            raise RuntimeError("Fallo de transporte")

        with patch("notificaciones.services.EmailMultiAlternatives.send", side_effect=fallar):
            self.assertEqual(procesar_correos(), 0)
        self.assertEqual(CorreoPendiente.objects.get().estado, "cancelado")

    def test_heartbeat_is_refreshed_while_processing_a_long_batch(self):
        self.news()
        base = timezone.now()
        ticks = iter(base + timedelta(seconds=31 * i) for i in range(20))
        with (
            patch("notificaciones.services.timezone", wraps=timezone) as reloj,
            patch("django.core.cache.cache.set") as latido,
        ):
            reloj.now.side_effect = lambda: next(ticks)
            self.assertEqual(procesar_correos(), 1)
        latido.assert_called()
        self.assertEqual(latido.call_args.args[0], "notificaciones:trabajador")
