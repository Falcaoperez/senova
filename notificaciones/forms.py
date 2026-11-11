from urllib.parse import urlsplit

from django import forms
from django.utils import timezone

from .models import Novedad, PlazoReporte, PreferenciasNotificacion


class NovedadForm(forms.ModelForm):
    class Meta:
        model = Novedad
        fields = ["titulo", "contenido", "enlace", "grupos"]
        labels = {
            "titulo": "Título de la novedad",
            "contenido": "Mensaje para la comunidad",
            "enlace": "Enlace adicional (opcional)",
            "grupos": "Dirigida a",
        }
        help_texts = {"grupos": "Sin selección, la novedad se dirige a todos los usuarios activos."}
        widgets = {"contenido": forms.Textarea(attrs={"rows": 6}), "grupos": forms.CheckboxSelectMultiple()}

    def clean_enlace(self):
        enlace = self.cleaned_data["enlace"]
        if enlace and urlsplit(enlace).scheme not in ["https", "http"]:
            raise forms.ValidationError("Utiliza un enlace HTTP o HTTPS.")
        return enlace


class PlazoReporteForm(forms.ModelForm):
    class Meta:
        model = PlazoReporte
        fields = ["titulo", "descripcion", "proyecto", "fecha_limite", "recordatorio_horas", "grupos", "activo"]
        labels = {
            "titulo": "Nombre del reporte o entrega",
            "descripcion": "Indicaciones",
            "proyecto": "Proyecto",
            "fecha_limite": "Fecha y hora límite (Colombia)",
            "recordatorio_horas": "Recordar con estas horas de anticipación",
            "grupos": "Dirigido a",
            "activo": "Plazo activo",
        }
        help_texts = {
            "grupos": "Sin selección, aplica a todos los usuarios activos.",
            "proyecto": "Sin selección, admite cualquiera de los proyectos.",
        }
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 4}),
            "fecha_limite": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
            "grupos": forms.CheckboxSelectMultiple(),
        }

    def clean_fecha_limite(self):
        fecha = self.cleaned_data["fecha_limite"]
        if fecha <= timezone.now():
            raise forms.ValidationError("La fecha límite debe ser futura.")
        return fecha

    def clean_recordatorio_horas(self):
        horas = self.cleaned_data["recordatorio_horas"]
        if not 1 <= horas <= 720:
            raise forms.ValidationError("El recordatorio debe estar entre 1 y 720 horas antes del plazo.")
        return horas


class PreferenciasForm(forms.ModelForm):
    class Meta:
        model = PreferenciasNotificacion
        fields = ["correo_novedades", "correo_plazos", "correo_evidencias"]
        labels = {
            "correo_novedades": "Novedades de la comunidad",
            "correo_plazos": "Recordatorios y vencimientos de reportes",
            "correo_evidencias": "Revisión y observaciones de mis evidencias",
        }
