"""Comprueba consultas acotadas con 1.200 usuarios y 12.000 evidencias."""

from datetime import timedelta
from time import perf_counter

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from Gesicom.models import Envio

from .models import CorreoPendiente, Notificacion, Novedad, PlazoReporte
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

    def test_follow_up_and_personal_agenda_keep_queries_bounded(self):
        plazo = PlazoReporte.objects.create(titulo="Entrega masiva", fecha_limite=timezone.now() + timedelta(days=1))
        plazo.grupos.add(Group.objects.get(name="instructor"))
        Envio.objects.filter(usuario_id__in=self.ids[:600]).update(plazo=plazo, limite_aplicado=plazo.fecha_limite)
        self.client.force_login(self.admin)
        inicio = perf_counter()
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("notificaciones:seguimiento_plazo", args=[plazo.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["seguimiento"]["total"], 1200)
        self.assertEqual(response.context["seguimiento"]["entregados"], 600)
        self.assertEqual(len(response.context["destinatarios"]), 25)
        self.assertLessEqual(len(queries), 20)
        print(
            f"ESCALA seguimiento 1200 destinatarios / 12000 evidencias: {len(queries)} consultas, {(perf_counter() - inicio) * 1000:.1f} ms"
        )
        self.client.force_login(User.objects.get(pk=self.ids[-1]))
        for name in ["role_instructor", "notificaciones:mis_plazos"]:
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            self.assertLessEqual(len(queries), 22)
