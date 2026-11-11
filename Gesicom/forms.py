from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class ProfileForm(forms.ModelForm):
    nombre = forms.CharField(label="Nombre", max_length=150)
    apellido = forms.CharField(label="Apellido", max_length=150)
    correo = forms.EmailField(label="Correo electrónico")
    contrasena = forms.CharField(
        label="Nueva contraseña (opcional)",
        required=False,
        strip=False,
        widget=forms.PasswordInput,
        help_text="Mínimo 8 caracteres, con un número o símbolo.",
    )

    class Meta:
        model = User
        fields = ["username"]
        labels = {"username": "Nombre de usuario"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for alias, field in [("nombre", "first_name"), ("apellido", "last_name"), ("correo", "email")]:
            self.fields[alias].initial = getattr(self.instance, field)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input-linea"

    def clean_correo(self):
        email = self.cleaned_data["correo"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ese correo ya está registrado.")
        return email

    def clean(self):
        data = super().clean()
        self.instance.username = data.get("username", self.instance.username)
        self.instance.first_name = data.get("nombre", "")
        self.instance.last_name = data.get("apellido", "")
        self.instance.email = data.get("correo", "")
        if data.get("contrasena"):
            try:
                validate_password(data["contrasena"], self.instance)
            except forms.ValidationError as error:
                self.add_error("contrasena", error)
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data["contrasena"]:
            user.set_password(self.cleaned_data["contrasena"])
        if commit:
            user.save()
        return user
