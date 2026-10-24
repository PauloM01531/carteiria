<#
  Restaura um backup em um banco NOVO (nunca sobrescreve o principal).
  Uso:  powershell -ExecutionPolicy Bypass -File scripts\restore.ps1 -File backups\carteiria-AAAAMMDD-HHMMSS.dump [-Target carteiria_restaurado]
  Depois de conferir, troque DB_NAME no .env (com a API parada) ou renomeie os bancos.
#>
param([Parameter(Mandatory = $true)][string]$File, [string]$Target = "carteiria_restaurado")
$ErrorActionPreference = "Stop"
if ($Target -notmatch '^[a-z_][a-z0-9_]*$') { throw "Nome de banco inválido." }
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$full = Resolve-Path $File

$owner = (Select-String -Path .env -Pattern '^DB_OWNER_USER=(.+)$').Matches[0].Groups[1].Value
$app = (Select-String -Path .env -Pattern '^DB_APP_USER=(.+)$').Matches[0].Groups[1].Value

docker compose exec -T db psql -U postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $Target" | Out-Null
docker compose exec -T db psql -U postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $Target OWNER $owner" | Out-Null
docker compose exec -T db psql -U postgres -v ON_ERROR_STOP=1 -c "REVOKE ALL ON DATABASE $Target FROM PUBLIC; GRANT CONNECT ON DATABASE $Target TO $app" | Out-Null
cmd /c "docker compose exec -T db pg_restore -U postgres -d $Target --exit-on-error < `"$full`""
if ($LASTEXITCODE -ne 0) { throw "Falha na restauração." }

$users = docker compose exec -T db psql -U postgres -d $Target -tAc "SELECT count(*) FROM users"
$tx = docker compose exec -T db psql -U postgres -d $Target -tAc "SELECT count(*) FROM transactions"
$rls = docker compose exec -T db psql -U postgres -d $Target -tAc "SELECT count(*) FROM pg_class WHERE relforcerowsecurity"
Write-Output "Restaurado em '$Target': $($users.Trim()) usuários, $($tx.Trim()) lançamentos, $($rls.Trim()) tabelas com RLS forçado."
