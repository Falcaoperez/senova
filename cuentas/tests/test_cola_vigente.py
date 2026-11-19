"""El siguiente correo del lote usa el estado actual de la recuperación."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from ..correos import encolar_pin, invalidar_recuperaciones, procesar_correos_seguridad
from ..models import CorreoSeguridad, PasswordResetToken


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ColaVigenteTests(TestCase):
    def crear(self, nombre):
        usuario = User.objects.create_user(nombre, email=nombre + "@example.invalid")
        solicitud = PasswordResetToken.crear_para_usuario(usuario)
        return usuario, solicitud, encolar_pin(solicitud)

    def test_cancelar_el_segundo_pin_durante_el_lote_impide_su_envio(self):
        primero, _, _ = self.crear("primer_pin_vigente")
        segundo, _, correo = self.crear("segundo_pin_retirado")
        original = EmailMultiAlternatives.send

        def enviar(mensaje, *args, **kwargs):
            if mensaje.to == [primero.email]:
                invalidar_recuperaciones(segundo)
            return original(mensaje, *args, **kwargs)

        with patch("cuentas.correos.EmailMultiAlternatives.send", autospec=True, side_effect=enviar):
            self.assertEqual(procesar_correos_seguridad(2), 1)
        self.assertEqual([mensaje.to for mensaje in mail.outbox], [[primero.email]])
        correo.refresh_from_db()
        self.assertEqual(correo.estado, CorreoSeguridad.Estado.CANCELADO)
        self.assertEqual(correo.contenido_cifrado, "")

    def durante_el_primero(self, modificar):
        primero, _, _ = self.crear("primer_pin_del_lote")
        segundo, solicitud, correo = self.crear("siguiente_pin_del_lote")
        original = EmailMultiAlternatives.send

        def enviar(mensaje, *args, **kwargs):
            if mensaje.to == [primero.email]:
                modificar(segundo, solicitud, correo)
            return original(mensaje, *args, **kwargs)

        with patch("cuentas.correos.EmailMultiAlternatives.send", autospec=True, side_effect=enviar):
            self.assertEqual(procesar_correos_seguridad(2), 1)
        self.assertEqual([mensaje.to for mensaje in mail.outbox], [[primero.email]])
        correo.refresh_from_db()
        return correo

    def comprobar_cancelado(self, correo):
        self.assertEqual(correo.estado, CorreoSeguridad.Estado.CANCELADO)
        self.assertEqual(correo.contenido_cifrado, "")
        self.assertIsNone(correo.bloqueado_hasta)

    def test_una_solicitud_utilizada_despues_del_primer_envio_no_se_entrega(self):
        correo = self.durante_el_primero(
            lambda usuario, solicitud, correo: PasswordResetToken.objects.filter(pk=solicitud.pk).update(utilizado=True)
        )
        self.comprobar_cancelado(correo)

    def test_un_pin_verificado_durante_el_lote_no_se_vuelve_a_enviar(self):
        correo = self.durante_el_primero(
            lambda usuario, solicitud, correo: PasswordResetToken.objects.filter(pk=solicitud.pk).update(
                verificado_en=timezone.now()
            )
        )
        self.comprobar_cancelado(correo)

    def test_un_cambio_de_correo_durante_el_lote_invalida_el_pin_preparado(self):
        correo = self.durante_el_primero(
            lambda usuario, solicitud, correo: User.objects.filter(pk=usuario.pk).update(
                email="direccion_actualizada@example.invalid"
            )
        )
        self.comprobar_cancelado(correo)

    def test_un_cambio_de_contrasena_durante_el_lote_invalida_el_pin_preparado(self):
        correo = self.durante_el_primero(
            lambda usuario, solicitud, correo: User.objects.filter(pk=usuario.pk).update(password="!actualizada")
        )
        self.comprobar_cancelado(correo)

    def test_una_cuenta_desactivada_durante_el_lote_no_recibe_el_pin(self):
        correo = self.durante_el_primero(
            lambda usuario, solicitud, correo: User.objects.filter(pk=usuario.pk).update(is_active=False)
        )
        self.comprobar_cancelado(correo)

    def test_un_correo_reclamado_de_nuevo_se_deja_al_trabajador_actual(self):
        nuevo_bloqueo = timezone.now() + timedelta(hours=1)
        correo = self.durante_el_primero(
            lambda usuario, solicitud, correo: CorreoSeguridad.objects.filter(pk=correo.pk).update(
                bloqueado_hasta=nuevo_bloqueo
            )
        )
        self.assertEqual(correo.estado, CorreoSeguridad.Estado.PROCESANDO)
        self.assertEqual(correo.bloqueado_hasta, nuevo_bloqueo)
        self.assertTrue(correo.contenido_cifrado)

    def test_un_correo_eliminado_durante_el_lote_no_se_recrea_ni_envia(self):
        primero, _, _ = self.crear("pin_antes_de_eliminar")
        _, _, siguiente = self.crear("pin_eliminado_del_lote")
        pk = siguiente.pk
        original = EmailMultiAlternatives.send

        def enviar(mensaje, *args, **kwargs):
            if mensaje.to == [primero.email]:
                CorreoSeguridad.objects.filter(pk=pk).delete()
            return original(mensaje, *args, **kwargs)

        with patch("cuentas.correos.EmailMultiAlternatives.send", autospec=True, side_effect=enviar):
            self.assertEqual(procesar_correos_seguridad(2), 1)
        self.assertFalse(CorreoSeguridad.objects.filter(pk=pk).exists())
        self.assertEqual([mensaje.to for mensaje in mail.outbox], [[primero.email]])

    def test_una_reserva_vencida_entre_mensajes_no_autoriza_el_siguiente(self):
        primero, _, _ = self.crear("pin_antes_de_vencer_reserva")
        _, _, correo = self.crear("pin_con_reserva_vencida")
        ahora = timezone.now()
        original = EmailMultiAlternatives.send
        with patch("cuentas.correos.timezone.now", return_value=ahora) as reloj:

            def enviar(mensaje, *args, **kwargs):
                if mensaje.to == [primero.email]:
                    reloj.return_value = ahora + timedelta(hours=1)
                return original(mensaje, *args, **kwargs)

            with patch("cuentas.correos.EmailMultiAlternatives.send", autospec=True, side_effect=enviar):
                self.assertEqual(procesar_correos_seguridad(2), 1)
        correo.refresh_from_db()
        self.assertEqual([mensaje.to for mensaje in mail.outbox], [[primero.email]])
        self.assertEqual(correo.estado, CorreoSeguridad.Estado.PROCESANDO)
        self.assertLess(correo.bloqueado_hasta, ahora + timedelta(hours=1))

    def comprobar_resultado_tardio(self, *, fallo=False, cifrado_roto=False):
        _, solicitud, correo = self.crear("pin_resultado_tardio")
        CorreoSeguridad.objects.filter(pk=correo.pk).update(intentos=2)
        nuevo_bloqueo = timezone.now() + timedelta(hours=1)
        cifrado_original = correo.contenido_cifrado

        def reclamar_de_nuevo(*args, **kwargs):
            CorreoSeguridad.objects.filter(pk=correo.pk).update(
                estado=CorreoSeguridad.Estado.PROCESANDO,
                bloqueado_hasta=nuevo_bloqueo,
                intentos=0,
                ultimo_error="Reclamación posterior",
            )
            if fallo:
                raise RuntimeError("Detalle privado del proveedor")
            return 1

        if cifrado_roto:
            from cryptography.fernet import InvalidToken

            def descifrar(*args, **kwargs):
                reclamar_de_nuevo()
                raise InvalidToken

            with patch("cuentas.correos._cifrador") as cifrador:
                cifrador.return_value.decrypt.side_effect = descifrar
                self.assertEqual(procesar_correos_seguridad(1), 0)
        else:
            with patch("cuentas.correos.EmailMultiAlternatives.send", side_effect=reclamar_de_nuevo):
                self.assertEqual(procesar_correos_seguridad(1), 0 if fallo else 1)
        correo.refresh_from_db()
        solicitud.refresh_from_db()
        self.assertEqual(correo.estado, CorreoSeguridad.Estado.PROCESANDO)
        self.assertEqual(correo.bloqueado_hasta, nuevo_bloqueo)
        self.assertEqual(correo.intentos, 0)
        self.assertEqual(correo.ultimo_error, "Reclamación posterior")
        self.assertEqual(correo.contenido_cifrado, cifrado_original)
        self.assertIsNone(correo.enviado_en)
        self.assertFalse(solicitud.utilizado)

    def test_un_exito_tardio_no_sobrescribe_una_reclamacion_posterior(self):
        self.comprobar_resultado_tardio()

    def test_un_tercer_fallo_tardio_no_invalida_el_pin_de_la_reclamacion_actual(self):
        self.comprobar_resultado_tardio(fallo=True)

    def test_un_fallo_de_descifrado_sin_reserva_no_invalida_la_solicitud_actual(self):
        self.comprobar_resultado_tardio(cifrado_roto=True)

    def test_cancelar_durante_smtp_conserva_la_invalidacion_aunque_haya_aceptacion(self):
        usuario, solicitud, correo = self.crear("pin_cancelado_en_transporte")

        def aceptar(*args, **kwargs):
            invalidar_recuperaciones(usuario)
            return 1

        with patch("cuentas.correos.EmailMultiAlternatives.send", side_effect=aceptar):
            self.assertEqual(procesar_correos_seguridad(1), 1)
        correo.refresh_from_db()
        solicitud.refresh_from_db()
        self.comprobar_cancelado(correo)
        self.assertTrue(solicitud.utilizado)

    def test_otro_trabajador_recupera_una_reserva_vencida_y_respeta_la_vigente(self):
        primero, _, vencido = self.crear("pin_reserva_vencida")
        _, _, vigente = self.crear("pin_reserva_vigente")
        futuro = timezone.now() + timedelta(hours=1)
        CorreoSeguridad.objects.filter(pk=vencido.pk).update(
            estado="procesando", bloqueado_hasta=timezone.now() - timedelta(seconds=1)
        )
        CorreoSeguridad.objects.filter(pk=vigente.pk).update(estado="procesando", bloqueado_hasta=futuro)
        self.assertEqual(procesar_correos_seguridad(2), 1)
        self.assertEqual([mensaje.to for mensaje in mail.outbox], [[primero.email]])
        vencido.refresh_from_db()
        vigente.refresh_from_db()
        self.assertEqual(vencido.estado, CorreoSeguridad.Estado.ENVIADO)
        self.assertEqual(vigente.bloqueado_hasta, futuro)
        self.assertEqual(vigente.estado, CorreoSeguridad.Estado.PROCESANDO)

    def test_1200_correos_se_leen_por_reserva_y_con_estado_actual_individual(self):
        usuario = User.objects.create_user("cola_1200", email="cola_1200@example.invalid")
        CorreoSeguridad.objects.bulk_create(
            [CorreoSeguridad(usuario=usuario, tipo="cambio", destinatario=usuario.email) for _ in range(1200)],
            batch_size=500,
        )
        with CaptureQueriesContext(connection) as consultas:
            self.assertEqual(procesar_correos_seguridad(25), 25)
        tabla = connection.ops.quote_name(CorreoSeguridad._meta.db_table)
        lecturas = [q["sql"] for q in consultas if q["sql"].startswith("SELECT") and f"FROM {tabla}" in q["sql"]]
        self.assertEqual(len(lecturas), 26)
        self.assertIn("LIMIT 25", lecturas[0])
        self.assertTrue(all("LIMIT 1" in sql for sql in lecturas[1:]))
        self.assertFalse(any("OFFSET" in sql for sql in lecturas))
        self.assertEqual(CorreoSeguridad.objects.filter(estado="pendiente").count(), 1175)
        self.assertEqual(len(mail.outbox), 25)
        print("ESCALA correo de seguridad / 1200 filas: reserva de 25 y 25 lecturas actuales de una fila, sin OFFSET.")
