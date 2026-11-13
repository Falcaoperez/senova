import datetime
import re

from django import forms
from django.db import connection
from django.utils import timezone

from .models import Notificacion, Novedad, PlazoReporte, PreferenciasNotificacion


class FiltrosBandejaForm(forms.Form):
    q = forms.CharField(label="Buscar aviso", required=False, max_length=100)
    tipo = forms.ChoiceField(
        label="Tipo",
        required=False,
        choices=[("", "Todos los tipos"), *Notificacion.Tipo.choices],
        error_messages={"invalid_choice": "Selecciona un tipo válido."},
    )
    estado = forms.ChoiceField(
        label="Lectura",
        required=False,
        choices=[("", "Todos"), ("pendiente", "Sin leer"), ("leida", "Leídos")],
        error_messages={"invalid_choice": "Selecciona un estado válido."},
    )
    aviso = forms.IntegerField(label="Aviso", min_value=1, max_value=2**63 - 1, required=False)
    desde = forms.CharField(label="Desde", required=False, max_length=10)
    hasta = forms.CharField(label="Hasta", required=False, max_length=10)

    def clean_aviso(self):
        value = self.cleaned_data.get("aviso")
        if self.data.get("aviso") and not re.fullmatch(r"[0-9]{1,19}", str(self.data["aviso"])):
            raise forms.ValidationError("Selecciona un aviso válido.")
        return value

    def _fecha(self, nombre):
        value = self.cleaned_data[nombre]
        if not value:
            return None
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) and 1000 <= int(value[:4]) <= 9998:
            try:
                return datetime.date.fromisoformat(value)
            except ValueError:
                pass
        raise forms.ValidationError("Elige una fecha válida entre 1000-01-01 y 9998-12-31.")

    def clean_desde(self):
        return self._fecha("desde")

    def clean_hasta(self):
        return self._fecha("hasta")

    def clean(self):
        data = super().clean()
        if data.get("desde") and data.get("hasta") and data["desde"] > data["hasta"]:
            self.add_error("hasta", "La fecha final debe ser igual o posterior a la inicial.")
        return data


class FiltrosAgendaForm(forms.Form):
    q = forms.CharField(label="Buscar plazo", required=False, max_length=100)
    proyecto = forms.ChoiceField(
        label="Proyecto",
        required=False,
        choices=[("", "Todos los proyectos"), *PlazoReporte.PROYECTOS],
        error_messages={"invalid_choice": "Selecciona un proyecto válido."},
    )
    estado = forms.ChoiceField(
        label="Estado",
        required=False,
        choices=[
            ("", "Todos"),
            ("pendiente", "Pendiente"),
            ("vencido", "Vencido sin entrega"),
            ("entregado", "Entregado"),
            ("tardia", "Entregado fuera de plazo"),
        ],
        error_messages={"invalid_choice": "Selecciona un estado válido."},
    )
    plazo = forms.IntegerField(label="Plazo", min_value=1, max_value=2**63 - 1, required=False)
    vista = forms.ChoiceField(
        label="Vista",
        required=False,
        choices=[("lista", "Lista"), ("calendario", "Calendario")],
        error_messages={"invalid_choice": "Selecciona una vista válida."},
    )
    mes = forms.CharField(label="Mes", required=False, max_length=7)

    def __init__(self, data=None, **kwargs):
        data = data.copy() if data is not None else {}
        if not data.get("vista"):
            data["vista"] = "lista"
        self.mes_automatico = data.get("vista") == "calendario" and "mes" not in data
        if self.mes_automatico:
            data["mes"] = timezone.localdate().strftime("%Y-%m")
        super().__init__(data, **kwargs)

    def clean_mes(self):
        value = self.cleaned_data.get("mes", "")
        if value and (not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value) or not 1000 <= int(value[:4]) <= 9998):
            raise forms.ValidationError("Elige un mes válido entre 1000-01 y 9998-12.")
        return value

    def clean_plazo(self):
        value = self.cleaned_data.get("plazo")
        if self.data.get("plazo") and not re.fullmatch(r"[0-9]{1,19}", str(self.data["plazo"])):
            raise forms.ValidationError("Selecciona un plazo válido.")
        return value

    def clean(self):
        data = super().clean()
        if data.get("vista") == "calendario" and "mes" in data and not data["mes"]:
            self.add_error("mes", "Elige un mes para ver el calendario.")
        return data

    def fecha_mes(self):
        value = self.cleaned_data.get("mes")
        return datetime.date.fromisoformat(value + "-01") if value else None

    def consulta_url(self, **cambios):
        from django.http import QueryDict

        datos = self.cleaned_data if self.is_valid() else self.data
        params = QueryDict(mutable=True)
        for nombre in self.fields:
            value = cambios.get(nombre, datos.get(nombre))
            if value not in (None, ""):
                params[nombre] = value
        return "?" + params.urlencode() if params else ""


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
