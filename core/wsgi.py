"""
Configuración WSGI para el proyecto SENNOVA.

Este módulo expone la aplicación WSGI como la variable de módulo
`application`, que es la interfaz que utilizan servidores WSGI
(por ejemplo Gunicorn o uWSGI) para procesar solicitudes HTTP.

Incluye una referencia para despliegue y está escrita en español
para facilitar su explicación en una presentación.

Para más información: https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Establece el módulo de configuración de Django si no está definido
# en las variables de entorno (no sobrescribe si ya existe).
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SENNOVA.settings')

# Objeto WSGI que el servidor usará para atender las peticiones.
application = get_wsgi_application()
