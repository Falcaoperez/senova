#!/usr/bin/env python3
"""Prepara cuentas dedicadas sin mostrar contraseñas ni dar privilegios de DBA a Django."""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from database.seguridad.perfiles import generar_sql, literal, perfiles_desde_entorno, plan_publico


def entorno_local():
    datos = {}
    path = ROOT / ".env"
    if path.exists():
        for linea in path.read_text().splitlines():
            if linea and not linea.lstrip().startswith("#") and "=" in linea:
                clave, valor = linea.split("=", 1)
                valor = valor.strip()
                if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in {"'", '"'}:
                    valor = valor[1:-1]
                datos[clave.strip()] = valor
    return {**datos, **os.environ}


def ejecutar_sql(sql, contenedor=None):
    if contenedor:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", contenedor):
            raise ValueError("Selecciona un nombre de contenedor válido.")
        comando = ["docker", "exec", "-i", contenedor]
    else:
        comando = ["docker", "compose", "exec", "-T", "database"]
    comando += ["sh", "-c", 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot --batch --skip-column-names']
    resultado = subprocess.run(comando, input=sql, text=True, capture_output=True, cwd=ROOT, check=False)
    if resultado.returncode:
        raise RuntimeError(
            "MySQL rechazó la preparación. Revisa el servicio y su credencial administrativa; no se muestran consultas ni secretos."
        )
    return resultado.stdout


def comprobar_dedicacion(perfiles, contenedor):
    esquemas = {p.esquema for p in perfiles}
    # Permite retirar la concesión histórica de pruebas de la cuenta de ejecución.
    esquemas.add("test_" + perfiles[0].esquema)
    esquemas.update(s.replace("_", "\\_") for s in list(esquemas))
    permitidos = ", ".join(literal(v) for v in esquemas)
    anteriores = []
    for perfil in perfiles:
        usuario = literal(perfil.nombre)
        grantee = literal("'" + perfil.nombre + "'@'%'")
        consulta = f"""SET SESSION sql_mode='NO_BACKSLASH_ESCAPES';
SELECT JSON_OBJECT(
 'globales', (SELECT COUNT(*) FROM information_schema.USER_PRIVILEGES WHERE GRANTEE={grantee} AND (PRIVILEGE_TYPE<>'USAGE' OR IS_GRANTABLE='YES')),
 'roles', (SELECT COUNT(*) FROM mysql.role_edges WHERE TO_USER={usuario} AND TO_HOST='%'),
 'roles_obligatorios', IF(@@GLOBAL.mandatory_roles='', 0, 1),
 'proxy', (SELECT COUNT(*) FROM mysql.proxies_priv WHERE User={usuario} AND Host='%'),
 'otros_hosts', (SELECT COUNT(*) FROM mysql.user WHERE User={usuario} AND Host<>'%'),
 'otros_esquemas', (SELECT COUNT(*) FROM information_schema.SCHEMA_PRIVILEGES WHERE GRANTEE={grantee} AND TABLE_SCHEMA NOT IN ({permitidos})),
 'otras_tablas', (SELECT COUNT(*) FROM information_schema.TABLE_PRIVILEGES WHERE GRANTEE={grantee} AND TABLE_SCHEMA NOT IN ({permitidos})),
 'otras_columnas', (SELECT COUNT(*) FROM information_schema.COLUMN_PRIVILEGES WHERE GRANTEE={grantee} AND TABLE_SCHEMA NOT IN ({permitidos})),
 'existe', (SELECT COUNT(*) FROM mysql.user WHERE User={usuario} AND Host='%'));
"""
        filas = ejecutar_sql(consulta, contenedor).splitlines()
        resultado = json.loads(filas[-1])
        if any(resultado[k] for k in resultado if k != "existe"):
            raise ValueError(
                "Una cuenta tiene concesiones globales, roles o acceso fuera del proyecto. Configura cuentas dedicadas antes de aplicar el plan."
            )
        grants = ejecutar_sql(f"SHOW GRANTS FOR {usuario}@'%';", contenedor).splitlines() if resultado["existe"] else []
        anteriores.append({"cuenta": perfil.nombre, "concesiones": grants})
    return anteriores


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modos = parser.add_mutually_exclusive_group()
    modos.add_argument(
        "--aplicar",
        action="store_true",
        help="Comprueba dedicación y aplica el plan mediante el servicio MySQL de Docker.",
    )
    modos.add_argument(
        "--guardar-sql",
        action="store_true",
        help="Guarda el plan con secretos en .local/mysql/perfiles.sql (permiso 600).",
    )
    parser.add_argument(
        "--con-pruebas", action="store_true", help="Prepara también una cuenta limitada a test_<DB_NAME>."
    )
    parser.add_argument(
        "--contenedor", help="Contenedor local existente; por defecto usa el servicio database de Compose."
    )
    args = parser.parse_args()
    try:
        perfiles = perfiles_desde_entorno(entorno_local(), pruebas=args.con_pruebas)
        if args.aplicar or args.guardar_sql:
            carpeta = ROOT / ".local/mysql"
            carpeta.mkdir(mode=0o700, parents=True, exist_ok=True)
            carpeta.chmod(0o700)
            if args.guardar_sql:
                path = carpeta / "perfiles.sql"
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as salida:
                    salida.write(generar_sql(perfiles))
                path.chmod(0o600)
                print("Plan privado guardado en .local/mysql/perfiles.sql. Contiene credenciales; no lo publiques.")
            else:
                anteriores = comprobar_dedicacion(perfiles, args.contenedor)
                copia = carpeta / ("permisos-anteriores-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + ".json")
                fd = os.open(copia, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as salida:
                    json.dump(anteriores, salida, indent=2)
                ejecutar_sql(generar_sql(perfiles), args.contenedor)
                print("Perfiles aplicados. Las concesiones anteriores quedaron en .local/mysql/.")
        print(json.dumps(plan_publico(perfiles), ensure_ascii=False, indent=2))
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError):
        print(
            "No se pudo preparar MySQL. Verifica nombres, credenciales privadas y que las cuentas sean exclusivas del proyecto.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
