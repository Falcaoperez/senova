from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth.models import Group, User
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from notificaciones.models import Notificacion

from ..models import Envio
from ..services import ConflictoEvidencia, corregir_evidencia, revisar_evidencia


class RevisionesConcurrentesTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "mysql":
            self.skipTest("Los bloqueos se comprueban con MySQL.")
        self.user = User.objects.create_user("autor_concurrente", email="autor@example.invalid")
        self.reviewer = User.objects.create_user("revisor_concurrente")
        self.reviewer.groups.add(Group.objects.get(name="coordinador"))
        self.envio = Envio.objects.create(
            usuario=self.user,
            nombre="Informe",
            proyecto="LEM",
            tipo_evidencia="Documento",
            link_evidencia="https://example.com",
        )

    def ejecutar(self, acciones):
        barrier = Barrier(2)

        def call(accion):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    accion()
                    return "guardado"
                except ConflictoEvidencia:
                    return "conflicto"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(call, acciones))
        self.assertCountEqual(results, ["guardado", "conflicto"])
        self.envio.refresh_from_db()
        self.assertEqual(self.envio.version, 2)
        self.assertEqual(self.envio.historial.count(), 1)

    def test_two_reviewers_cannot_overwrite_the_same_version(self):
        self.ejecutar(
            [
                lambda: revisar_evidencia(self.reviewer, self.envio.pk, True, version=1),
                lambda: revisar_evidencia(self.reviewer, self.envio.pk, False, version=1),
            ]
        )
        self.assertEqual(Notificacion.objects.filter(usuario=self.user, envio=self.envio).count(), 1)

    def test_correction_and_approval_are_serialized(self):
        datos = {
            "version": 1,
            "nombre": "Informe corregido",
            "proyecto": "LEM",
            "evidencias": ["Documento"],
            "linkArchivo": "https://example.com/nuevo",
            "motivo": "Enlace corregido",
        }
        self.ejecutar(
            [
                lambda: revisar_evidencia(self.reviewer, self.envio.pk, True, version=1),
                lambda: corregir_evidencia(self.user, self.envio.pk, datos),
            ]
        )
        if self.envio.aprobada:
            self.assertEqual(self.envio.nombre, "Informe")
        else:
            self.assertEqual(self.envio.nombre, "Informe corregido")
