#!/usr/bin/env bash
# watchtower_trigger.sh — Dispara manualmente a atualização do container "web"
# via HTTP API do Watchtower (docker-compose.prod.yml).
#
# O Watchtower está configurado em modo --http-api-update, sem polling
# automático: o CI publica a imagem "latest" no GHCR a cada push, mas o
# container em produção só troca quando este script (ou uma chamada
# equivalente) é executado manualmente no servidor.
#
# Pré-requisito: WATCHTOWER_HTTP_API_TOKEN definido no .env do servidor
# (mesmo diretório do docker-compose.prod.yml).
#
# Uso (rodar no servidor, a partir da raiz do projeto):
#   bash scripts/watchtower_trigger.sh

set -euo pipefail

ENV_FILE=".env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Erro: $ENV_FILE não encontrado. Rode a partir da raiz do projeto no servidor." >&2
  exit 1
fi

TOKEN=$(grep -E '^WATCHTOWER_HTTP_API_TOKEN=' "$ENV_FILE" | cut -d '=' -f2-)

if [[ -z "$TOKEN" ]]; then
  echo "Erro: WATCHTOWER_HTTP_API_TOKEN não definido em $ENV_FILE." >&2
  exit 1
fi

echo "Disparando atualização via Watchtower..."
# -X POST é obrigatório — a API do Watchtower (nicholas-fedor/watchtower)
# rejeita GET (curl sem -X) com 405 Method Not Allowed. Achado 2026-08-06
# rodando este script pela primeira vez em produção.
curl -fsS -X POST -H "Authorization: Bearer ${TOKEN}" "http://127.0.0.1:8081/v1/update"
echo
echo "OK — acompanhe com: docker logs -f \$(docker ps -qf name=watchtower)"
