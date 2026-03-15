import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SENNOVA.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()

print('Usuarios totales antes:', User.objects.count())
qs = User.objects.filter(is_superuser=False)
print('No-superusuarios encontrados:', list(qs.values_list('username', flat=True)))
for u in list(qs):
    print('Eliminando:', u.username)
    u.delete()
print('Usuarios totales después:', User.objects.count())
