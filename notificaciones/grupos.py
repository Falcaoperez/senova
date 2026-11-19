"""Protección de audiencias al asignar y eliminar grupos de comunicación."""

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef, Q

from .models import Novedad, PlazoReporte

MENSAJE_GRUPO_ASIGNADO = "El grupo tiene novedades o plazos asignados. Reasigna sus destinatarios antes de eliminarlo."
MENSAJE_GRUPO_RETIRADO = (
    "Un grupo seleccionado ya no está disponible. Actualiza el formulario y vuelve a elegir los destinatarios."
)


def grupos_con_comunicaciones(consulta):
    novedades = Novedad.grupos.through.objects.filter(group_id=OuterRef("pk"))
    plazos = PlazoReporte.grupos.through.objects.filter(group_id=OuterRef("pk"))
    return consulta.alias(tiene_novedades=Exists(novedades), tiene_plazos=Exists(plazos)).filter(
        Q(tiene_novedades=True) | Q(tiene_plazos=True)
    )


def bloquear_grupos(grupos):
    """Valida y bloquea los grupos elegidos dentro de la transacción de guardado."""
    ids = {grupo.pk for grupo in grupos}
    if None in ids:
        raise ValidationError(MENSAJE_GRUPO_RETIRADO)
    actuales = list(Group.objects.select_for_update().filter(pk__in=ids).only("pk").order_by("pk"))
    if len(actuales) != len(ids):
        raise ValidationError(MENSAJE_GRUPO_RETIRADO)
    return actuales
