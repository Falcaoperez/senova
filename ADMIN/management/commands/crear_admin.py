import getpass
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

User = get_user_model()


class Command(BaseCommand):
    help = "Crea una cuenta del panel administrativo con una contraseña validada."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", required=True)

    def handle(self, *args, **options):
        user = User(username=options["username"], email=options["email"], is_active=True)
        password = os.environ.get("GESICOM_ADMIN_PASSWORD") or getpass.getpass("Contraseña del administrador: ")
        try:
            user.full_clean(exclude=["password"])
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages))
        with transaction.atomic():
            user.set_password(password)
            user.save()
            group, _ = Group.objects.get_or_create(name="administrador")
            user.groups.set([group])
        self.stdout.write(self.style.SUCCESS(f"Cuenta administrativa creada: {user.username}"))
