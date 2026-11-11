"""Validaciones comunes de cuentas para registro, administración y edición."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


def validar_correo_unico(email, user_id=None):
    correo = email.strip().lower()
    if User.objects.filter(email__iexact=correo).exclude(pk=user_id).exists():
        raise forms.ValidationError("Ese correo ya está registrado.")
    return correo


class RegistroForm(forms.ModelForm):
    email = forms.EmailField(required=True)
    password1 = forms.CharField(strip=False, widget=forms.PasswordInput)
    password2 = forms.CharField(strip=False, widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ["username", "email"]

    def clean_email(self):
        return validar_correo_unico(self.cleaned_data["email"])

    def clean(self):
        data = super().clean()
        if data.get("password1") != data.get("password2"):
            self.add_error("password2", "Las contraseñas no coinciden.")
        if data.get("password1"):
            candidato = User(username=data.get("username", ""), email=data.get("email", ""))
            try:
                validate_password(data["password1"], candidato)
            except forms.ValidationError as error:
                self.add_error("password1", error)
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class CrearUsuarioForm(forms.ModelForm):
    email = forms.EmailField(required=True)
    password = forms.CharField(strip=False, widget=forms.PasswordInput)
    password_confirm = forms.CharField(strip=False, widget=forms.PasswordInput)
    grupos = forms.ModelMultipleChoiceField(queryset=Group.objects.order_by("name"), required=False)

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name"]

    def clean_email(self):
        return validar_correo_unico(self.cleaned_data["email"])

    def clean(self):
        data = super().clean()
        if data.get("password") != data.get("password_confirm"):
            self.add_error("password_confirm", "Las contraseñas no coinciden.")
        if data.get("password"):
            user = User(
                username=data.get("username", ""),
                email=data.get("email", ""),
                first_name=data.get("first_name", ""),
                last_name=data.get("last_name", ""),
            )
            try:
                validate_password(data["password"], user)
            except forms.ValidationError as error:
                self.add_error("password", error)
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
            if self.cleaned_data["grupos"]:
                user.groups.set(self.cleaned_data["grupos"])
        return user


class EditarUsuarioForm(forms.ModelForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]

    def clean_email(self):
        return validar_correo_unico(self.cleaned_data["email"], self.instance.pk)
