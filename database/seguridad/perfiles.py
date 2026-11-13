"""Plan SQL de cuentas dedicadas; no define tablas ni contiene credenciales fijas."""

import re
from dataclasses import dataclass, field

CRUD = ("SELECT", "INSERT", "UPDATE", "DELETE")
DDL = (*CRUD, "CREATE", "ALTER", "INDEX", "DROP", "REFERENCES")
RESERVADAS = {"mysql", "sys", "information_schema", "performance_schema"}


def identificador(valor, *, cuenta=False):
    limite = 32 if cuenta else 64
    if not isinstance(valor, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0," + str(limite - 1) + r"}", valor):
        raise ValueError("Utiliza nombres ASCII de cuentas y bases, con letras, números y guion bajo.")
    if valor.casefold() in RESERVADAS or cuenta and valor.casefold() == "root":
        raise ValueError("No se pueden preparar cuentas o esquemas del sistema.")
    return valor


def literal(valor):
    # El plan fija NO_BACKSLASH_ESCAPES antes de usar literales.
    if not isinstance(valor, str) or not valor or len(valor) > 256 or any(ord(c) < 32 or ord(c) == 127 for c in valor):
        raise ValueError("Las contraseñas deben ser privadas, no vacías y de una sola línea.")
    if valor.startswith("replace-"):
        raise ValueError("Genera credenciales privadas antes de preparar las cuentas de MySQL.")
    return "'" + valor.replace("'", "''") + "'"


@dataclass(frozen=True)
class Perfil:
    nombre: str
    esquema: str
    permisos: tuple[str, ...]
    password: str = field(repr=False)


def perfiles_desde_entorno(entorno, *, pruebas=False):
    esquema = identificador(entorno.get("DB_NAME", "senova"))
    test = identificador("test_" + esquema) if pruebas else None
    perfiles = [
        Perfil(
            identificador(entorno.get("DB_USER", "gesicom_app"), cuenta=True),
            esquema,
            CRUD,
            entorno.get("DB_PASSWORD", ""),
        ),
        Perfil(
            identificador(entorno.get("DB_MIGRATION_USER", "gesicom_migraciones"), cuenta=True),
            esquema,
            DDL,
            entorno.get("DB_MIGRATION_PASSWORD", ""),
        ),
    ]
    if pruebas:
        perfiles.append(
            Perfil(
                identificador(entorno.get("DB_TEST_USER", "gesicom_pruebas"), cuenta=True),
                test,
                DDL,
                entorno.get("DB_TEST_PASSWORD", ""),
            )
        )
    if len({p.nombre.casefold() for p in perfiles}) != len(perfiles):
        raise ValueError("Ejecución, migraciones y pruebas requieren cuentas distintas.")
    for perfil in perfiles:
        literal(perfil.password)
    if len({p.password for p in perfiles}) != len(perfiles):
        raise ValueError("Cada cuenta de MySQL necesita una contraseña diferente.")
    return perfiles


def plan_publico(perfiles):
    return [
        {"cuenta": p.nombre, "esquema": p.esquema, "permisos": list(p.permisos), "requiere_tls": True} for p in perfiles
    ]


def generar_sql(perfiles):
    lineas = ["SET SESSION sql_mode='NO_BACKSLASH_ESCAPES';"]
    for esquema in sorted({p.esquema for p in perfiles}):
        lineas.append(
            f"CREATE DATABASE IF NOT EXISTS `{identificador(esquema)}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"
        )
    for p in perfiles:
        if not p.permisos or not set(p.permisos).issubset(DDL):
            raise ValueError("El plan contiene privilegios ajenos al catálogo permitido.")
        cuenta = literal(identificador(p.nombre, cuenta=True)) + "@'%'"
        esquema = identificador(p.esquema)
        escapado = esquema.replace("_", "\\_")
        lineas.extend(
            [
                f"CREATE USER IF NOT EXISTS {cuenta} IDENTIFIED BY {literal(p.password)} REQUIRE SSL;",
                f"ALTER USER {cuenta} IDENTIFIED BY {literal(p.password)} REQUIRE SSL;",
                f"REVOKE ALL PRIVILEGES, GRANT OPTION FROM {cuenta};",
                # MySQL interpreta '_' como comodín si partial_revokes está desactivado.
                f"SET @gesicom_scope = IF(@@GLOBAL.partial_revokes, {literal('`' + esquema + '`.*')}, {literal('`' + escapado + '`.*')});",
                f"SET @gesicom_grant = CONCAT({literal('GRANT ' + ', '.join(p.permisos) + ' ON ')}, @gesicom_scope, {literal(' TO ' + cuenta)});",
                "PREPARE gesicom_acl FROM @gesicom_grant;",
                "EXECUTE gesicom_acl;",
                "DEALLOCATE PREPARE gesicom_acl;",
            ]
        )
    return "\n".join([*lineas, "SET @gesicom_scope = NULL, @gesicom_grant = NULL;"]) + "\n"
