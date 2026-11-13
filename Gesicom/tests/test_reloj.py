"""El reloj inicial conserva la fecha colombiana incluso en otra zona activa."""

import datetime
from unittest.mock import patch

from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.utils import timezone


class RelojColombiaTests(SimpleTestCase):
    def test_server_fallback_uses_colombian_date_at_midnight(self):
        for utc, fecha, hora in [
            ("2026-11-14T04:59:59+00:00", "2026-11-13", "23:59:59"),
            ("2026-11-14T05:00:00+00:00", "2026-11-14", "00:00:00"),
        ]:
            with (
                self.subTest(utc=utc),
                timezone.override("Asia/Tokyo"),
                patch("Gesicom.templatetags.ui.timezone") as reloj,
            ):
                reloj.now.return_value = datetime.datetime.fromisoformat(utc)
                html = render_to_string("ui/reloj_colombia.html")
                self.assertIn(f'datetime="{fecha}T{hora}-05:00"', html)
                self.assertIn(f"<strong data-clock-time>{hora}</strong>", html)
                self.assertIn('aria-live="off"', html)
