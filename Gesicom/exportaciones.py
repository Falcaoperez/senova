"""Recorridos SQL acotados y respuestas CSV sin acumular el documento."""

import csv

from django.db.models import Max, Q
from django.http import StreamingHttpResponse

from .utils import safe_csv_cell


def iterar_por_id(consulta):
    """Recorre una consulta sin paginar por OFFSET ni traer todo el resultado."""
    return iterar_ordenados(consulta, campo="pk")


def iterar_ordenados(consulta, *, campo):
    """Lotes de 500, por un campo escalar no nulo y el ID en igual dirección.

    El campo procede del código o de las opciones validadas del formulario.
    El corte de ID excluye altas posteriores; no es una instantánea de ediciones.
    """
    tope = consulta.aggregate(ultimo=Max("pk"))["ultimo"]
    if tope is None:
        return
    descendente = campo.startswith("-")
    nombre = campo.removeprefix("-")
    comparador = "lt" if descendente else "gt"
    orden = [campo] if nombre == "pk" else [campo, "-pk" if descendente else "pk"]
    cursor = None
    while True:
        siguientes = consulta.filter(pk__lte=tope)
        if cursor is not None:
            posterior = Q(**{f"{nombre}__{comparador}": cursor[0]})
            if nombre != "pk":
                posterior |= Q(**{nombre: cursor[0], f"pk__{comparador}": cursor[1]})
            siguientes = siguientes.filter(posterior)
        lote = list(siguientes.order_by(*orden)[:500])
        if not lote:
            return
        cursor = (getattr(lote[-1], nombre), lote[-1].pk)
        yield from lote
        if len(lote) < 500 or (campo == "pk" and cursor[1] == tope):
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
