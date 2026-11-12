import errno
import smtplib
import socket
import ssl
from email.utils import parseaddr

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import get_connection
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email


class Command(BaseCommand):
    help = "Comprueba la configuración y conexión SMTP sin enviar mensajes ni mostrar secretos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--solo-configuracion", action="store_true", help="Valida los datos sin abrir una conexión de red."
        )

    def handle(self, *args, **options):
        if "console" in settings.EMAIL_BACKEND or "locmem" in settings.EMAIL_BACKEND:
            raise CommandError(
                "El correo usa un backend local. Define EMAIL_HOST y un backend SMTP para enviar correos reales."
            )
        if not settings.EMAIL_HOST:
            raise CommandError("Falta EMAIL_HOST.")
        if settings.EMAIL_USE_TLS and settings.EMAIL_USE_SSL:
            raise CommandError("Usa STARTTLS o SSL, no ambos a la vez.")
        if (settings.EMAIL_HOST_PASSWORD or settings.EMAIL_OAUTH2_ACCESS_TOKEN) and not (
            settings.EMAIL_USE_TLS or settings.EMAIL_USE_SSL
        ):
            raise CommandError("Las credenciales SMTP requieren TLS o SSL.")
        try:
            remitente = parseaddr(settings.DEFAULT_FROM_EMAIL)[1]
            validate_email(remitente)
        except Exception:
            raise CommandError("DEFAULT_FROM_EMAIL debe contener una dirección válida.")
        if settings.EMAIL_HOST.casefold() in {"smtp.gmail.com", "smtp.googlemail.com"}:
            if not (settings.EMAIL_USE_TLS or settings.EMAIL_USE_SSL):
                raise CommandError("Gmail requiere TLS o SSL.")
            if remitente.casefold() != settings.EMAIL_HOST_USER.casefold():
                raise CommandError("En Gmail, DEFAULT_FROM_EMAIL debe coincidir con la cuenta autenticada.")
        if settings.EMAIL_HOST_USER and not (settings.EMAIL_HOST_PASSWORD or settings.EMAIL_OAUTH2_ACCESS_TOKEN):
            raise CommandError(
                "Falta EMAIL_HOST_PASSWORD o EMAIL_OAUTH2_ACCESS_TOKEN en la configuración privada del entorno. No se intentó conectar."
            )
        self.stdout.write(f"Servidor: {settings.EMAIL_HOST}:{settings.EMAIL_PORT}")
        self.stdout.write(f"Remitente: {settings.DEFAULT_FROM_EMAIL}")
        if options["solo_configuracion"]:
            self.stdout.write(self.style.SUCCESS("Configuración SMTP válida. Conexión pendiente de comprobar."))
            return
        try:
            connection = get_connection(fail_silently=False)
            connection.open()
            connection.close()
        except smtplib.SMTPAuthenticationError:
            ayuda = (
                "Gmail requiere una contraseña de aplicación de Google o un token OAuth2 vigente."
                if settings.EMAIL_HOST.casefold() in {"smtp.gmail.com", "smtp.googlemail.com"}
                else "Revisa las credenciales y la autorización SMTP de la cuenta."
            )
            raise CommandError(f"El proveedor rechazó la autenticación. {ayuda}") from None
        except ssl.SSLCertVerificationError:
            raise CommandError(
                "No se pudo verificar el certificado TLS del servidor SMTP. Revisa la cadena de confianza."
            ) from None
        except socket.gaierror:
            raise CommandError(
                "No se pudo resolver el nombre del servidor SMTP. La autenticación no se comprobó."
            ) from None
        except TimeoutError:
            raise CommandError(
                "El servidor SMTP no respondió dentro del tiempo configurado. La autenticación no se comprobó."
            ) from None
        except OSError as error:
            if error.errno in {errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EACCES, errno.EPERM}:
                raise CommandError(
                    "Este entorno no tiene acceso de red al servidor SMTP. La autenticación no se comprobó."
                ) from None
            raise CommandError(
                "No se pudo abrir la conexión SMTP. Revisa el acceso al host y puerto configurados."
            ) from None
        except (smtplib.SMTPException, ImproperlyConfigured):
            raise CommandError(
                "No se pudo establecer la conexión SMTP. Revisa host, puerto, cifrado y autorización del proveedor."
            ) from None
        self.stdout.write(self.style.SUCCESS("Conexión SMTP y autenticación correctas. No se enviaron mensajes."))
