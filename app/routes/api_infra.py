"""Rotas de infraestrutura/observabilidade: health check, cron interno, relatório CSP.

Separado de api_chamados.py (que fica só com regra de negócio de chamado) —
health/cron/csp-report são três categorias de infra que não têm relação de
domínio entre si nem com chamados, e coabitar o mesmo módulo dificultava
entender o que era regra de negócio e o que era operação (achado em
auditoria, 2026-08-05).
"""

import hmac
import logging
import os

from flask import abort, current_app, jsonify, request
from sqlalchemy import text

from app import db as db_module
from app.cache import cache_set
from app.limiter import limiter
from app.routes import main
from app.services.api_response import erro_json, sucesso_json

logger = logging.getLogger(__name__)
_csp_logger = logging.getLogger("app.csp")


def _obter_health_token_request() -> str:
    """Lê token de autenticação do health check.

    Canal primário: header X-Health-Token (não aparece em access logs).
    Canal deprecado: query string ?token= (compat UptimeRobot legado — migrar para header).
    """
    header = request.headers.get("X-Health-Token", "").strip()
    if header:
        return header
    return request.args.get("token", "").strip()


@main.route("/health", methods=["GET"])
@limiter.exempt
def health():
    """Health check para monitoramento externo.

    Modo raso (padrão): apenas confirma que a app está no ar — rápido, sem I/O.
    Modo deep (?deep=1): verifica conectividade com Postgres — para UptimeRobot/BetterUptime.

    Autenticação (quando HEALTH_SECRET estiver configurado):
      Exigida em AMBOS os modos (raso e deep) — impede mapeamento de liveness por atacantes.
      Canal primário  : header X-Health-Token: <secret>  ← não aparece em access logs
      Canal deprecado : query string ?token=<secret>     ← migrar para header

    Sem HEALTH_SECRET (dev/CI): sem autenticação em nenhum modo. Em produção,
    porém, o modo deep exige HEALTH_SECRET configurado mesmo sem token
    nenhum enviado — sem isso, qualquer host com rede até o app descobriria
    saúde/latência do Postgres de graça (o modo raso não vaza nada além de
    {"status":"ok"}, então continua liberado).

    Configuração de monitoramento:
      curl -H "X-Health-Token: $HEALTH_SECRET" "https://host/health"
      curl -H "X-Health-Token: $HEALTH_SECRET" "https://host/health?deep=1"

    Returns:
        200 {"status": "ok"}        — tudo saudável
        401                         — token ausente/inválido, ou modo deep em
                                      produção sem HEALTH_SECRET configurado
        503 {"status": "degraded"}  — alguma dependência falhou (apenas no modo deep)
    """
    import time

    # Quando HEALTH_SECRET estiver configurado, exige token em AMBOS os modos.
    # Sem HEALTH_SECRET (dev/CI): sem autenticação.
    secret = os.getenv("HEALTH_SECRET", "").strip()
    if secret:
        provided = _obter_health_token_request()
        if not provided or not hmac.compare_digest(provided, secret):
            abort(401)

    shallow = request.args.get("deep") not in ("1", "true")

    if shallow:
        return jsonify({"status": "ok"}), 200

    # Fail-closed: em produção, modo deep sem HEALTH_SECRET configurado não
    # tem como exigir token nenhum — bloqueia em vez de rodar aberto.
    if not secret and current_app.config.get("ENV") == "production":
        abort(401)

    # checks críticos: impactam overall; checks opcionais: apenas informativos
    critical_checks: dict[str, str] = {}
    optional_checks: dict[str, str] = {}
    start = time.perf_counter()

    # Postgres: dependência crítica — sem ele a app não funciona
    try:
        with db_module.SessionLocal() as session:
            session.execute(text("SELECT 1"))
        critical_checks["postgres"] = "ok"
    except Exception as exc:
        critical_checks["postgres"] = f"error:{type(exc).__name__}"
        logger.error("health_check postgres falhou: %s", exc)

    # Redis / cache em memória — opcional, degrada performance mas não bloqueia
    try:
        cache_set("__health__", "1", ttl_seconds=10)
        optional_checks["cache"] = "ok"
    except Exception as exc:
        optional_checks["cache"] = f"degraded:{type(exc).__name__}"

    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    all_critical_ok = all(v == "ok" for v in critical_checks.values())
    overall = "ok" if all_critical_ok else "degraded"
    status_code = 200 if all_critical_ok else 503
    checks = {**critical_checks, **optional_checks}

    payload = {
        "status": overall,
        "checks": checks,
        "duration_ms": duration_ms,
    }
    logger.info("health_check status=%s duration_ms=%.1f checks=%s", overall, duration_ms, checks)
    return jsonify(payload), status_code


def _obter_cron_token_request() -> str:
    """Lê token de autenticação do endpoint de cron interno (header X-Cron-Token)."""
    return request.headers.get("X-Cron-Token", "").strip()


@main.route("/internal/cron/sla-escalacao", methods=["POST"])
def cron_sla_escalacao():
    """Executa sob demanda o job de escalonamento SLA (motor unificado + avisos).

    Gatilho manual/backup, não usado em produção normal: o servidor físico
    on-premise fica sempre ligado, então o APScheduler in-process
    (`app/__init__.py:_iniciar_scheduler`) já cobre sozinho o job a cada 10
    min (ver `.env.example`). Esta rota existia originalmente pra acordar o
    Container App em modo scale-to-zero (free tier, era pré-Marco 12) — esse
    workflow do GitHub Actions está desativado desde a migração pro servidor
    físico. A rota permanece disponível como gatilho manual/backup, reaproveitando
    o lock Redis já existente (`executar_job_com_lock`) pra não duplicar
    execução caso o scheduler in-process já esteja rodando.

    Autenticação: header X-Cron-Token: <CRON_SECRET>.
    Sem CRON_SECRET configurado, a rota nunca fica aberta por engano.

    Returns:
        200 {"sucesso": true, "dados": {...}}  — job executado
        401                                     — token ausente ou inválido
        503                                     — CRON_SECRET não configurado
    """
    secret = os.getenv("CRON_SECRET", "").strip()
    if not secret:
        logger.error("cron_sla_escalacao chamado sem CRON_SECRET configurado no ambiente")
        return erro_json("cron não configurado", 503)

    provided = _obter_cron_token_request()
    if not provided or not hmac.compare_digest(provided, secret):
        abort(401)

    from app.services.scheduler_lock import executar_job_com_lock
    from app.services.sla_escalacao_service import (
        processar_avisos_resolucao,
        processar_escalonamento,
    )

    resultado: dict = {}
    erro: Exception | None = None

    def _job():
        nonlocal erro
        try:
            resultado["escalonamento"] = processar_escalonamento()
            resultado["avisos_resolucao"] = processar_avisos_resolucao()
        except Exception as exc:  # noqa: BLE001 — convertido em 500 genérico abaixo
            erro = exc

    executar_job_com_lock(current_app._get_current_object(), "sla_escalacao", _job)

    if erro is not None:
        logger.exception("Erro no job SLA Escalonamento via cron HTTP: %s", erro)
        return erro_json("erro ao processar escalonamento", 500)

    logger.info("cron_sla_escalacao executado via HTTP: %s", resultado)
    return sucesso_json(dados=resultado)


@main.route("/api/csp-report", methods=["POST"])
@limiter.limit("20 per minute", methods=["POST"])
def csp_report():
    """Recebe relatórios de violação CSP enviados pelo browser (sem autenticação, sem CSRF)."""
    body = request.get_json(silent=True, force=True) or {}
    report = body.get("csp-report", body)
    _csp_logger.warning(
        "CSP violation: blocked-uri=%s violated-directive=%s document-uri=%s",
        report.get("blocked-uri", ""),
        report.get("violated-directive", ""),
        report.get("document-uri", ""),
    )
    return "", 204
