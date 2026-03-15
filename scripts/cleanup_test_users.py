import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SENNOVA.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()

patterns = ['ui_test', 'testuser_tmp', 'ui_test_cli', 'ui_test_mcp', 'ui_test2', 'ui_test3', 'ui_test5', 'ui_test_mcp2']
print('Users before:', User.objects.count())
removed = []
for p in patterns:
    qs = User.objects.filter(username__startswith=p)
    for u in qs:
        removed.append(u.username)
        u.delete()
print('Removed users:', removed)
print('Users after:', User.objects.count())
