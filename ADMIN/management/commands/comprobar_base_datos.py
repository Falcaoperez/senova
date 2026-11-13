import json

from django.core.management.base import BaseCommand, CommandError

from SENNOVA.database_security import inspeccionar_conexion


class Command(BaseCommand):
    help = "Comprueba permisos mínimos, TLS y opciones de MySQL sin modificar la base."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Devuelve únicamente el informe público en JSON.")
        parser.add_argument("--estricto", action="store_true", help="Termina con error si hay controles por revisar.")

    def handle(self, *args, **options):
        informe = inspeccionar_conexion()
        if options["json"]:
            self.stdout.write(json.dumps(informe, ensure_ascii=False))
        else:
            self.stdout.write("Seguridad de MySQL: " + informe["estado"].replace("_", " "))
            for control in informe["controles"]:
                self.stdout.write(("OK · " if control["correcto"] else "REVISAR · ") + control["titulo"])
        if options["estricto"] and not informe["correcto"]:
            raise CommandError("La conexión de ejecución tiene controles de seguridad pendientes de revisión.")
