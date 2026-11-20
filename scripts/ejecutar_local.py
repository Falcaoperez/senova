#!/usr/bin/env python3
"""Inicia web y notificaciones con el perfil local y el Python de .venv."""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from SENNOVA.desarrollo import archivo_perfil, entorno_local, python_del_entorno


def detener(procesos):
    for proceso in procesos:
        if proceso.poll() is None:
            proceso.terminate()
    for proceso in procesos:
        try:
            proceso.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proceso.kill()
            proceso.wait()


def iniciar(raiz, *, puerto=8000):
    python = python_del_entorno(raiz)
    if not python.is_file() or not archivo_perfil(raiz).is_file():
        raise RuntimeError("Ejecuta primero: python scripts/configurar_entorno.py --inicio-rapido")
    entorno = entorno_local(raiz, puerto=puerto)
    entorno["PYTHONUNBUFFERED"] = "1"
    entorno["PYTHONUTF8"] = "1"
    procesos = []
    try:
        for argumentos in [
            ["-m", "waitress", f"--listen=127.0.0.1:{puerto}", "SENNOVA.wsgi:application"],
            ["manage.py", "procesar_notificaciones", "--continuo", "--intervalo", "5", "--lote", "50"],
        ]:
            procesos.append(subprocess.Popen([str(python), *argumentos], cwd=raiz, env=entorno))
        print(f"GESICOM: http://127.0.0.1:{puerto}/ - Ctrl+C para detener web y trabajador.", flush=True)
        while all(proceso.poll() is None for proceso in procesos):
            time.sleep(0.25)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        detener(procesos)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puerto", type=int, default=8000)
    args = parser.parse_args(argv)
    if not 1024 <= args.puerto <= 65535:
        parser.error("El puerto debe estar entre 1024 y 65535.")
    try:
        return iniciar(ROOT, puerto=args.puerto)
    except (OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
