"""Novedades, plazos de entrega y una bandeja individual con cola de correo."""

import uuid

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from django.utils import timezone


class Novedad(models.Model):
    titulo = models.CharField(max_length=150)
    contenido = models.TextField(max_length=5000)
    enlace = models.URLField(blank=True)
    grupos = models.ManyToManyField(Group, blank=True, related_name="novedades")
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="novedades_publicadas"
    )
    publicada_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-publicada_en"]

    def __str__(self):
        return self.titulo

    @property
    def enlace_publico(self):
        from .acceso import enlace_seguro

        return enlace_seguro(self.enlace)


class PlazoReporte(models.Model):
    PROYECTOS = [
        ("LEM", "LEM"),
        ("GIVIT", "GIVIT"),
        ("ACAF", "ACAF"),
        ("DEPOS", "DEPOS"),
        ("IFPI", "IFPI"),
        ("TUGA", "TUGA"),
    ]
    titulo = models.CharField(max_length=150)
    descripcion = models.TextField(max_length=3000, blank=True)
    proyecto = models.CharField(max_length=20, choices=PROYECTOS, blank=True)
    fecha_limite = models.DateTimeField(db_index=True)
    recordatorio_horas = models.PositiveSmallIntegerField(default=24)
    grupos = models.ManyToManyField(Group, blank=True, related_name="plazos_reportes")
    activo = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    revision = models.PositiveIntegerField(default=1, db_default=1, editable=False)
    actualizado_en = models.DateTimeField(null=True, blank=True, editable=False)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="plazos_creados"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["fecha_limite"]
        indexes = [models.Index(fields=["activo", "fecha_limite"])]

    @property
    def vencido(self):
        return timezone.now() >= self.fecha_limite

    def __str__(self):
        return self.titulo


class Notificacion(models.Model):
    class Tipo(models.TextChoices):
        NOVEDAD = "novedad", "Novedad"
        APERTURA = "apertura", "Nuevo plazo"
        RECORDATORIO = "recordatorio", "Próximo vencimiento"
        VENCIMIENTO = "vencimiento", "Plazo vencido"
        EVIDENCIA = "evidencia", "Revisión de evidencia"
        SEGUIMIENTO = "seguimiento", "Recordatorio adicional"

    lote_id = models.UUIDField(default=uuid.uuid4, db_index=True, editable=False)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notificaciones")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    titulo = models.CharField(max_length=180)
    mensaje = models.TextField()
    enlace = models.CharField(max_length=300, blank=True)
    creada_en = models.DateTimeField(default=timezone.now)
    leida_en = models.DateTimeField(null=True, blank=True)
    novedad = models.ForeignKey(Novedad, on_delete=models.CASCADE, null=True, blank=True)
    plazo = models.ForeignKey(PlazoReporte, on_delete=models.CASCADE, null=True, blank=True)
    version_plazo = models.PositiveIntegerField(default=1)
    envio = models.ForeignKey("Gesicom.Envio", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-creada_en", "-pk"]
        indexes = [models.Index(fields=["usuario", "leida_en", "-creada_en"])]
        constraints = [
            models.UniqueConstraint(fields=["usuario", "novedad", "tipo"], name="notificacion_novedad_unica"),
            models.UniqueConstraint(
                fields=["usuario", "plazo", "version_plazo", "tipo"], name="notificacion_plazo_unica"
            ),
        ]

    def __str__(self):
        return self.titulo


class PreferenciasNotificacion(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="preferencias_notificacion"
    )
    correo_novedades = models.BooleanField(default=True)
    correo_plazos = models.BooleanField(default=True)
    correo_evidencias = models.BooleanField(default=True)


class CorreoPendiente(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        PROCESANDO = "procesando", "Procesando"
        ENVIADO = "enviado", "Enviado"
        ERROR = "error", "Error"
        CANCELADO = "cancelado", "Cancelado"

    notificacion = models.OneToOneField(Notificacion, on_delete=models.CASCADE, related_name="correo")
    estado = models.CharField(max_length=15, choices=Estado.choices, default=Estado.PENDIENTE)
    intentos = models.PositiveSmallIntegerField(default=0)
    proximo_intento = models.DateTimeField(default=timezone.now, db_index=True)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)
    enviado_en = models.DateTimeField(null=True, blank=True)
    ultimo_error = models.CharField(max_length=200, blank=True)

    class Meta:
        indexes = [models.Index(fields=["estado", "proximo_intento"])]
