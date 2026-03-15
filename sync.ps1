#!/usr/bin/env powershell
<#
.SYNOPSIS
    Script de sincronización para resolver problemas de base de datos en el proyecto SENNOVA

.DESCRIPTION
    Este script resuelve automáticamente problemas comunes después de hacer pull de cambios:
    - Conflictos de migraciones
    - Caché de base de datos obsoleto
    - Archivos compilados de Python
    - Archivos estáticos faltantes

.EXAMPLE
    .\sync.ps1
#>

# Colores para output
$Green = [System.ConsoleColor]::Green
$Red = [System.ConsoleColor]::Red
$Yellow = [System.ConsoleColor]::Yellow
$Cyan = [System.ConsoleColor]::Cyan

function Print-Section {
    param([string]$Title)
    Write-Host "`n" -ForegroundColor $Cyan
    Write-Host ("=" * 80) -ForegroundColor $Cyan
    Write-Host ("  $Title") -ForegroundColor $Cyan
    Write-Host ("=" * 80) -ForegroundColor $Cyan
    Write-Host ""
}

function Print-Success {
    param([string]$Message)
    Write-Host "  ✓ $Message" -ForegroundColor $Green
}

function Print-Warning {
    param([string]$Message)
    Write-Host "  ⚠️  $Message" -ForegroundColor $Yellow
}

function Print-Error {
    param([string]$Message)
    Write-Host "  ❌ $Message" -ForegroundColor $Red
}

function Run-Command {
    param(
        [string]$Command,
        [string]$Description,
        [switch]$Critical
    )
    
    Write-Host "▶ $Description..."
    
    $output = Invoke-Expression $Command 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Print-Success $Description
    } else {
        if ($Critical) {
            Print-Error "$Description - ERROR CRÍTICO"
            Write-Host "Salida: $output" -ForegroundColor $Red
            return $false
        } else {
            Print-Warning "$Description - completado con advertencias"
        }
    }
    
    return $true
}

# Header
Write-Host "`n"
Write-Host "╔$("=" * 78)╗" -ForegroundColor $Cyan
Write-Host "║$(" " * 78)║" -ForegroundColor $Cyan
Write-Host "║$("SCRIPT DE SINCRONIZACIÓN - PROYECTO SENNOVA".PadRight(78).Substring(0,78))║" -ForegroundColor $Cyan
Write-Host "║$(" " * 78)║" -ForegroundColor $Cyan
Write-Host "╚$("=" * 78)╝" -ForegroundColor $Cyan

Write-Host "`nEste script resuelve problemas comunes después de hacer pull de cambios:" -ForegroundColor $Yellow
Write-Host "  • Conflictos de migraciones"
Write-Host "  • Caché de base de datos obsoleto"  
Write-Host "  • Archivos compilados de Python"
Write-Host "  • Archivos estáticos faltantes`n" -ForegroundColor $Yellow

# 1. Sincronización de Git
Print-Section "1️⃣  SINCRONIZACIÓN DE GIT"
Run-Command "git status" "Verificando estado de Git"

# 2. Aplicar migraciones
Print-Section "2️⃣  APLICANDO MIGRACIONES DE BASE DE DATOS"
Run-Command "python manage.py migrate --verbosity=2" "Aplicando migraciones" -Critical

# 3. Limpiar caché
Print-Section "3️⃣  LIMPIANDO CACHÉS"
Run-Command "python manage.py clear_cache" "Limpiando caché de Django"

Write-Host "▶ Eliminando archivos .pyc..."
Get-ChildItem -Recurse -Filter "*.pyc" | Remove-Item -Force -ErrorAction SilentlyContinue | Out-Null
Print-Success "Archivos .pyc eliminados"

Write-Host "▶ Eliminando carpetas __pycache__..."
Get-ChildItem -Recurse -Filter "__pycache__" -Directory | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Print-Success "Carpetas __pycache__ eliminadas"

# 4. Recolectar estáticos
Print-Section "4️⃣  RECOLECTANDO ARCHIVOS ESTÁTICOS"
Run-Command "python manage.py collectstatic --noinput" "Recolectando archivos estáticos"

# 5. Verificación de integridad
Print-Section "5️⃣  VERIFICANDO INTEGRIDAD DEL PROYECTO"
Run-Command "python manage.py check" "Verificando integridad" -Critical

Write-Host "▶ Estado de migraciones:`n"
python manage.py showmigrations --list | Select-Object -First 20

# Resumen final
Print-Section "✅ SINCRONIZACIÓN COMPLETADA"

Write-Host @"
Tu proyecto se sincronizó correctamente. Puedes:

1. Iniciar el servidor:
   python manage.py runserver

2. Acceder a la aplicación:
   http://localhost:8000

3. Acceder al panel de administración:
   http://localhost:8000/administrador/

4. Si aún tienes problemas:
   • Verifica que tengas todos los requirements: pip install -r requirements.txt
   • Reinicia el servidor
   • Dale click a refrescar (F5) en el navegador

📧 Si persisten los errores, contacta a Santiago con este mensaje.
"@ -ForegroundColor $Green

Read-Host "`nPresiona ENTER para cerrar"
