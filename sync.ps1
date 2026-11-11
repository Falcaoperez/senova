$ErrorActionPreference = "Stop"
python sync_database.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
