# Deploy para Cloud Run FORÇANDO rebuild sem cache
# Use quando fizer mudanças no código e elas nao aparecerem na URL publicada
# Uso: .\deploy_fresh.ps1

$ErrorActionPreference = "Stop"
$project = "sistema-de-chamados-dtx-aero"
$region = "us-central1"
$service = "sistema-chamados-dtx"

Write-Host "Deploy COM rebuild completo (--no-cache) - suas alteracoes serao aplicadas." -ForegroundColor Cyan
Write-Host "Servico: $service | Regiao: $region | Projeto: $project" -ForegroundColor Gray
Write-Host ""

gcloud run deploy $service `
  --source . `
  --platform managed `
  --region $region `
  --project $project `
  --no-cache `
  --allow-unauthenticated `
  --memory=512Mi `
  --timeout=60 `
  --max-instances=10

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Deploy concluido. Aguarde 1-2 min e teste a URL (ou use Ctrl+Shift+R no navegador)." -ForegroundColor Green
} else {
    Write-Host "Deploy falhou. Veja a mensagem acima ou rode: .\ver_logs_build.ps1" -ForegroundColor Red
    exit 1
}
