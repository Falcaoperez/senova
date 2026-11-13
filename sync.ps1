$ErrorActionPreference = "Stop"
python "$PSScriptRoot/scripts/actualizar_instalacion.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
