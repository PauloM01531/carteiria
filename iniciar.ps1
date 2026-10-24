<#
  Inicia a CarteirIA no seu computador para testes locais.
  Uso: clique com o botão direito > "Executar com o PowerShell"
       ou, no terminal:  powershell -ExecutionPolicy Bypass -File iniciar.ps1
  Abre duas janelas (API e site). Para parar, feche essas janelas.
#>
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

Write-Host "1/4 Verificando o Docker..." -ForegroundColor Cyan
docker info --format "{{.ServerVersion}}" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    Write-Host "   Abrindo o Docker Desktop (pode levar 1 minuto)..."
    do { Start-Sleep 5; docker info --format "{{.ServerVersion}}" 2>$null | Out-Null } while ($LASTEXITCODE -ne 0)
}

Write-Host "2/4 Subindo banco de dados e caixa de e-mail local..." -ForegroundColor Cyan
docker compose --env-file .env up -d | Out-Null

Write-Host "3/4 Aplicando atualizações do banco..." -ForegroundColor Cyan
Push-Location backend
.\.venv\Scripts\alembic upgrade head
Pop-Location

Write-Host "4/4 Abrindo a API e o site..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\backend'; `$host.UI.RawUI.WindowTitle='CarteirIA - API'; .\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\frontend'; `$host.UI.RawUI.WindowTitle='CarteirIA - Site'; npm run dev -- --host 127.0.0.1 --port 5173"

Start-Sleep 8
Start-Process "http://localhost:5173"
Start-Process "http://localhost:8025"
Write-Host ""
Write-Host "Pronto! Site: http://localhost:5173   |   E-mails de teste: http://localhost:8025" -ForegroundColor Green
