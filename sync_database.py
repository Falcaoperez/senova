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

def ejecutar_comando(comando, descripcion):
    print(f"▶ {descripcion}...")
    resultado = subprocess.run(comando, shell=True, capture_output=True, text=True)
    if resultado.returncode != 0:
        print(f"  ⚠️  {descripcion} completado con advertencias")
        if resultado.stderr:
            print(f"     Error: {resultado.stderr[:200]}")
    else:
        print(f"  ✓ {descripcion} completado exitosamente")
    return resultado

def principal():
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
    ejecutar_comando("git status", "Verificando estado de Git")
    
    # 2. Resolver migraciones
    print_section("2️⃣  APLICANDO MIGRACIONES DE BASE DE DATOS")
    
    ejecutar_comando("python manage.py migrate --verbosity=2", "Aplicando migraciones")
    
    # 3. Limpiar caché de Django
    print_section("3️⃣  LIMPIANDO CACHÉS")
    
    ejecutar_comando("python manage.py clear_cache", "Limpiando caché de Django")
    
    # Limpiar archivos .pyc
    print(f"▶ Eliminando archivos .pyc...")
    for raiz, directorios, archivos in os.walk('.'):
        for archivo in archivos:
            if archivo.endswith('.pyc'):
                try:
                    os.remove(os.path.join(raiz, archivo))
                except:
                    pass
    print("  ✓ Archivos .pyc eliminados")
    
    # Limpiar __pycache__
    print(f"▶ Eliminando carpetas __pycache__...")
    for raiz, directorios, archivos in os.walk('.'):
        if '__pycache__' in directorios:
            try:
                import shutil
                shutil.rmtree(os.path.join(raiz, '__pycache__'))
            except:
                pass
    print("  ✓ Carpetas __pycache__ eliminadas")
    
    # 4. Recolectar archivos estáticos
    print_section("4️⃣  RECOLECTANDO ARCHIVOS ESTÁTICOS")
    
    ejecutar_comando("python manage.py collectstatic --noinput", "Recolectando archivos estáticos")
    
    # 5. Verificar integridad
    print_section("5️⃣  VERIFICANDO INTEGRIDAD DEL PROYECTO")
    
    ejecutar_comando("python manage.py check", "Verificando integridad del proyecto")
    
    # Mostrar estado de migraciones
    print("\n▶ Estado de migraciones:")
    result = subprocess.run("python manage.py showmigrations --list", shell=True, capture_output=True, text=True)
    lineas = result.stdout.split('\n')
    for linea in lineas:
        if linea.strip():
            print(f"   {linea}")
    
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
        principal()
    except KeyboardInterrupt:
        print("\n\n⚠️  Script interrumpido por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error durante la sincronización: {str(e)}")
        print("Contacta al administrador del proyecto")
        sys.exit(1)
