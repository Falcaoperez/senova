from datetime import timedelta
from html.parser import HTMLParser
from urllib.parse import urlencode

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import iri_to_uri

from cuentas.models import SesionUsuario
from cuentas.sesiones import CLAVE_VERSION
from notificaciones.models import Notificacion


class CamposOcultos(HTMLParser):
    def __init__(self, contenido):
        super().__init__()
        self.campos = {}
        self.feed(contenido.decode())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("type") == "hidden":
            self.campos[attrs.get("name")] = attrs.get("value", "")


class RetornoLoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.clave = "RevisionDeAcceso42!"
        cls.usuario = User.objects.create_user("retorno_login", email="retorno@example.invalid", password=cls.clave)
        cls.usuario.groups.add(Group.objects.get(name="usuario"))

    def setUp(self):
        self.login = reverse("login")
        self.destino = (
            reverse("notificaciones:bandeja") + "?" + urlencode({"q": "reporte SENA", "estado": "pendiente", "page": 2})
        )

    def ingresar(self, *, client=None, **datos):
        return (client or self.client).post(
            self.login, {"username": self.usuario.username, "password": self.clave, **datos}
        )

    def test_una_pagina_protegida_se_recupera_con_sus_filtros_tras_ingresar(self):
        response = self.client.get(self.destino)
        self.assertRedirects(response, self.login + "?" + urlencode({"next": self.destino}))
        formulario = self.client.get(response.url)
        next_url = CamposOcultos(formulario.content).campos["next"]
        self.assertEqual(next_url, self.destino)
        ingreso = self.ingresar(next=next_url)
        self.assertRedirects(ingreso, self.destino)

    def test_error_de_clave_conserva_destino_y_usuario_pero_no_la_clave(self):
        response = self.ingresar(next=self.destino, password="NoEsLaClave42!")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CamposOcultos(response.content).campos["next"], self.destino)
        self.assertContains(response, self.usuario.username)
        self.assertNotContains(response, "NoEsLaClave42!")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_correo_y_ruta_historica_de_login_conservan_el_destino(self):
        response = self.client.post(
            reverse("login_root"), {"username": self.usuario.email, "password": self.clave, "next": self.destino}
        )
        self.assertRedirects(response, self.destino)

    def test_destinos_externos_ambiguos_o_inexistentes_no_se_reflejan_ni_redirigen(self):
        destinos = [
            "https://externo.example/",
            "http://testserver/notificaciones/",
            "https://testserver/notificaciones/",
            "//externo.example/",
            "///externo.example/",
            "/\\externo.example/",
            "\\\\externo.example/",
            "javascript:alert(1)",
            "data:text/html,externo",
            "notificaciones/",
            " /notificaciones/",
            "/notificaciones/\n",
            "/notificaciones/\r\nLocation: https://externo.example/",
            "/notificaciones/\x00",
            "/notificaciones/\x7f",
            "/%2fexterno.example/",
            "/%5cexterno.example/",
            "/media/../login/",
            "/media/%2e%2e/login/",
            "/media/%2E%2e/%2e/login/",
            "/media/%0d%0aarchivo.pdf",
            "/ruta-que-no-existe/",
            "/notificaciones/?q=" + "x" * 2048,
        ]
        for destino in destinos:
            with self.subTest(destino=repr(destino[:60])):
                client = Client()
                formulario = client.get(self.login, {"next": destino})
                self.assertNotIn("next", CamposOcultos(formulario.content).campos)
                ingreso = self.ingresar(client=client, next=destino)
                self.assertEqual(ingreso.url, reverse("usuario"))

    def test_login_y_salida_no_se_usan_como_destinos_de_retorno(self):
        for nombre in ["login", "login_root", "logout", "admin:login", "admin:logout"]:
            with self.subTest(nombre=nombre):
                client = Client()
                destino = reverse(nombre) + "?next=/notificaciones/"
                self.assertNotIn("next", CamposOcultos(client.get(self.login, {"next": destino}).content).campos)
                self.assertEqual(self.ingresar(client=client, next=destino).url, reverse("usuario"))

    def test_post_prevalece_sobre_la_consulta_y_un_valor_vacio_descarta_el_retorno(self):
        url = self.login + "?" + urlencode({"next": reverse("evidencias_list")})
        datos = {"username": self.usuario.username, "password": self.clave}
        self.assertEqual(self.client.post(url, {**datos, "next": self.destino}).url, self.destino)
        self.assertEqual(Client().post(url, {**datos, "next": ""}).url, reverse("usuario"))
        self.assertEqual(Client().post(url, {**datos, "next": "//externo.example/"}).url, reverse("usuario"))
        self.assertEqual(Client().post(url, datos).url, reverse("evidencias_list"))

    def test_destino_con_comillas_y_fragmento_se_escapa_y_se_conserva(self):
        destino = reverse("evidencias_list") + '?q=""><script>alert(1)</script>&estado=pendiente#resultados'
        formulario = self.client.get(self.login, {"next": destino})
        self.assertEqual(CamposOcultos(formulario.content).campos["next"], destino)
        self.assertNotContains(formulario, "<script>alert(1)</script>")
        self.assertEqual(self.ingresar(next=destino).url, iri_to_uri(destino))

    def test_no_se_conceden_permisos_por_elegir_un_destino_administrativo(self):
        destino = reverse("notificaciones:novedades_admin")
        response = self.ingresar(next=destino)
        self.assertEqual(response.url, destino)
        self.assertEqual(self.client.get(destino).status_code, 403)
        self.assertEqual(set(self.usuario.groups.values_list("name", flat=True)), {"usuario"})

    def test_un_nombre_de_archivo_codificado_conserva_su_destino_local(self):
        destino = "/media/Informaci%C3%B3n%20SENA.pdf?descargar=1"
        response = self.client.get(self.login, {"next": destino})
        self.assertEqual(CamposOcultos(response.content).campos["next"], destino)
        self.assertEqual(self.ingresar(next=destino).url, destino)

    def test_sin_destino_se_conservan_los_paneles_y_prioridades_de_rol(self):
        for rol, ruta in [
            ("usuario", "usuario"),
            ("instructor", "role_instructor"),
            ("investigador", "role_investigador"),
            ("dinamizador", "role_dinamizador"),
            ("coordinador", "role_coordinador"),
            ("administrador", "admin_personalizado:dashboard"),
        ]:
            with self.subTest(rol=rol):
                self.usuario.groups.set([Group.objects.get(name=rol)])
                self.assertEqual(self.ingresar(client=Client()).url, reverse(ruta))
        self.usuario.groups.add(Group.objects.get(name="instructor"))
        self.assertEqual(
            self.ingresar(client=Client(), role="instructor").url, reverse("admin_personalizado:dashboard")
        )
        self.usuario.groups.clear()
        self.assertEqual(self.ingresar(client=Client()).url, reverse("home"))
        User.objects.filter(pk=self.usuario.pk).update(is_superuser=True)
        self.assertEqual(self.ingresar(client=Client()).url, reverse("admin_personalizado:dashboard"))

    def test_cuenta_inactiva_no_inicia_sesion_aunque_su_destino_sea_valido(self):
        User.objects.filter(pk=self.usuario.pk).update(is_active=False)
        response = self.ingresar(next=self.destino)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CamposOcultos(response.content).campos["next"], self.destino)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_con_retorno_conserva_csrf_rotacion_de_sesion_y_recordarme(self):
        client = Client(enforce_csrf_checks=True)
        session = client.session
        session["visita_previa"] = True
        session.save()
        anterior = session.session_key
        formulario = client.get(self.login, {"next": self.destino})
        self.assertEqual(self.ingresar(client=client, next=self.destino).status_code, 403)
        response = self.ingresar(
            client=client,
            next=self.destino,
            remember="on",
            csrfmiddlewaretoken=CamposOcultos(formulario.content).campos["csrfmiddlewaretoken"],
        )
        self.assertRedirects(response, self.destino)
        self.assertNotEqual(client.session.session_key, anterior)
        self.assertEqual(client.session.get_expiry_age(), 14 * 24 * 60 * 60)
        self.assertEqual(SesionUsuario.objects.get(sesion_id=client.session.session_key).usuario_id, self.usuario.pk)
        otro = Client()
        self.assertEqual(self.ingresar(client=otro, next=self.destino).status_code, 302)
        self.assertTrue(otro.session.get_expire_at_browser_close())

    def test_formulario_de_login_no_se_almacena_en_cache_y_no_consulta_usuarios(self):
        with self.assertNumQueries(0):
            response = self.client.get(self.login, {"next": self.destino})
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("no-cache", response["Cache-Control"])

    def test_un_retorno_se_abre_con_get_sin_repetir_operaciones_previas(self):
        aviso = Notificacion.objects.create(
            usuario=self.usuario, tipo="novedad", titulo="Sin leer", mensaje="Aviso de prueba"
        )
        accion = reverse("notificaciones:marcar_todas")
        response = self.ingresar(next=accion, alcance="todas")
        self.assertEqual(response.url, accion)
        self.assertEqual(self.client.get(response.url).status_code, 405)
        aviso.refresh_from_db()
        self.assertIsNone(aviso.leida_en)

    @override_settings(SESSION_IDLE_TIMEOUT=1800)
    def test_inactividad_y_version_antigua_conservan_solo_destinos_de_lectura(self):
        for causa in ["inactividad", "version"]:
            with self.subTest(causa=causa):
                client = Client()
                client.force_login(self.usuario)
                if causa == "inactividad":
                    SesionUsuario.objects.filter(sesion_id=client.session.session_key).update(
                        ultimo_uso=timezone.now() - timedelta(minutes=31)
                    )
                else:
                    session = client.session
                    del session[CLAVE_VERSION]
                    session.save()
                response = client.get(self.destino)
                self.assertEqual(response.url, self.login + "?" + urlencode({"next": self.destino}))
                self.assertNotIn("_auth_user_id", client.session)
        client = Client()
        client.force_login(self.usuario)
        SesionUsuario.objects.filter(sesion_id=client.session.session_key).update(
            ultimo_uso=timezone.now() - timedelta(minutes=31)
        )
        self.assertEqual(client.post(reverse("notificaciones:marcar_todas"), {"alcance": "todas"}).url, self.login)

    @override_settings(SESSION_IDLE_TIMEOUT=1800)
    def test_head_caducado_conserva_la_consulta_sin_repetir_su_contenido(self):
        self.client.force_login(self.usuario)
        SesionUsuario.objects.filter(sesion_id=self.client.session.session_key).update(
            ultimo_uso=timezone.now() - timedelta(minutes=31)
        )
        response = self.client.head(self.destino)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.login + "?" + urlencode({"next": self.destino}))
        self.assertEqual(response.content, b"")

    def test_parametros_repetidos_no_permiten_conservar_un_destino_externo(self):
        response = self.client.get(self.login, {"next": [self.destino, "//externo.example/"]})
        self.assertNotIn("next", CamposOcultos(response.content).campos)
        response = self.ingresar(next=[self.destino, "//externo.example/"])
        self.assertEqual(response.url, reverse("usuario"))
