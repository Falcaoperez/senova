#!/usr/bin/env python3
"""Carga HTTP local con cuentas temporales; limpia únicamente sus propios registros."""

import argparse
import concurrent.futures
import json
import os
import secrets
import statistics
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SENNOVA.settings")
import django

django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.sessions.backends.cached_db import SessionStore
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.db import close_old_connections
from django.test import Client

from Gesicom.models import Envio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usuarios", type=int, default=1200)
    parser.add_argument("--peticiones", type=int, default=2400)
    parser.add_argument("--concurrencia", type=int, default=40)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--salida", default=".local/rendimiento_http.json")
    options = parser.parse_args()
    if urlsplit(options.url).hostname not in ["127.0.0.1", "localhost", "::1"]:
        parser.error("La prueba se ejecuta únicamente contra un servidor local.")
    if (
        not 1 <= options.usuarios <= 5000
        or not 1 <= options.concurrencia <= 100
        or not 1 <= options.peticiones <= 10000
    ):
        parser.error("Usa hasta 5000 usuarios, 100 clientes concurrentes y 10000 peticiones.")
    User = get_user_model()
    prefix = "carga_http_" + secrets.token_hex(5) + "_"
    keys = []
    cookies = []
    try:
        User.objects.bulk_create(
            [
                User(username=f"{prefix}{i}", email=f"{prefix}{i}@example.invalid", password="!", first_name="Carga")
                for i in range(options.usuarios)
            ],
            batch_size=400,
        )
        users = list(User.objects.filter(username__startswith=prefix))
        group = Group.objects.get(name="usuario")
        User.groups.through.objects.bulk_create(
            [User.groups.through(user_id=user.pk, group_id=group.pk) for user in users], batch_size=400
        )
        Envio.objects.bulk_create(
            [
                Envio(usuario=user, nombre=f"Reporte temporal {j}", proyecto="LEM", tipo_evidencia="Informe Final")
                for user in users
                for j in range(10)
            ],
            batch_size=500,
        )
        for user in users:
            client = Client()
            client.force_login(user)
            key = client.cookies[settings.SESSION_COOKIE_NAME].value
            keys.append(key)
            cookies.append(f"{settings.SESSION_COOKIE_NAME}={key}")
        close_old_connections()
        print(
            f"Preparados {len(users)} usuarios y {len(users) * 10} evidencias temporales. Ejecutando carga HTTP…",
            flush=True,
        )

        def request(index):
            start = time.perf_counter()
            route = "/usuario/" if index % 2 == 0 else "/evidencias/"
            req = urllib.request.Request(
                options.url.rstrip("/") + route, headers={"Cookie": cookies[index % len(cookies)]}
            )
            try:
                with urllib.request.urlopen(req, timeout=20) as response:
                    body = response.read()
                    valid = response.status == 200 and (
                        b"Tu trabajo" in body if route == "/usuario/" else b"Lista de evidencias" in body
                    )
                return (time.perf_counter() - start) * 1000, valid
            except Exception:
                return (time.perf_counter() - start) * 1000, False

        started = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=options.concurrencia) as executor:
            results = list(executor.map(request, range(options.peticiones)))
        total = time.perf_counter() - started
        durations = sorted(result[0] for result in results)
        report = {
            "usuarios": options.usuarios,
            "evidencias": options.usuarios * 10,
            "peticiones": options.peticiones,
            "concurrencia": options.concurrencia,
            "errores": sum(not row[1] for row in results),
            "duracion_s": round(total, 2),
            "mediana_ms": round(statistics.median(durations), 2),
            "p95_ms": round(durations[min(len(durations) - 1, int(len(durations) * 0.95))], 2),
            "peticiones_por_segundo": round(len(results) / total, 2),
            "alcance": "HTTP local, lecturas autenticadas; no simula 1200 inicios de sesión simultáneos.",
        }
        path = Path(options.salida)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if report["errores"]:
            return 1
        return 0
    finally:
        close_old_connections()
        User.objects.filter(username__startswith=prefix).delete()
        Session.objects.filter(session_key__in=keys).delete()
        cache.delete_many([SessionStore(session_key=key).cache_key for key in keys])
        print("Datos temporales de carga eliminados.", flush=True)


if __name__ == "__main__":
    sys.exit(main())
