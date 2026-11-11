"""Credenciales de revisión privadas y aleatorias, sin cuentas automáticas al iniciar."""

import json
import secrets
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

User = get_user_model()


class Command(BaseCommand):
    help = "Crea una cuenta de revisión por rol y guarda las credenciales en un archivo privado."

    def add_arguments(self, parser):
        parser.add_argument("--archivo", default=".local/credenciales_revision.json")

    def handle(self, *args, **options):
        destination = Path(options["archivo"]).resolve()
        if destination.exists():
            self.stdout.write("El archivo de credenciales ya existe. No se cambiaron las contraseñas.")
            return
        credentials = []
        with transaction.atomic():
            for role in ["administrador", "usuario", "instructor", "investigador", "coordinador", "dinamizador"]:
                username = f"revision.{role}"
                if User.objects.filter(username=username).exists():
                    self.stdout.write(f"La cuenta {username} ya existe; se conserva sin cambios.")
                    continue
                password = secrets.token_urlsafe(18)
                user = User.objects.create_user(
                    username=username,
                    email=f"revision.{role}@example.invalid",
                    password=password,
                    first_name="Revisión",
                    last_name=role.capitalize(),
                    is_staff=role == "administrador",
                    is_superuser=role == "administrador",
                )
                group, _ = Group.objects.get_or_create(name=role)
                user.groups.set([group])
                credentials.append({"rol": role, "usuario": username, "password": password})
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination.write_text(json.dumps(credentials, ensure_ascii=False, indent=2))
        destination.chmod(0o600)
        self.stdout.write(
            self.style.SUCCESS(f"{len(credentials)} cuentas de revisión creadas. Credenciales privadas: {destination}")
        )
