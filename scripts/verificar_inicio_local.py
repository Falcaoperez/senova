#!/usr/bin/env python3
"""Prueba HTTP reproducible del perfil local, sin Docker ni servicios externos."""

import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.ejecutar_local import detener
from SENNOVA.desarrollo import archivo_perfil, entorno_local, python_del_entorno


def verificar(raiz=ROOT):
    python = python_del_entorno(raiz)
    entorno = entorno_local(raiz)
    entorno["PYTHONUTF8"] = "1"
    perfil_antes = archivo_perfil(raiz).read_bytes()
    archivo_original = raiz / ".env"
    original_antes = archivo_original.read_bytes() if archivo_original.exists() else None
    codigo = """
import importlib.util, json, django
from pathlib import Path
django.setup()
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth import get_user_model
assert importlib.util.find_spec('MySQLdb') is None, 'El entorno portátil debe instalarse sin mysqlclient'
assert importlib.util.find_spec('gunicorn') is None, 'Gunicorn pertenece al perfil de producción'
assert settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3'
assert Path(settings.DATABASES['default']['NAME']).parent == settings.BASE_DIR / '.local' / 'desarrollo'
assert get_user_model().objects.filter(username__startswith='revision.').count() == 6
assert settings.EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend'
assert not settings.EMAIL_HOST_PASSWORD
assert cache.get('notificaciones:trabajador'), 'La señal del trabajador debe compartirse entre procesos'
print(json.dumps({'usuarios_revision': 6, 'cache_compartida': True, 'sin_cliente_mysql': True}))
"""
    subprocess.run(
        [str(python), "manage.py", "procesar_notificaciones", "--lote", "1"], cwd=raiz, env=entorno, check=True
    )
    subprocess.run([str(python), "-c", codigo], cwd=raiz, env=entorno, check=True)
    with socket.socket() as reserva:
        reserva.bind(("127.0.0.1", 0))
        puerto = reserva.getsockname()[1]
    with tempfile.TemporaryFile() as registro:
        proceso = subprocess.Popen(
            [str(python), "-m", "waitress", f"--listen=127.0.0.1:{puerto}", "SENNOVA.wsgi:application"],
            cwd=raiz,
            env=entorno,
            stdout=registro,
            stderr=subprocess.STDOUT,
        )
        try:
            limite = time.monotonic() + 30
            while True:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/health/", timeout=2) as respuesta:
                        assert json.load(respuesta)["estado"] == "ok"
                    break
                except (urllib.error.URLError, TimeoutError):
                    if proceso.poll() is not None or time.monotonic() >= limite:
                        raise RuntimeError("El servidor local no completó el arranque en 30 segundos.") from None
                    time.sleep(0.25)
            with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/login/", timeout=5) as respuesta:
                assert respuesta.status == 200
                assert b"csrfmiddlewaretoken" in respuesta.read()
        finally:
            detener([proceso])
    assert archivo_perfil(raiz).read_bytes() == perfil_antes, "El secreto local debe conservarse"
    original_despues = archivo_original.read_bytes() if archivo_original.exists() else None
    assert original_despues == original_antes, ".env debe conservarse exactamente"
    print(
        "Inicio portátil verificado: SQLite, seis roles, trabajador, caché compartida, HTTP y configuración conservada."
    )


if __name__ == "__main__":
    verificar()
