# Cuentas y conexiones de MySQL

El esquema de tablas continúa definido por las migraciones de Django. Esta carpeta define únicamente los perfiles de acceso. No contiene claves ni una segunda definición de tablas.

| Perfil | Variables privadas | Alcance |
| --- | --- | --- |
| Ejecución web y trabajador | `DB_USER`, `DB_PASSWORD` | `SELECT`, `INSERT`, `UPDATE`, `DELETE` en `DB_NAME` |
| Migraciones | `DB_MIGRATION_USER`, `DB_MIGRATION_PASSWORD` | Los cuatro anteriores y `CREATE`, `ALTER`, `INDEX`, `DROP`, `REFERENCES` en `DB_NAME` |
| Pruebas, opcional | `DB_TEST_USER`, `DB_TEST_PASSWORD` | Los mismos que migraciones, exclusivamente en `test_<DB_NAME>` |

Cada cuenta necesita un nombre y contraseña distintos. Ninguna recibe privilegios globales, roles, permisos para crear usuarios ni `GRANT OPTION`. Los nombres usan letras ASCII, números y guion bajo, sin comodines. Se escapan los guiones bajos de los esquemas cuando `partial_revokes` está desactivado: MySQL los interpretaría como coincidencias de cualquier carácter. El plan consulta esa configuración sin modificarla.

## Preparación y actualización

Respalda primero MySQL y los archivos. Conserva las claves existentes; `configurar_local.py` genera solamente las que faltan. Para un servicio Docker nuevo:

```bash
python scripts/configurar_local.py
docker compose up -d database redis
python scripts/preparar_mysql.py                   # Solo muestra el plan público.
python scripts/preparar_mysql.py --aplicar         # Producción, sin cuenta de pruebas.
docker compose up --build -d
docker compose exec app python manage.py comprobar_base_datos --estricto
```

En desarrollo añade el perfil de Mailpit al arranque de servicios y utiliza `--aplicar --con-pruebas`, como indica el README principal. Para un contenedor existente se admite `--contenedor nombre`; el operador accede como administrador mediante su socket local. No se abre una cuenta root de red ni se incluye su clave en la aplicación.

En una instalación existente, antes de reducir permisos, carga la configuración TLS en los procesos web y trabajador y verifica su conexión. Actualiza también los trabajos de mantenimiento para usar el perfil apropiado. El preparador comprueba que las cuentas sean exclusivas: rechaza privilegios globales, roles, proxy, otros hosts o concesiones fuera de los esquemas del proyecto antes de escribir. Puede retirar la concesión histórica de `test_<DB_NAME>` de la cuenta web. Guarda las concesiones anteriores en `.local/mysql/` con permisos privados. No elimina tablas ni usuarios; sustituye los privilegios de las cuentas dedicadas.

Los cambios de permisos de MySQL no son una transacción. Si una operación falla, revisa el servidor y vuelve a aplicar el plan completo antes de abrir tráfico. Las concesiones anteriores ayudan a la revisión, pero no constituyen una restauración automática de contraseñas ni de configuración del servidor.

Para un servidor administrado externo, el operador puede generar `python scripts/preparar_mysql.py --guardar-sql [--con-pruebas]` y ejecutar `.local/mysql/perfiles.sql` mediante una conexión administrativa de confianza. Ese archivo **contiene contraseñas** y debe permanecer privado y eliminarse al terminar. La ejecución manual no realiza la comprobación previa de dedicación: revisa las cuentas y concesiones antes de usarlo. Si el proveedor no permite preparar cuentas, pídele los tres perfiles equivalentes y adapta los nombres en el entorno.

## Migraciones y pruebas

```bash
# En un entorno Python con las variables privadas del operador:
python manage.py migrate --noinput --settings=SENNOVA.migration_settings
python manage.py test --settings=SENNOVA.test_settings --noinput

# Servicios con credenciales independientes:
docker compose run --rm migrate
docker compose --profile tools run --rm test
```

`migrate` es una tarea de una sola ejecución y debe terminar correctamente antes del servicio web. El arranque web ya no aplica migraciones. Los servicios web y trabajador solo reciben la cuenta de ejecución; el servicio `test` recibe la cuenta de pruebas y el de migraciones, su cuenta propia. No ejecutes `runserver` ni Gunicorn con `migration_settings` o `test_settings`. En desarrollo sin contenedores el operador conserva todas las claves en su `.env`; la separación de procesos no aísla ese archivo frente a otros procesos del mismo usuario del sistema.

El ejecutor de pruebas crea y elimina únicamente `test_<DB_NAME>`; no uses ese nombre para datos de una instalación. El prefijo también se aplica a la conexión inicial para que el perfil de pruebas nunca necesite acceso a `DB_NAME`.

## TLS y opciones del cliente

Todos los perfiles preparados exigen `REQUIRE SSL`. Django usa `DB_SSL_MODE=REQUIRED` por defecto y rechaza modos que permitan texto plano. El servidor de Compose deshabilita `local_infile` y exige transporte seguro; el socket local del operador sigue disponible. Un volumen existente conserva sus tablas y cuentas hasta que se aplique el preparador. Los cambios de opciones de arranque del servidor requieren recrear su contenedor conservando el volumen.

`REQUIRED` cifra el canal, pero no valida la identidad del servidor. Para una base remota configura `DB_SSL_MODE=VERIFY_IDENTITY` y `DB_SSL_CA` con una CA de confianza, además de un nombre DNS que figure en el certificado. Se rechazan IP y el socket de `localhost` en ese modo: el cliente MariaDB de la instalación comprobada acepta el certificado válido al conectarse por IP sin comprobar su nombre. Con DNS se verificó que rechaza un nombre ajeno al certificado. `VERIFY_CA` comprueba la CA, sin prometer validación de identidad; algunos clientes pueden imponer además la coincidencia de nombre.

Los modos `VERIFY_CA` y `VERIFY_IDENTITY` requieren una CA existente; una ruta ausente detiene el arranque. En Compose monta ese archivo de solo lectura en web, trabajador, migraciones y pruebas mediante un override privado. No incluyas claves privadas del servidor en la imagen.

El cliente deshabilita `LOCAL INFILE` y las sentencias encadenadas. Esto no reemplaza el uso de parámetros del ORM ni la validación de entradas. Los cuatro privilegios de ejecución todavía permiten modificar o eliminar registros; la autorización por propietario y rol se aplica en Django. Las copias privadas, el control de acceso al servidor y las restauraciones verificadas siguen siendo necesarios.

## Comprobación de solo lectura

```bash
python manage.py comprobar_base_datos --estricto
python manage.py comprobar_base_datos --json
```

Comprueba la conexión activa: CRUD en el esquema exacto, ausencia de concesiones desconocidas o roles, cifrado TLS, opciones del cliente, cargas locales, modo estricto, claves foráneas e InnoDB. No expone nombres de cuentas, servidores, concesiones SQL ni credenciales. `--estricto` termina con error si no puede comprobar todos los controles. Ejecútalo con la configuración de ejecución: una cuenta de migraciones o pruebas debe aparecer con permisos por revisar.

Administración → Permisos → **Revisar seguridad de la base de datos** ofrece el mismo informe a administradores y superusuarios, sin editar concesiones y sin consultas periódicas. Un resultado correcto describe esos controles de esa conexión; no certifica aislamiento de infraestructura, configuración completa del servidor ni capacidad frente a una carga determinada.
