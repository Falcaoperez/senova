from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Rol(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre


class InstructorProfile(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    especialidad = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"Instructor: {self.usuario.get_full_name()}"


class Envio(models.Model):
    PROYECTO_CHOICES = [
        ("LEM", "LEM"),
        ("GIVIT", "GIVIT"),
        ("ACAF", "ACAF"),
        ("DEPOS", "DEPOS"),
        ("IFPI", "IFPI"),
        ("TUGA", "TUGA"),
    ]
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name="envios")
    nombre = models.CharField(max_length=80, blank=True)
    proyecto = models.CharField(max_length=20, choices=PROYECTO_CHOICES, blank=True)
    tipo_evidencia = models.CharField(max_length=50)
    link_evidencia = models.URLField(max_length=200, blank=True, null=True)
    archivo_evidencia = models.FileField(upload_to="evidencias/", blank=True, null=True)
    observaciones = models.TextField(blank=True, null=True)
    aprobada = models.BooleanField(default=False)
    rechazada = models.BooleanField(default=False)
    fecha_envio = models.DateField(default=timezone.localdate)
    registrado_en = models.DateTimeField(default=timezone.now, db_index=True)
    limite_aplicado = models.DateTimeField(null=True, blank=True)
    plazo = models.ForeignKey(
        "notificaciones.PlazoReporte", null=True, blank=True, on_delete=models.SET_NULL, related_name="envios"
    )

    class Meta:
        ordering = ["-fecha_envio", "-pk"]
        indexes = [
            models.Index(fields=["usuario", "fecha_envio"]),
            models.Index(fields=["proyecto", "fecha_envio"]),
            models.Index(fields=["aprobada", "rechazada", "fecha_envio"]),
        ]
        constraints = [
            models.CheckConstraint(condition=~models.Q(aprobada=True, rechazada=True), name="envio_estado_consistente")
        ]

    @property
    def entrega_tardia(self):
        return bool(self.limite_aplicado and self.registrado_en > self.limite_aplicado)

    def __str__(self):
        return self.tipo_evidencia
