"""Impide que el borrado en cascada de un grupo convierta su audiencia en pública."""

from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .grupos import MENSAJE_GRUPO_ASIGNADO, grupos_con_comunicaciones


@receiver(pre_delete, sender=Group, dispatch_uid="gesicom.proteger_audiencias_grupo")
def proteger_audiencias_grupo(sender, instance, using, **kwargs):
    with transaction.atomic(using=using):
        candidato = Group.objects.using(using).filter(pk=instance.pk)
        # Las asignaciones necesitan la clave foránea de este grupo. El bloqueo
        # serializa su guardado antes de comprobar si el grupo sigue sin uso.
        if candidato.select_for_update().values_list("pk", flat=True).first() is None:
            return
        if grupos_con_comunicaciones(candidato).exists():
            raise ProtectedError(MENSAJE_GRUPO_ASIGNADO, {instance})
