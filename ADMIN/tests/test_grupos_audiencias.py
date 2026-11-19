"""La confirmación de borrado conserva las audiencias y no revela sus contenidos."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin, messages
from django.contrib.admin.models import DELETION, LogEntry
from django.contrib.auth.models import Group, Permission, User
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from cuentas.models import RegistroSeguridad
from notificaciones.grupos import MENSAJE_GRUPO_ASIGNADO, MENSAJE_GRUPO_RETIRADO, bloquear_grupos
from notificaciones.models import Notificacion, Novedad, PlazoReporte, SolicitudNovedad
from notificaciones.selectors import destinatarios


class BorradoGrupoAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = User.objects.create_user("operador_borrado_grupos", is_staff=True)
        cls.actor.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="auth", codename__in=["view_group", "delete_group"])
        )
        cls.libre = Group.objects.create(name="Equipo libre de comunicaciones")
        cls.grupo = Group.objects.create(name="Equipo de comunicaciones privadas")
        cls.ajeno = User.objects.create_user("lector_fuera_del_equipo")
        cls.novedad = Novedad.objects.create(titulo="Título que no debe mostrarse al operador", contenido="Privado.")
        cls.novedad.grupos.add(cls.grupo)

    def setUp(self):
        cache.clear()
        self.client.force_login(self.actor)
        self.lista = reverse("admin:auth_group_changelist")

    def test_confirmar_el_borrado_no_convierte_una_novedad_en_publica(self):
        response = self.client.post(reverse("admin:auth_group_delete", args=[self.grupo.pk]), {"post": "yes"})
        self.assertFalse(
            destinatarios(self.novedad.grupos).filter(pk=self.ajeno.pk).exists(),
            "La eliminación nativa no debe ampliar la audiencia.",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Group.objects.filter(pk=self.grupo.pk).exists())
        self.assertNotContains(response, self.novedad.titulo)

    def test_confirmacion_explica_la_reasignacion_sin_mostrar_contenidos(self):
        response = self.client.get(reverse("admin:auth_group_delete", args=[self.grupo.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, MENSAJE_GRUPO_ASIGNADO)
        self.assertNotContains(response, self.novedad.titulo)
        self.assertNotContains(response, 'name="post"')
        self.assertTrue(response.context["protected"])

    def test_un_plazo_archivado_tambien_aparece_protegido(self):
        plazo = PlazoReporte.objects.create(
            titulo="No mostrar este título al operador", fecha_limite=timezone.now(), activo=False
        )
        plazo.grupos.add(self.libre)
        response = self.client.post(reverse("admin:auth_group_delete", args=[self.libre.pk]), {"post": "yes"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, MENSAJE_GRUPO_ASIGNADO)
        self.assertNotContains(response, plazo.titulo)
        self.assertTrue(Group.objects.filter(pk=self.libre.pk).exists())

    def lote(self, ids):
        return self.client.post(self.lista, {"action": "delete_selected", "_selected_action": ids, "post": "yes"})

    def test_borrado_masivo_mixto_conserva_todo_el_lote_y_no_registra_eliminaciones(self):
        response = self.lote([self.libre.pk, self.grupo.pk])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, MENSAJE_GRUPO_ASIGNADO)
        self.assertEqual(Group.objects.filter(pk__in=[self.libre.pk, self.grupo.pk]).count(), 2)
        self.assertFalse(LogEntry.objects.filter(action_flag=DELETION).exists())

    def test_el_grupo_libre_se_elimina_y_queda_en_la_auditoria(self):
        response = self.client.post(reverse("admin:auth_group_delete", args=[self.libre.pk]), {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Group.objects.filter(pk=self.libre.pk).exists())
        self.assertTrue(Group.objects.filter(pk=self.grupo.pk).exists())
        self.assertEqual(LogEntry.objects.filter(action_flag=DELETION).count(), 1)
        self.assertTrue(
            RegistroSeguridad.objects.filter(actor=self.actor, accion="admin:auth_group_delete:302").exists()
        )

    def test_un_lote_de_grupos_libres_sigue_funcionando(self):
        otro = Group.objects.create(name="Otro equipo libre")
        response = self.lote([self.libre.pk, otro.pk])
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Group.objects.filter(pk__in=[self.libre.pk, otro.pk]).exists())
        self.assertEqual(LogEntry.objects.filter(action_flag=DELETION).count(), 2)

    def test_usuarios_sin_permiso_no_pueden_borrar_un_grupo_libre(self):
        staff = User.objects.create_user("lector_de_grupos", is_staff=True)
        staff.user_permissions.add(Permission.objects.get(content_type__app_label="auth", codename="view_group"))
        for usuario, estado in [(self.ajeno, 302), (staff, 403)]:
            with self.subTest(estado=estado):
                client = Client()
                client.force_login(usuario)
                response = client.post(reverse("admin:auth_group_delete", args=[self.libre.pk]), {"post": "yes"})
                self.assertEqual(response.status_code, estado)
                self.assertTrue(Group.objects.filter(pk=self.libre.pk).exists())

    def test_el_superusuario_tambien_debe_reasignar_antes_de_borrar(self):
        root = User.objects.create_superuser("raiz_audiencias", email="raiz@example.invalid")
        self.client.force_login(root)
        response = self.client.post(reverse("admin:auth_group_delete", args=[self.grupo.pk]), {"post": "yes"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, MENSAJE_GRUPO_ASIGNADO)
        self.assertTrue(Group.objects.filter(pk=self.grupo.pk).exists())

    def preview_desactualizado(self):
        modelo_admin = admin.site._registry[Group]
        original = modelo_admin.get_deleted_objects

        def sin_proteccion_previa(objs, request):
            eliminados, conteos, permisos, _ = original(objs, request)
            return eliminados, conteos, permisos, []

        return patch.object(modelo_admin, "get_deleted_objects", side_effect=sin_proteccion_previa)

    def test_cambio_entre_confirmacion_y_borrado_no_genera_error_500_ni_exito_falso(self):
        with self.preview_desactualizado():
            response = self.client.post(reverse("admin:auth_group_delete", args=[self.grupo.pk]), {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.lista)
        avisos = list(messages.get_messages(response.wsgi_request))
        self.assertTrue(any(m.level == messages.ERROR and str(m) == MENSAJE_GRUPO_ASIGNADO for m in avisos))
        self.assertFalse(any(m.level == messages.SUCCESS for m in avisos))
        self.assertTrue(Group.objects.filter(pk=self.grupo.pk).exists())
        self.assertFalse(LogEntry.objects.filter(action_flag=DELETION).exists())

    def test_cambio_concurrente_en_lote_revierte_tambien_la_bitacora_nativa(self):
        with self.preview_desactualizado():
            response = self.lote([self.libre.pk, self.grupo.pk])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Group.objects.filter(pk__in=[self.libre.pk, self.grupo.pk]).count(), 2)
        self.assertFalse(LogEntry.objects.filter(action_flag=DELETION).exists())
        self.assertTrue(any(m.level == messages.ERROR for m in messages.get_messages(response.wsgi_request)))

    def test_el_borrado_individual_y_masivo_mantiene_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.actor)
        for url, datos in [
            (reverse("admin:auth_group_delete", args=[self.libre.pk]), {"post": "yes"}),
            (self.lista, {"action": "delete_selected", "_selected_action": [self.libre.pk], "post": "yes"}),
        ]:
            self.assertEqual(client.post(url, datos).status_code, 403)
            self.assertTrue(Group.objects.filter(pk=self.libre.pk).exists())

    @override_settings(RATE_LIMITS_ENABLED=True)
    @patch("SENNOVA.middleware.time")
    def test_ambos_tipos_de_borrado_tienen_limite_y_regreso_al_listado(self, reloj):
        reloj.time.return_value = 1_800_000_123
        for url, datos in [
            (reverse("admin:auth_group_delete", args=[self.grupo.pk]), {"post": "yes"}),
            (self.lista, {"action": "delete_selected", "_selected_action": [self.grupo.pk], "post": "yes"}),
        ]:
            with self.subTest(url=url):
                cache.clear()
                for _ in range(20):
                    self.assertEqual(self.client.post(url, datos).status_code, 200)
                response = self.client.post(url, datos)
                self.assertEqual(response.status_code, 429)
                self.assertContains(response, self.lista, status_code=429)
                self.assertIn("Retry-After", response)
                self.assertTrue(Group.objects.filter(pk=self.grupo.pk).exists())

    @override_settings(RATE_LIMITS_ENABLED=True)
    def test_fallo_del_limitador_impide_el_borrado_y_mantiene_la_pagina_de_regreso(self):
        with patch("SENNOVA.middleware.cache.add", side_effect=RuntimeError("Caché no disponible")):
            response = self.client.post(reverse("admin:auth_group_delete", args=[self.libre.pk]), {"post": "yes"})
        self.assertContains(response, self.lista, status_code=503)
        self.assertTrue(Group.objects.filter(pk=self.libre.pk).exists())


class AsignacionGruposAdminTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_superuser("autor_nativo_audiencias", email="autor@example.invalid")
        self.grupo = Group.objects.create(name="Equipo elegido en el formulario")
        self.client.force_login(self.actor)

    def datos(self, *, plazo=False):
        if not plazo:
            return {
                "titulo": "Novedad privada",
                "contenido": "Solo para el equipo.",
                "grupos": [self.grupo.pk],
                "_save": "Guardar",
            }
        return {
            "titulo": "Plazo privado",
            "descripcion": "Solo para el equipo.",
            "proyecto": "LEM",
            "fecha_limite": timezone.localtime(timezone.now() + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M"),
            "recordatorio_horas": 24,
            "activo": "on",
            "grupos": [self.grupo.pk],
            "_save": "Guardar",
        }

    def retirar_antes_del_bloqueo(self, grupos):
        Group.objects.filter(pk=self.grupo.pk).delete()
        return bloquear_grupos(grupos)

    def test_altas_nativas_muestran_error_de_campo_si_el_grupo_desaparece(self):
        for plazo, nombre, modelo in [
            (False, "admin:notificaciones_novedad_add", Novedad),
            (True, "admin:notificaciones_plazoreporte_add", PlazoReporte),
        ]:
            with self.subTest(plazo=plazo):
                if not Group.objects.filter(pk=self.grupo.pk).exists():
                    self.grupo = Group.objects.create(name="Equipo de la segunda operación")
                with patch("notificaciones.forms.bloquear_grupos", side_effect=self.retirar_antes_del_bloqueo):
                    response = self.client.post(reverse(nombre), self.datos(plazo=plazo))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["adminform"].form.has_error("grupos"))
                self.assertContains(response, MENSAJE_GRUPO_RETIRADO)
                self.assertFalse(modelo.objects.exists())
                self.assertFalse(Notificacion.objects.exists())

    def test_altas_personalizadas_rechazan_grupos_desaparecidos_sin_publicacion_parcial(self):
        for plazo, nombre, modulo, modelo in [
            (False, "notificaciones:crear_novedad", "notificaciones.publicacion", Novedad),
            (True, "notificaciones:crear_plazo", "notificaciones.plazos", PlazoReporte),
        ]:
            with self.subTest(plazo=plazo):
                with patch(modulo + ".bloquear_grupos", side_effect=self.retirar_antes_del_bloqueo):
                    response = self.client.post(reverse(nombre), self.datos(plazo=plazo))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].non_field_errors())
                self.assertContains(response, MENSAJE_GRUPO_RETIRADO)
                self.assertFalse(modelo.objects.exists())
                self.assertFalse(Notificacion.objects.exists())
                self.assertFalse(SolicitudNovedad.objects.exists())
