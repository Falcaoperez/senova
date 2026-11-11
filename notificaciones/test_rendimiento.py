"""Comprueba consultas acotadas con 1.200 usuarios y 12.000 evidencias."""

from time import perf_counter

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from Gesicom.models import Envio

from .models import CorreoPendiente, Notificacion, Novedad
from .services import publicar_novedad

User = get_user_model()


class EscalaMilUsuariosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        members = [
            User(username=f"carga_{index:04d}", email=f"carga_{index}@example.invalid", password="!")
            for index in range(1200)
        ]
        User.objects.bulk_create(members, batch_size=400)
        cls.ids = list(User.objects.filter(username__startswith="carga_").values_list("pk", flat=True))
        group = Group.objects.get(name="instructor")
        User.groups.through.objects.bulk_create(
            [User.groups.through(user_id=pk, group_id=group.pk) for pk in cls.ids], batch_size=400
        )
        Envio.objects.bulk_create(
            [
                Envio(
                    usuario_id=cls.ids[index % 1200],
                    nombre=f"Informe {index}",
                    proyecto="LEM",
                    tipo_evidencia="Informe Final",
                    aprobada=index % 3 == 0,
                )
                for index in range(12000)
            ],
            batch_size=500,
        )
        cls.admin = User.objects.create_superuser(
            "carga_admin", email="carga_admin@example.invalid", password="ClaveLocalCarga42!"
        )

    def test_views_do_not_load_every_user(self):
        self.client.force_login(self.admin)
        for name in ["admin_personalizado:gestionar_usuarios", "evidencias_list", "reportes"]:
            start = perf_counter()
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(reverse(name))
            elapsed = (perf_counter() - start) * 1000
            self.assertEqual(response.status_code, 200)
            self.assertLessEqual(len(queries), 26)
            if name == "admin_personalizado:gestionar_usuarios":
                self.assertEqual(len(response.context["usuarios"]), 25)
            print(f"ESCALA 1200 usuarios / 12000 evidencias: {name}: {len(queries)} consultas, {elapsed:.1f} ms")

    def test_broadcast_uses_batches_and_does_not_send_in_request(self):
        novedad = Novedad.objects.create(
            titulo="Prueba de capacidad", contenido="Novedad para el grupo de prueba.", creada_por=self.admin
        )
        novedad.grupos.add(Group.objects.get(name="instructor"))
        start = perf_counter()
        with CaptureQueriesContext(connection) as queries:
            total = publicar_novedad(novedad)
        elapsed = (perf_counter() - start) * 1000
        self.assertEqual(total, 1200)
        self.assertEqual(Notificacion.objects.filter(novedad=novedad).count(), 1200)
        self.assertEqual(CorreoPendiente.objects.filter(notificacion__novedad=novedad).count(), 1200)
        self.assertLessEqual(len(queries), 30)
        print(
            f"ESCALA aviso para 1200 usuarios: {len(queries)} consultas, {elapsed:.1f} ms; correo encolado, no enviado en la petición"
        )
