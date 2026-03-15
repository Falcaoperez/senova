from django.apps import AppConfig


class GesicomConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Gesicom'

    def ready(self):
        # Import signals
        import Gesicom.signals
        
        # Crear superusuario automático al iniciar el servidor (si no existe)
        import sys
        if 'runserver' in sys.argv:
            try:
                from django.contrib.auth.models import User, Group
                if not User.objects.filter(username='admin').exists():
                    admin_user = User.objects.create_superuser(
                        username='admin',
                        email='admin@example.com',
                        password='Sena2026',
                        first_name='Admin',
                        last_name='Sennova'
                    )
                    # Asignar grupo administrador
                    group_admin, _ = Group.objects.get_or_create(name='administrador')
                    admin_user.groups.add(group_admin)
                    print("\n>>> CUENTA ADMIN CREADA AUTOMÁTICAMENTE: admin / Sena2026 <<<\n")
            except Exception:
                # Silenciar errores si las tablas aún no existen (primera migración)
                pass
