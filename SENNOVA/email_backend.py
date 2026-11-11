"""SMTP transport with explicit credentials and optional OAuth2 authentication."""

import smtplib

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.smtp import EmailBackend


class SMTPBackend(EmailBackend):
    def open(self):
        token = getattr(settings, "EMAIL_OAUTH2_ACCESS_TOKEN", "")
        if self.username and not (self.password or token):
            raise ImproperlyConfigured("Faltan las credenciales de la cuenta SMTP. Configúralas en el entorno.")
        if not token:
            return super().open()
        if self.connection:
            return False
        if not self.use_tls and not self.use_ssl:
            raise ImproperlyConfigured("OAuth2 por SMTP requiere TLS o SSL.")
        try:
            self.connection = self.connection_class(
                self.host, self.port, timeout=self.timeout, **({"context": self.ssl_context} if self.use_ssl else {})
            )
            self.connection.ehlo()
            if self.use_tls:
                self.connection.starttls(context=self.ssl_context)
                self.connection.ehlo()
            auth_string = f"user={self.username}\x01auth=Bearer {token}\x01\x01"
            self.connection.auth("XOAUTH2", lambda challenge=None: auth_string if challenge is None else "")
            return True
        except (OSError, smtplib.SMTPException):
            self.close()
            if not self.fail_silently:
                raise
            return False
