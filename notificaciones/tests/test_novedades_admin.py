"""Filtros administrativos y métricas de las novedades visibles."""

import datetime
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from ..models import CorreoPendiente, Notificacion, Novedad


class NovedadesAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("novedades_operadora", first_name="Ana", last_name="Gómez")
        cls.admin.groups.add(Group.objects.get(name="administrador"))
        cls.usuarios = [User.objects.create_user(f"novedades_destino_{i}") for i in range(4)]
        cls.general = Novedad.objects.create(
            titulo="Jornada de innovación", contenido="Mensaje general", creada_por=cls.admin
        )
        cls.dirigida = Novedad.objects.create(
            titulo="Informe del equipo", contenido="Convocatoria dirigida", creada_por=cls.admin
        )
        cls.dirigida.grupos.add(*Group.objects.filter(name__in=["instructor", "investigador"]))
        cls.sin_correo = Novedad.objects.create(titulo="Boletín sin correo", contenido="Actualización interna")
        cls.vacia = Novedad.objects.create(
            titulo="Sin destinatarios", contenido="Información general", creada_por=cls.admin
        )
        for i, estado in enumerate(["enviado", "pendiente", "error", "cancelado"]):
            aviso = Notificacion.objects.create(
                usuario=cls.usuarios[i],
                novedad=cls.general,
                tipo="novedad",
                titulo=cls.general.titulo,
                mensaje="Contenido no necesario para las métricas",
                leida_en=timezone.now() if i % 2 == 0 else None,
            )
            CorreoPendiente.objects.create(notificacion=aviso, estado=estado)
        for i in range(2):
            aviso = Notificacion.objects.create(
                usuario=cls.usuarios[i],
                novedad=cls.dirigida,
                tipo="novedad",
                titulo=cls.dirigida.titulo,
                mensaje="Otro aviso",
                leida_en=timezone.now() if i == 1 else None,
            )
            if i == 0:
                CorreoPendiente.objects.create(notificacion=aviso, estado="procesando")
        Notificacion.objects.create(
            usuario=cls.usuarios[2],
            novedad=cls.sin_correo,
            tipo="novedad",
            titulo="Sin correo",
            mensaje="Aviso interno",
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse("notificaciones:novedades_admin")

    def ids(self, **params):
        return {n.pk for n in self.client.get(self.url, params).context["novedades"]}

    def test_busqueda_larga_no_se_recorta_para_ampliar_los_resultados(self):
        Novedad.objects.create(titulo="N" * 100, contenido="Coincidencia del prefijo")
        response = self.client.get(self.url, {"q": "N" * 101})
        self.assertEqual(response.context["novedades"].paginator.count, 0)
        self.assertTrue(response.context["filtros_form"].errors)

    def test_lectura_de_creadores_no_carga_campos_privados_de_la_cuenta(self):
        with CaptureQueriesContext(connection) as consultas:
            response = self.client.get(self.url)
        self.assertEqual(len(response.context["novedades"]), 4)
        lecturas = [
            c["sql"] for c in consultas if "FROM " + connection.ops.quote_name(Novedad._meta.db_table) in c["sql"]
        ]
        self.assertTrue(lecturas)
        for sql in lecturas:
            for campo in ("password", "email", "is_superuser", "last_login"):
                self.assertNotIn(connection.ops.quote_name(campo), sql)

    def test_audiencia_distingue_general_y_grupos_sin_duplicar_novedades(self):
        self.assertSetEqual(self.ids(audiencia="general"), {self.general.pk, self.sin_correo.pk, self.vacia.pk})
        self.assertSetEqual(self.ids(audiencia="grupos"), {self.dirigida.pk})

    def test_correo_distingue_cola_errores_aceptados_cancelados_y_sin_preparar(self):
        for estado, esperados in [
            ("pendientes", {self.general.pk, self.dirigida.pk}),
            ("error", {self.general.pk}),
            ("enviado", {self.general.pk}),
            ("cancelado", {self.general.pk}),
            ("sin_correo", {self.sin_correo.pk, self.vacia.pk}),
        ]:
            with self.subTest(estado=estado):
                self.assertSetEqual(self.ids(correo=estado), esperados)

    def test_filtros_combinados_y_busqueda_de_titulo_o_contenido(self):
        self.assertSetEqual(self.ids(audiencia="grupos", correo="pendientes", q="convocatoria"), {self.dirigida.pk})
        self.assertSetEqual(self.ids(audiencia="grupos", correo="error"), set())
        self.assertSetEqual(self.ids(q="innovación"), {self.general.pk})

    def test_opciones_invalidas_y_caracter_nulo_muestran_error_sin_resultados(self):
        for params in [{"audiencia": "otra"}, {"correo": "otro"}, {"q": "\x00"}, {"q": "x" * 101}]:
            with self.subTest(params=params):
                response = self.client.get(self.url, params)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["filtros_form"].errors)
                self.assertEqual(response.context["novedades"].paginator.count, 0)
                self.assertContains(response, "Revisa los filtros antes de continuar.")

    def test_metricas_conservan_todos_los_avisos_al_filtrar_por_un_estado(self):
        novedad = self.client.get(self.url, {"correo": "error"}).context["novedades"][0]
        self.assertEqual(novedad.pk, self.general.pk)
        self.assertEqual(novedad.destinatarios_total, 4)
        self.assertEqual(novedad.leidas_total, 2)
        self.assertEqual(novedad.enviados_total, 1)
        self.assertEqual(novedad.pendientes_total, 1)
        self.assertEqual(novedad.errores_total, 1)
        self.assertEqual(novedad.cancelados_total, 1)
        self.assertEqual(novedad.sin_correo_total, 0)
        self.assertEqual(novedad.lectura_porcentaje, 50)

    def test_varios_grupos_no_multiplican_los_conteos_y_procesando_cuenta_en_cola(self):
        novedad = self.client.get(self.url, {"audiencia": "grupos"}).context["novedades"][0]
        self.assertEqual(len(novedad.grupos.all()), 2)
        self.assertEqual(novedad.destinatarios_total, 2)
        self.assertEqual(novedad.leidas_total, 1)
        self.assertEqual(novedad.pendientes_total, 1)
        self.assertEqual(novedad.sin_correo_total, 1)

    def test_sin_destinatarios_y_autor_ausente_se_presentan_sin_division_por_cero(self):
        response = self.client.get(self.url, {"correo": "sin_correo"})
        registros = {n.pk: n for n in response.context["novedades"]}
        self.assertEqual(registros[self.vacia.pk].lectura_porcentaje, 0)
        self.assertEqual(registros[self.vacia.pk].destinatarios_total, 0)
        self.assertContains(response, "Cuenta no disponible")
        self.assertContains(response, "Sin correos preparados")

    def test_lectura_no_publica_no_reintenta_y_no_abre_smtp(self):
        antes = (Notificacion.objects.count(), CorreoPendiente.objects.count())
        with patch("notificaciones.services.get_connection") as conectar:
            self.client.get(self.url, {"correo": "error"})
        conectar.assert_not_called()
        self.assertEqual((Notificacion.objects.count(), CorreoPendiente.objects.count()), antes)
        self.assertEqual(CorreoPendiente.objects.filter(estado="error").count(), 1)

    def test_otras_funciones_y_personal_sin_rol_no_pueden_consultar(self):
        for rol in ["usuario", "instructor", "investigador", "coordinador", "dinamizador"]:
            usuario = self.usuarios[0]
            usuario.groups.set([Group.objects.get(name=rol)])
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(self.url, {"correo": "error"}).status_code, 403)
        usuario.groups.clear()
        usuario.is_staff = True
        usuario.save(update_fields=["is_staff"])
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_superusuario_sin_rol_y_revocacion_del_administrador(self):
        root = User.objects.create_superuser("novedades_supervisor", email="root@example.invalid")
        self.client.force_login(root)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.client.force_login(self.admin)
        self.admin.groups.clear()
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_pagina_requiere_autenticacion_y_solo_admite_get_head(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.head(self.url).status_code, 200)
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_fragmentos_comparten_resultados_y_actualizan_cola_y_lista(self):
        full = self.client.get(self.url, {"audiencia": "grupos"})
        part = self.client.get(self.url, {"audiencia": "grupos"}, HTTP_X_WORKSPACE_FRAGMENT="1")
        self.assertEqual([n.pk for n in full.context["novedades"]], [n.pk for n in part.context["novedades"]])
        self.assertContains(part, 'data-live-region="news-mail"', count=1)
        self.assertContains(part, 'data-live-region="news"', count=1)
        self.assertNotContains(part, "<html")
        self.assertIn("no-store", part["Cache-Control"])
        self.assertIn("X-Workspace-Fragment", part["Vary"])

    def test_fechas_colombianas_independientes_del_huso_activo(self):
        Novedad.objects.filter(pk=self.general.pk).update(
            publicada_en=datetime.datetime(2026, 11, 18, 4, 59, tzinfo=datetime.UTC)
        )
        with timezone.override("Asia/Tokyo"):
            response = self.client.get(self.url, {"q": "innovación"})
        self.assertContains(response, 'datetime="2026-11-17T23:59:00-05:00"')

    def test_paginacion_conserva_solo_los_filtros_validados(self):
        Novedad.objects.bulk_create(
            [Novedad(titulo=f"Paginar novedad {i:02}", contenido="Contenido") for i in range(30)]
        )
        response = self.client.get(
            self.url,
            {"q": "Paginar novedad", "audiencia": "general", "correo": "sin_correo", "token": "no-propagar-qa"},
        )
        self.assertContains(response, "q=Paginar+novedad&amp;audiencia=general&amp;correo=sin_correo&amp;page=2")
        self.assertNotContains(response, "no-propagar-qa")
        self.assertEqual(len(response.context["novedades"]), 20)

    def test_textos_se_escapan_y_sql_sigue_parametrizado(self):
        Novedad.objects.create(titulo="<script>alert(1)</script>", contenido='<img src=x onerror="alert(2)">')
        response = self.client.get(self.url, {"q": "<script>"})
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertSetEqual(self.ids(q="' OR 1=1 --"), set())


class EscalaNovedadesAdminTests(TestCase):
    def test_metricas_y_grupos_solo_de_la_pagina_no_generan_n_mas_uno(self):
        from ..forms import FiltrosNovedadesForm
        from ..novedades import pagina_novedades

        autor = User.objects.create_user("novedades_escala_autor")
        destino = User.objects.create_user("novedades_escala_destino")
        Novedad.objects.bulk_create(
            [Novedad(titulo=f"Escala {i:04}", contenido="C" * 1000, creada_por=autor) for i in range(1200)]
        )
        registros = list(Novedad.objects.order_by("pk"))
        grupo = Group.objects.get(name="instructor")
        Novedad.grupos.through.objects.bulk_create(
            [Novedad.grupos.through(novedad_id=n.pk, group_id=grupo.pk) for n in registros[::2]]
        )
        Notificacion.objects.bulk_create(
            [
                Notificacion(usuario=destino, novedad=n, tipo="novedad", titulo="Aviso", mensaje="No cargar" * 300)
                for n in registros
            ]
        )
        with CaptureQueriesContext(connection) as consultas:
            pagina = pagina_novedades(FiltrosNovedadesForm({}), 1)
            for novedad in pagina:
                novedad.creada_por.get_full_name()
                list(novedad.grupos.all())
        self.assertEqual(pagina.paginator.count, 1200)
        self.assertEqual(len(pagina), 20)
        self.assertEqual(len(consultas), 4)
        self.assertNotIn("GROUP BY", consultas[0]["sql"])
        self.assertIn("LIMIT 20", consultas[1]["sql"])
        self.assertTrue(all(n.destinatarios_total == 1 for n in pagina))
        for consulta in consultas:
            for campo in ("password", "email", "is_superuser", "mensaje", "ultimo_error"):
                self.assertNotIn(connection.ops.quote_name(campo), consulta["sql"])
        metricas = consultas[-1]["sql"]
        ids = metricas.split(connection.ops.quote_name("novedad_id") + " IN (", 1)[1].split(")", 1)[0]
        self.assertSetEqual({int(pk.strip()) for pk in ids.split(",")}, {n.pk for n in pagina})
        print("ESCALA novedades / 1200 publicaciones: 4 consultas; autores mínimos, grupos y métricas de 20 filas.")
