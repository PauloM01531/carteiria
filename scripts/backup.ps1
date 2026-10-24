<#
  Backup do banco da CarteirIA (desenvolvimento local, Windows).
  Uso:  powershell -ExecutionPolicy Bypass -File scripts\backup.ps1 [-Keep 14]
  - Roda pg_dump DENTRO do contêiner como superusuário (necessário: RLS forçado esconde linhas do dono).
  - Salva em backups\ (fora do Git) e mantém só os N arquivos mais recentes.
#>
param([int]$Keep = 14, [string]$Database = "carteiria")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
New-Item -ItemType Directory -Force backups | Out-Null
$file = Join-Path $root ("backups\{0}-{1}.dump" -f $Database, (Get-Date -Format "yyyyMMdd-HHmmss"))

# Saída binária: usamos cmd para não corromper o arquivo com a codificação do PowerShell.
cmd /c "docker compose exec -T db pg_dump -U postgres -d $Database -Fc > `"$file`""
if ($LASTEXITCODE -ne 0 -or (Get-Item $file).Length -lt 1024) { throw "Falha no backup." }

# Verificação: o arquivo precisa ser legível pelo pg_restore.
cmd /c "docker compose exec -T db pg_restore --list < `"$file`" > NUL"
if ($LASTEXITCODE -ne 0) { throw "Backup gerado, mas ilegível." }

Get-ChildItem backups -Filter "$Database-*.dump" | Sort-Object LastWriteTime -Descending | Select-Object -Skip $Keep | Remove-Item
Write-Output "Backup salvo: $file ($([math]::Round((Get-Item $file).Length / 1KB)) KB)"
