from concurrent.futures import ThreadPoolExecutor

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.mail import get_connection
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings

from .models import CorreoPendiente, Notificacion, Novedad
from .services import procesar_correos, publicar_novedad

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
