from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group


class Command(BaseCommand):
    help = 'Crea un usuario administrador con el grupo "administrador"'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, required=True, help='Nombre de usuario')
        parser.add_argument('--email', type=str, required=True, help='Correo electrónico')
        parser.add_argument('--password', type=str, required=True, help='Contraseña')

    def handle(self, *args, **options):
        username = options['username']
        email = options['email']
        password = options['password']

        # Verificar si el usuario ya existe
        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.ERROR(f'El usuario "{username}" ya existe.'))
            return

        # Crear el usuario con is_active=True para asegurar que puede acceder
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            is_staff=False,
            is_superuser=False,
            is_active=True  # 👈 IMPORTANTE: Asegurar que el usuario sea activo
        )

        # Asignar al grupo "administrador"
        admin_group, created = Group.objects.get_or_create(name='administrador')
        user.groups.add(admin_group)
        
        if created:
            self.stdout.write(self.style.SUCCESS('Grupo "administrador" creado'))

        self.stdout.write(
            self.style.SUCCESS(
                f'Usuario administrador "{username}" creado exitosamente y asignado al grupo "administrador".\n'
                f'EMAIL: {email}\n'
                f'Estado: ✓ ACTIVO (puede acceder de inmediato)'
            )
        )


