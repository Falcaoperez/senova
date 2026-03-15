from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group


class Command(BaseCommand):
    help = 'Crea usuarios de prueba para el panel de administración'

    def handle(self, *args, **options):
        # Crear grupos si no existen
        grupos_nombres = ['Autor', 'Editor', 'Administrador']
        grupos = {}

        for nombre_grupo in grupos_nombres:
            grupo, created = Group.objects.get_or_create(name=nombre_grupo.lower())
            grupos[nombre_grupo] = grupo
            if created:
                self.stdout.write(self.style.SUCCESS(f'Grupo "{nombre_grupo}" creado'))

        # Datos de usuarios de prueba
        usuarios_data = [
            {'username': 'maria.rodriguez', 'email': 'maria.r@email.com', 'first_name': 'María', 'last_name': 'Rodríguez', 'grupo': 'Autor', 'activo': True},
            {'username': 'juan.perez', 'email': 'juan.p@email.com', 'first_name': 'Juan', 'last_name': 'Pérez', 'grupo': 'Autor', 'activo': True},
            {'username': 'maria.folaia', 'email': 'pun.c@email.com', 'first_name': 'María', 'last_name': 'Folaia', 'grupo': 'Editor', 'activo': True},
            {'username': 'maria.herez', 'email': 'juan.g@email.com', 'first_name': 'María', 'last_name': 'Hérez', 'grupo': 'Editor', 'activo': False},
            {'username': 'cntry.marco', 'email': 'enm.e@email.com', 'first_name': 'Cntry', 'last_name': 'Marco', 'grupo': 'Administrador', 'activo': False},
            {'username': 'lan.rorez', 'email': 'con.n@email.com', 'first_name': 'Lan', 'last_name': 'Rorez', 'grupo': 'Administrador', 'activo': False},
            {'username': 'mary.diolez', 'email': 'man.v@email.com', 'first_name': 'Mary', 'last_name': 'Diolez', 'grupo': 'Editor', 'activo': False},
            {'username': 'lisra.cargez', 'email': 'con.p@email.com', 'first_name': 'Lisra', 'last_name': 'Cargez', 'grupo': 'Autor', 'activo': False},
        ]

        usuarios_creados = 0
        for user_data in usuarios_data:
            username = user_data['username']

            # Verificar si el usuario ya existe
            if User.objects.filter(username=username).exists():
                self.stdout.write(self.style.WARNING(f'Usuario "{username}" ya existe, omitiendo...'))
                continue

            # Crear el usuario
            user = User.objects.create_user(
                username=username,
                email=user_data['email'],
                password='Sena2024',  # Contraseña por defecto para todos
                first_name=user_data['first_name'],
                last_name=user_data['last_name'],
                is_active=user_data['activo']
            )

            # Asignar grupo
            grupo = grupos[user_data['grupo']]
            user.groups.add(grupo)

            usuarios_creados += 1
            self.stdout.write(self.style.SUCCESS(
                f'Usuario "{username}" creado - Grupo: {user_data["grupo"]} - '
                f'Estado: {"Activo" if user_data["activo"] else "Inactivo"}'
            ))

        self.stdout.write(
            self.style.SUCCESS(
                f'\nProceso completado: {usuarios_creados} usuarios de prueba creados.\n'
                f'Contrasena por defecto para todos: Sena2024'
            )
        )
