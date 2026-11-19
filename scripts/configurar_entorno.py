#!/usr/bin/env python3
"""Prepara .venv para VS Code sin sobrescribir la configuración privada existente."""

import argparse
import json
import os
import secrets
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VARIABLES_LOCALES = {
    "DJANGO_SETTINGS_MODULE": "SENNOVA.settings",
    "DJANGO_DEBUG": "True",
    "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1",
    "DB_ENGINE": "sqlite",
    "REDIS_URL": "",
    "EMAIL_BACKEND": "django.core.mail.backends.console.EmailBackend",
    "PUBLIC_BASE_URL": "http://127.0.0.1:8000",
    "CSRF_TRUSTED_ORIGINS": "http://localhost:8000,http://127.0.0.1:8000",
}


def python_del_entorno(raiz, *, windows=None):
    windows = os.name == "nt" if windows is None else windows
    return raiz / ".venv" / ("Scripts/python.exe" if windows else "bin/python")


def crear_entorno(raiz):
    carpeta = raiz / ".venv"
    if not carpeta.exists():
        print("Creando .venv con Python 3.12…", flush=True)
        venv.EnvBuilder(with_pip=True).create(carpeta)
    python = python_del_entorno(raiz)
    if not (carpeta / "pyvenv.cfg").is_file() or not python.is_file():
        raise RuntimeError(".venv existe pero está incompleto. Renómbralo y vuelve a ejecutar este comando.")
    try:
        salida = subprocess.check_output(
            [
                str(python),
                "-c",
                "import json,sys; print(json.dumps({'version':list(sys.version_info[:2]),"
                "'prefix':sys.prefix,'base':sys.base_prefix}))",
            ],
            text=True,
            cwd=raiz,
        )
        info = json.loads(salida)
        valido = (
            info["version"] == [3, 12]
            and Path(info["prefix"]).resolve() == carpeta.resolve()
            and info["prefix"] != info["base"]
        )
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        raise RuntimeError("No se pudo verificar .venv. Renómbralo y vuelve a prepararlo con Python 3.12.") from error
    if not valido:
        raise RuntimeError(
            ".venv debe ser un entorno aislado de Python 3.12. No se instalaron paquetes en otro Python."
        )
    return python


def crear_configuracion_local(raiz):
    valores = {
        **VARIABLES_LOCALES,
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(48),
        "DEFAULT_FROM_EMAIL": "GESICOM <no-reply@gesicom.local>",
    }
    try:
        descriptor = os.open(raiz / ".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
        archivo.write("# Desarrollo local: SQLite y correo en consola. No publicar este archivo.\n")
        archivo.write("\n".join(f"{clave}={valor}" for clave, valor in valores.items()) + "\n")
    return True


def ejecutar(argumentos, raiz, *, entorno=None):
    subprocess.run([str(argumento) for argumento in argumentos], cwd=raiz, env=entorno, check=True)


def preparar(raiz, *, inicio_rapido=False):
    python = crear_entorno(raiz)
    privados = raiz / ".local"
    privados.mkdir(exist_ok=True, mode=0o700)
    print("Instalando dependencias de ejecución, pruebas, análisis y depuración…", flush=True)
    ejecutar(
        [
            python,
            "-m",
            "pip",
            "--require-virtualenv",
            "--cache-dir",
            privados / "cache" / "pip",
            "install",
            "--disable-pip-version-check",
            "-r",
            raiz / "requirements-dev.txt",
        ],
        raiz,
    )
    ejecutar([python, "-m", "pip", "--require-virtualenv", "--cache-dir", privados / "cache" / "pip", "check"], raiz)
    if inicio_rapido:
        if crear_configuracion_local(raiz):
            # Estas operaciones se limitan a SQLite local aunque el proceso
            # padre tenga variables de conexión de otro entorno.
            entorno = {**os.environ, **VARIABLES_LOCALES}
            for comando in [
                ["migrate", "--noinput", "--settings=SENNOVA.migration_settings"],
                ["collectstatic", "--noinput"],
                ["crear_usuarios_revision", "--archivo", ".local/desarrollo/credenciales_revision.json"],
                ["check"],
            ]:
                ejecutar([python, raiz / "manage.py", *comando], raiz, entorno=entorno)
            print("Inicio local listo. Cuentas creadas: .local/desarrollo/credenciales_revision.json")
        else:
            print("Se conserva .env. No se migró ni se cambió la base de datos configurada.")
    print(".venv preparado. En VS Code: Python: Select Interpreter → .venv, y después F5.")
    print("Para el PIN local, inicia también el perfil de correos en consola de VS Code.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inicio-rapido",
        action="store_true",
        help="Si no existe .env, prepara SQLite, estáticos y cuentas privadas de revisión para desarrollo local.",
    )
    args = parser.parse_args(argv)
    if sys.version_info[:2] != (3, 12):
        print(
            "Usa Python 3.12: Windows: py -3.12 scripts/configurar_entorno.py; Linux/macOS: python3.12.",
            file=sys.stderr,
        )
        return 2
    try:
        preparar(ROOT, inicio_rapido=args.inicio_rapido)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"No se pudo completar la preparación: {error}", file=sys.stderr)
        print("Revisa los requisitos de Python y del cliente MySQL en docs/VSCODE.md.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
