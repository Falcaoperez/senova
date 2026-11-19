"""Un trabajador no consume correos reclamados por otro proceso."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from ..models import CorreoPendiente, Notificacion, PreferenciasNotificacion
from ..services import procesar_correos


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ColaVigenteTests(TestCase):
    def crear(self, nombre):
        usuario = User.objects.create_user(nombre, email=nombre + "@example.invalid")
        aviso = Notificacion.objects.create(usuario=usuario, tipo="novedad", titulo="Aviso ficticio", mensaje="Equipo")
        return usuario, CorreoPendiente.objects.create(notificacion=aviso)

    def test_el_segundo_correo_reclamado_por_otro_trabajador_no_se_consume(self):
        primero, _ = self.crear("primer_aviso_vigente")
        _, correo = self.crear("segundo_aviso_reclamado")
        original = EmailMultiAlternatives.send
        nuevo_bloqueo = timezone.now() + timedelta(hours=1)

        def enviar(mensaje, *args, **kwargs):
            if mensaje.to == [primero.email]:
                CorreoPendiente.objects.filter(pk=correo.pk).update(bloqueado_hasta=nuevo_bloqueo)
            return original(mensaje, *args, **kwargs)

        with patch("notificaciones.services.EmailMultiAlternatives.send", autospec=True, side_effect=enviar):
            self.assertEqual(procesar_correos(2), 1)
        self.assertEqual([mensaje.to for mensaje in mail.outbox], [[primero.email]])
        correo.refresh_from_db()
        self.assertEqual(correo.estado, CorreoPendiente.Estado.PROCESANDO)
        self.assertEqual(correo.bloqueado_hasta, nuevo_bloqueo)

    def comprobar_resultado_tardio(self, fallo=False):
        _, correo = self.crear("aviso_resultado_tardio")
        nuevo_bloqueo = timezone.now() + timedelta(hours=1)

        def reclamar_de_nuevo(*args, **kwargs):
            CorreoPendiente.objects.filter(pk=correo.pk).update(
                bloqueado_hasta=nuevo_bloqueo, intentos=3, ultimo_error="Reclamación posterior"
            )
            if fallo:
                raise RuntimeError("Detalle privado del proveedor")
            return 1

        with patch("notificaciones.services.EmailMultiAlternatives.send", side_effect=reclamar_de_nuevo):
            self.assertEqual(procesar_correos(1), 0 if fallo else 1)
        correo.refresh_from_db()
        self.assertEqual(correo.estado, CorreoPendiente.Estado.PROCESANDO)
        self.assertEqual(correo.bloqueado_hasta, nuevo_bloqueo)
        self.assertEqual(correo.intentos, 3)
        self.assertEqual(correo.ultimo_error, "Reclamación posterior")
        self.assertIsNone(correo.enviado_en)

    def test_un_exito_tardio_no_sobrescribe_la_reserva_del_trabajador_actual(self):
        self.comprobar_resultado_tardio()

    def test_un_fallo_tardio_no_reactiva_el_correo_de_otro_trabajador(self):
        self.comprobar_resultado_tardio(fallo=True)

    def durante_el_primero(self, modificar):
        primero, _ = self.crear("primer_aviso_del_lote")
        segundo, correo = self.crear("siguiente_aviso_del_lote")
        original = EmailMultiAlternatives.send

        def enviar(mensaje, *args, **kwargs):
            if mensaje.to == [primero.email]:
                modificar(segundo, correo)
            return original(mensaje, *args, **kwargs)

        with patch("notificaciones.services.EmailMultiAlternatives.send", autospec=True, side_effect=enviar):
            self.assertEqual(procesar_correos(2), 1)
        self.assertEqual([mensaje.to for mensaje in mail.outbox], [[primero.email]])
        correo.refresh_from_db()
        return correo

    def test_la_reserva_vencida_antes_del_siguiente_mensaje_se_deja_de_usar(self):
        primero, _ = self.crear("aviso_antes_de_vencer_reserva")
        _, correo = self.crear("aviso_con_reserva_vencida")
        ahora = timezone.now()
        original = EmailMultiAlternatives.send
        with patch("notificaciones.services.timezone.now", return_value=ahora) as reloj:

            def enviar(mensaje, *args, **kwargs):
                if mensaje.to == [primero.email]:
                    reloj.return_value = ahora + timedelta(hours=1)
                return original(mensaje, *args, **kwargs)

            with patch("notificaciones.services.EmailMultiAlternatives.send", autospec=True, side_effect=enviar):
                self.assertEqual(procesar_correos(2), 1)
        correo.refresh_from_db()
        self.assertEqual([mensaje.to for mensaje in mail.outbox], [[primero.email]])
        self.assertEqual(correo.estado, CorreoPendiente.Estado.PROCESANDO)
        self.assertLess(correo.bloqueado_hasta, ahora + timedelta(hours=1))

    def test_la_cancelacion_del_siguiente_aviso_se_respeta(self):
        correo = self.durante_el_primero(
            lambda usuario, correo: CorreoPendiente.objects.filter(pk=correo.pk).update(
                estado="cancelado", bloqueado_hasta=None, ultimo_error="Aviso retirado"
            )
        )
        self.assertEqual(correo.estado, CorreoPendiente.Estado.CANCELADO)
        self.assertEqual(correo.ultimo_error, "Aviso retirado")

    def test_la_desactivacion_del_siguiente_usuario_se_respeta(self):
        correo = self.durante_el_primero(
            lambda usuario, correo: User.objects.filter(pk=usuario.pk).update(is_active=False)
        )
        self.assertEqual(correo.estado, CorreoPendiente.Estado.CANCELADO)

    def test_la_preferencia_de_correo_modificada_durante_el_lote_se_respeta(self):
        correo = self.durante_el_primero(
            lambda usuario, correo: PreferenciasNotificacion.objects.update_or_create(
                usuario=usuario, defaults={"correo_novedades": False}
            )
        )
        self.assertEqual(correo.estado, CorreoPendiente.Estado.CANCELADO)

    def test_una_aceptacion_smtp_se_registra_si_el_aviso_se_cancelo_durante_el_envio(self):
        _, correo = self.crear("aviso_aceptado_tras_cancelar")

        def aceptar(*args, **kwargs):
            CorreoPendiente.objects.filter(pk=correo.pk).update(estado="cancelado", bloqueado_hasta=None)
            return 1

        with patch("notificaciones.services.EmailMultiAlternatives.send", side_effect=aceptar):
            self.assertEqual(procesar_correos(1), 1)
        correo.refresh_from_db()
        self.assertEqual(correo.estado, CorreoPendiente.Estado.ENVIADO)
        self.assertIsNotNone(correo.enviado_en)

    def test_una_cancelacion_durante_un_fallo_smtp_no_se_reactiva(self):
        _, correo = self.crear("aviso_cancelado_tras_fallo")

        def fallar(*args, **kwargs):
            CorreoPendiente.objects.filter(pk=correo.pk).update(
                estado="cancelado", bloqueado_hasta=None, ultimo_error="Aviso retirado"
            )
            raise RuntimeError("Detalle privado del proveedor")

        with patch("notificaciones.services.EmailMultiAlternatives.send", side_effect=fallar):
            self.assertEqual(procesar_correos(1), 0)
        correo.refresh_from_db()
        self.assertEqual(correo.estado, CorreoPendiente.Estado.CANCELADO)
        self.assertEqual(correo.ultimo_error, "Aviso retirado")

    def test_el_otro_trabajador_recupera_solo_la_reserva_vencida(self):
        primero, vencido = self.crear("aviso_reserva_vencida")
        _, vigente = self.crear("aviso_reserva_vigente")
        futuro = timezone.now() + timedelta(hours=1)
        CorreoPendiente.objects.filter(pk=vencido.pk).update(
            estado="procesando", bloqueado_hasta=timezone.now() - timedelta(seconds=1)
        )
        CorreoPendiente.objects.filter(pk=vigente.pk).update(estado="procesando", bloqueado_hasta=futuro)
        self.assertEqual(procesar_correos(2), 1)
        self.assertEqual([mensaje.to for mensaje in mail.outbox], [[primero.email]])
        vencido.refresh_from_db()
        vigente.refresh_from_db()
        self.assertEqual(vencido.estado, CorreoPendiente.Estado.ENVIADO)
        self.assertEqual(vigente.estado, CorreoPendiente.Estado.PROCESANDO)
        self.assertEqual(vigente.bloqueado_hasta, futuro)

    def test_1200_avisos_no_se_cargan_para_reservar_un_lote_de_25(self):
        usuario = User.objects.create_user("avisos_1200", email="avisos_1200@example.invalid")
        Notificacion.objects.bulk_create(
            [
                Notificacion(usuario=usuario, tipo="novedad", titulo="Aviso ficticio", mensaje="Equipo")
                for _ in range(1200)
            ],
            batch_size=500,
        )
        avisos = Notificacion.objects.filter(usuario=usuario).values_list("pk", flat=True)
        CorreoPendiente.objects.bulk_create([CorreoPendiente(notificacion_id=pk) for pk in avisos], batch_size=500)
        with CaptureQueriesContext(connection) as consultas:
            self.assertEqual(procesar_correos(25), 25)
        tabla = connection.ops.quote_name(CorreoPendiente._meta.db_table)
        lecturas = [q["sql"] for q in consultas if q["sql"].startswith("SELECT") and f"FROM {tabla}" in q["sql"]]
        self.assertEqual(len(lecturas), 26)
        self.assertIn("LIMIT 25", lecturas[0])
        self.assertTrue(all("LIMIT 1" in sql for sql in lecturas[1:]))
        self.assertFalse(any("OFFSET" in sql for sql in lecturas))
        self.assertEqual(CorreoPendiente.objects.filter(estado="pendiente").count(), 1175)
        self.assertEqual(len(mail.outbox), 25)
        print("ESCALA avisos por correo / 1200 filas: reserva de 25 y 25 lecturas actuales de una fila, sin OFFSET.")
