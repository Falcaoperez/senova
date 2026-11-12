from django import forms
from django.db import connection
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
        from .acceso import enlace_seguro

        enlace = self.cleaned_data["enlace"]
        if enlace and not enlace_seguro(enlace):
            raise forms.ValidationError("Utiliza un enlace HTTP o HTTPS.")
        return enlace


class PlazoReporteForm(forms.ModelForm):
    fecha_limite = forms.DateTimeField(
        label="Fecha y hora límite (Colombia)",
        widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
    )
    revision_actual = forms.IntegerField(min_value=1, required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fecha_original = self.instance.fecha_limite if self.instance.pk else None
        if self.instance.pk:
            self.initial["revision_actual"] = self.instance.revision
            self.fields["revision_actual"].required = True

    def clean(self):
        data = super().clean()
        if self.instance.pk and data.get("revision_actual"):
            from .plazos import comprobar_revision

            queryset = PlazoReporte.objects.all()
            if connection.in_atomic_block:
                queryset = queryset.select_for_update()
            vigente = queryset.filter(pk=self.instance.pk).first()
            if not vigente:
                raise forms.ValidationError("El plazo ya no está disponible.")
            comprobar_revision(vigente, data["revision_actual"])
        return data

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
            "grupos": forms.CheckboxSelectMultiple(),
        }

    def clean_fecha_limite(self):
        fecha = self.cleaned_data["fecha_limite"]
        if self.fecha_original:
            original_visible = timezone.localtime(self.fecha_original).replace(second=0, microsecond=0)
            if fecha == original_visible or fecha == self.fecha_original:
                return self.fecha_original
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
