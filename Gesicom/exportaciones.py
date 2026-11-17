"""Respuestas CSV reutilizables, con Unicode y sin acumulación del documento."""

import csv

from django.db.models import Max
from django.http import StreamingHttpResponse

from .utils import safe_csv_cell


def iterar_por_id(consulta):
    """Recorre una consulta sin paginar por OFFSET ni traer todo el resultado."""
    tope = consulta.aggregate(ultimo=Max("pk"))["ultimo"]
    if tope is None:
        return
    ultimo = 0
    while ultimo < tope:
        lote = list(consulta.filter(pk__gt=ultimo, pk__lte=tope).order_by("pk")[:500])
        if not lote:
            return
        yield from lote
        ultimo = lote[-1].pk
        if len(lote) < 500:
            return


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
