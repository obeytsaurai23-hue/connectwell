# PowerShell script to backup Postgres using pg_dump
param(
  [string]$OutDir = "C:\backups",
  [int]$Keep = 7
)

if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }

$env:PGHOST = $env:PGHOST -or ($env:DATABASE_URL -match "@([^:/]+)") | Out-Null
$timestamp = (Get-Date).ToString('yyyyMMddTHHmmssZ')
$db = $env:PGDATABASE
if (-not $db) { Write-Error "PGDATABASE or DATABASE_URL must be set"; exit 2 }

$fname = "$OutDir\${db}_$timestamp.sql.gz"
Write-Host "Creating backup $fname"
& pg_dump --host $env:PGHOST --port ${env:PGPORT:-5432} --username $env:PGUSER $db | gzip > $fname
Write-Host "Backup completed"
# rotation (keep latest N)
Get-ChildItem -Path $OutDir -Filter "*.sql.gz" | Sort-Object LastWriteTime -Descending | Select-Object -Skip $Keep | Remove-Item -Force
Write-Host "Rotated backups, kept $Keep latest files"
