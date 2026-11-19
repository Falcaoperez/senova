"""Una eliminación de grupo no debe convertir comunicaciones privadas en públicas."""

import datetime
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import skipUnless

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext

from ..grupos import grupos_con_comunicaciones
from ..models import CorreoPendiente, Notificacion, Novedad, PlazoReporte, SolicitudNovedad
from ..plazos import guardar_plazo
from ..publicacion import publicar_o_recuperar
from ..selectors import destinatarios, plazos_para_usuario


class AudienciasGrupoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.libre = Group.objects.create(name="Equipo sin comunicaciones")
        cls.grupo = Group.objects.create(name="Equipo privado de comunicaciones")
        cls.ajeno = User.objects.create_user("audiencia_ajena")
        cls.novedad = Novedad.objects.create(titulo="Contenido privado de revisión", contenido="Solo para el equipo.")
        cls.novedad.grupos.add(cls.grupo)

    def test_eliminar_el_grupo_no_convierte_la_novedad_en_publica(self):
        self.assertFalse(destinatarios(self.novedad.grupos).filter(pk=self.ajeno.pk).exists())
        try:
            with transaction.atomic():
                self.grupo.delete()
        except ProtectedError:
            pass
        self.assertFalse(
            destinatarios(self.novedad.grupos).filter(pk=self.ajeno.pk).exists(),
            "Eliminar un grupo no debe publicar su contenido para toda la comunidad.",
        )
        self.assertTrue(Group.objects.filter(pk=self.grupo.pk).exists())

    def test_instancia_y_queryset_conservan_grupo_y_relaciones_con_error_protegido(self):
        for borrar in (self.grupo.delete, Group.objects.filter(pk=self.grupo.pk).delete):
            with self.assertRaises(ProtectedError), transaction.atomic():
                borrar()
            self.assertTrue(self.novedad.grupos.filter(pk=self.grupo.pk).exists())
            self.assertFalse(Notificacion.objects.exists())
            self.assertFalse(CorreoPendiente.objects.exists())

    def test_plazos_activos_y_archivados_conservan_su_grupo(self):
        for activo in (True, False):
            with self.subTest(activo=activo):
                grupo = Group.objects.create(name=f"Equipo con plazo {activo}")
                plazo = PlazoReporte.objects.create(
                    titulo="Plazo restringido",
                    fecha_limite=datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC),
                    activo=activo,
                )
                plazo.grupos.add(grupo)
                with self.assertRaises(ProtectedError), transaction.atomic():
                    grupo.delete()
                self.assertTrue(plazo.grupos.filter(pk=grupo.pk).exists())
                PlazoReporte.objects.filter(pk=plazo.pk).update(activo=True)
                self.assertFalse(plazos_para_usuario(self.ajeno, pendientes=False).filter(pk=plazo.pk).exists())

    def test_tener_otro_grupo_no_autoriza_un_cambio_implicito_de_destinatarios(self):
        self.novedad.grupos.add(self.libre)
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.grupo.delete()
        self.assertEqual(self.novedad.grupos.count(), 2)

    def test_lote_mixto_no_elimina_siquiera_el_grupo_libre(self):
        with self.assertRaises(ProtectedError), transaction.atomic():
            Group.objects.filter(pk__in=[self.libre.pk, self.grupo.pk]).delete()
        self.assertEqual(Group.objects.filter(pk__in=[self.libre.pk, self.grupo.pk]).count(), 2)
        self.assertEqual(self.novedad.grupos.count(), 1)

    def test_reasignar_antes_permite_eliminar_sin_convertir_la_audiencia_en_publica(self):
        self.novedad.grupos.set([self.libre])
        pk = self.grupo.pk
        self.grupo.delete()
        self.assertFalse(Group.objects.filter(pk=pk).exists())
        self.assertEqual(list(self.novedad.grupos.values_list("pk", flat=True)), [self.libre.pk])
        self.assertFalse(destinatarios(self.novedad.grupos).filter(pk=self.ajeno.pk).exists())

    def test_retirar_ambos_tipos_de_comunicacion_libera_el_grupo(self):
        plazo = PlazoReporte.objects.create(
            titulo="Pendiente", fecha_limite=datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)
        )
        plazo.grupos.add(self.grupo)
        self.novedad.delete()
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.grupo.delete()
        plazo.delete()
        pk = self.grupo.pk
        self.grupo.delete()
        self.assertFalse(Group.objects.filter(pk=pk).exists())

    def test_eliminar_una_cuenta_conserva_el_grupo_y_la_audiencia(self):
        titular = User.objects.create_user("titular_del_equipo")
        titular.groups.add(self.grupo)
        Novedad.objects.filter(pk=self.novedad.pk).update(creada_por=titular)
        titular.delete()
        self.novedad.refresh_from_db()
        self.assertIsNone(self.novedad.creada_por_id)
        self.assertTrue(Group.objects.filter(pk=self.grupo.pk).exists())
        self.assertFalse(destinatarios(self.novedad.grupos).filter(pk=self.ajeno.pk).exists())

    @skipUnless(connection.vendor == "mysql", "Comprueba la restricción inmediata de MySQL.")
    def test_el_fk_tambien_rechaza_borrar_el_padre_mediante_sql_directo(self):
        tabla = connection.ops.quote_name(Group._meta.db_table)
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM {tabla} WHERE id = %s", [self.grupo.pk])
        self.assertTrue(Group.objects.filter(pk=self.grupo.pk).exists())
        self.assertEqual(self.novedad.grupos.count(), 1)


class GruposDesactualizadosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = User.objects.create_user("autor_grupo_desactualizado", is_superuser=True)
        cls.ajeno = User.objects.create_user("receptor_fuera_del_grupo")

    def grupo_retirado(self):
        grupo = Group.objects.create(name="Equipo retirado después de validar")
        Group.objects.filter(pk=grupo.pk).delete()
        return grupo

    def test_novedad_no_se_publica_si_el_grupo_desaparecio_tras_validar(self):
        grupo = self.grupo_retirado()
        with self.assertRaises(ValidationError), transaction.atomic():
            publicar_o_recuperar(
                self.actor,
                {
                    "titulo": "Novedad privada",
                    "contenido": "Contenido confidencial del equipo.",
                    "grupos": [grupo],
                    "solicitud": uuid.uuid4(),
                },
            )
        self.assertFalse(Novedad.objects.exists(), "Un grupo desaparecido no debe producir una publicación general.")
        self.assertFalse(SolicitudNovedad.objects.exists())
        self.assertFalse(Notificacion.objects.exists())
        self.assertFalse(CorreoPendiente.objects.exists())

    def test_plazo_no_se_publica_si_el_grupo_desaparecio_tras_validar(self):
        grupo = self.grupo_retirado()
        with self.assertRaises(ValidationError), transaction.atomic():
            guardar_plazo(
                self.actor,
                {
                    "titulo": "Plazo privado",
                    "descripcion": "Instrucciones del equipo.",
                    "proyecto": "LEM",
                    "fecha_limite": datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC),
                    "recordatorio_horas": 24,
                    "activo": True,
                    "grupos": [grupo],
                },
            )
        self.assertFalse(PlazoReporte.objects.exists(), "Un grupo desaparecido no debe producir un plazo general.")
        self.assertFalse(Notificacion.objects.exists())
        self.assertFalse(CorreoPendiente.objects.exists())

    def test_una_seleccion_parcialmente_retirada_tampoco_se_publica(self):
        retirado = self.grupo_retirado()
        valido = Group.objects.create(name="Equipo que permanece")
        with self.assertRaises(ValidationError), transaction.atomic():
            publicar_o_recuperar(
                self.actor,
                {
                    "titulo": "Selección incompleta",
                    "contenido": "Solo para los equipos elegidos.",
                    "grupos": [valido, retirado],
                },
            )
        self.assertFalse(Novedad.objects.exists())
        self.assertFalse(Notificacion.objects.exists())

    def test_elegir_explicitamente_toda_la_comunidad_sigue_funcionando(self):
        resultado = publicar_o_recuperar(self.actor, {"titulo": "Público", "contenido": "Para todos.", "grupos": []})
        self.assertFalse(resultado.novedad.grupos.exists())
        self.assertTrue(destinatarios(resultado.novedad.grupos).filter(pk=self.ajeno.pk).exists())


class ConsultaGruposTests(TestCase):
    def test_1200_grupos_se_comprueban_con_una_consulta_sin_leer_contenidos(self):
        Group.objects.bulk_create([Group(name=f"Consulta de audiencia {i:04}") for i in range(1200)], batch_size=500)
        ids = list(
            Group.objects.filter(name__startswith="Consulta de audiencia ").order_by("pk").values_list("pk", flat=True)
        )
        novedad = Novedad.objects.create(titulo="No cargar este título", contenido="No cargar este contenido")
        plazo = PlazoReporte.objects.create(
            titulo="No cargar este plazo", fecha_limite=datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)
        )
        Novedad.grupos.through.objects.bulk_create(
            [Novedad.grupos.through(novedad_id=novedad.pk, group_id=pk) for i, pk in enumerate(ids) if i % 2 == 0],
            batch_size=500,
        )
        PlazoReporte.grupos.through.objects.bulk_create(
            [
                PlazoReporte.grupos.through(plazoreporte_id=plazo.pk, group_id=pk)
                for i, pk in enumerate(ids)
                if i % 3 == 0
            ],
            batch_size=500,
        )
        with CaptureQueriesContext(connection) as consultas:
            usados = set(grupos_con_comunicaciones(Group.objects.filter(pk__in=ids)).values_list("pk", flat=True))
        self.assertEqual(usados, {pk for i, pk in enumerate(ids) if i % 2 == 0 or i % 3 == 0})
        self.assertEqual(len(usados), 800)
        self.assertEqual(len(consultas), 1)
        self.assertIn("EXISTS", consultas[0]["sql"])
        for campo in ("titulo", "contenido", "descripcion", "password", "email"):
            self.assertNotIn(connection.ops.quote_name(campo), consultas[0]["sql"])
        print(
            "ESCALA protección de audiencias / 1200 grupos: 1 consulta con EXISTS; 800 grupos asignados, sin leer contenidos."
        )


class GruposConcurrentesTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "mysql":
            self.skipTest("Requiere bloqueos y claves foráneas de MySQL.")
        self.grupo = Group.objects.create(name="Equipo de borrado concurrente")

    @staticmethod
    def en_hilo(operacion):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION innodb_lock_wait_timeout = 10")
            return operacion()
        finally:
            connection.close()

    def test_una_asignacion_pendiente_se_comprueba_despues_del_bloqueo_del_grupo(self):
        novedad = Novedad.objects.create(titulo="Equipo concreto", contenido="Privado")
        asignado, comprobar, confirmar = Event(), Event(), Event()

        def asignar():
            with transaction.atomic():
                Novedad.grupos.through.objects.create(novedad_id=novedad.pk, group_id=self.grupo.pk)
                asignado.set()
                if not confirmar.wait(15):
                    raise AssertionError("Falta confirmar la asignación.")
            return "asignado"

        def detectar_bloqueo(execute, sql, params, many, context):
            if "FOR UPDATE" in sql and connection.ops.quote_name(Group._meta.db_table) in sql:
                comprobar.set()
            return execute(sql, params, many, context)

        def borrar():
            try:
                with connection.execute_wrapper(detectar_bloqueo):
                    Group.objects.get(pk=self.grupo.pk).delete()
            except ProtectedError:
                return "protegido"
            return "eliminado"

        with ThreadPoolExecutor(max_workers=2) as pool:
            alta = pool.submit(self.en_hilo, asignar)
            try:
                self.assertTrue(asignado.wait(10))
                baja = pool.submit(self.en_hilo, borrar)
                self.assertTrue(comprobar.wait(10))
            finally:
                confirmar.set()
            self.assertEqual(alta.result(timeout=20), "asignado")
            self.assertEqual(baja.result(timeout=20), "protegido")
        self.assertTrue(Group.objects.filter(pk=self.grupo.pk).exists())
        self.assertEqual(novedad.grupos.count(), 1)

    def test_si_el_borrado_gana_la_publicacion_concurrente_se_revierte_completa(self):
        actor = User.objects.create_user("autor_concurrente_grupo", is_superuser=True)
        bloqueado, intentando_asignar, continuar = Event(), Event(), Event()

        def esperar_antes_de_comprobar(execute, sql, params, many, context):
            if "EXISTS" in sql and connection.ops.quote_name(Group._meta.db_table) in sql:
                bloqueado.set()
                if not continuar.wait(15):
                    raise AssertionError("Falta continuar el borrado.")
            return execute(sql, params, many, context)

        def borrar():
            with connection.execute_wrapper(esperar_antes_de_comprobar):
                Group.objects.get(pk=self.grupo.pk).delete()
            return "eliminado"

        def detectar_intento(execute, sql, params, many, context):
            if "FOR UPDATE" in sql and connection.ops.quote_name(Group._meta.db_table) in sql:
                intentando_asignar.set()
            return execute(sql, params, many, context)

        def publicar():
            try:
                with connection.execute_wrapper(detectar_intento):
                    publicar_o_recuperar(
                        User.objects.get(pk=actor.pk),
                        {
                            "titulo": "Publicación concurrente",
                            "contenido": "Solo para el equipo.",
                            "grupos": [self.grupo],
                            "solicitud": uuid.uuid4(),
                        },
                    )
            except ValidationError:
                return "rechazado"
            return "publicado"

        with ThreadPoolExecutor(max_workers=2) as pool:
            baja = pool.submit(self.en_hilo, borrar)
            try:
                self.assertTrue(bloqueado.wait(10))
                alta = pool.submit(self.en_hilo, publicar)
                self.assertTrue(intentando_asignar.wait(10))
            finally:
                continuar.set()
            self.assertEqual(baja.result(timeout=20), "eliminado")
            self.assertEqual(alta.result(timeout=20), "rechazado")
        self.assertFalse(Group.objects.filter(pk=self.grupo.pk).exists())
        for modelo in (Novedad, SolicitudNovedad, Notificacion, CorreoPendiente):
            self.assertFalse(modelo.objects.exists())
