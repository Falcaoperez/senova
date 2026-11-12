"""Cambios de lectura acotados a la cuenta que realiza la petición."""

from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.urls import reverse
from django.utils import timezone

from .models import Notificacion


def regreso_bandeja(valor):
    destino = reverse("notificaciones:bandeja")
    valor = valor or ""
    if "\\" in valor or any(ord(c) < 32 for c in valor):
        return destino
    try:
        url = urlsplit(valor)
    except ValueError:
        return destino
    return valor if not url.scheme and not url.netloc and url.path == destino else destino


@transaction.atomic
def cambiar_lectura(usuario, identificadores, accion):
    if accion not in {"leida", "pendiente"}:
        raise ValidationError("Selecciona una acción de lectura válida.")
    if not 1 <= len(identificadores) <= 100 or any(
        not pk.isascii() or not pk.isdigit() or len(pk) > 18 for pk in identificadores
    ):
        raise ValidationError("Selecciona entre 1 y 100 notificaciones.")
    ids = {int(pk) for pk in identificadores}
    avisos = Notificacion.objects.select_for_update().filter(pk__in=ids, usuario=usuario).order_by("pk")
    if len(list(avisos.values_list("pk", flat=True))) != len(ids):
        raise Http404
    if accion == "leida":
        return avisos.filter(leida_en__isnull=True).update(leida_en=timezone.now())
    return avisos.filter(leida_en__isnull=False).update(leida_en=None)
