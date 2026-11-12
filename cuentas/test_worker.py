from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TransactionTestCase, override_settings

from .correos import encolar_pin
from .models import CorreoSeguridad, PasswordResetToken


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class DrenajeWorkerTests(TransactionTestCase):
    def test_worker_drains_ready_batches_before_waiting(self):
        for i in range(5):
            user = get_user_model().objects.create_user(f"batchpin{i}", email=f"batchpin{i}@example.invalid")
            encolar_pin(PasswordResetToken.crear_para_usuario(user))
        with patch(
            "notificaciones.management.commands.procesar_notificaciones.time.sleep", side_effect=KeyboardInterrupt
        ) as pause:
            call_command("procesar_notificaciones", continuo=True, lote=2, stdout=StringIO())
        self.assertEqual(CorreoSeguridad.objects.filter(estado="enviado").count(), 5)
        self.assertEqual(len(mail.outbox), 5)
        pause.assert_called_once()
