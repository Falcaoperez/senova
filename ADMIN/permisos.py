"""Permisos de grupos con alcance explícito, revisión y confirmación de identidad."""

from django import forms
from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q
from django.utils.crypto import constant_time_compare, salted_hmac

from cuentas.models import RegistroSeguridad

from .services import _actor_autorizado

ROLES_SISTEMA = {"usuario", "instructor", "investigador", "coordinador", "dinamizador", "administrador"}
CATALOGO = (
    ("Gesicom", "envio", "view_envio", "Consultar evidencias", "Consulta de evidencias desde Django admin."),
    ("Gesicom", "envio", "add_envio", "Crear evidencias", "Registro de evidencias desde Django admin."),
    ("Gesicom", "envio", "change_envio", "Editar evidencias", "Edición y revisión desde Django admin."),
    ("Gesicom", "envio", "delete_envio", "Eliminar evidencias", "Eliminación de evidencias desde Django admin."),
    ("auth", "user", "change_user", "Editar cuentas", "Edición en Django admin, respetando las cuentas protegidas."),
    (
        "admin",
        "logentry",
        "view_logentry",
        "Consultar registro administrativo",
        "Permiso histórico de Django. No habilita el acceso al panel de administración.",
    ),
)


class ConflictoPermisos(ValidationError):
    def __init__(self):
        super().__init__(
            "Los permisos del grupo cambiaron en otra sesión. Recarga la versión actual antes de guardar.",
            code="conflicto",
        )


def revision_permisos(grupo):
    ids = sorted(grupo.permissions.values_list("pk", flat=True))
    return salted_hmac(
        "gesicom.permisos", f"{grupo.pk}:{grupo.name}:" + ",".join(map(str, ids)), algorithm="sha256"
    ).hexdigest()


def grupo_protegido(grupo):
    return grupo.name == "administrador" or grupo.user_set.filter(Q(is_staff=True) | Q(is_superuser=True)).exists()


def permisos_catalogo():
    condicion = Q(pk__in=[])
    for app, modelo, codigo, _, _ in CATALOGO:
        condicion |= Q(content_type__app_label=app, content_type__model=modelo, codename=codigo)
    return {p.codename: p for p in Permission.objects.filter(condicion).select_related("content_type")}


def _actor(actor, password, *, nativo=False, crear=False):
    actual = User.objects.filter(pk=actor.pk, is_active=True).first()
    if not actual:
        raise ValidationError("La cuenta ya no está autorizada.")
    if nativo:
        permiso = "auth.add_group" if crear else "auth.change_group"
        if not (actual.is_staff and actual.has_perm(permiso)):
            raise ValidationError("No tienes permiso para administrar este grupo.")
    else:
        _actor_autorizado(actual)
    if not actual.check_password(password or ""):
        raise ValidationError("Confirma tu contraseña actual para guardar los permisos.")
    return actual


def _grupo(pk, revision, actor):
    grupo = Group.objects.select_for_update().filter(pk=pk).first()
    if not grupo:
        raise ValidationError("El grupo ya no está disponible.")
    if not actor.is_superuser and grupo_protegido(grupo):
        raise ValidationError("Solo un superadministrador puede modificar un grupo con cuentas protegidas.")
    if not constant_time_compare(revision or "", revision_permisos(grupo)):
        raise ConflictoPermisos()
    return grupo


def _guardar(actor, grupo, ids, *, nombre=None):
    actuales = set(grupo.permissions.values_list("pk", flat=True)) if grupo.pk else set()
    cambio_nombre = nombre is not None and nombre != grupo.name
    if cambio_nombre and grupo.name in ROLES_SISTEMA:
        raise ValidationError("Los nombres de los roles del sistema deben conservarse.")
    cambios = len(ids ^ actuales)
    nuevo = not grupo.pk
    if cambio_nombre:
        grupo.name = nombre
    if nuevo or cambio_nombre:
        grupo.save()
    if nuevo or cambios:
        grupo.permissions.set(ids)
    if nuevo or cambios or cambio_nombre:
        RegistroSeguridad.objects.create(
            actor=actor, accion="admin:permisos_grupo", ruta=f"/administrador/permisos/?group={grupo.pk}"
        )
    return grupo, cambios


@transaction.atomic
def actualizar_permisos(actor, pk, revision, cambios, password):
    actual = _actor(actor, password)
    grupo = _grupo(pk, revision, actual)
    catalogo = permisos_catalogo()
    if (
        not cambios
        or not set(cambios).issubset(catalogo)
        or any(v not in {"allowed", "inherited", "denied"} for v in cambios.values())
    ):
        raise ValidationError("Selecciona opciones de permiso válidas.")
    ids = set(grupo.permissions.values_list("pk", flat=True))
    for codigo, valor in cambios.items():
        if valor == "allowed":
            ids.add(catalogo[codigo].pk)
        else:
            ids.discard(catalogo[codigo].pk)
    return _guardar(actual, grupo, ids)[1]


@transaction.atomic
def guardar_grupo_nativo(actor, datos, *, pk=None):
    actual = _actor(actor, datos.get("contrasena_actual"), nativo=True, crear=pk is None)
    grupo = _grupo(pk, datos.get("revision_actual"), actual) if pk is not None else Group(name=datos["name"])
    ids = {p.pk for p in datos.get("permissions", [])}
    return _guardar(actual, grupo, ids, nombre=datos.get("name", grupo.name))[0]


class PermisosGrupoForm(forms.Form):
    group = forms.IntegerField(min_value=1, max_value=2**63 - 1, widget=forms.HiddenInput)
    revision_actual = forms.CharField(widget=forms.HiddenInput)
    contrasena_actual = forms.CharField(
        label="Tu contraseña actual",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, *args, grupo, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial.update(group=grupo.pk, revision_actual=revision_permisos(grupo))
        asignados = set(grupo.permissions.values_list("pk", flat=True))
        catalogo = permisos_catalogo()
        self.opciones = []
        self.campos_enviados = set(self.data)
        if self.is_bound:
            self.data = self.data.copy()
        for _, _, codigo, label, ayuda in CATALOGO:
            permiso = catalogo.get(codigo)
            if not permiso:
                continue
            nombre = f"perm_{codigo}_1"
            field = forms.ChoiceField(
                label=label,
                help_text=ayuda,
                required=False,
                choices=[("inherited", "Sin asignar"), ("allowed", "Asignado"), ("denied", "Retirar permiso")],
                initial="allowed" if permiso.pk in asignados else "inherited",
            )
            # Acepta el valor histórico en POST, sin ofrecer dos opciones equivalentes.
            field.widget.choices = field.choices[:2]
            self.fields[nombre] = field
            if self.is_bound and nombre not in self.data:
                self.data[nombre] = field.initial
            self.opciones.append(self[nombre])

    def clean(self):
        datos = super().clean()
        if any(k.startswith("perm_") and k not in self.fields for k in self.data):
            raise ValidationError("Hay una opción de permiso no reconocida; no se guardó ningún cambio.")
        if hasattr(self.data, "getlist") and any(
            len(self.data.getlist(k)) > 1 for k in self.fields if k.startswith("perm_") and k in self.data
        ):
            raise ValidationError("Cada permiso debe tener una sola opción.")
        return datos

    def cambios(self):
        return {
            codigo: self.cleaned_data[f"perm_{codigo}_1"]
            for _, _, codigo, _, _ in CATALOGO
            if f"perm_{codigo}_1" in self.campos_enviados and f"perm_{codigo}_1" in self.cleaned_data
        }


class GrupoNativoForm(forms.ModelForm):
    revision_actual = forms.CharField(required=False, widget=forms.HiddenInput)
    contrasena_actual = forms.CharField(
        label="Tu contraseña actual",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    class Meta:
        model = Group
        fields = ["name", "permissions"]

    def __init__(self, *args, usuario=None, **kwargs):
        self.usuario = usuario
        super().__init__(*args, **kwargs)
        if self.instance.pk and "revision_actual" in self.fields:
            self.initial["revision_actual"] = revision_permisos(self.instance)
            self.fields["revision_actual"].required = True

    def clean(self):
        data = super().clean()
        if self.instance.pk and data.get("revision_actual"):
            consulta = Group.objects.select_for_update() if connection.in_atomic_block else Group.objects.all()
            actual = consulta.filter(pk=self.instance.pk).first()
            if not actual:
                raise ValidationError("El grupo ya no está disponible.")
            if not constant_time_compare(data["revision_actual"], revision_permisos(actual)):
                raise ConflictoPermisos()
        if data.get("contrasena_actual") and self.usuario:
            _actor(self.usuario, data["contrasena_actual"], nativo=True, crear=not self.instance.pk)
        return data
