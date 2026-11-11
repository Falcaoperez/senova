"""Persistencia de solicitudes de recuperación y auditoría, sin secretos en texto plano."""

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import models
from django.utils import timezone


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

    class Meta:
        verbose_name = "Solicitud de recuperación"
        verbose_name_plural = "Solicitudes de recuperación"
        ordering = ["-creado_en"]
        indexes = [models.Index(fields=["token"]), models.Index(fields=["expira_en", "utilizado"])]

    def __str__(self):
        return f"Recuperación #{self.pk}"

    def es_valido(self):
        return (
            not self.utilizado
            and self.intentos < settings.PASSWORD_RESET_MAX_ATTEMPTS
            and timezone.now() < self.expira_en
        )

    @classmethod
    def crear_para_usuario(cls, user):
        pin = f"{secrets.randbelow(1_000_000):06d}"
        cls.objects.filter(usuario=user, utilizado=False).update(utilizado=True)
        solicitud = cls.objects.create(
            usuario=user,
            token=make_password(pin),
            expira_en=timezone.now() + timedelta(minutes=settings.PASSWORD_RESET_PIN_MINUTES),
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
