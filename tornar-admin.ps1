<#
  Torna uma conta JÁ CADASTRADA e com e-mail confirmado administradora (somente no seu computador).
  Uso:  powershell -ExecutionPolicy Bypass -File tornar-admin.ps1 seu@email.com
#>
param([Parameter(Mandatory = $true)][string]$Email)
Set-Location (Join-Path $PSScriptRoot "backend")
.\.venv\Scripts\python -m app.cli promote-admin $Email
