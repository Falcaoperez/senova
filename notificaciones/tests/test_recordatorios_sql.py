"""Elegibilidad temporal y alcance actual de destinatarios resueltos en MySQL."""

from datetime import timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Group, User
from django.core import mail
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from Gesicom.models import Envio

from ..models import CorreoPendiente, Notificacion, Novedad, PlazoReporte, PreferenciasNotificacion
from ..selectors import destinatarios
from ..services import sincronizar_plazos


class DestinatariosSQLTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Group.objects.get(name="instructor")
        cls.b = Group.objects.get(name="investigador")
        cls.usuarios = [User.objects.create_user(f"alcance_sql_{i}", is_active=i != 3) for i in range(5)]
        for i, grupos in enumerate([[cls.a], [cls.b], [cls.a, cls.b], [cls.a], []]):
            cls.usuarios[i].groups.set(grupos)
        cls.plazo = PlazoReporte.objects.create(titulo="Audiencia actual", fecha_limite=timezone.now())
        cls.plazo.grupos.add(cls.a, cls.b)

    def test_construir_el_alcance_no_ejecuta_una_consulta_de_grupos(self):
        with self.assertNumQueries(0):
            consulta = destinatarios(self.plazo.grupos)
        with self.assertNumQueries(1):
            nombres = set(consulta.values_list("username", flat=True))
        self.assertSetEqual(nombres, {u.username for u in self.usuarios[:3]})

    def test_sin_grupos_incluye_activos_y_no_duplica_pertenencias(self):
        self.plazo.grupos.clear()
        with self.assertNumQueries(1):
            nombres = list(destinatarios(self.plazo.grupos).values_list("username", flat=True))
        self.assertSetEqual(set(nombres), {u.username for i, u in enumerate(self.usuarios) if i != 3})
        self.assertEqual(len(nombres), 4)

    def test_prefetch_no_conserva_un_grupo_retirado_por_otra_instancia(self):
        self.plazo.grupos.set([self.a])
        anterior = PlazoReporte.objects.prefetch_related("grupos").get(pk=self.plazo.pk)
        PlazoReporte.objects.get(pk=self.plazo.pk).grupos.set([self.b])
        with self.assertNumQueries(1):
            nombres = set(destinatarios(anterior.grupos).values_list("username", flat=True))
        self.assertSetEqual(nombres, {self.usuarios[1].username, self.usuarios[2].username})

    def test_prefetch_vacio_no_amplia_una_asignacion_nueva(self):
        self.plazo.grupos.clear()
        anterior = PlazoReporte.objects.prefetch_related("grupos").get(pk=self.plazo.pk)
        PlazoReporte.objects.get(pk=self.plazo.pk).grupos.set([self.a])
        with self.assertNumQueries(1):
            nombres = set(destinatarios(anterior.grupos).values_list("username", flat=True))
        self.assertSetEqual(nombres, {self.usuarios[0].username, self.usuarios[2].username})

    def test_novedades_reutilizan_el_alcance_actual_de_grupos(self):
        novedad = Novedad.objects.create(titulo="Audiencia de novedad", contenido="Prueba")
        novedad.grupos.add(self.a, self.b)
        with self.assertNumQueries(1):
            nombres = list(destinatarios(novedad.grupos).values_list("username", flat=True))
        self.assertEqual(len(nombres), 3)
        self.assertSetEqual(set(nombres), {u.username for u in self.usuarios[:3]})


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RecordatoriosSQLTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.grupo = Group.objects.get(name="instructor")
        cls.usuarios = [
            User.objects.create_user(f"aviso_sql_{i}", email=f"aviso_sql_{i}@example.invalid") for i in range(3)
        ]
        for usuario in cls.usuarios:
            usuario.groups.add(cls.grupo)
            PreferenciasNotificacion.objects.create(usuario=usuario, correo_plazos=False)
        cls.ajeno = User.objects.create_user("aviso_sql_ajeno")
        cls.inactivo = User.objects.create_user("aviso_sql_inactivo", is_active=False)
        cls.inactivo.groups.add(cls.grupo)

    def setUp(self):
        self.ahora = timezone.now().replace(microsecond=500000)

    def plazo(self, horas=2, margen=24, activo=True):
        plazo = PlazoReporte.objects.create(
            titulo="Ventana del recordatorio",
            descripcion="X" * 3000,
            fecha_limite=self.ahora + timedelta(hours=horas),
            recordatorio_horas=margen,
            activo=activo,
        )
        plazo.grupos.add(self.grupo)
        return plazo

    def test_mil_doscientos_plazos_futuros_se_descartan_en_una_consulta(self):
        PlazoReporte.objects.bulk_create(
            [
                PlazoReporte(
                    titulo=f"Futuro SQL {i}",
                    descripcion="X" * 3000,
                    fecha_limite=self.ahora + timedelta(days=40),
                    recordatorio_horas=1 + i % 720,
                )
                for i in range(1200)
            ]
        )
        with CaptureQueriesContext(connection) as consultas:
            self.assertEqual(sincronizar_plazos(self.ahora), 0)
        print(f"ESCALA trabajador / 1200 plazos fuera de ventana: {len(consultas)} consultas.")
        self.assertEqual(len(consultas), 1)
        self.assertNotIn(connection.ops.quote_name("descripcion"), consultas[0]["sql"])
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_una_vez_por_tipo_en_limites_exactos_con_microsegundos(self):
        plazo = self.plazo(horas=2, margen=2)
        self.assertEqual(sincronizar_plazos(self.ahora - timedelta(microseconds=1)), 0)
        self.assertEqual(sincronizar_plazos(self.ahora), 3)
        self.assertEqual(sincronizar_plazos(self.ahora), 0)
        self.assertEqual(sincronizar_plazos(plazo.fecha_limite - timedelta(microseconds=1)), 0)
        self.assertEqual(sincronizar_plazos(plazo.fecha_limite), 3)
        self.assertEqual(sincronizar_plazos(plazo.fecha_limite + timedelta(days=1)), 0)
        self.assertEqual(Notificacion.objects.filter(tipo="recordatorio").count(), 3)
        self.assertEqual(Notificacion.objects.filter(tipo="vencimiento").count(), 3)
        self.assertFalse(CorreoPendiente.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_avisados_y_entregados_se_excluyen_antes_de_materializar_ids(self):
        plazo = self.plazo()
        Notificacion.objects.create(
            usuario=self.usuarios[0],
            plazo=plazo,
            tipo="recordatorio",
            version_plazo=plazo.version,
            titulo="Ya avisado",
            mensaje="Prueba",
        )
        Envio.objects.create(usuario=self.usuarios[1], plazo=plazo, nombre="Entrega existente")
        with patch("notificaciones.services._crear_avisos", return_value=0) as crear:
            sincronizar_plazos(self.ahora)
        candidatos = crear.call_args.args[0]
        self.assertEqual(list(candidatos.values_list("pk", flat=True)), [self.usuarios[2].pk])

    def test_solo_considera_plazos_activos_y_lecturas_minimas(self):
        self.plazo(activo=False)
        self.plazo(horas=200, margen=1)
        vigente = self.plazo()
        with CaptureQueriesContext(connection) as consultas:
            self.assertEqual(sincronizar_plazos(self.ahora), 3)
        self.assertSetEqual(set(Notificacion.objects.values_list("plazo_id", flat=True)), {vigente.pk})
        lectura = consultas[0]["sql"]
        for campo in ["descripcion", "creado_por_id", "actualizado_en"]:
            self.assertNotIn(connection.ops.quote_name(campo), lectura)

    def test_version_y_tipo_anteriores_no_suprimen_el_aviso_actual(self):
        plazo = self.plazo()
        Notificacion.objects.create(
            usuario=self.usuarios[0],
            plazo=plazo,
            tipo="apertura",
            version_plazo=plazo.version,
            titulo="Apertura",
            mensaje="Prueba",
        )
        Notificacion.objects.create(
            usuario=self.usuarios[1],
            plazo=plazo,
            tipo="recordatorio",
            version_plazo=plazo.version + 1,
            titulo="Otra versión",
            mensaje="Prueba",
        )
        self.assertEqual(sincronizar_plazos(self.ahora), 3)
        self.assertEqual(sincronizar_plazos(self.ahora), 0)
        self.assertEqual(
            Notificacion.objects.filter(plazo=plazo, tipo="recordatorio", version_plazo=plazo.version).count(), 3
        )

    def test_instante_equivalente_con_otro_huso_no_cambia_elegibilidad(self):
        self.plazo(horas=1, margen=1)
        with timezone.override("Asia/Tokyo"):
            self.assertEqual(sincronizar_plazos(self.ahora.astimezone(ZoneInfo("Asia/Tokyo"))), 3)
        self.assertEqual(sincronizar_plazos(self.ahora), 0)

    def test_margen_maximo_y_cero_horas_historico(self):
        anticipado = self.plazo(horas=720, margen=720)
        historico = self.plazo(horas=65535, margen=65535)
        sin_anticipo = self.plazo(horas=1, margen=0)
        self.assertEqual(sincronizar_plazos(self.ahora), 6)
        self.assertSetEqual(set(Notificacion.objects.values_list("plazo_id", flat=True)), {anticipado.pk, historico.pk})
        self.assertEqual(sincronizar_plazos(sin_anticipo.fecha_limite), 3)
        self.assertEqual(Notificacion.objects.filter(plazo=sin_anticipo, tipo="vencimiento").count(), 3)
