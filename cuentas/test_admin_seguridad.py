from types import SimpleNamespace

from django.contrib import admin
from django.contrib.auth.models import Group, Permission, User
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CorreoSeguridad, PasswordResetToken, SesionUsuario


class SeguridadAdminNativoTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser(
            "administradorsistema", email="root@example.invalid", password="ClaveLocalAdmin42!"
        )
        self.staff = User.objects.create_user("operadorstaff", is_staff=True)
        self.staff.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="auth", codename__in=["view_user", "change_user", "add_user", "delete_user"]
            )
        )
        self.user = User.objects.create_user(
            "personaequipo", email="antes@example.invalid", password="ClaveOriginal42!"
        )
        self.client.force_login(self.root)

    def payload(self, usuario, **changes):
        fecha = timezone.localtime(usuario.date_joined)
        data = {
            "username": usuario.username,
            "email": usuario.email,
            "first_name": usuario.first_name,
            "last_name": usuario.last_name,
            "is_active": "on",
            "date_joined_0": fecha.strftime("%Y-%m-%d"),
            "date_joined_1": fecha.strftime("%H:%M:%S"),
            "groups": list(usuario.groups.values_list("pk", flat=True)),
            "_save": "Guardar",
        }
        if usuario.is_staff:
            data["is_staff"] = "on"
        if usuario.is_superuser:
            data["is_superuser"] = "on"
        data.update(changes)
        return data

    def test_staff_cannot_escalate_privileges_through_posted_fields(self):
        self.client.force_login(self.staff)
        url = reverse("admin:auth_user_change", args=[self.user.pk])
        response = self.client.post(
            url,
            self.payload(
                self.user,
                is_staff="on",
                is_superuser="on",
                groups=[Group.objects.get(name="administrador").pk],
                user_permissions=list(Permission.objects.values_list("pk", flat=True)),
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertFalse(self.user.groups.filter(name="administrador").exists())
        self.assertFalse(self.user.user_permissions.exists())

    def test_protected_accounts_are_not_accessible_to_staff_editors(self):
        protected = User.objects.create_user("administradorcomunidad")
        protected.groups.add(Group.objects.get(name="administrador"))
        self.client.force_login(self.staff)
        for user in [self.root, self.staff, protected]:
            url = reverse("admin:auth_user_change", args=[user.pk])
            response = self.client.get(url)
            # Django redirige el objeto inexistente al índice y muestra el aviso; no expone el formulario.
            self.assertNotEqual(response.status_code, 200)
            self.client.post(url, self.payload(user, email="tomada@example.invalid"))
            user.refresh_from_db()
            self.assertNotEqual(user.email, "tomada@example.invalid")
            response = self.client.get(reverse("admin:auth_user_password_change", args=[user.pk]))
            self.assertNotEqual(response.status_code, 200)

    def test_superuser_cannot_remove_own_access_or_delete_self(self):
        response = self.client.post(
            reverse("admin:auth_user_change", args=[self.root.pk]),
            self.payload(self.root, is_active="", is_staff="", is_superuser=""),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No puedes retirar tu propio acceso administrativo.")
        self.root.refresh_from_db()
        self.assertTrue(self.root.is_active and self.root.is_superuser and self.root.is_staff)
        self.client.post(
            reverse("admin:auth_user_changelist"),
            {"action": "delete_selected", "_selected_action": [self.root.pk, self.user.pk], "post": "yes"},
        )
        self.assertTrue(User.objects.filter(pk=self.root.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_native_deactivation_invalidates_sessions_and_recovery(self):
        other = Client()
        other.force_login(self.user)
        token = PasswordResetToken.crear_para_usuario(self.user)
        response = self.client.post(
            reverse("admin:auth_user_change", args=[self.user.pk]), self.payload(self.user, is_active="")
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        token.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertTrue(token.utilizado)
        self.assertFalse(SesionUsuario.objects.filter(usuario=self.user).exists())

    def test_native_email_change_notifies_both_addresses(self):
        token = PasswordResetToken.crear_para_usuario(self.user)
        response = self.client.post(
            reverse("admin:auth_user_change", args=[self.user.pk]),
            self.payload(self.user, email="despues@example.invalid"),
        )
        self.assertEqual(response.status_code, 302)
        token.refresh_from_db()
        self.assertTrue(token.utilizado)
        self.assertEqual(
            set(CorreoSeguridad.objects.filter(usuario=self.user).values_list("destinatario", flat=True)),
            {"antes@example.invalid", "despues@example.invalid"},
        )

    def test_native_password_change_revokes_old_sessions_and_notifies(self):
        other = Client()
        other.force_login(self.user)
        token = PasswordResetToken.crear_para_usuario(self.user)
        url = reverse("admin:auth_user_password_change", args=[self.user.pk])
        response = self.client.post(
            url,
            {"password1": "NuevaClaveDePruebas42!", "password2": "NuevaClaveDePruebas42!", "usable_password": "true"},
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        token.refresh_from_db()
        self.assertTrue(self.user.check_password("NuevaClaveDePruebas42!"))
        self.assertTrue(token.utilizado)
        self.assertFalse(SesionUsuario.objects.filter(usuario=self.user).exists())
        self.assertTrue(CorreoSeguridad.objects.filter(usuario=self.user, tipo="cambio").exists())

    def test_profile_save_does_not_restore_an_old_password_hash(self):
        snapshot = User.objects.get(pk=self.user.pk)
        self.user.set_password("ClaveActualizada42!")
        self.user.save(update_fields=["password"])
        snapshot.first_name = "Laura"
        request = RequestFactory().post("/admin/auth/user/")
        request.user = self.root
        request.session = self.client.session
        admin.site._registry[User].save_model(request, snapshot, SimpleNamespace(changed_data=["first_name"]), True)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("ClaveActualizada42!"))
        self.assertEqual(self.user.first_name, "Laura")

    def test_native_password_change_keeps_own_current_session(self):
        response = self.client.post(
            reverse("admin:auth_user_password_change", args=[self.root.pk]),
            {"password1": "CambioAdministrativo42!", "password2": "CambioAdministrativo42!", "usable_password": "true"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
