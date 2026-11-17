"""Filas del seguimiento: campos visibles, fecha de Colombia y SQL por lotes."""

from zoneinfo import ZoneInfo

from django.utils import timezone

from Gesicom.exportaciones import iterar_por_id


def filas_seguimiento(consulta):
    yield ["Usuario", "Nombre", "Correo", "Entrega", "Última entrega (Colombia)", "Última revisión"]
    zona = ZoneInfo("America/Bogota")
    for usuario in iterar_por_id(consulta):
        entrega = "Pendiente" if not usuario.entregado else "A tiempo" if usuario.a_tiempo else "Fuera de plazo"
        revision = (
            ""
            if not usuario.entregado
            else "Aprobada"
            if usuario.ultima_aprobada
            else "Rechazada"
            if usuario.ultima_rechazada
            else "En revisión"
        )
        fecha = (
            timezone.localtime(usuario.ultima_entrega, zona).strftime("%Y-%m-%d %H:%M:%S")
            if usuario.ultima_entrega
            else ""
        )
        yield [usuario.username, usuario.get_full_name(), usuario.email, entrega, fecha, revision]
