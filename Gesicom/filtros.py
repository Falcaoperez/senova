"""Filtros compartidos por la lista, los gráficos y las descargas autorizadas."""

import datetime
import re

from django import forms
from django.http import QueryDict

from .models import Envio

SIN_PROYECTO = "__sin_proyecto"
ORDENES = [("fecha_envio", "Fecha"), ("nombre", "Nombre"), ("proyecto", "Proyecto"), ("tipo_evidencia", "Tipo")]
ESTADOS = [
    ("", "Todos los estados"),
    ("pendiente", "En revisión"),
    ("aprobada", "Aprobada"),
    ("rechazada", "Rechazada"),
]


class FiltrosEvidenciasForm(forms.Form):
    q = forms.CharField(label="Buscar evidencia", max_length=100, required=False)
    proyecto = forms.ChoiceField(label="Proyecto", required=False)
    estado = forms.ChoiceField(label="Estado", choices=ESTADOS, required=False)
    start = forms.CharField(label="Desde", required=False, widget=forms.TextInput(attrs={"type": "month"}))
    end = forms.CharField(label="Hasta", required=False, widget=forms.TextInput(attrs={"type": "month"}))
    quarters = forms.IntegerField(
        label="Trimestres",
        min_value=1,
        max_value=12,
        required=False,
        widget=forms.Select(choices=[(i, f"{i} trimestre{'s' if i != 1 else ''}") for i in range(1, 13)]),
    )
    order = forms.ChoiceField(choices=ORDENES, required=False, widget=forms.HiddenInput)
    dir = forms.ChoiceField(
        choices=[("asc", "Ascendente"), ("desc", "Descendente")], required=False, widget=forms.HiddenInput
    )
    plazo = forms.IntegerField(min_value=1, max_value=2**63 - 1, required=False, widget=forms.HiddenInput)
    usuario = forms.IntegerField(min_value=1, max_value=2**63 - 1, required=False, widget=forms.HiddenInput)

    def __init__(self, data=None, *, visibles, **kwargs):
        self.campos_recibidos = tuple(data or {})
        if data is not None:
            data = data.copy()
            for campo, valor in (("quarters", "4"), ("order", "fecha_envio"), ("dir", "desc")):
                if not str(data.get(campo, "")).strip():
                    data[campo] = valor
        super().__init__(data, **kwargs)
        self.fields["quarters"].initial = 4
        for campo, valor in (("quarters", "4"), ("order", "fecha_envio"), ("dir", "desc")):
            self.fields[campo].widget.attrs["data-default-value"] = valor
        for campo in ("start", "end"):
            self.fields[campo].widget.attrs.update(min="1000-01", max="9999-12")
        conocidos = dict(Envio.PROYECTO_CHOICES)
        historicos = (
            visibles.exclude(proyecto__in=conocidos)
            .exclude(proyecto="")
            .order_by("proyecto")
            .values_list("proyecto", flat=True)
            .distinct()
        )
        self.fields["proyecto"].choices = [
            ("", "Todos los proyectos"),
            *Envio.PROYECTO_CHOICES,
            (SIN_PROYECTO, "Sin proyecto"),
            *((p, p) for p in historicos),
        ]
        self.fields["q"].widget.attrs.update({"data-live-input": True, "placeholder": "Nombre, tipo u observaciones…"})

    def clean(self):
        data = super().clean()
        for field in ("start", "end"):
            value = data.get(field)
            if value and (not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value) or int(value[:4]) < 1000):
                self.add_error(field, "Indica un mes válido entre 1000-01 y 9999-12.")
        if (
            "start" in self.cleaned_data
            and "end" in self.cleaned_data
            and data.get("start")
            and data.get("end")
            and data["start"] > data["end"]
        ):
            self.add_error("end", "La fecha final no puede ser anterior a la inicial.")
        for field in ("plazo", "usuario"):
            raw = self.data.get(field, "")
            if raw and not re.fullmatch(r"[0-9]{1,19}", str(raw)):
                self.add_error(field, "El identificador debe ser un número válido.")
        data["quarters"] = data.get("quarters") or 4
        data["order"] = data.get("order") or "fecha_envio"
        data["dir"] = data.get("dir") or "desc"
        return data

    def mes(self, campo):
        value = self.cleaned_data.get(campo)
        return datetime.date.fromisoformat(value + "-01") if value else None

    def consulta_url(self):
        valido = self.is_valid()
        params = QueryDict(mutable=True)
        for campo in self.campos_recibidos:
            valor = self.cleaned_data.get(campo) if valido else self.data.get(campo)
            if campo in self.fields and valor not in (None, ""):
                params[campo] = valor
        return "?" + params.urlencode() if params else ""
