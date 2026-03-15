import os
import sys
from pathlib import Path


def main():
    # Ensure project root (where manage.py lives) is on sys.path so apps
    # (like Gesicom) can be imported reliably when running management commands.
    project_root = Path(__file__).resolve().parent
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SENNOVA.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)

if __name__ == "__main__":
    main()
