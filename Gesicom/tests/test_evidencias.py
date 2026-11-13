from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from ..models import Envio


class EnvioViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", email="u@example.com", password="Abcdef1!")
        g, _ = Group.objects.get_or_create(name="usuario")
        self.user.groups.add(g)

    def test_evidencia_requires_auth(self):
        resp = self.client.get(reverse("evidencia"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_evidencia_post_validation(self):
        self.client.login(username="u", password="Abcdef1!")
        # Falta enlace y archivo
        resp = self.client.post(
            reverse("evidencia"),
            {
                "nombre": "Prueba",
                "proyecto": "LEM",
                "evidencias": ["Documento"],
                "observaciones": "Test",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Debe proporcionar un enlace")

    def test_evidencia_post_success_with_link(self):
        self.client.login(username="u", password="Abcdef1!")
        resp = self.client.post(
            reverse("evidencia"),
            {
                "nombre": "Prueba",
                "proyecto": "LEM",
                "evidencias": ["Documento"],
                "linkArchivo": "https://example.com/file",
                "observaciones": "Test",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        # el texto de éxito se muestra en el template
        self.assertContains(resp, "Evidencia enviada correctamente")
        self.assertEqual(Envio.objects.count(), 1)

    def test_evidencias_list(self):
        self.client.login(username="u", password="Abcdef1!")
        Envio.objects.create(usuario=self.user, nombre="n", proyecto="LEM", tipo_evidencia="Doc")
        resp = self.client.get(reverse("evidencias_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "LEM")


class ApplicationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("reader", email="reader@example.com", password="Strongpass42!")
        self.other = User.objects.create_user("other", email="other@example.com", password="Strongpass42!")
        self.envio = Envio.objects.create(
            usuario=self.other, nombre="Privada", proyecto="LEM", tipo_evidencia="Documento"
        )

    def test_public_pages(self):
        for name in [
            "login",
            "register",
            "home",
            "nosotros",
            "contacto",
            "ayuda",
            "password_reset",
            "password_reset_done",
            "password_reset_complete",
            "password_reset_update",
        ]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_role_panels(self):
        self.client.force_login(self.user)
        for role in ["instructor", "investigador", "dinamizador", "coordinador"]:
            self.user.groups.set([Group.objects.get(name=role)])
            with self.subTest(role=role):
                response = self.client.get(reverse("role_" + role))
                self.assertEqual(response.status_code, 200)
                self.assertIn("total_envios", response.context)

    def test_personal_scope_and_real_dashboard(self):
        self.user.groups.add(Group.objects.get(name="instructor"))
        Envio.objects.create(
            usuario=self.user, nombre="Propia", proyecto="LEM", tipo_evidencia="Documento", aprobada=True
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("role_instructor"))
        self.assertEqual(response.context["total_envios"], 1)
        self.assertEqual(response.context["aprobadas"], 1)
        self.assertNotContains(self.client.get(reverse("evidencias_list")), "Privada")
        self.assertEqual(self.client.get(reverse("ver_evidencia", args=[self.envio.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("reportes_csv")), "Privada")

    def test_reviewer_can_see_all(self):
        self.user.groups.add(Group.objects.get(name="coordinador"))
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("evidencias_list")), "Privada")

    def test_approval_permissions_and_redirect(self):
        url = reverse("set_aprobada", args=[self.envio.pk])
        self.assertEqual(self.client.post(url, {"valor": "1"}).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(url, {"valor": "1"}).status_code, 403)
        self.envio.refresh_from_db()
        self.assertFalse(self.envio.aprobada)
        self.user.groups.add(Group.objects.get(name="coordinador"))
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, {"valor": "invalid"}).status_code, 400)
        response = self.client.post(url, {"valor": "1", "next": "https://example.org/"})
        self.assertRedirects(response, reverse("evidencias_list"))
        self.envio.refresh_from_db()
        self.assertTrue(self.envio.aprobada)
        self.assertFalse(self.envio.rechazada)

    def test_reports_require_login(self):
        for name in ["reportes", "reportes_csv", "reportes_trimestrales_csv", "proyecciones"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 302)

    def test_profile_validation_and_session(self):
        self.client.force_login(self.user)
        payload = {
            "username": "reader",
            "nombre": "Ana",
            "apellido": "Pérez",
            "correo": "reader@example.com",
            "contrasena": "NuevaSegura42!",
            "confirmar_contrasena": "NuevaSegura42!",
            "contrasena_actual": "Strongpass42!",
        }
        response = self.client.post(reverse("editar_perfil"), payload)
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NuevaSegura42!"))
        self.assertEqual(self.client.get(reverse("editar_perfil")).status_code, 200)
        payload["contrasena"] = "short"
        payload["contrasena_actual"] = "NuevaSegura42!"
        payload["nombre"] = "No guardar"
        self.assertEqual(self.client.post(reverse("editar_perfil"), payload).status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Ana")
        payload.update(contrasena="", username="other")
        response = self.client.post(reverse("editar_perfil"), payload)
        self.assertTrue(response.context["form"].errors)

    def test_invalid_evidence_is_not_saved(self):
        self.client.force_login(self.user)
        for data in [
            {"proyecto": "INVALID", "linkArchivo": "https://example.com"},
            {"proyecto": "LEM", "linkArchivo": "javascript:alert(1)"},
        ]:
            response = self.client.post(reverse("evidencia"), {"nombre": "Ejemplo", **data})
            self.assertTrue(response.context["errores"])
        self.assertEqual(Envio.objects.count(), 1)

    def test_missing_observation_returns_404(self):
        self.user.groups.add(Group.objects.get(name="administrador"))
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.post(reverse("actualizar_observaciones", args=[99999]), {"observaciones": "x"}).status_code, 404
        )

    def test_admin_group_has_access(self):
        self.user.groups.add(Group.objects.get(name="administrador"))
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("role_coordinador")).status_code, 200)

    def test_no_automatic_admin(self):
        self.assertFalse(User.objects.filter(username="admin", is_superuser=True).exists())


class StaticResourceTests(TestCase):
    def test_all_template_static_paths_exist(self):
        import re
        from pathlib import Path

        from django.conf import settings
        from django.contrib.staticfiles import finders

        for app in ["Gesicom", "ADMIN", "instructor"]:
            for template in (Path(settings.BASE_DIR) / app / "templates").rglob("*.html"):
                for asset in re.findall(r"{%\s*static\s+['\"]([^'\"]+)['\"]\s*%}", template.read_text()):
                    with self.subTest(template=str(template), asset=asset):
                        self.assertIsNotNone(finders.find(asset.lstrip("/")))

    def test_pagination_keeps_filters(self):
        user = User.objects.create_user("pages")
        Envio.objects.bulk_create(
            [Envio(usuario=user, nombre="Buscar", proyecto="LEM", tipo_evidencia="Documento") for _ in range(11)]
        )
        self.client.force_login(user)
        response = self.client.get(reverse("evidencias_list"), {"q": "Buscar", "proyecto": "LEM"})
        self.assertContains(response, "q=Buscar&amp;proyecto=LEM&amp;page=2")

    def test_report_chart_data_and_download_filters(self):
        user = User.objects.create_user("chartuser")
        envio = Envio.objects.create(
            usuario=user, nombre="En período", proyecto="LEM", tipo_evidencia="Documento", aprobada=True
        )
        Envio.objects.filter(pk=envio.pk).update(fecha_envio="2026-03-12")
        self.client.force_login(user)
        response = self.client.get(reverse("reportes"), {"start": "2026-03", "end": "2026-03", "proyecto": "LEM"})
        self.assertEqual(response.context["total_envios"], 1)
        self.assertEqual(response.context["aprobadas"], 1)
        self.assertEqual(sum(response.context["categorias_data_json"]), 1)
        self.assertContains(response, 'type="application/json"')
        self.assertContains(response, "/reportes.csv?start=2026-03&amp;end=2026-03&amp;proyecto=LEM")
        response = self.client.get(reverse("reportes"), {"start": "2026-04"})
        self.assertEqual(response.context["total_envios"], 0)

    def test_user_panel_has_single_navigation_and_real_data(self):
        user = User.objects.create_user("dashboarduser")
        user.groups.add(Group.objects.get(name="usuario"))
        Envio.objects.create(usuario=user, nombre="Mi registro", proyecto="LEM", tipo_evidencia="Documento")
        self.client.force_login(user)
        response = self.client.get(reverse("usuario"))
        self.assertEqual(response.context["total_envios"], 1)
        self.assertContains(response, 'id="main-navigation"', count=1)
        self.assertContains(response, "<main ", count=1)
        self.assertContains(response, "Mi registro")

    def test_state_filter_and_preserved_old_link_field(self):
        user = User.objects.create_user("filteruser")
        self.client.force_login(user)
        Envio.objects.create(usuario=user, nombre="Aprobada", proyecto="LEM", tipo_evidencia="Documento", aprobada=True)
        Envio.objects.create(usuario=user, nombre="Pendiente", proyecto="LEM", tipo_evidencia="Documento")
        response = self.client.get(reverse("evidencias_list"), {"estado": "pendiente"})
        self.assertEqual(response.context["total_envios"], 1)
        self.assertEqual(response.context["envios"][0].nombre, "Pendiente")
        response = self.client.post(
            reverse("evidencia"),
            {"nombre": "Enlace anterior", "proyecto": "LEM", "link_evidencia": "https://www.sena.edu.co"},
        )
        self.assertRedirects(response, reverse("ver_evidencia", args=[Envio.objects.get(nombre="Enlace anterior").pk]))
        self.assertEqual(Envio.objects.get(nombre="Enlace anterior").link_evidencia, "https://www.sena.edu.co")

    def test_csv_matches_search_and_state_filters(self):
        user = User.objects.create_user("csvfilters")
        self.client.force_login(user)
        Envio.objects.create(
            usuario=user, nombre="Informe aprobado", proyecto="LEM", tipo_evidencia="Documento", aprobada=True
        )
        Envio.objects.create(usuario=user, nombre="Informe pendiente", proyecto="LEM", tipo_evidencia="Documento")
        response = self.client.get(reverse("reportes_csv"), {"q": "Informe", "estado": "pendiente"})
        self.assertContains(response, "Informe pendiente")
        self.assertNotContains(response, "Informe aprobado")
