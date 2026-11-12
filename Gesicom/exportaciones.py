"""Respuestas CSV reutilizables, con Unicode y sin acumulación del documento."""

import csv

from django.http import StreamingHttpResponse

from .utils import safe_csv_cell


class _SalidaCSV:
    def write(self, value):
        return value


def respuesta_csv(filas, nombre):
    def contenido():
        escritor = csv.writer(_SalidaCSV())
        yield "\ufeff"
        for fila in filas:
            yield escritor.writerow([safe_csv_cell(valor) for valor in fila])

    respuesta = StreamingHttpResponse(contenido(), content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    respuesta["Cache-Control"] = "no-store"
    return respuesta
