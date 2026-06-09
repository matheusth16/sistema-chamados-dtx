#!/usr/bin/env bash
# deploy_cloud_run.sh — Deploy manual para Cloud Run (fallback se Cloud Build trigger não estiver configurado)
#
# Pré-requisito: gcloud CLI instalado e autenticado
#   gcloud auth login
#   gcloud config set project SEU_PROJECT_ID
#
# Uso:
#   bash scripts/deploy_cloud_run.sh
#   bash scripts/deploy_cloud_run.sh --dry-run   (mostra comandos sem executar)

set -euo pipefail

# ── Configuração ────────────────────────────────────────────────────────────────
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
REGION="southamerica-east1"
SERVICE="sistema-chamados"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE}"
DRY_RUN=false

for arg in "$@"; do
  [[ "$arg" == "--dry-run" ]] && DRY_RUN=true
done

run() {
  echo "  $ $*"
  $DRY_RUN || eval "$*"
}

# ── 1. Verificações pré-deploy ───────────────────────────────────────────────
echo "=== [1/5] Verificações pré-deploy ==="

if [ -z "$PROJECT_ID" ]; then
  echo "ERRO: PROJECT_ID não configurado. Execute: gcloud config set project SEU_ID"
  exit 1
fi
echo "Projeto: $PROJECT_ID | Região: $REGION | Serviço: $SERVICE"

# Testes locais antes de enviar
echo "Rodando testes..."
run "python -m pytest --tb=short -q --no-cov"

# ── 2. Build e push da imagem ────────────────────────────────────────────────
echo ""
echo "=== [2/5] Build Docker ==="
SHA=$(git rev-parse --short HEAD)
run "docker build -t ${IMAGE}:${SHA} -t ${IMAGE}:latest ."
run "docker push --all-tags ${IMAGE}"

# ── 3. Deploy no Cloud Run ───────────────────────────────────────────────────
echo ""
echo "=== [3/5] Deploy Cloud Run ==="
run "gcloud run deploy ${SERVICE} \
  --image ${IMAGE}:${SHA} \
  --region ${REGION} \
  --platform managed \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 3 \
  --memory 512Mi \
  --cpu 1 \
  --timeout 300 \
  --set-env-vars FLASK_ENV=production,PYTHONUNBUFFERED=1"

# ── 4. Smoke test ────────────────────────────────────────────────────────────
echo ""
echo "=== [4/5] Smoke test ==="
SERVICE_URL=$(gcloud run services describe "${SERVICE}" \
  --region="${REGION}" --format='value(status.url)' 2>/dev/null || echo "")

if [ -n "$SERVICE_URL" ] && ! $DRY_RUN; then
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${SERVICE_URL}/health")
  echo "URL: ${SERVICE_URL}"
  echo "Health check: ${HTTP_CODE}"
  if [ "$HTTP_CODE" != "200" ]; then
    echo "FALHA no health check! Iniciando rollback..."
    PREV_SHA=$(git rev-parse --short HEAD~1)
    gcloud run deploy "${SERVICE}" \
      --image "${IMAGE}:${PREV_SHA}" \
      --region "${REGION}" --platform managed
    echo "Rollback para ${PREV_SHA} concluído."
    exit 1
  fi
  echo "Health check OK."
else
  echo "(dry-run ou URL não disponível — smoke test ignorado)"
fi

# ── 5. Confirmação ───────────────────────────────────────────────────────────
echo ""
echo "=== [5/5] Deploy concluído ==="
echo "SHA: ${SHA}"
$DRY_RUN && echo "(DRY-RUN: nenhum comando foi executado)"
echo ""
echo "Próximos 15 minutos: monitore os logs em:"
echo "  gcloud run services logs read ${SERVICE} --region ${REGION} --limit 50"
echo "  https://console.cloud.google.com/run/detail/${REGION}/${SERVICE}/logs"
