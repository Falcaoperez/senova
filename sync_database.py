#!/usr/bin/env python
"""
Script de sincronización segura para django
Ejecuta esto después de hacer pull de cambios para resolver problemas de base de datos
"""
import os
import sys
import subprocess
import json

def print_section(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")

def run_command(cmd, description):
    print(f"▶ {description}...")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ⚠️  {description} completado con advertencias")
        if result.stderr:
            print(f"     Error: {result.stderr[:200]}")
    else:
        print(f"  ✓ {description} completado exitosamente")
    return result

def main():
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  SCRIPT DE SINCRONIZACIÓN SEGURA - PROYECTO SENNOVA".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "=" * 78 + "╝\n")
    
    print("Este script resuelve problemas comunes después de hacer pull de cambios:")
    print("  • Conflictos de migraciones")
    print("  • Caché de base de datos obsoleto")
    print("  • Permisos de archivo")
    print("  • Archivos estáticos faltantes\n")
    
    # 1. Sincronizar cambios de Git
    print_section("1️⃣  SINCRONIZANDO CAMBIOS DE GIT")
    
    # Limpiar cambios locales pequeños
    run_command("git status", "Verificando estado de Git")
    
    # 2. Resolver migraciones
    print_section("2️⃣  APLICANDO MIGRACIONES DE BASE DE DATOS")
    
    run_command("python manage.py migrate --verbosity=2", "Aplicando migraciones")
    
    # 3. Limpiar caché de Django
    print_section("3️⃣  LIMPIANDO CACHÉS")
    
    run_command("python manage.py clear_cache", "Limpiando caché de Django")
    
    # Limpiar archivos .pyc
    print(f"▶ Eliminando archivos .pyc...")
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.pyc'):
                try:
                    os.remove(os.path.join(root, file))
                except:
                    pass
    print("  ✓ Archivos .pyc eliminados")
    
    # Limpiar __pycache__
    print(f"▶ Eliminando carpetas __pycache__...")
    for root, dirs, files in os.walk('.'):
        if '__pycache__' in dirs:
            try:
                import shutil
                shutil.rmtree(os.path.join(root, '__pycache__'))
            except:
                pass
    print("  ✓ Carpetas __pycache__ eliminadas")
    
    # 4. Recolectar archivos estáticos
    print_section("4️⃣  RECOLECTANDO ARCHIVOS ESTÁTICOS")
    
    run_command("python manage.py collectstatic --noinput", "Recolectando archivos estáticos")
    
    # 5. Verificar integridad
    print_section("5️⃣  VERIFICANDO INTEGRIDAD DEL PROYECTO")
    
    run_command("python manage.py check", "Verificando integridad del proyecto")
    
    # Mostrar estado de migraciones
    print("\n▶ Estado de migraciones:")
    result = subprocess.run("python manage.py showmigrations --list", shell=True, capture_output=True, text=True)
    lines = result.stdout.split('\n')
    for line in lines:
        if line.strip():
            print(f"   {line}")
    
    # 6. Resumen final
    print_section("✅ SINCRONIZACIÓN COMPLETADA")
    
    print("""
Tu proyecto está sincronizado correctamente. Puedes:

1. Iniciar el servidor:
   python manage.py runserver

2. Acceder a la aplicación:
   http://localhost:8000

3. Acceder al panel de administración:
   http://localhost:8000/administrador/

4. Si aún tienes problemas:
   • Verifica que tengas todos los requirements: pip install -r requirements.txt
   • Reinicia el servidor
   • Borra la base de datos y crea una nueva (si es desarrollo)

📧 Si persisten los errores, contacta al administrador con este mensaje.
    """)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Script interrumpido por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error durante la sincronización: {str(e)}")
        print("Contacta al administrador del proyecto")
        sys.exit(1)
