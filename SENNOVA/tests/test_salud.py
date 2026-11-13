from unittest.mock import patch

from django.test import TestCase, override_settings


@override_settings(SECURE_SSL_REDIRECT=True)
class ProductionHealthTests(TestCase):
    def test_internal_health_works_while_application_requires_https(self):
        self.assertEqual(self.client.get("/health/").json(), {"estado": "ok"})
        response = self.client.get("/login/")
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response["Location"].startswith("https://"))

    def test_unavailable_service_returns_503_without_internal_details(self):
        with patch("SENNOVA.health.cache.get", side_effect=ConnectionError("private connection details")):
            response = self.client.get("/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"estado": "no disponible"})
