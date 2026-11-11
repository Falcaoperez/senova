"""SMTP integration checks use only an ephemeral local server."""

from io import StringIO
from socketserver import StreamRequestHandler, TCPServer
from threading import Thread
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, override_settings

from SENNOVA.email_backend import SMTPBackend


class LocalSMTPHandler(StreamRequestHandler):
    def handle(self):
        self.wfile.write(b"220 localhost ESMTP\r\n")
        while True:
            line = self.rfile.readline()
            if not line:
                return
            verb = line.split(b" ", 1)[0].strip().upper()
            if verb in [b"EHLO", b"HELO"]:
                self.wfile.write(b"250 localhost\r\n")
            elif verb == b"DATA":
                self.wfile.write(b"354 End with a dot\r\n")
                lines = []
                while True:
                    part = self.rfile.readline()
                    if part in [b".\r\n", b""]:
                        break
                    lines.append(part)
                self.server.messages.append(b"".join(lines))
                self.wfile.write(b"250 Stored\r\n")
            elif verb == b"QUIT":
                self.wfile.write(b"221 Bye\r\n")
                return
            else:
                if verb == b"RCPT":
                    self.server.recipients.append(line)
                self.wfile.write(b"250 OK\r\n")


@override_settings(
    EMAIL_BACKEND="SENNOVA.email_backend.SMTPBackend",
    EMAIL_HOST_USER="",
    EMAIL_HOST_PASSWORD="",
    EMAIL_OAUTH2_ACCESS_TOKEN="",
    EMAIL_USE_TLS=False,
    EMAIL_USE_SSL=False,
    EMAIL_TIMEOUT=2,
    DEFAULT_FROM_EMAIL="GESICOM <santiagoocoy2025@gmail.com>",
)
class SMTPConfigurationTests(SimpleTestCase):
    def setUp(self):
        self.server = TCPServer(("127.0.0.1", 0), LocalSMTPHandler)
        self.server.messages = []
        self.server.recipients = []
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.local_settings = self.settings(EMAIL_HOST="127.0.0.1", EMAIL_PORT=self.server.server_address[1])
        self.local_settings.enable()

    def tearDown(self):
        self.local_settings.disable()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_sender_and_multiple_recipient_domains(self):
        from django.conf import settings

        result = send_mail(
            "Prueba local",
            "Contenido de recuperación",
            settings.DEFAULT_FROM_EMAIL,
            ["destino@gmail.com", "destino@outlook.com", "destino@sena.edu.co"],
        )
        self.assertEqual(result, 1)
        self.assertEqual(len(self.server.messages), 1)
        self.assertEqual(len(self.server.recipients), 3)
        self.assertIn(b"santiagoocoy2025@gmail.com", self.server.messages[0])

    def test_connection_command_does_not_send_messages(self):
        output = StringIO()
        call_command("comprobar_correo", stdout=output)
        self.assertIn("Conexión SMTP y autenticación correctas", output.getvalue())
        self.assertEqual(self.server.messages, [])

    @override_settings(
        EMAIL_HOST_USER="sender@example.com",
        EMAIL_HOST_PASSWORD="secret-test-only",
        EMAIL_USE_TLS=False,
        EMAIL_USE_SSL=False,
    )
    def test_credentials_cannot_be_sent_without_encryption(self):
        with patch.object(SMTPBackend, "connection_class") as connection:
            with self.assertRaises(ImproperlyConfigured):
                SMTPBackend().open()
            connection.assert_not_called()

    @override_settings(
        EMAIL_HOST="smtp.gmail.com",
        EMAIL_HOST_USER="santiagoocoy2025@gmail.com",
        DEFAULT_FROM_EMAIL="GESICOM <another@example.com>",
        EMAIL_USE_TLS=True,
    )
    def test_gmail_requires_matching_sender(self):
        with self.assertRaisesMessage(CommandError, "debe coincidir"):
            call_command("comprobar_correo", solo_configuracion=True, stdout=StringIO())

    @override_settings(EMAIL_HOST_USER="sender@example.com")
    def test_missing_credentials_prevent_connection(self):
        with patch.object(SMTPBackend, "connection_class") as connection:
            with self.assertRaises(ImproperlyConfigured):
                SMTPBackend().open()
            connection.assert_not_called()
        with self.assertRaisesMessage(CommandError, "Falta EMAIL_HOST_PASSWORD"):
            call_command("comprobar_correo", solo_configuracion=True)

    @override_settings(
        EMAIL_HOST_USER="sender@example.com", EMAIL_HOST_PASSWORD="not-a-real-secret", EMAIL_USE_TLS=True
    )
    def test_auth_failure_command_does_not_expose_credentials(self):
        import smtplib

        with patch("cuentas.management.commands.comprobar_correo.get_connection") as connection:
            connection.return_value.open.side_effect = smtplib.SMTPAuthenticationError(535, b"not-a-real-secret")
            with self.assertRaises(CommandError) as result:
                call_command("comprobar_correo", stdout=StringIO())
            self.assertNotIn("not-a-real-secret", str(result.exception))

    @override_settings(EMAIL_HOST_USER="sender@example.com", EMAIL_OAUTH2_ACCESS_TOKEN="test-token", EMAIL_USE_TLS=True)
    def test_oauth_uses_encrypted_connection(self):
        with patch.object(SMTPBackend, "connection_class") as connection:
            backend = SMTPBackend()
            self.assertTrue(backend.open())
            connection.return_value.starttls.assert_called_once()
            mechanism, callback = connection.return_value.auth.call_args.args
            self.assertEqual(mechanism, "XOAUTH2")
            self.assertIn("auth=Bearer test-token", callback())
            backend.close()
