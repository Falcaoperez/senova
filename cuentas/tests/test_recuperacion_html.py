"""Recuperación progresiva con las mismas protecciones para HTML y JSON."""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.db import close_old_connections, connection
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from cuentas.correos import procesar_correos_seguridad
from cuentas.models import CorreoSeguridad, PasswordResetToken
from cuentas.presentacion import prefiere_html

HTML = {"HTTP_ACCEPT": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
PASSWORD = "ClaveRenovadaAzul54!"


class NegociacionRecuperacionTests(SimpleTestCase):
    def test_accept_predeterminado_comodines_y_json_conservan_la_api(self):
        for accept in [
            "",
            "*/*",
            "application/json",
            "application/json,text/html",
            "text/html;q=0,application/json",
            "text/html;q=.2,application/json;q=.9",
        ]:
            request = RequestFactory().post("/api/olvide_password/", HTTP_ACCEPT=accept)
            with self.subTest(accept=accept):
                self.assertFalse(prefiere_html(request))

    def test_navegacion_html_explicita_usa_formularios(self):
        for accept in [HTML["HTTP_ACCEPT"], "text/html", "application/json;q=.5,text/html;q=1"]:
            self.assertTrue(prefiere_html(RequestFactory().post("/api/olvide_password/", HTTP_ACCEPT=accept)))


@override_settings(RATE_LIMITS_ENABLED=False, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RecuperacionHTMLTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "recuperacion_nativa", email="recuperacion@example.invalid", password="AnteriorDePrueba76!"
        )
        cache.clear()

    def solicitar(self, cliente=None):
        cliente = cliente or self.client
        response = cliente.post(reverse("olvide_password"), {"email": self.user.email}, **HTML)
        self.assertRedirects(response, reverse("password_reset_update"), fetch_redirect_response=False)
        procesar_correos_seguridad()
        return re.search(r"\b[0-9]{6}\b", mail.outbox[-1].body).group()

    def verificar(self, pin, cliente=None):
        return (cliente or self.client).post(
            reverse("verificar_pin"), {"email": self.user.email, "codigo": pin}, **HTML
        )

    def cambiar(self, cliente=None, **cambios):
        return (cliente or self.client).post(
            reverse("restablecer_password"), {"password": PASSWORD, "password_confirm": PASSWORD, **cambios}, **HTML
        )

    def test_tres_pasos_nativos_y_reutilizacion_rechazada(self):
        pin = self.solicitar()
        self.assertRedirects(self.verificar(pin), reverse("password_reset_new"), fetch_redirect_response=False)
        self.assertRedirects(self.cambiar(), reverse("password_reset_complete"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))
        self.assertEqual(self.cambiar().status_code, 403)
        self.assertEqual(self.verificar(pin).status_code, 400)

    def test_cuenta_desconocida_tiene_la_misma_redireccion_sin_correo_ni_fuga(self):
        real = self.client.post(reverse("olvide_password"), {"email": self.user.email}, **HTML)
        desconocida = self.client.post(reverse("olvide_password"), {"email": "ausente@example.invalid"}, **HTML)
        self.assertEqual((real.status_code, real["Location"]), (desconocida.status_code, desconocida["Location"]))
        self.assertEqual(CorreoSeguridad.objects.count(), 1)
        self.assertContains(self.client.get(reverse("password_reset_update")), "ausente@example.invalid")

    def test_correo_invalido_se_conserva_escapado_y_no_crea_solicitud(self):
        response = self.client.post(reverse("olvide_password"), {"email": '<img src=x onerror="alert(1)">'}, **HTML)
        self.assertContains(response, "Ingresa un correo válido", status_code=400)
        self.assertContains(response, "&lt;img", status_code=400)
        self.assertNotContains(response, "<img src=x", status_code=400)
        self.assertEqual(PasswordResetToken.objects.count(), 0)

    def test_pin_erroneo_conserva_correo_pero_nunca_muestra_el_codigo(self):
        pin = self.solicitar()
        wrong = "112233" if pin != "112233" else "223344"
        response = self.verificar(wrong)
        self.assertContains(response, "El PIN no es válido", status_code=400)
        self.assertContains(response, self.user.email, status_code=400)
        self.assertNotContains(response, f'value="{wrong}"', status_code=400)
        self.assertEqual(PasswordResetToken.objects.get(usuario=self.user, utilizado=False).intentos, 1)

    def test_pin_debe_ser_ascii_y_mantiene_limite_de_cinco_intentos(self):
        pin = self.solicitar()
        for invalido in ["１２３４５６", "١٢٣٤٥٦", "12345", "12a456"]:
            response = self.verificar(invalido)
            self.assertContains(response, "PIN de seis dígitos", status_code=400)
        wrong = "112233" if pin != "112233" else "223344"
        for _ in range(5):
            self.assertEqual(self.verificar(wrong).status_code, 400)
        self.assertEqual(self.verificar(pin).status_code, 400)

    def test_caducidad_y_solicitud_nueva_invalidan_la_prueba(self):
        pin = self.solicitar()
        PasswordResetToken.objects.filter(usuario=self.user).update(expira_en=timezone.now())
        self.assertEqual(self.verificar(pin).status_code, 400)
        pin = self.solicitar()
        self.verificar(pin)
        self.solicitar()
        self.assertEqual(self.cambiar().status_code, 403)

    def test_verificacion_no_se_transfiere_a_otra_sesion(self):
        self.verificar(self.solicitar())
        ajeno = Client()
        response = self.cambiar(ajeno)
        self.assertContains(response, "Verifica primero", status_code=403)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("AnteriorDePrueba76!"))

    def test_volver_al_pin_ya_verificado_continua_al_paso_de_password(self):
        self.verificar(self.solicitar())
        response = self.client.get(reverse("password_reset_update"))
        self.assertRedirects(response, reverse("password_reset_new"))
        self.assertIn("no-store", response["Cache-Control"])

    def test_cuenta_verificada_solo_se_muestra_a_la_sesion_autorizada(self):
        self.verificar(self.solicitar())
        response = self.client.get(reverse("password_reset_new"))
        self.assertContains(response, self.user.email)
        rechazado = Client().get(reverse("password_reset_new"))
        self.assertEqual(rechazado.status_code, 302)
        self.assertNotIn(self.user.email, rechazado.content.decode())
        debil = self.cambiar(password="short", password_confirm="short")
        self.assertContains(debil, self.user.email, status_code=400)

    def test_errores_de_password_no_se_reflejan_en_html_y_permiten_corregir(self):
        self.verificar(self.solicitar())
        for cambios in [
            {"password_confirm": "OtraClaveNoReflejar44!"},
            {"password": "short", "password_confirm": "short"},
        ]:
            response = self.cambiar(**cambios)
            self.assertEqual(response.status_code, 400)
            self.assertNotContains(response, PASSWORD, status_code=400)
            self.assertNotContains(response, 'value="short"', status_code=400)
            self.assertNotContains(response, "OtraClaveNoReflejar44!", status_code=400)
        self.assertEqual(self.cambiar().status_code, 302)

    def test_formularios_y_respuestas_sensibles_son_no_store(self):
        pin = self.solicitar()
        respuestas = [
            self.client.get(reverse("password_reset")),
            self.client.get(reverse("password_reset_update")),
            self.verificar(pin),
        ]
        respuestas.append(self.client.get(reverse("password_reset_new")))
        respuestas.append(self.cambiar(password_confirm="diferente"))
        for response in respuestas:
            self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("Accept", respuestas[-1]["Vary"])

    def test_json_historico_sigue_disponible_con_y_sin_accept(self):
        for headers in [{}, {"HTTP_ACCEPT": "application/json"}]:
            response = self.client.post(reverse("olvide_password"), {"email": self.user.email}, **headers)
            self.assertEqual(response.status_code, 200)
            self.assertIn("mensaje", response.json())
            self.assertIn("no-store", response["Cache-Control"])
            self.assertIn("Accept", response["Vary"])

    def test_flujo_nativo_aplica_csrf(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.get(reverse("password_reset"))
        self.assertEqual(cliente.post(reverse("olvide_password"), {"email": self.user.email}, **HTML).status_code, 403)
        token = cliente.cookies[settings.CSRF_COOKIE_NAME].value
        response = cliente.post(
            reverse("olvide_password"), {"email": self.user.email, "csrfmiddlewaretoken": token}, **HTML
        )
        self.assertEqual(response.status_code, 302)

    @override_settings(RATE_LIMITS_ENABLED=True)
    @patch("SENNOVA.middleware.time")
    def test_limites_html_redirigen_al_paso_correcto_y_conservan_retry_after(self, reloj):
        reloj.time.return_value = 1_800_000_123
        for _ in range(3):
            self.assertEqual(
                self.client.post(reverse("olvide_password"), {"email": self.user.email}, **HTML).status_code, 302
            )
        response = self.client.post(reverse("olvide_password"), {"email": self.user.email}, **HTML)
        self.assertContains(response, "Vuelve a intentarlo", status_code=429)
        self.assertContains(response, reverse("password_reset"), status_code=429)
        self.assertIn("Retry-After", response)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("Accept", response["Vary"])

    @override_settings(RATE_LIMITS_ENABLED=True)
    @patch("SENNOVA.middleware.cache.add", side_effect=ConnectionError("detalle privado"))
    def test_cache_no_disponible_muestra_html_sin_detalles_privados(self, contador):
        for nombre, volver in [
            ("verificar_pin", "password_reset_update"),
            ("restablecer_password", "password_reset_new"),
        ]:
            response = self.client.post(reverse(nombre), {}, **HTML)
            self.assertContains(response, reverse(volver), status_code=503)
            self.assertNotContains(response, "detalle privado", status_code=503)
            self.assertIn("no-store", response["Cache-Control"])


@override_settings(RATE_LIMITS_ENABLED=False)
class VerificacionConcurrenteTests(TransactionTestCase):
    def test_solo_una_sesion_puede_verificar_el_mismo_pin(self):
        if connection.vendor != "mysql":
            self.skipTest("Requiere bloqueos de MySQL.")
        user = get_user_model().objects.create_user("pin_concurrente_html", email="concurrente_html@example.invalid")
        solicitud = PasswordResetToken.crear_para_usuario(user)
        pin = solicitud.pin_para_envio

        def verificar(indice):
            close_old_connections()
            try:
                cliente = Client()
                response = cliente.post(
                    reverse("verificar_pin"), {"email": user.email, "codigo": pin}, **(HTML if indice else {})
                )
                return response.status_code, bool(cliente.session.get("recuperacion_verificada"))
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(verificar, range(2)))
        self.assertEqual(sum(estado in (200, 302) for estado, _ in resultados), 1)
        self.assertEqual(sum(verificado for _, verificado in resultados), 1)
        self.assertEqual(sum(estado == 400 for estado, _ in resultados), 1)


class IndicesRecuperacionTests(TransactionTestCase):
    def test_busqueda_activa_acotada_con_ocho_mil_solicitudes_historicas(self):
        if connection.vendor != "mysql":
            self.skipTest("Requiere el optimizador de MySQL.")
        user = get_user_model().objects.create_user("historial_indices", email="indices@example.invalid")
        PasswordResetToken.objects.bulk_create(
            [
                PasswordResetToken(
                    usuario=user,
                    token=f"valor-sintetico-no-valido-como-pin-{i}",
                    utilizado=True,
                    expira_en=timezone.now() - timezone.timedelta(days=1),
                )
                for i in range(8000)
            ],
            batch_size=500,
        )
        vigente = PasswordResetToken.crear_para_usuario(user)
        tabla = PasswordResetToken._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE TABLE " + connection.ops.quote_name(tabla))
            cursor.fetchall()
            indices = connection.introspection.get_constraints(cursor, tabla)
            token = [i for i in indices.values() if i["index"] and i["columns"] == ["token"]]
            self.assertEqual(len(token), 1)
            self.assertTrue(token[0]["unique"])
            self.assertFalse(any(i["index"] and i["columns"] == ["expires_at"] for i in indices.values()))
            compuesto = next(
                nombre
                for nombre, i in indices.items()
                if i["index"] and i["columns"] == ["user_id", "used", "created_at"]
            )
            consulta = PasswordResetToken.objects.filter(usuario=user, utilizado=False).order_by("-creado_en")[:1]
            sql, params = consulta.query.sql_with_params()
            sin_indice = sql.replace(
                "FROM " + connection.ops.quote_name(tabla),
                "FROM "
                + connection.ops.quote_name(tabla)
                + " IGNORE INDEX ("
                + connection.ops.quote_name(compuesto)
                + ")",
                1,
            )
            cursor.execute("EXPLAIN FORMAT=JSON " + sin_indice, params)
            antes = json.loads(cursor.fetchone()[0])
            cursor.execute("EXPLAIN FORMAT=JSON " + sql, params)
            despues = json.loads(cursor.fetchone()[0])

        def valores(objeto, clave):
            if isinstance(objeto, dict):
                for nombre, dato in objeto.items():
                    if nombre == clave:
                        yield dato
                    yield from valores(dato, clave)
            elif isinstance(objeto, list):
                for dato in objeto:
                    yield from valores(dato, clave)

        self.assertIn(compuesto, list(valores(despues, "key")))
        self.assertIn(True, list(valores(antes, "using_filesort")))
        self.assertNotIn(True, list(valores(despues, "using_filesort")))
        filas_antes = max(valores(antes, "rows_examined_per_scan"))
        filas_despues = max(valores(despues, "rows_examined_per_scan"))
        self.assertGreater(filas_antes, filas_despues)
        self.assertEqual(list(consulta.values_list("pk", flat=True)), [vigente.pk])
        print(
            f"ESCALA recuperación / 8000 solicitudes históricas: {filas_antes} → {filas_despues} filas estimadas; sin ordenación adicional."
        )
