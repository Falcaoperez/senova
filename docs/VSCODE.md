# Ejecutar GESICOM en Visual Studio Code

Usa Python **3.15 de 64 bits**, o una versión compatible entre 3.12 y 3.14, y abre en VS Code la carpeta que contiene `manage.py`, `requirements.txt` y `SENNOVA/`. Django 6.1 admite Python 3.15. Instala las extensiones recomendadas por el proyecto: Python, Pylance, Python Debugger, Ruff y Django.

## Primera instalación

En la terminal de VS Code ejecuta el comando de tu sistema.

Windows:

```powershell
py -3.15 scripts/configurar_entorno.py --inicio-rapido
```

Linux o macOS:

```bash
python3.15 scripts/configurar_entorno.py --inicio-rapido
```

El comando crea `.venv` e instala `requirements-dev.txt`, que incluye todas las dependencias de ejecución de `requirements.txt`, las herramientas de comprobación y `debugpy`. Comprueba que no haya dependencias incompatibles. Puede repetirse: reutiliza un entorno válido y conserva la configuración privada existente.

En Debian/Ubuntu instala antes las bibliotecas necesarias para compilar `mysqlclient`:

```bash
sudo apt-get update
sudo apt-get install build-essential default-libmysqlclient-dev pkg-config
```

En macOS con Homebrew:

```bash
brew install python@3.15 mysql-client pkg-config
export PKG_CONFIG_PATH="$(brew --prefix mysql-client)/lib/pkgconfig"
python3.15 scripts/configurar_entorno.py --inicio-rapido
```

En Linux, instala además `venv` y las cabeceras de tu versión de Python si tu distribución los separa en paquetes, por ejemplo `python3.15-venv` y `python3.15-dev` cuando estén disponibles en sus repositorios. En Windows usa Python de 64 bits para instalar las ruedas disponibles de `mysqlclient`, Pillow, cryptography y debugpy. Gunicorn se instala en sistemas distintos de Windows; la depuración utiliza el servidor de desarrollo de Django.

El instalador utiliza el Python con el que lo ejecutas. Para otra versión compatible ajusta el comando, por ejemplo `py -3.14`. Si ya existe `.venv` con otro Python, renombra esa carpeta antes de ejecutar el instalador con 3.15; los archivos del proyecto y `.env` se conservan. No se sustituye silenciosamente el intérprete elegido por otro.

## Configuración y cuentas locales

Si todavía no existe `.env`, `--inicio-rapido` genera una clave privada aleatoria y prepara desarrollo con SQLite, caché local y correo en consola. Aplica las migraciones locales, recopila estáticos y crea seis cuentas de revisión con contraseñas aleatorias. Sus credenciales se guardan en:

```text
.local/desarrollo/credenciales_revision.json
```

Abre ese archivo en tu equipo para consultar cada usuario y contraseña. `.env`, las credenciales, la base local y `.venv` permanecen fuera de Git y del ZIP del código. Cada equipo genera su propio entorno virtual porque los ejecutables dependen de Python y del sistema operativo.

Si `.env` ya existe, se conserva exactamente. El instalador no migra ni crea cuentas en la base configurada. Si utiliza MySQL y Redis, inicia esos servicios antes de ejecutar la aplicación. El procedimiento de MySQL, cuentas dedicadas y Mailpit está en el [inicio local del proyecto](../README.md#inicio-local-con-docker). Para preparar solo las dependencias ejecuta el instalador sin `--inicio-rapido`.

MySQL sigue siendo el destino principal de despliegue y de las pruebas de permisos y concurrencia. El inicio con SQLite permite desarrollar y revisar la interfaz sin servicios adicionales.

## Seleccionar el intérprete y ejecutar

1. Abre `Ctrl+Shift+P` y selecciona **Python: Select Interpreter**.
2. Elige `.venv\Scripts\python.exe` en Windows o `.venv/bin/python` en Linux/macOS. Si VS Code recuerda otro intérprete, cámbialo aquí.
3. En **Ejecutar y depurar**, selecciona **GESICOM: aplicación y correos locales** y pulsa **F5**.
4. Abre http://127.0.0.1:8000/ y usa las cuentas creadas en la instalación nueva o las que ya tenía tu base.

El perfil conjunto inicia Django y el trabajador. Los PIN y las confirmaciones aparecen en la terminal del trabajador; ese perfil utiliza correo en consola y no entrega mensajes a Internet. El botón de detener finaliza ambos procesos. También puedes iniciar solo **GESICOM: Django** o solo **GESICOM: correos en consola local**.

Para ejecutar comandos manuales no es obligatorio activar PowerShell. En Windows:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

En Linux/macOS:

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

## Tareas disponibles

**Terminal → Ejecutar tarea** ofrece preparación de `.venv`, comprobación de Django, migraciones con la cuenta dedicada, recopilación de estáticos, pruebas de Django y Ruff. Las tareas usan el intérprete seleccionado; las pruebas utilizan `SENNOVA.test_settings` y una base independiente. Con MySQL necesitan las credenciales exclusivas descritas en [database/README.md](../database/README.md).

La extensión Django reconoce las plantillas como `django-html`; Ruff utiliza la versión de `.venv`. Solo se comparten cuatro archivos de `.vscode/`; los demás archivos personales del editor permanecen excluidos.

## Resolver errores

| Mensaje o síntoma | Comprobación |
| --- | --- |
| `No module named django`, `redis`, `PIL` o `cryptography` | Ejecuta el instalador, selecciona `.venv` y abre una terminal nueva. |
| `Import ... could not be resolved` en Pylance | Selecciona `.venv`; ejecuta **Developer: Reload Window** si conserva el intérprete anterior. |
| `Can not find valid pkg-config name` o fallo al compilar `mysqlclient` | Instala las bibliotecas indicadas para Linux/macOS y repite el instalador. |
| Falta `clang` al compilar, pero `cc` está instalado | En Linux/macOS ejecuta `CC=cc python3.15 scripts/configurar_entorno.py --inicio-rapido`. |
| PowerShell bloquea `Activate.ps1` | Usa `.\.venv\Scripts\python.exe` directamente; no hace falta cambiar la política de ejecución. |
| `.venv` está incompleto o usa otra versión | Renombra esa carpeta y ejecuta el instalador con tu Python 3.15, o el compatible que hayas elegido. |
| Conexión rechazada a MySQL o Redis | Revisa los servicios y tu `.env` existente; el instalador conserva sus credenciales. |
| Puerto 8000 ocupado | Detén la otra instancia o cambia el puerto de `runserver` en el perfil de depuración. |
| No aparece el PIN | Inicia el trabajador y consulta su terminal; la web solo encola los mensajes. |

El diagnóstico básico es ejecutar el Python de `.venv` con `-m pip check` y `manage.py check`. Comparte únicamente el mensaje necesario del error, sin contraseñas ni el contenido de `.env`.
