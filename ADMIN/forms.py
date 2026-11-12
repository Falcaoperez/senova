"""Filtros del directorio con el mismo catálogo de roles mostrado en pantalla."""

from django import forms


class FiltrosUsuariosForm(forms.Form):
    q = forms.CharField(label="Búsqueda", required=False, max_length=100)
    estado = forms.ChoiceField(
        label="Estado",
        required=False,
        choices=[("", "Todos"), ("activo", "Activos"), ("inactivo", "Inactivos")],
        error_messages={"invalid_choice": "Selecciona un estado válido."},
    )
    rol = forms.ChoiceField(label="Rol", required=False, error_messages={"invalid_choice": "Selecciona un rol válido."})

    def __init__(self, data=None, *, grupos):
        super().__init__(data)
        self.fields["rol"].choices = [("", "Todos los roles"), *[(str(g.pk), g.name) for g in grupos]]
