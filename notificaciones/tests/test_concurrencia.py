from concurrent.futures import ThreadPoolExecutor

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.mail import get_connection
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings

from ..models import CorreoPendiente, Notificacion, Novedad
from ..services import procesar_correos, publicar_novedad

User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class TrabajadoresConcurrentesTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "mysql":
            self.skipTest("La concurrencia se comprueba con los bloqueos reales de MySQL.")
        group = Group.objects.get(name="instructor")
        User.objects.bulk_create(
            [User(username=f"cola_{i}", email=f"cola_{i}@example.invalid", password="!") for i in range(20)]
        )
        ids = User.objects.filter(username__startswith="cola_").values_list("pk", flat=True)
        User.groups.through.objects.bulk_create([User.groups.through(user_id=pk, group_id=group.pk) for pk in ids])
        self.novedad = Novedad.objects.create(titulo="Prueba de concurrencia", contenido="Un aviso por destinatario.")
        self.novedad.grupos.add(group)
        get_connection()
        mail.outbox = []

    def ejecutar(self, callback):
        close_old_connections()
        try:
            return callback()
        finally:
            close_old_connections()

    def test_two_publishers_do_not_duplicate_notifications(self):
        pk = self.novedad.pk

        def publish():
            return publicar_novedad(Novedad.objects.get(pk=pk))

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.ejecutar(publish), range(2)))
        self.assertEqual(sum(results), 20)
        self.assertEqual(Notificacion.objects.count(), 20)
        self.assertEqual(CorreoPendiente.objects.count(), 20)

    def test_two_workers_claim_different_messages(self):
        publicar_novedad(self.novedad)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.ejecutar(lambda: procesar_correos(10)), range(2)))
        self.assertEqual(sum(results), 20)
        self.assertEqual(CorreoPendiente.objects.filter(estado="enviado").count(), 20)
        self.assertEqual(len(mail.outbox), 20)
        self.assertEqual(len({message.to[0] for message in mail.outbox}), 20)

    def test_manual_reminders_from_two_administrators_are_not_duplicated(self):
        from datetime import timedelta

        from django.utils import timezone

        from ..models import PlazoReporte
        from ..plazos import recordar_pendientes

        admin = User.objects.create_superuser(
            "plazos_concurrentes", "concurrente@example.invalid", "PruebaConcurrente29!"
        )
        plazo = PlazoReporte.objects.create(
            titulo="Seguimiento concurrente", fecha_limite=timezone.now() + timedelta(days=1)
        )
        plazo.grupos.add(Group.objects.get(name="instructor"))

        def recordar():
            return recordar_pendientes(User.objects.get(pk=admin.pk), plazo.pk, 1)

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(lambda _: self.ejecutar(recordar), range(2)))
        self.assertEqual(sum(resultados), 20)
        self.assertEqual(Notificacion.objects.filter(tipo="seguimiento").count(), 20)
        self.assertEqual(CorreoPendiente.objects.count(), 20)

    def test_two_deadline_editors_cannot_overwrite_the_same_revision(self):
        from datetime import timedelta

        from django.utils import timezone

        from ..models import PlazoReporte
        from ..plazos import ConflictoPlazo, guardar_plazo

        admin = User.objects.create_superuser("editar_concurrente", "edicion@example.invalid", "PruebaConcurrente29!")
        plazo = PlazoReporte.objects.create(titulo="Antes de editar", fecha_limite=timezone.now() + timedelta(days=1))
        grupo = Group.objects.get(name="instructor")
        plazo.grupos.add(grupo)
        datos = {
            "descripcion": "",
            "proyecto": "",
            "fecha_limite": plazo.fecha_limite,
            "recordatorio_horas": 24,
            "activo": True,
            "revision_actual": 1,
            "grupos": [grupo],
        }

        def editar(indice):
            try:
                guardar_plazo(
                    User.objects.get(pk=admin.pk), {**datos, "titulo": f"Versión del editor {indice}"}, pk=plazo.pk
                )
                return "guardado"
            except ConflictoPlazo:
                return "conflicto"

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(lambda i: self.ejecutar(lambda: editar(i)), range(2)))
        self.assertCountEqual(resultados, ["guardado", "conflicto"])
        plazo.refresh_from_db()
        self.assertEqual(plazo.revision, 2)
        self.assertEqual(Notificacion.objects.filter(plazo=plazo).count(), 20)
