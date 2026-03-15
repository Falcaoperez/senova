# Generated initial migration for Gesicom
# This creates the missing Gesicom_Rol table to satisfy the error

from django.db import migrations, models


class Migration(migrations.Migration):

    # No parent dependencies - this is the first migration in Gesicom 
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Rol',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=50, unique=True)),
                ('descripcion', models.CharField(blank=True, max_length=100)),
            ],
            options={
                'verbose_name': 'Rol',
                'verbose_name_plural': 'Roles',
                'ordering': ['nombre'],
            },
        ),
    ]
