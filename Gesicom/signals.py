"""Señales (signals) para gestionar grupos y asignaciones automáticas.

- `ensure_groups`: crea los grupos necesarios tras aplicar migraciones.
- `assign_default_group`: al crear un usuario, se le asigna el grupo 'usuario' por defecto.
"""
from django.db.models.signals import post_save, post_migrate
from django.dispatch import receiver
from django.contrib.auth.models import User, Group


@receiver(post_migrate)
def ensure_groups_and_admin(sender, **kwargs):
    """Crea grupos de rol y usuario administrador si no existen."""
    # 1. Crear Grupos
    for name in ["usuario", "instructor", "investigador", "dinamizador", "coordinador", "administrador"]:
        Group.objects.get_or_create(name=name)
    
    # 2. Crear Superusuario Automático
    if not User.objects.filter(username='admin').exists():
        admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='Sena2026',
            first_name='Admin',
            last_name='Sennova'
        )
        # Asignarle el grupo administrador por si acaso
        group_admin = Group.objects.get(name='administrador')
        admin_user.groups.add(group_admin)
        print("\n>>> USUARIO ADMINISTRADOR CREADO AUTOMÁTICAMENTE: admin / Sena2026 <<<\n")


@receiver(post_save, sender=User)
def assign_default_group(sender, instance, created, **kwargs):
    """Al crear un usuario nuevo, añadirlo al grupo 'usuario' por defecto."""
    if created:
        group, _ = Group.objects.get_or_create(name="usuario")
        instance.groups.add(group)
