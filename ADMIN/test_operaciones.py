"""Seguridad de operaciones administrativas y consultas del panel."""

from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from cuentas.models import CorreoSeguridad, PasswordResetToken, RegistroSeguridad, SesionUsuario
from Gesicom.models import Envio
from notificaciones.models import PlazoReporte

from .selectors import centro_operaciones
from .services import cambiar_estados, cambiar_roles


class OperacionesAdminTests(TestCase):
    def setUp(self):
        self.password = "ClaveLocalDePruebas42!"
        self.admin = User.objects.create_user("operador", password=self.password)
        self.admin.groups.add(Group.objects.get(name="administrador"))
        self.member = User.objects.create_user("equipo", email="equipo@example.com", password=self.password)
        self.root = User.objects.create_superuser("protegido", email="root@example.com", password=self.password)
        self.client.force_login(self.admin)
        self.directory = reverse("admin_personalizado:gestionar_usuarios")
        self.detail = reverse("admin_personalizado:detalle_usuario", args=[self.member.pk])

    def test_bulk_mutations_require_current_password(self):
        for password in ["", "incorrecta"]:
            self.client.post(
                self.directory, {"accion": "desactivar", "usuarios": [self.member.pk], "contrasena_actual": password}
            )
            self.member.refresh_from_db()
            self.assertTrue(self.member.is_active)
        self.client.post(
            self.directory, {"accion": "desactivar", "usuarios": [self.member.pk], "contrasena_actual": self.password}
        )
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)
        self.assertTrue(RegistroSeguridad.objects.filter(actor=self.admin, accion="admin:desactivar").exists())

    def test_bulk_is_atomic_for_protected_or_self_accounts(self):
        for ids in [[self.member.pk, self.root.pk], [self.member.pk, self.admin.pk], [self.member.pk, 999999]]:
            with self.subTest(ids=ids), self.assertRaises(ValidationError):
                cambiar_estados(self.admin, ids, activo=False)
            self.member.refresh_from_db()
            self.assertTrue(self.member.is_active)

    def test_superuser_can_manage_protected_accounts_but_not_disable_self(self):
        self.assertEqual(cambiar_estados(self.root, [self.admin.pk], activo=False), 1)
        with self.assertRaises(ValidationError):
            cambiar_estados(self.root, [self.root.pk], activo=False)
        with self.assertRaises(ValidationError):
            cambiar_roles(self.admin, {self.member.pk: []})

    def test_deactivation_revokes_sessions_and_pending_pins(self):
        from django.test import Client

        client = Client()
        client.force_login(self.member)
        token = PasswordResetToken.crear_para_usuario(self.member)
        self.assertTrue(SesionUsuario.objects.filter(usuario=self.member).exists())
        cambiar_estados(self.admin, [self.member.pk], activo=False)
        self.assertFalse(SesionUsuario.objects.filter(usuario=self.member).exists())
        token.refresh_from_db()
        self.assertTrue(token.utilizado)
        cambiar_estados(self.admin, [self.member.pk], activo=True)
        self.assertRedirects(
            client.get(reverse("centro_seguridad")), "/login/?next=/mi-cuenta/seguridad/", fetch_redirect_response=False
        )

    def test_role_changes_are_atomic_and_preserve_admin_access(self):
        self.member.groups.add(Group.objects.get(name="instructor"))
        with self.assertRaises(ValidationError):
            cambiar_roles(self.admin, {self.member.pk: [], self.admin.pk: []})
        self.assertTrue(self.member.groups.filter(name="instructor").exists())
        with self.assertRaises(ValidationError):
            cambiar_roles(self.admin, {self.member.pk: [999999]})
        self.assertTrue(self.member.groups.filter(name="instructor").exists())

    def test_legacy_mutation_paths_cannot_bypass_protections(self):
        self.client.post(
            reverse("admin_personalizado:activar_desactivar", args=[self.admin.pk]),
            {"accion": "desactivar", "contrasena_actual": self.password},
        )
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        for action in ["update_status", "update_groups", "change_password", "update_profile"]:
            response = self.client.post(
                reverse("admin_personalizado:detalle_usuario", args=[self.root.pk]),
                {
                    "action": action,
                    "contrasena_actual": self.password,
                    "email": "otro@example.com",
                    "nueva_password": "OtraClaveSegura42!",
                    "confirmar_password": "OtraClaveSegura42!",
                },
            )
            self.assertEqual(response.status_code, 302)
        self.root.refresh_from_db()
        self.assertTrue(self.root.is_active)
        self.assertEqual(self.root.email, "root@example.com")
        self.assertTrue(self.root.check_password(self.password))

    def test_detail_profile_and_password_require_proof_and_notify(self):
        self.client.post(self.detail, {"action": "update_profile", "email": "otra@example.com"})
        self.member.refresh_from_db()
        self.assertEqual(self.member.email, "equipo@example.com")
        self.client.post(
            self.detail, {"action": "update_profile", "email": "otra@example.com", "contrasena_actual": self.password}
        )
        self.assertEqual(
            set(CorreoSeguridad.objects.filter(usuario=self.member).values_list("destinatario", flat=True)),
            {"equipo@example.com", "otra@example.com"},
        )
        token = PasswordResetToken.crear_para_usuario(self.member)
        self.client.post(
            self.detail,
            {
                "action": "change_password",
                "nueva_password": "NuevaClaveSegura42!",
                "confirmar_password": "NuevaClaveSegura42!",
                "contrasena_actual": self.password,
            },
        )
        self.member.refresh_from_db()
        token.refresh_from_db()
        self.assertTrue(self.member.check_password("NuevaClaveSegura42!"))
        self.assertTrue(token.utilizado)

    def test_self_password_change_keeps_current_session(self):
        self.client.post(
            reverse("admin_personalizado:detalle_usuario", args=[self.admin.pk]),
            {
                "action": "change_password",
                "nueva_password": "NuevaClaveSegura42!",
                "confirmar_password": "NuevaClaveSegura42!",
                "contrasena_actual": self.password,
            },
        )
        self.assertEqual(self.client.get(reverse("admin_personalizado:dashboard")).status_code, 200)

    def test_empty_oversized_or_invalid_bulk_requests_make_no_changes(self):
        for ids in [[], list(range(1, 102)), ["bad"], [-1]]:
            with self.subTest(ids=ids), self.assertRaises(ValidationError):
                cambiar_estados(self.admin, ids, activo=False)
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)

    def test_dashboard_period_and_metrics_use_real_dates(self):
        hoy = timezone.localdate()
        Envio.objects.create(usuario=self.member, tipo_evidencia="Doc", fecha_envio=hoy, aprobada=True)
        Envio.objects.create(usuario=self.member, tipo_evidencia="Doc", fecha_envio=hoy - timedelta(days=8))
        Envio.objects.create(usuario=self.member, tipo_evidencia="Doc", fecha_envio=hoy + timedelta(days=1))
        PlazoReporte.objects.create(titulo="Vigente", fecha_limite=timezone.now() + timedelta(days=1))
        PlazoReporte.objects.create(titulo="Vencido", fecha_limite=timezone.now() - timedelta(days=1))
        context = centro_operaciones("7")
        self.assertEqual(context["resumen"]["recibidas"], 1)
        self.assertEqual(context["resumen"]["anteriores"], 1)
        self.assertEqual(context["resumen"]["aprobadas"], 1)
        self.assertEqual(sum(context["actividad_grafico"]["valores"]), 1)
        self.assertEqual(context["proximos_plazos"], 1)
        self.assertEqual(centro_operaciones("999999")["periodo"], "30")

    def test_dashboard_and_directory_queries_are_bounded(self):
        User.objects.bulk_create([User(username=f"equipo_{i}", first_name="Equipo") for i in range(130)])
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("admin_personalizado:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 30)
        response = self.client.get(self.directory, {"q": "equipo_", "estado": "activo"})
        self.assertEqual(response.context["usuarios"].paginator.count, 130)
        self.assertEqual(len(response.context["usuarios"]), 25)

    def test_dashboard_supports_system_events_and_legacy_evidence_without_owner(self):
        RegistroSeguridad.objects.create(actor=None, accion="mantenimiento:credenciales")
        Envio.objects.create(usuario=None, nombre="Histórica", tipo_evidencia="Doc")
        response = self.client.get(reverse("admin_personalizado:dashboard"))
        self.assertContains(response, "Sistema")
        self.assertContains(response, "Sin usuario")

    def test_historical_user_list_keeps_the_same_filters(self):
        self.member.is_active = False
        self.member.save(update_fields=["is_active"])
        response = self.client.get(reverse("admin_personalizado:usuarios"), {"q": "equipo", "estado": "inactivo"})
        self.assertEqual(list(response.context["usuarios"]), [self.member])
