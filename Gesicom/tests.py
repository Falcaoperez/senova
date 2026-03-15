from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Group
from .models import Envio


class EnvioViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u', email='u@example.com', password='Abcdef1!')
        g, _ = Group.objects.get_or_create(name='usuario')
        self.user.groups.add(g)

    def test_evidencia_requires_auth(self):
        resp = self.client.get(reverse('evidencia'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.url)

    def test_evidencia_post_validation(self):
        self.client.login(username='u', password='Abcdef1!')
        # Falta enlace y archivo
        resp = self.client.post(reverse('evidencia'), {
            'nombre': 'Prueba',
            'proyecto': 'LEM',
            'evidencias': ['Documento'],
            'observaciones': 'Test',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Debe proporcionar un enlace')

    def test_evidencia_post_success_with_link(self):
        self.client.login(username='u', password='Abcdef1!')
        resp = self.client.post(reverse('evidencia'), {
            'nombre': 'Prueba',
            'proyecto': 'LEM',
            'evidencias': ['Documento'],
            'linkArchivo': 'https://example.com/file',
            'observaciones': 'Test',
        })
        self.assertEqual(resp.status_code, 200)
        # el texto de éxito se muestra en el template
        self.assertContains(resp, 'Evidencia enviada correctamente')
        self.assertEqual(Envio.objects.count(), 1)

    def test_evidencias_list(self):
        self.client.login(username='u', password='Abcdef1!')
        Envio.objects.create(usuario=self.user, nombre='n', proyecto='LEM', tipo_evidencia='Doc')
        resp = self.client.get(reverse('evidencias_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'LEM')
