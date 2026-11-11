from django.contrib.auth.hashers import check_password, make_password
from django.db import migrations


def desactivar_predeterminado(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    queryset = User.objects.using(schema_editor.connection.alias).filter(username='admin', email='admin@example.com', is_superuser=True)
    for user in queryset:
        if check_password('Sena2026', user.password):
            user.password = make_password(None)
            user.is_active = False
            user.save(update_fields=['password', 'is_active'])


class Migration(migrations.Migration):
    dependencies = [('cuentas', '0004_email_unico_y_tokens_anteriores')]
    operations = [migrations.RunPython(desactivar_predeterminado, migrations.RunPython.noop)]
