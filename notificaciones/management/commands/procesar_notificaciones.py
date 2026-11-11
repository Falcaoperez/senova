import time

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from notificaciones.services import procesar_correos, sincronizar_plazos


class Command(BaseCommand):
    help = "Genera avisos de vencimiento y procesa la cola de correos con reintentos."

    def add_arguments(self, parser):
        parser.add_argument("--continuo", action="store_true", help="Mantiene el trabajador activo.")
        parser.add_argument("--intervalo", type=int, default=30)
        parser.add_argument("--lote", type=int, default=50)

    def handle(self, *args, **options):
        try:
            while True:
                close_old_connections()
                cache.set("notificaciones:trabajador", timezone.now().isoformat(), timeout=120)
                avisos = sincronizar_plazos()
                enviados = procesar_correos(limite=max(1, min(options["lote"], 500)))
                self.stdout.write(f"Avisos nuevos: {avisos}; correos enviados: {enviados}.")
                if not options["continuo"]:
                    return
                time.sleep(max(5, min(options["intervalo"], 60)))
        except KeyboardInterrupt:
            self.stdout.write("Trabajador detenido.")
