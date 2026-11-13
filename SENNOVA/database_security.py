"""Diagnóstico de solo lectura de la conexión activa, sin publicar concesiones."""

import re

from django.db import DatabaseError, connection

from database.seguridad.perfiles import CRUD

_GRANT = re.compile(r"^GRANT ([A-Z, _]+) ON (.+) TO `(?:[^`]|``)+`@`(?:[^`]|``)+`$")


def concesiones_minimas(concesiones, esquema, *, partial_revokes=False):
    """Cualquier concesión desconocida, rol o alcance adicional requiere revisión."""
    if not isinstance(esquema, str) or not esquema:
        return False
    nombre = esquema if partial_revokes else esquema.replace("_", "\\_")
    alcance = "`" + nombre.replace("`", "``") + "`.*"
    permisos = set()
    for concesion in concesiones:
        coincidencia = _GRANT.fullmatch(concesion)
        if not coincidencia:
            return False
        lista, destino = coincidencia.groups()
        actuales = set(lista.split(", "))
        if destino == "*.*" and actuales == {"USAGE"}:
            continue
        if destino != alcance or not actuales.issubset(CRUD):
            return False
        permisos.update(actuales)
    return permisos == set(CRUD)


def _informe(estado, controles=()):
    return {"motor": "mysql", "estado": estado, "correcto": estado == "correcto", "controles": list(controles)}


def inspeccionar_conexion(conexion=None):
    """No ejecuta DDL, DML, pruebas de permisos ni consultas sobre datos personales."""
    db = conexion if conexion is not None else connection
    if db.vendor != "mysql":
        return _informe("no_disponible")
    try:
        from MySQLdb.constants import CLIENT

        with db.cursor() as cursor:
            cursor.execute(
                "SELECT CURRENT_USER(), DATABASE(), @@SESSION.foreign_key_checks, "
                "@@SESSION.sql_mode, @@default_storage_engine, @@GLOBAL.partial_revokes, "
                "CURRENT_ROLE(), @@GLOBAL.mandatory_roles, @@GLOBAL.local_infile"
            )
            cuenta, esquema, fk, modo, motor, parciales, roles, obligatorios, cargas = cursor.fetchone()
            cursor.execute("SHOW GRANTS")
            grants = [fila[0] for fila in cursor.fetchall()]
            cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
            fila = cursor.fetchone()
            cifrada = bool(fila and fila[1])
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_TYPE = 'BASE TABLE' AND ENGINE <> 'InnoDB'"
            )
            motores_ajenos = cursor.fetchone()[0]
        flags = db.connection.client_flag
        usuario_configurado = db.settings_dict["USER"]
        cuenta_correcta = cuenta.rsplit("@", 1)[0] == usuario_configurado
        permisos = (
            cuenta_correcta
            and concesiones_minimas(grants, esquema, partial_revokes=bool(parciales))
            and roles == "NONE"
            and not obligatorios
        )
        opciones = db.settings_dict.get("OPTIONS", {})
        tls = cifrada and opciones.get("ssl_mode") in {"REQUIRED", "VERIFY_CA", "VERIFY_IDENTITY"}
        if opciones.get("ssl_mode") == "REQUIRED":
            detalle_tls = (
                "El canal está cifrado. REQUIRED no verifica la identidad del servidor; "
                "para ello configura VERIFY_IDENTITY con una CA de confianza."
            )
        else:
            detalle_tls = "Canal cifrado con verificación del certificado solicitada en la configuración."
        cliente_restringido = not bool(flags & (CLIENT.MULTI_STATEMENTS | CLIENT.LOCAL_FILES)) and not cargas
        controles = [
            {
                "codigo": "permisos",
                "titulo": "Permisos de ejecución",
                "correcto": bool(permisos),
                "detalle": "Solo lectura, creación, edición y eliminación de registros en el esquema de la aplicación. Sin roles ni permisos para modificar tablas o conceder accesos."
                if permisos
                else "Revisa la cuenta: se requieren únicamente permisos sobre registros en el esquema exacto de la aplicación, sin roles ni concesiones adicionales.",
            },
            {
                "codigo": "tls",
                "titulo": "Conexión cifrada",
                "correcto": bool(tls),
                "detalle": detalle_tls if tls else "La conexión activa debe exigir y utilizar TLS.",
            },
            {
                "codigo": "cliente",
                "titulo": "Consultas y cargas locales",
                "correcto": cliente_restringido,
                "detalle": "Sentencias encadenadas deshabilitadas en el cliente y cargas de archivos locales deshabilitadas en cliente y servidor."
                if cliente_restringido
                else "Revisa las opciones del cliente y del servidor: deben deshabilitar sentencias encadenadas y cargas locales.",
            },
            {
                "codigo": "integridad",
                "titulo": "Integridad de los datos",
                "correcto": bool(fk)
                and bool({"STRICT_TRANS_TABLES", "STRICT_ALL_TABLES"} & set(modo.split(",")))
                and motor.casefold() == "innodb"
                and not motores_ajenos,
                "detalle": "Se comprueban claves foráneas activas, modo estricto y tablas de aplicación en InnoDB.",
            },
        ]
        return _informe("correcto" if all(c["correcto"] for c in controles) else "revisar", controles)
    except DatabaseError:
        # Un fallo nunca devuelve SQL, concesiones, nombres internos ni credenciales.
        return _informe("no_disponible")
