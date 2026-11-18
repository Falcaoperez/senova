"""Reenvíos del formulario sin duplicar publicaciones ni su cola de avisos."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core import mail, signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from ..models import CorreoPendiente, Notificacion, Novedad

DOMINIO = "gesicom.solicitud-novedad.v1"


class PublicacionSeguraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("publicacion_autor")
        cls.other = User.objects.create_user("publicacion_otro_admin")
        grupo_admin = Group.objects.get(name="administrador")
        cls.admin.groups.add(grupo_admin)
        cls.other.groups.add(grupo_admin)
        cls.grupo = Group.objects.get(name="instructor")
        for i in range(4):
            user = User.objects.create_user(f"publicacion_destino_{i}", email=f"publicacion-{i}@example.invalid")
            user.groups.add(cls.grupo)

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse("notificaciones:crear_novedad")

    def token(self, usuario=None):
        return signing.dumps({"usuario": (usuario or self.admin).pk, "codigo": str(uuid.uuid4())}, salt=DOMINIO)

    def datos(self, **extra):
        return {
            "titulo": "Informe de actividades",
            "contenido": "Información del grupo",
            "enlace": "",
            "grupos": [self.grupo.pk],
            **extra,
        }

    def recibos(self):
        from ..models import SolicitudNovedad

        return SolicitudNovedad.objects

    def datos_servicio(self, codigo):
        return {**self.datos(), "grupos": [self.grupo], "solicitud": codigo}

    def test_mismo_formulario_conserva_una_publicacion_y_un_conjunto_de_avisos(self):
        datos = self.datos(solicitud=self.token())
        with patch("notificaciones.services.get_connection") as conectar:
            primero = self.client.post(self.url, datos)
            segundo = self.client.post(self.url, datos)
        self.assertEqual((primero.status_code, segundo.status_code), (302, 302))
        self.assertEqual(Novedad.objects.count(), 1)
        self.assertEqual(Notificacion.objects.count(), 4)
        self.assertEqual(CorreoPendiente.objects.count(), 4)
        self.assertEqual(self.recibos().count(), 1)
        conectar.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)
        self.assertContains(self.client.get(segundo.url), "Este formulario ya había sido enviado")

    def test_get_entrega_un_identificador_por_formulario_sin_crear_recibos(self):
        from ..publicacion import verificar_solicitud_novedad

        uno = self.client.get(self.url).context["form"]["solicitud"].value()
        dos = self.client.get(self.url).context["form"]["solicitud"].value()
        self.assertNotEqual(uno, dos)
        self.assertIsInstance(verificar_solicitud_novedad(uno, self.admin), uuid.UUID)
        self.assertEqual(self.recibos().count(), 0)
        self.assertFalse(Novedad.objects.exists())

    def test_reenvio_incompleto_recupera_el_resultado_sin_sobrescribir_texto_ni_grupos(self):
        token = self.token()
        self.client.post(self.url, self.datos(solicitud=token))
        segundo = self.client.post(self.url, {"solicitud": token, "titulo": "No sobrescribir"})
        self.assertEqual(segundo.status_code, 302)
        self.assertEqual(Novedad.objects.count(), 1)
        novedad = Novedad.objects.get()
        self.assertEqual(novedad.titulo, "Informe de actividades")
        self.assertEqual(novedad.contenido, "Información del grupo")
        self.assertEqual(list(novedad.grupos.all()), [self.grupo])
        self.assertEqual(CorreoPendiente.objects.count(), 4)

    def test_error_de_validacion_no_consume_el_identificador(self):
        token = self.token()
        response = self.client.post(self.url, self.datos(solicitud=token, titulo=""))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(self.recibos().exists())
        self.assertEqual(response.context["form"]["solicitud"].value(), token)
        self.assertEqual(self.client.post(self.url, self.datos(solicitud=token)).status_code, 302)
        self.assertEqual(Novedad.objects.count(), 1)

    def test_formularios_distintos_y_clientes_anteriores_crean_publicaciones_distintas(self):
        for _ in range(2):
            self.assertEqual(self.client.post(self.url, self.datos(solicitud=self.token())).status_code, 302)
        self.assertEqual(self.client.post(self.url, self.datos()).status_code, 302)
        self.assertEqual(Novedad.objects.count(), 3)
        self.assertEqual(self.recibos().count(), 2)
        self.assertEqual(Notificacion.objects.count(), 12)

    def test_identificadores_alterados_ajenos_o_de_evidencias_no_publican(self):
        from Gesicom.solicitudes import crear_solicitud

        for token in [self.token() + "alterado", self.token(self.other), crear_solicitud(self.admin), "x" * 513]:
            response = self.client.post(self.url, self.datos(solicitud=token))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].has_error("solicitud"))
            self.assertFalse(Novedad.objects.exists())
            self.assertFalse(self.recibos().exists())

    def test_identificador_caducado_no_se_acepta(self):
        with patch("django.core.signing.time") as reloj:
            reloj.time.return_value = 1_800_000_000
            token = self.token()
            reloj.time.return_value = 1_800_086_401
            response = self.client.post(self.url, self.datos(solicitud=token))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].has_error("solicitud"))
        self.assertFalse(Novedad.objects.exists())

    def test_publicacion_eliminada_no_reaparece_con_un_reenvio(self):
        token = self.token()
        self.client.post(self.url, self.datos(solicitud=token))
        Novedad.objects.get().delete()
        response = self.client.post(self.url, self.datos(solicitud=token))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "publicación ya fue procesada")
        self.assertFalse(Novedad.objects.exists())
        self.assertIsNone(self.recibos().get().novedad_id)
        self.assertFalse(Notificacion.objects.exists())

    def test_grupo_retirado_no_impide_recuperar_un_envio_aceptado(self):
        grupo = Group.objects.create(name="Equipo temporal de publicación")
        self.admin.groups.add(grupo)
        token = self.token()
        datos = self.datos(solicitud=token, grupos=[grupo.pk])
        self.client.post(self.url, datos)
        grupo.delete()
        self.assertEqual(self.client.post(self.url, datos).status_code, 302)
        self.assertEqual(Novedad.objects.count(), 1)
        self.assertEqual(Notificacion.objects.count(), 1)

    def test_original_reasignado_no_se_modifica_con_el_identificador_anterior(self):
        token = self.token()
        self.client.post(self.url, self.datos(solicitud=token))
        Novedad.objects.update(creada_por=self.other)
        response = self.client.post(self.url, self.datos(solicitud=token))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].non_field_errors())
        self.assertEqual(Novedad.objects.count(), 1)
        self.assertEqual(Novedad.objects.get().creada_por_id, self.other.pk)

    def test_servicio_comprueba_rol_y_estado_actual_de_la_cuenta(self):
        from ..publicacion import publicar_o_recuperar

        datos = self.datos_servicio(uuid.uuid4())
        self.admin.groups.clear()
        with self.assertRaises(PermissionDenied):
            publicar_o_recuperar(self.admin, datos)
        self.admin.groups.add(Group.objects.get(name="administrador"))
        User.objects.filter(pk=self.admin.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            publicar_o_recuperar(self.admin, datos)
        self.assertFalse(Novedad.objects.exists())
        self.assertFalse(self.recibos().exists())

    def test_otro_administrador_no_puede_apropiarse_del_recibo(self):
        from ..publicacion import publicar_o_recuperar

        codigo = uuid.uuid4()
        publicar_o_recuperar(self.admin, self.datos_servicio(codigo))
        with self.assertRaises(PermissionDenied):
            publicar_o_recuperar(self.other, self.datos_servicio(codigo))
        self.assertEqual(Novedad.objects.count(), 1)
        self.assertEqual(self.recibos().get().usuario_id, self.admin.pk)

    def test_fallo_revierte_recibo_publicacion_grupos_avisos_y_cola(self):
        from ..publicacion import publicar_o_recuperar
        from ..services import publicar_novedad

        codigo = uuid.uuid4()

        def fallar(novedad):
            publicar_novedad(novedad)
            raise IntegrityError("Fallo controlado para comprobar rollback")

        with (
            patch("notificaciones.publicacion.publicar_novedad", side_effect=fallar),
            self.assertRaises(IntegrityError),
        ):
            publicar_o_recuperar(self.admin, self.datos_servicio(codigo))
        for modelo in (Novedad, Notificacion, CorreoPendiente):
            self.assertFalse(modelo.objects.exists())
        self.assertFalse(self.recibos().exists())
        resultado = publicar_o_recuperar(self.admin, self.datos_servicio(codigo))
        self.assertFalse(resultado.reutilizado)
        self.assertEqual(resultado.nuevos_avisos, 4)

    def test_administrador_nativo_conserva_su_formulario_y_publicacion(self):
        root = User.objects.create_superuser("publicacion_root", email="root@example.invalid")
        self.client.force_login(root)
        url = reverse("admin:notificaciones_novedad_add")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("solicitud", response.context["adminform"].form.fields)
        response = self.client.post(url, self.datos(_save="Guardar"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Novedad.objects.count(), 1)
        self.assertEqual(Notificacion.objects.count(), 4)

    def test_csrf_y_metodos_se_conservan(self):
        protegido = Client(enforce_csrf_checks=True)
        protegido.force_login(self.admin)
        self.assertEqual(protegido.post(self.url, self.datos(solicitud=self.token())).status_code, 403)
        protegido.get(self.url)
        self.assertEqual(
            protegido.post(
                self.url, self.datos(solicitud=self.token()), HTTP_X_CSRFTOKEN=protegido.cookies["csrftoken"].value
            ).status_code,
            302,
        )
        self.assertEqual(self.client.put(self.url).status_code, 405)
        self.assertEqual(self.client.delete(self.url).status_code, 405)

    def test_la_solicitud_de_publicacion_no_se_acepta_como_una_de_evidencia(self):
        from Gesicom.solicitudes import verificar_solicitud

        with self.assertRaises(ValidationError):
            verificar_solicitud(self.token(), self.admin)

    def test_rotacion_controlada_de_clave_conserva_la_firma_vigente(self):
        from ..publicacion import verificar_solicitud_novedad

        token = self.token()
        anterior = settings.SECRET_KEY
        with override_settings(
            SECRET_KEY="clave-nueva-exclusiva-de-pruebas-de-publicacion-2026", SECRET_KEY_FALLBACKS=[anterior]
        ):
            self.assertIsInstance(verificar_solicitud_novedad(token, self.admin), uuid.UUID)


class PublicacionConcurrenteTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "mysql":
            self.skipTest("Requiere los bloqueos reales de MySQL.")
        self.admin = User.objects.create_user("publicacion_concurrente")
        self.admin.groups.add(Group.objects.get(name="administrador"))
        self.grupo = Group.objects.get(name="instructor")
        User.objects.bulk_create(
            [User(username=f"publicacion_lote_{i}", email=f"lote-{i}@example.invalid", password="!") for i in range(20)]
        )
        User.groups.through.objects.bulk_create(
            [
                User.groups.through(user_id=u.pk, group_id=self.grupo.pk)
                for u in User.objects.filter(username__startswith="publicacion_lote_")
            ]
        )

    def enviar(self, codigo):
        from ..publicacion import publicar_o_recuperar

        close_old_connections()
        try:
            resultado = publicar_o_recuperar(
                User.objects.get(pk=self.admin.pk),
                {
                    "titulo": "Publicación concurrente",
                    "contenido": "Una publicación por formulario",
                    "enlace": "",
                    "grupos": [Group.objects.get(pk=self.grupo.pk)],
                    "solicitud": codigo,
                },
            )
            return resultado.novedad.pk, resultado.nuevos_avisos, resultado.reutilizado
        finally:
            close_old_connections()

    def test_dos_envios_simultaneos_del_mismo_formulario_publican_una_sola_vez(self):
        from ..models import SolicitudNovedad

        codigo = uuid.uuid4()
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(self.enviar, [codigo, codigo]))
        self.assertEqual(len({r[0] for r in resultados}), 1)
        self.assertEqual(sum(r[1] for r in resultados), 20)
        self.assertEqual(sum(r[2] for r in resultados), 1)
        self.assertEqual(SolicitudNovedad.objects.count(), 1)
        self.assertEqual(Novedad.objects.count(), 1)
        self.assertEqual(Notificacion.objects.count(), 20)
        self.assertEqual(CorreoPendiente.objects.count(), 20)

    def test_formularios_simultaneos_distintos_no_se_bloquean_como_duplicados(self):
        from ..models import SolicitudNovedad

        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(self.enviar, [uuid.uuid4(), uuid.uuid4()]))
        self.assertEqual(len({r[0] for r in resultados}), 2)
        self.assertEqual(sum(r[1] for r in resultados), 40)
        self.assertEqual(SolicitudNovedad.objects.count(), 2)
        self.assertEqual(Notificacion.objects.count(), 40)
