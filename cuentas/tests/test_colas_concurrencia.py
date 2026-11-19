"""Una reserva recuperada por otro trabajador se respeta con conexiones reales."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event, local
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from notificaciones.models import CorreoPendiente, Notificacion
from notificaciones.services import procesar_correos

from ..correos import encolar_pin, invalidar_recuperaciones, procesar_correos_seguridad
from ..models import CorreoSeguridad, PasswordResetToken


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ReclamacionesConcurrentesTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "mysql":
            self.skipTest("Comprueba la recuperación de reservas con conexiones reales de MySQL.")
        get_connection()
        mail.outbox = []

    def comprobar(self, seguridad):
        modelo = CorreoSeguridad if seguridad else CorreoPendiente
        procesar = procesar_correos_seguridad if seguridad else procesar_correos
        correos = []
        usuarios = []
        for indice in range(2):
            usuario = User.objects.create_user(f"reserva_real_{indice}", email=f"reserva_real_{indice}@example.invalid")
            usuarios.append(usuario)
            if seguridad:
                correos.append(encolar_pin(PasswordResetToken.crear_para_usuario(usuario)))
            else:
                aviso = Notificacion.objects.create(usuario=usuario, tipo="novedad", titulo="Mensaje ficticio")
                correos.append(CorreoPendiente.objects.create(notificacion=aviso))
        primer_envio, nuevo_en_envio, continuar_anterior, continuar_nuevo = Event(), Event(), Event(), Event()
        identidad = local()
        original = EmailMultiAlternatives.send

        def enviar(mensaje, *args, **kwargs):
            if identidad.trabajador == "anterior" and mensaje.to == [usuarios[0].email]:
                primer_envio.set()
                if not continuar_anterior.wait(15):
                    raise AssertionError("Falta continuar el primer trabajador.")
            if identidad.trabajador == "nuevo":
                nuevo_en_envio.set()
                if not continuar_nuevo.wait(15):
                    raise AssertionError("Falta continuar el nuevo trabajador.")
            return original(mensaje, *args, **kwargs)

        def trabajar(nombre, limite):
            close_old_connections()
            identidad.trabajador = nombre
            try:
                return procesar(limite)
            finally:
                connection.close()

        with patch.object(EmailMultiAlternatives, "send", autospec=True, side_effect=enviar):
            with ThreadPoolExecutor(max_workers=2) as pool:
                anterior = pool.submit(trabajar, "anterior", 2)
                try:
                    self.assertTrue(primer_envio.wait(10))
                    # Se adelanta solo la caducidad de esta reserva de prueba.
                    # El segundo trabajador la recupera con su propia transacción.
                    modelo.objects.filter(pk=correos[1].pk).update(
                        bloqueado_hasta=timezone.now() - timedelta(seconds=1)
                    )
                    nuevo = pool.submit(trabajar, "nuevo", 1)
                    self.assertTrue(nuevo_en_envio.wait(10))
                    continuar_anterior.set()
                    self.assertEqual(anterior.result(timeout=20), 1)
                finally:
                    continuar_anterior.set()
                    continuar_nuevo.set()
                self.assertEqual(nuevo.result(timeout=20), 1)
        self.assertEqual(modelo.objects.filter(estado="enviado").count(), 2)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual({tuple(mensaje.to) for mensaje in mail.outbox}, {(usuario.email,) for usuario in usuarios})
        if seguridad:
            self.assertFalse(CorreoSeguridad.objects.exclude(contenido_cifrado="").exists())

    def test_la_reserva_de_seguridad_recuperada_no_se_envia_dos_veces(self):
        self.comprobar(seguridad=True)

    def test_la_reserva_de_avisos_recuperada_no_se_envia_dos_veces(self):
        self.comprobar(seguridad=False)

    def test_la_invalidacion_concurrente_y_un_fallo_final_comparten_orden_de_bloqueo(self):
        usuario = User.objects.create_user("pin_cambio_concurrente", email="cambio_concurrente@example.invalid")
        solicitud = PasswordResetToken.crear_para_usuario(usuario)
        correo = encolar_pin(solicitud)
        CorreoSeguridad.objects.filter(pk=correo.pk).update(intentos=2)
        solicitud_bloqueada, finalizando, en_smtp = Event(), Event(), Event()

        def invalidar():
            close_old_connections()
            try:
                with transaction.atomic():
                    PasswordResetToken.objects.select_for_update().get(pk=solicitud.pk)
                    solicitud_bloqueada.set()
                    if not finalizando.wait(15):
                        raise AssertionError("Falta finalizar el trabajador.")
                    invalidar_recuperaciones(usuario)
                return "invalidado"
            finally:
                connection.close()

        def fallar(*args, **kwargs):
            en_smtp.set()
            raise RuntimeError("Transporte ficticio no disponible")

        def detectar_finalizacion(execute, sql, params, many, context):
            tabla = connection.ops.quote_name(PasswordResetToken._meta.db_table)
            if en_smtp.is_set() and tabla in sql and "FOR UPDATE" in sql:
                finalizando.set()
            return execute(sql, params, many, context)

        def procesar():
            close_old_connections()
            try:
                with connection.execute_wrapper(detectar_finalizacion):
                    return procesar_correos_seguridad(1)
            finally:
                connection.close()

        with patch("cuentas.correos.EmailMultiAlternatives.send", side_effect=fallar):
            with ThreadPoolExecutor(max_workers=2) as pool:
                cambio = pool.submit(invalidar)
                try:
                    self.assertTrue(solicitud_bloqueada.wait(10))
                    trabajador = pool.submit(procesar)
                    self.assertTrue(finalizando.wait(10))
                    self.assertEqual(cambio.result(timeout=20), "invalidado")
                    self.assertEqual(trabajador.result(timeout=20), 0)
                finally:
                    finalizando.set()
        correo.refresh_from_db()
        solicitud.refresh_from_db()
        self.assertEqual(correo.estado, CorreoSeguridad.Estado.CANCELADO)
        self.assertEqual(correo.contenido_cifrado, "")
        self.assertEqual(correo.intentos, 2)
        self.assertTrue(solicitud.utilizado)
        self.assertEqual(len(mail.outbox), 0)
