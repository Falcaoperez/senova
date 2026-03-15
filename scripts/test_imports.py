import importlib, sys
from pathlib import Path
import os

project_root = Path(__file__).resolve().parent.parent
project_root_str = str(project_root)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

print('CWD:', os.getcwd())
print('Inserted project root to sys.path:', project_root_str)
print('sys.path first entries:')
for p in sys.path[:6]:
    print('  ', p)

for name in ('Gesicom', 'instructor', 'cuentas'):
    try:
        importlib.import_module(name)
        print(f'Imported {name} OK')
    except Exception as e:
        print(f'Error importing {name}:', type(e).__name__, e)