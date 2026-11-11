from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse


class AdminPanelTests(TestCase):
    def test_access_and_pages(self):
        user = User.objects.create_user("member", password="SeguraLarga42!")
        self.client.force_login(user)
        self.assertRedirects(
            self.client.get(reverse("admin_personalizado:dashboard")),
            "/access-denied/?next=/administrador/",
            fetch_redirect_response=False,
        )
        user.groups.add(Group.objects.get(name="administrador"))
        for page in ["dashboard", "usuarios", "gestionar_usuarios", "crear_usuario", "permisos"]:
            with self.subTest(page=page):
                self.assertEqual(self.client.get(reverse("admin_personalizado:" + page)).status_code, 200)

    def test_bulk_roles_preserve_unchanged_memberships(self):
        admin = User.objects.create_user("role_admin", password="Segura42!")
        admin.groups.add(Group.objects.get(name="administrador"))
        member = User.objects.create_user("multirole")
        member.groups.set(Group.objects.filter(name__in=["usuario", "instructor"]))
        self.client.force_login(admin)
        response = self.client.post(
            reverse("admin_personalizado:gestionar_usuarios"), {f"role_{member.pk}": "__keep__"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(set(member.groups.values_list("name", flat=True)), {"usuario", "instructor"})
        self.client.post(reverse("admin_personalizado:gestionar_usuarios"), {f"role_{member.pk}": "999999"})
        self.assertEqual(set(member.groups.values_list("name", flat=True)), {"usuario", "instructor"})

    def test_permissions_form_and_save_use_existing_fields(self):
        from django.contrib.auth.models import Permission

        admin = User.objects.create_user("permission_admin")
        admin.groups.add(Group.objects.get(name="administrador"))
        self.client.force_login(admin)
        group = Group.objects.create(name="grupo_prueba")
        permission = Permission.objects.get(codename="change_envio")
        url = reverse("admin_personalizado:permisos")
        response = self.client.get(url, {"group": group.pk})
        self.assertContains(response, "perm_change_envio_1", count=1)
        self.assertEqual(response.context["grupo_seleccionado"], group)
        self.client.post(url, {"group": group.pk, "perm_change_envio_1": "allowed"})
        self.assertTrue(group.permissions.filter(pk=permission.pk).exists())
        self.client.post(url, {"group": group.pk, "perm_change_envio_1": "denied"})
        self.assertFalse(group.permissions.filter(pk=permission.pk).exists())

    def test_existing_profile_edit_actions_remain_available(self):
        admin = User.objects.create_user("profile_admin")
        admin.groups.add(Group.objects.get(name="administrador"))
        member = User.objects.create_user("profile_member", email="before@example.com")
        self.client.force_login(admin)
        url = reverse("admin_personalizado:detalle_usuario", args=[member.pk])
        self.client.post(
            url,
            {"action": "update_profile", "first_name": "Laura", "last_name": "Ramírez", "email": "after@example.com"},
        )
        member.refresh_from_db()
        self.assertEqual(member.first_name, "Laura")
        self.assertEqual(member.email, "after@example.com")
        group = Group.objects.get(name="investigador")
        self.client.post(url, {"action": "update_groups", "grupos": [str(group.pk)]})
        self.assertEqual(list(member.groups.values_list("name", flat=True)), ["investigador"])

    def test_existing_django_admin_uses_institutional_brand(self):
        user = User.objects.create_superuser("framework_admin", email="admin@example.com", password="LocalTest42!")
        self.client.force_login(user)
        for path in ["/admin/", "/admin/auth/user/"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "css/sena-admin.css")
            self.assertContains(response, "img/brand/sena.svg")
