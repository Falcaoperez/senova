#!/usr/bin/env python3
"""Comprueba Django, aplica sus migraciones y recopila estáticos en ese orden."""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    for arguments in [["check"], ["migrate", "--noinput"], ["collectstatic", "--noinput"]]:
        subprocess.run([sys.executable, str(ROOT / "manage.py"), *arguments], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
