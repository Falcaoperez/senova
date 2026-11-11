"""Evita correos duplicados incluso durante registros simultáneos."""
from django.db import migrations
from django.db.models import Count
from django.db.models.functions import Lower


def preparar(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    duplicate = User.objects.using(schema_editor.connection.alias).exclude(email='').annotate(correo=Lower('email')).values('correo').annotate(total=Count('pk')).filter(total__gt=1).exists()
    if duplicate:
        raise RuntimeError('Existen usuarios con el mismo correo. Corrige los duplicados antes de aplicar el índice de cuentas.')
    tokens = apps.get_model('cuentas', 'PasswordResetToken')
    tokens.objects.using(schema_editor.connection.alias).filter(utilizado=False).update(utilizado=True)
    table = schema_editor.quote_name(User._meta.db_table)
    schema_editor.execute(f"CREATE UNIQUE INDEX cuentas_email_usuario_unico ON {table} ((NULLIF(LOWER(email), '')))")


def revertir(apps, schema_editor):
    table = schema_editor.quote_name(apps.get_model('auth', 'User')._meta.db_table)
    sql = f'DROP INDEX cuentas_email_usuario_unico ON {table}' if schema_editor.connection.vendor == 'mysql' else 'DROP INDEX cuentas_email_usuario_unico'
    schema_editor.execute(sql)


class Migration(migrations.Migration):
    atomic = False
    dependencies = [('cuentas', '0003_alter_passwordresettoken_options_and_more'), ('auth', '0012_alter_user_first_name_max_length')]
    operations = [migrations.RunPython(preparar, revertir)]
