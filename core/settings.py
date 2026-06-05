"""
Configuración de Django para el proyecto SENNOVA.

Este archivo contiene las principales opciones usadas por Django
para ejecutar la aplicación (rutas, base de datos, correo, etc.).
Los comentarios están en español y están pensados para que puedas
explicar cada bloque durante una presentación.
"""

from pathlib import Path
import os

# `Path` facilita construir rutas de forma segura y portable.
# `os` se usa para leer variables de entorno (configuración fuera del código).

# Directorio base del proyecto (dos niveles arriba de este archivo).
# Se utiliza para construir rutas a la base de datos, media, static, etc.
BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------
# Seguridad
# ---------------------------------------------------------
# Clave secreta para firmar sesiones y otros datos sensibles.
# En producción debe provenir de una variable de entorno y mantenerse privada.
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-xjv@=pz08182&5z4y-5o*&!xl&na@yg#str+@u6--2&p_=&8s*')

# Activa o desactiva el modo DEBUG. En producción siempre debe ser False.
DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'

# Hosts permitidos para responder peticiones. Se puede configurar
# con la variable de entorno `DJANGO_ALLOWED_HOSTS` usando comas.
_hosts = os.environ.get('DJANGO_ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [h.strip() for h in _hosts.split(',') if h.strip()] if _hosts else []


# ---------------------------------------------------------
# Aplicaciones y middleware
# ---------------------------------------------------------
# Lista de aplicaciones instaladas: apps de Django y apps del proyecto.
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'Gesicom.apps.GesicomConfig',
    'instructor.apps.UsuariosConfig',
    'cuentas.apps.CuentasConfig',
    'ADMIN.apps.AdminPersonalizadoConfig',
    'SENNOVA',
]

# Middleware: capas que procesan la petición/respuesta.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Módulo raíz de URLs del proyecto.
ROOT_URLCONF = 'SENNOVA.urls'

# Configuración de plantillas: dónde buscar templates y qué context processors usar.
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],  # Directorios adicionales de plantillas (vacío por defecto).
        'APP_DIRS': True,  # Buscar templates dentro de cada app en `templates/`.
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Punto de entrada WSGI para despliegue tradicional.
WSGI_APPLICATION = 'SENNOVA.wsgi.application'


# ---------------------------------------------------------
# Base de datos
# ---------------------------------------------------------
# Por defecto usa SQLite para desarrollo. En producción cambie a PostgreSQL u otro.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# ---------------------------------------------------------
# Validación de contraseñas
# ---------------------------------------------------------
# Conjunto de validadores que Django aplicará a las contraseñas de usuarios.
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
    {
        'NAME': 'Gesicom.validators.ValidadorContraseñaOchoCarActualMayusNumEspecial',
    },
]


# ---------------------------------------------------------
# Internacionalización y zona horaria
# ---------------------------------------------------------
# Idioma por defecto del proyecto. Cambiar a 'es-co' o similar si lo desea.
LANGUAGE_CODE = 'es'  # idioma principal cambiado a español

# Zona horaria del proyecto. Ajustar según ubicación del servidor/usuarios.
TIME_ZONE = 'UTC'

USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------
# Archivos estáticos y media
# ---------------------------------------------------------
# URL donde se sirven los archivos estáticos (CSS, JS, imágenes públicas).
STATIC_URL = 'static/'

# Archivos subidos por usuarios (media). `MEDIA_URL` es la ruta pública y
# `MEDIA_ROOT` es la carpeta en disco donde se guardan los archivos.
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ---------------------------------------------------------
# Configuración de correo
# ---------------------------------------------------------
# Si se define `EMAIL_HOST_USER` en el entorno, se configura SMTP automáticamente
# tratando de inferir los datos del proveedor (Gmail, Outlook, Yahoo, etc.).
# Si no hay configuración, Django enviará correos a la consola (útil en desarrollo).
if os.environ.get('EMAIL_HOST_USER'):
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    _user = os.environ.get('EMAIL_HOST_USER')
    _domain = (_user.split('@')[-1] if '@' in _user else '').lower()
    _providers = {
        'gmail.com': {'host': 'smtp.gmail.com', 'port': 587, 'tls': True},
        'outlook.com': {'host': 'smtp.office365.com', 'port': 587, 'tls': True},
        'hotmail.com': {'host': 'smtp.office365.com', 'port': 587, 'tls': True},
        'live.com': {'host': 'smtp.office365.com', 'port': 587, 'tls': True},
        'yahoo.com': {'host': 'smtp.mail.yahoo.com', 'port': 587, 'tls': True},
        'yahoo.es': {'host': 'smtp.mail.yahoo.com', 'port': 587, 'tls': True},
        'icloud.com': {'host': 'smtp.mail.me.com', 'port': 587, 'tls': True},
        'zoho.com': {'host': 'smtp.zoho.com', 'port': 587, 'tls': True},
        'proton.me': {'host': 'smtp.protonmail.ch', 'port': 587, 'tls': True},
        'protonmail.com': {'host': 'smtp.protonmail.ch', 'port': 587, 'tls': True},
    }
    _env_host = os.environ.get('EMAIL_HOST')
    _env_port = os.environ.get('EMAIL_PORT')
    _env_tls = os.environ.get('EMAIL_USE_TLS')
    _env_ssl = os.environ.get('EMAIL_USE_SSL')
    _cfg = _providers.get(_domain)
    _host = _env_host or (_cfg['host'] if _cfg else 'smtp.gmail.com')
    _port = int(_env_port or (_cfg['port'] if _cfg else 587))
    _tls = (_env_tls == 'True') if _env_tls is not None else ((_cfg['tls'] if _cfg else True))
    _ssl = (_env_ssl == 'True') if _env_ssl is not None else False
    if _ssl:
        _tls = False
    EMAIL_HOST = _host
    EMAIL_PORT = _port
    EMAIL_USE_TLS = _tls
    EMAIL_USE_SSL = _ssl
    EMAIL_HOST_USER = _user
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
else:
    # Backend por consola útil para desarrollo (imprime correos en stdout).
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'no-reply@gesicom.local')


# ---------------------------------------------------------
# Redirecciones de autenticación
# ---------------------------------------------------------
# URLs a las que se redirige tras iniciar o cerrar sesión.
LOGIN_REDIRECT_URL = '/home/'
LOGOUT_REDIRECT_URL = '/login/'
# ---------------------------------------------------------
# Otros
# ---------------------------------------------------------
# Tipo de campo por defecto para claves primarias en los modelos.
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
