"""Opciones de conexión de MySQL, sin habilitar cargas locales ni sentencias encadenadas."""

import ipaddress
import socket
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


def opciones_mysql(env):
    modo = env("DB_SSL_MODE", default="REQUIRED").upper()
    if modo not in {"REQUIRED", "VERIFY_CA", "VERIFY_IDENTITY"}:
        raise ImproperlyConfigured("DB_SSL_MODE debe exigir TLS: REQUIRED, VERIFY_CA o VERIFY_IDENTITY.")
    ca = env("DB_SSL_CA", default="")
    if modo in {"VERIFY_CA", "VERIFY_IDENTITY"} and not ca:
        raise ImproperlyConfigured("El modo de verificación de MySQL necesita DB_SSL_CA.")
    if ca and not Path(ca).is_file():
        raise ImproperlyConfigured("El certificado configurado en DB_SSL_CA no está disponible.")
    if modo == "VERIFY_IDENTITY":
        host = env("DB_HOST", default="127.0.0.1")
        es_ip = False
        try:
            ipaddress.ip_address(host.strip("[]"))
            es_ip = True
        except ValueError:
            try:
                # También rechaza representaciones IPv4 abreviadas, octales o hexadecimales.
                socket.inet_aton(host)
                es_ip = True
            except OSError:
                pass
        if not host or host.casefold() == "localhost" or es_ip:
            raise ImproperlyConfigured(
                "VERIFY_IDENTITY requiere un nombre DNS que coincida con el certificado; no uses una IP ni un socket local."
            )
    opciones = {
        "charset": "utf8mb4",
        "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        "connect_timeout": 10,
        "local_infile": False,
        "multi_statements": False,
        "ssl_mode": modo,
    }
    if ca:
        opciones["ssl"] = {"ca": ca}
    return opciones
