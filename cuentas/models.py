"""Persistencia de solicitudes de recuperación y auditoría, sin secretos en texto plano."""

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import models
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac


class PasswordResetToken(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="password_reset_tokens", db_column="user_id"
    )
    token = models.CharField(
        max_length=255, unique=True, help_text="Hash del PIN de recuperación; nunca contiene el PIN original."
    )
    creado_en = models.DateTimeField(auto_now_add=True, db_column="created_at")
    expira_en = models.DateTimeField(db_index=True, db_column="expires_at")
    utilizado = models.BooleanField(default=False, db_column="used")
    intentos = models.PositiveSmallIntegerField(default=0)
    verificado_en = models.DateTimeField(null=True, blank=True)
    firma_credenciales = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        verbose_name = "Solicitud de recuperación"
        verbose_name_plural = "Solicitudes de recuperación"
        ordering = ["-creado_en"]
        indexes = [models.Index(fields=["token"]), models.Index(fields=["expira_en", "utilizado"])]

    def __str__(self):
        return f"Recuperación #{self.pk}"

    def es_valido(self):
        if self.utilizado or self.intentos >= settings.PASSWORD_RESET_MAX_ATTEMPTS or timezone.now() >= self.expira_en:
            return False
        usuario = self.usuario
        keys = [settings.SECRET_KEY, *getattr(settings, "SECRET_KEY_FALLBACKS", [])]
        return usuario.is_active and any(
            constant_time_compare(self.firma_credenciales, self._firma_usuario(usuario, secret)) for secret in keys
        )

    @staticmethod
    def _firma_usuario(usuario, secret):
        value = f"{usuario.pk}:{usuario.password}:{usuario.email.casefold()}"
        return salted_hmac("gesicom.reset-account-binding.v1", value, secret=secret, algorithm="sha256").hexdigest()

    @classmethod
    def crear_para_usuario(cls, user):
        pin = f"{secrets.randbelow(1_000_000):06d}"
        cls.objects.filter(usuario=user, utilizado=False).update(utilizado=True)
        solicitud = cls.objects.create(
            usuario=user,
            token=make_password(pin),
            expira_en=timezone.now() + timedelta(minutes=settings.PASSWORD_RESET_PIN_MINUTES),
            firma_credenciales=cls._firma_usuario(user, settings.SECRET_KEY),
        )
        solicitud.pin_para_envio = pin  # Solo vive durante este envío, no se persiste.
        return solicitud


class RegistroSeguridad(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    accion = models.CharField(max_length=80)
    ruta = models.CharField(max_length=255, blank=True)
    direccion_ip = models.GenericIPAddressField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.accion} · {self.creado_en}"


class CorreoSeguridad(models.Model):
    class Tipo(models.TextChoices):
        PIN = "pin", "PIN de recuperación"
        CAMBIO = "cambio", "Cambio de credenciales"

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        PROCESANDO = "procesando", "En proceso"
        ENVIADO = "enviado", "Enviado"
        ERROR = "error", "Error"
        CANCELADO = "cancelado", "Cancelado"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    solicitud = models.OneToOneField(PasswordResetToken, null=True, blank=True, on_delete=models.CASCADE)
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    destinatario = models.EmailField()
    # Solo contiene un PIN cifrado mientras se espera el envío; nunca se muestra en administración.
    contenido_cifrado = models.TextField(blank=True)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    intentos = models.PositiveSmallIntegerField(default=0)
    creado_en = models.DateTimeField(auto_now_add=True)
    proximo_intento = models.DateTimeField(default=timezone.now)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)
    enviado_en = models.DateTimeField(null=True, blank=True)
    ultimo_error = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Correo de seguridad"
        verbose_name_plural = "Correos de seguridad"
        indexes = [models.Index(fields=["estado", "proximo_intento"])]

    def __str__(self):
        return f"Correo de seguridad #{self.pk}"


class SesionUsuario(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sesiones_activas")
    sesion = models.OneToOneField("sessions.Session", on_delete=models.CASCADE, related_name="registro_cuenta")
    creada_en = models.DateTimeField(default=timezone.now)
    ultimo_uso = models.DateTimeField(default=timezone.now)
    direccion_ip = models.GenericIPAddressField(null=True, blank=True)
    agente = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Sesión de usuario"
        verbose_name_plural = "Sesiones de usuarios"
        ordering = ["-ultimo_uso"]

    @property
    def dispositivo(self):
        navegador = next(
            (
                name
                for key, name in [
                    ("Edg/", "Edge"),
                    ("Firefox/", "Firefox"),
                    ("Chrome/", "Chrome"),
                    ("Safari/", "Safari"),
                ]
                if key in self.agente
            ),
            "Navegador",
        )
        sistema = next(
            (
                name
                for key, name in [
                    ("Android", "Android"),
                    ("iPhone", "iPhone"),
                    ("iPad", "iPad"),
                    ("Windows", "Windows"),
                    ("Macintosh", "macOS"),
                    ("Linux", "Linux"),
                ]
                if key in self.agente
            ),
            "Dispositivo",
        )
        return f"{navegador} · {sistema}"

    def __str__(self):
        return f"Sesión #{self.pk} · {self.usuario_id}"
