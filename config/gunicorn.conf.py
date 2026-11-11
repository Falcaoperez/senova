"""Servidor WSGI con concurrencia acotada y reciclaje de trabajadores."""

import os

bind = "0.0.0.0:8000"
workers = int(os.environ.get("WEB_WORKERS", "4"))
threads = int(os.environ.get("WEB_THREADS", "2"))
worker_class = "gthread"
timeout = 45
graceful_timeout = 30
keepalive = 3
max_requests = 1500
max_requests_jitter = 150
accesslog = "-"
errorlog = "-"
loglevel = "info"
# Los encabezados de proxy solo se confían cuando se configura explícitamente.
forwarded_allow_ips = os.environ.get("TRUSTED_PROXY_IPS", "127.0.0.1")
# La administración del proceso se realiza con Docker o el supervisor del servicio.
control_socket_disable = True
