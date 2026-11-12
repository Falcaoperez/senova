"""Los permisos se actualizan de forma íntegra, sin saltarse la protección de cuentas."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from cuentas.models import RegistroSeguridad

from .permisos import ConflictoPermisos, actualizar_permisos, revision_permisos

PASSWORD = "PermisosRevision42!"


class PermisosSegurosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser("permisos_root", "permisos_root@example.invalid", PASSWORD)
        cls.admin = User.objects.create_user("permisos_admin", password=PASSWORD)
        cls.admin.groups.add(Group.objects.get(name="administrador"))
        cls.user = User.objects.create_user("permisos_persona")
        cls.grupo = Group.objects.create(name="equipo_revision")
        cls.user.groups.add(cls.grupo)
        cls.editar = Permission.objects.get(content_type__app_label="Gesicom", codename="change_envio")
        cls.ver = Permission.objects.get(content_type__app_label="Gesicom", codename="view_envio")
        cls.fuera_catalogo = Permission.objects.get(content_type__app_label="auth", codename="view_user")

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse("admin_personalizado:permisos")

    def payload(self, **extra):
        return {
            "group": self.grupo.pk,
            "revision_actual": revision_permisos(self.grupo),
            "contrasena_actual": PASSWORD,
            "perm_change_envio_1": "allowed",
            **extra,
        }

    def test_password_and_revision_required_and_errors_do_not_partially_save(self):
        for datos in [
            self.payload(contrasena_actual="incorrecta"),
            self.payload(revision_actual=""),
            self.payload(perm_view_envio_1="invalid"),
        ]:
            response = self.client.post(self.url, datos)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(self.grupo.permissions.exists())
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 302)
        self.assertTrue(self.grupo.permissions.filter(pk=self.editar.pk).exists())

    def test_unknown_permission_never_grants_a_privilege_or_saves_other_changes(self):
        response = self.client.post(self.url, self.payload(perm_add_group_1="allowed"))
        self.assertContains(response, "opción de permiso no reconocida")
        self.assertFalse(self.grupo.permissions.exists())

    def test_posted_permission_name_must_match_the_exact_catalog_content_type(self):
        falso = Permission.objects.create(
            content_type=ContentType.objects.get_for_model(Group),
            codename="change_envio",
            name="Permiso homónimo de otro modelo",
        )
        self.grupo.permissions.add(falso)
        self.client.post(self.url, self.payload())
        self.assertSetEqual(set(self.grupo.permissions.values_list("pk", flat=True)), {falso.pk, self.editar.pk})
        self.client.post(self.url, self.payload(perm_change_envio_1="denied"))
        self.assertSetEqual(set(self.grupo.permissions.values_list("pk", flat=True)), {falso.pk})

    def test_partial_update_preserves_other_permissions_and_noop_does_not_add_audit(self):
        self.grupo.permissions.add(self.fuera_catalogo, self.ver)
        self.client.post(self.url, self.payload())
        self.assertSetEqual(
            set(self.grupo.permissions.values_list("pk", flat=True)),
            {self.editar.pk, self.ver.pk, self.fuera_catalogo.pk},
        )
        self.assertEqual(RegistroSeguridad.objects.filter(accion="admin:permisos_grupo").count(), 1)
        self.client.post(self.url, self.payload())
        self.assertEqual(RegistroSeguridad.objects.filter(accion="admin:permisos_grupo").count(), 1)

    def test_stale_tab_is_rejected_and_keeps_the_current_group(self):
        antigua = self.payload(perm_change_envio_1="inherited")
        self.client.post(self.url, self.payload())
        response = self.client.post(self.url, antigua)
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "Recargar permisos actuales", status_code=409)
        self.assertTrue(self.grupo.permissions.filter(pk=self.editar.pk).exists())

    def test_administrator_cannot_modify_group_of_staff_or_administrators(self):
        staff = User.objects.create_user("permisos_staff", is_staff=True)
        self.grupo.user_set.add(staff)
        response = self.client.get(self.url, {"group": self.grupo.pk})
        self.assertContains(response, "Solo un superadministrador")
        self.assertNotContains(response, "Guardar permisos")
        self.client.post(self.url, self.payload())
        self.assertFalse(self.grupo.permissions.exists())
        protegido = Group.objects.get(name="administrador")
        with self.assertRaises(ValidationError):
            actualizar_permisos(
                self.admin, protegido.pk, revision_permisos(protegido), {"change_envio": "allowed"}, PASSWORD
            )

    def test_root_can_modify_a_protected_group(self):
        self.grupo.user_set.add(self.root)
        self.client.force_login(self.root)
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 302)
        self.assertTrue(self.grupo.permissions.filter(pk=self.editar.pk).exists())

    def test_invalid_group_identifiers_render_an_error_instead_of_crashing(self):
        for valor in ["abc", "-1", "999999999999999999999999", "999999"]:
            for metodo in [self.client.get, self.client.post]:
                response = metodo(self.url, {"group": valor})
                self.assertEqual(response.status_code, 400)
        self.assertFalse(self.grupo.permissions.exists())

    def test_service_rechecks_removed_or_inactive_administrator(self):
        revision = revision_permisos(self.grupo)
        self.admin.groups.clear()
        with self.assertRaises(ValidationError):
            actualizar_permisos(self.admin, self.grupo.pk, revision, {"change_envio": "allowed"}, PASSWORD)
        self.assertFalse(self.grupo.permissions.exists())

    def test_csrf_is_enforced(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        self.assertEqual(cliente.post(self.url, self.payload()).status_code, 403)
        self.assertFalse(self.grupo.permissions.exists())

    @override_settings(RATE_LIMITS_ENABLED=True)
    @patch("SENNOVA.middleware.time")
    def test_password_attempts_are_limited(self, reloj):
        reloj.time.return_value = 1_800_000_123
        cache.clear()
        for _ in range(20):
            self.assertEqual(self.client.post(self.url, self.payload(contrasena_actual="incorrecta")).status_code, 200)
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 429)
        self.assertFalse(self.grupo.permissions.exists())

    def test_native_group_edit_uses_password_revision_and_keeps_core_roles(self):
        self.client.force_login(self.root)
        url = reverse("admin:auth_group_change", args=[self.grupo.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="id_contrasena_actual"')
        antigua = revision_permisos(self.grupo)
        datos = {
            "name": self.grupo.name,
            "permissions": [self.ver.pk],
            "revision_actual": antigua,
            "contrasena_actual": PASSWORD,
            "_save": "Guardar",
        }
        sin_password = {**datos, "contrasena_actual": ""}
        self.assertEqual(self.client.post(url, sin_password).status_code, 200)
        self.assertFalse(self.grupo.permissions.exists())
        self.client.post(self.url, self.payload())
        response = self.client.post(url, datos)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["adminform"].form.has_error("__all__", "conflicto"))
        datos["revision_actual"] = revision_permisos(self.grupo)
        self.assertEqual(self.client.post(url, datos).status_code, 302)
        self.assertSetEqual(set(self.grupo.permissions.values_list("pk", flat=True)), {self.ver.pk})
        protegido = Group.objects.get(name="instructor")
        url = reverse("admin:auth_group_change", args=[protegido.pk])
        response = self.client.post(
            url,
            {
                "name": "instructor_renombrado",
                "revision_actual": revision_permisos(protegido),
                "contrasena_actual": PASSWORD,
                "_save": "Guardar",
            },
        )
        self.assertEqual(response.status_code, 302)
        protegido.refresh_from_db()
        self.assertEqual(protegido.name, "instructor")

    def test_native_add_group_records_its_permissions(self):
        self.client.force_login(self.root)
        response = self.client.post(
            reverse("admin:auth_group_add"),
            {"name": "equipo_nativo", "permissions": [self.ver.pk], "contrasena_actual": PASSWORD, "_save": "Guardar"},
        )
        self.assertEqual(response.status_code, 302)
        grupo = Group.objects.get(name="equipo_nativo")
        self.assertSetEqual(set(grupo.permissions.values_list("pk", flat=True)), {self.ver.pk})

    def test_native_staff_cannot_escalate_through_a_group_containing_staff(self):
        staff = User.objects.create_user("grupo_editor_nativo", password=PASSWORD, is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename="change_group", content_type__app_label="auth"))
        staff.groups.add(self.grupo)
        self.client.force_login(staff)
        url = reverse("admin:auth_group_change", args=[self.grupo.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="contrasena_actual"')
        self.assertEqual(
            self.client.post(
                url,
                {
                    "permissions": [self.fuera_catalogo.pk],
                    "revision_actual": revision_permisos(self.grupo),
                    "contrasena_actual": PASSWORD,
                },
            ).status_code,
            403,
        )
        self.assertFalse(self.grupo.permissions.exists())

    def test_native_delete_cannot_remove_core_role_or_partially_delete_a_mixed_batch(self):
        self.client.force_login(self.root)
        rol = Group.objects.get(name="instructor")
        response = self.client.post(reverse("admin:auth_group_delete", args=[rol.pk]), {"post": "yes"})
        self.assertIn(response.status_code, [200, 403])
        self.assertTrue(Group.objects.filter(pk=rol.pk).exists())
        self.client.post(
            reverse("admin:auth_group_changelist"),
            {"action": "delete_selected", "_selected_action": [rol.pk, self.grupo.pk], "post": "yes"},
        )
        self.assertTrue(Group.objects.filter(pk=rol.pk).exists())
        self.assertTrue(Group.objects.filter(pk=self.grupo.pk).exists())


class PermisosConcurrentesTests(TransactionTestCase):
    def test_only_one_of_two_editors_can_save_the_same_revision(self):
        if connection.vendor != "mysql":
            self.skipTest("Requiere los bloqueos de MySQL.")
        root = User.objects.create_superuser("permisos_concurrente", "concurrente@example.invalid", PASSWORD)
        grupo = Group.objects.create(name="equipo_concurrente")
        revision = revision_permisos(grupo)

        def editar(indice):
            close_old_connections()
            try:
                codigo = "change_envio" if indice else "view_envio"
                try:
                    actualizar_permisos(User.objects.get(pk=root.pk), grupo.pk, revision, {codigo: "allowed"}, PASSWORD)
                    return "guardado"
                except ConflictoPermisos:
                    return "conflicto"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultado = list(executor.map(editar, range(2)))
        self.assertCountEqual(resultado, ["guardado", "conflicto"])
        self.assertEqual(grupo.permissions.count(), 1)
