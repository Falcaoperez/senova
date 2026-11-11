from concurrent.futures import ThreadPoolExecutor

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.mail import get_connection
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings

from .correos import encolar_pin, procesar_correos_seguridad
from .models import CorreoSeguridad, PasswordResetToken


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ColaSeguridadConcurrenteTests(TransactionTestCase):
    def test_workers_do_not_send_the_same_security_message(self):
        if connection.vendor != "mysql":
            self.skipTest("Se necesitan los bloqueos reales de MySQL.")
        for i in range(12):
            user = get_user_model().objects.create_user(f"parallelpin{i}", email=f"parallelpin{i}@example.invalid")
            encolar_pin(PasswordResetToken.crear_para_usuario(user))
        get_connection()
        mail.outbox = []

        def work(_):
            close_old_connections()
            try:
                return procesar_correos_seguridad(6)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            sent = list(executor.map(work, range(2)))
        self.assertEqual(sum(sent), 12)
        self.assertEqual(CorreoSeguridad.objects.filter(estado="enviado", contenido_cifrado="").count(), 12)
        self.assertEqual(len(mail.outbox), 12)
        self.assertEqual(len({message.to[0] for message in mail.outbox}), 12)
