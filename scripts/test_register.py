import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SENNOVA.settings')
import django
django.setup()
from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()
client = Client()
print('before:', User.objects.count())
resp = client.post('/register/', {
    'username': 'ui_test2',
    'email': 'ui_test2@example.com',
    'password1': 'Abcdef12',
    'password2': 'Abcdef12',
})
print('status_code:', resp.status_code)
print('redirect:', getattr(resp, 'url', None))
print('exists:', User.objects.filter(username='ui_test2').exists())
print('after:', User.objects.count())
