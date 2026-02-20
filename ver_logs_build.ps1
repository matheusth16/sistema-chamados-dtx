# Mostra os logs do último build do Cloud Build (para debugar deploy que falhou)
# Uso: .\ver_logs_build.ps1
# Ou com ID específico: .\ver_logs_build.ps1 -BuildId "c3596f94-9d0d-4452-8ad8-bc9e1b1d89eb"

param([string]$BuildId = "")

$project = "sistema-de-chamados-dtx-aero"
$region = "us-central1"

if ($BuildId) {
    Write-Host "Logs do build $BuildId :" -ForegroundColor Cyan
    gcloud builds log $BuildId --region=$region --project=$project
} else {
    Write-Host "Buscando o ID do ultimo build..." -ForegroundColor Yellow
    $last = gcloud builds list --region=$region --project=$project --limit=1 --format="value(id)" 2>$null
    if ($last) {
        Write-Host "Ultimo build: $last" -ForegroundColor Cyan
        gcloud builds log $last --region=$region --project=$project
    } else {
        Write-Host "Nenhum build encontrado ou gcloud nao configurado." -ForegroundColor Red
        Write-Host "Voce tambem pode abrir o link que aparece no erro do deploy (Cloud Console)." -ForegroundColor Gray
    }
}
