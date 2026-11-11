#!/usr/bin/env python3
"""Actualiza el esquema y los estáticos; se detiene si una operación falla."""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
for arguments in [['check'], ['migrate', '--noinput'], ['collectstatic', '--noinput']]:
    subprocess.run([sys.executable, str(root / 'manage.py'), *arguments], cwd=root, check=True)
