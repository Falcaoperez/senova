from django.db import models
from django.contrib.auth.models import User

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
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='envios')
    nombre = models.CharField(max_length=80, blank=True)
    proyecto = models.CharField(max_length=20, choices=PROYECTO_CHOICES, blank=True)
    tipo_evidencia = models.CharField(max_length=50)
    link_evidencia = models.URLField(max_length=200, blank=True, null=True)
    archivo_evidencia = models.FileField(upload_to='evidencias/', blank=True, null=True)
    observaciones = models.TextField(blank=True, null=True)
    aprobada = models.BooleanField(default=False)
    rechazada = models.BooleanField(default=False)
    fecha_envio = models.DateField(auto_now_add=True)
    class Meta:
        ordering = ['-fecha_envio']
    def __str__(self):
        return self.tipo_evidencia
