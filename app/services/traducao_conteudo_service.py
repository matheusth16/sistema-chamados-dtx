"""Tradução automática de conteúdo dinâmico dos chamados (descrição,
histórico, conversa) via LibreTranslate self-hosted.

Diferente de app/services/translation_service.py (tradução ADMIN-TIME de
nomes curtos de setor/categoria, mapa estático + MyMemory + cache em memória):
aqui o texto é livre/ilimitado, escrito por qualquer pessoa, e o cache é em
Postgres (traducoes_conteudo) — sobrevive a restart/deploy, o que o dict em
memória do translation_service.py não garante.

Idioma de origem nunca é presumido — sempre "auto" no LibreTranslate — e
quando o idioma detectado do texto já bate com o idioma destino, a tradução é
pulada (mostra o original, sem chamada de rede desperdiçada).

Fail-open: LIBRETRANSLATE_ENABLED=false, LibreTranslate fora do ar, timeout
ou resposta malformada nunca quebram a página — sempre cai de volta pro texto
original.
"""

import hashlib
import json
import logging
import urllib.request
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import db as db_module
from app.db.models.traducao_conteudo import TraducaoConteudoRow

logger = logging.getLogger(__name__)

# Idiomas suportados pela UI (app/i18n.py SUPPORTED_LANGUAGES) -> código ISO
# 639-1 usado pelo LibreTranslate/Argos.
_LANG_MAP = {"pt_BR": "pt", "en": "en", "es": "es"}


def _get_flask_config() -> dict | None:
    """Retorna current_app.config se dentro de contexto Flask, senão None."""
    try:
        from flask import current_app

        return current_app.config
    except RuntimeError:
        return None


def _sem_traducao(texto: str) -> dict[str, Any]:
    return {"texto": texto, "traduzido": False, "original": None}


def _hash_texto(texto: str) -> str:
    return hashlib.sha256(texto.strip().encode("utf-8")).hexdigest()


def traduzir_conteudo(texto: str, idioma_destino: str) -> dict[str, Any]:
    """Traduz um único texto pro idioma_destino ('pt_BR'|'en'|'es').

    Retorna {"texto": str, "traduzido": bool, "original": str | None} —
    "original" só vem preenchido quando "traduzido" é True (usado pelo link
    "ver original" na UI).
    """
    return traduzir_varios([texto], idioma_destino).get(texto, _sem_traducao(texto))


def traduzir_varios(textos: list[str], idioma_destino: str) -> dict[str, dict[str, Any]]:
    """Traduz vários textos em lote: 1 lookup de cache no Postgres + no máximo
    1 chamada HTTP ao LibreTranslate pros que faltarem no cache (evita N
    chamadas de rede num loop de histórico com várias entradas).

    Retorna {texto_original: {"texto": ..., "traduzido": bool, "original": ...}}.
    """
    resultado: dict[str, dict[str, Any]] = {}
    pendentes: list[str] = []
    for texto in textos:
        if texto in resultado:
            continue
        if not isinstance(texto, str) or not texto.strip():
            resultado[texto] = _sem_traducao(texto)
            continue
        pendentes.append(texto)

    if not pendentes:
        return resultado

    config = _get_flask_config() or {}
    if not config.get("LIBRETRANSLATE_ENABLED", False):
        for texto in pendentes:
            resultado[texto] = _sem_traducao(texto)
        return resultado

    lt_target = _LANG_MAP.get(idioma_destino)
    url = (config.get("LIBRETRANSLATE_URL") or "").strip()
    if not lt_target or not url:
        for texto in pendentes:
            resultado[texto] = _sem_traducao(texto)
        return resultado

    hash_por_texto = {texto: _hash_texto(texto) for texto in pendentes}
    cache_por_hash = _buscar_cache(list(set(hash_por_texto.values())), idioma_destino)

    faltando: list[str] = []
    for texto in pendentes:
        h = hash_por_texto[texto]
        if h in cache_por_hash:
            resultado[texto] = {
                "texto": cache_por_hash[h],
                "traduzido": True,
                "original": texto,
            }
        else:
            faltando.append(texto)

    if not faltando:
        return resultado

    timeout = int(config.get("LIBRETRANSLATE_TIMEOUT_SECONDS", 15))
    traduzidos, detectados = _traduzir_via_libretranslate(faltando, lt_target, url, timeout)
    if traduzidos is None:
        for texto in faltando:
            resultado[texto] = _sem_traducao(texto)
        return resultado

    novas_linhas = []
    for texto, traduzido, detectado in zip(faltando, traduzidos, detectados, strict=True):
        if detectado and detectado == lt_target:
            resultado[texto] = _sem_traducao(texto)
            continue
        resultado[texto] = {"texto": traduzido, "traduzido": True, "original": texto}
        novas_linhas.append(
            {
                "texto_original_hash": hash_por_texto[texto],
                "idioma_destino": idioma_destino,
                "idioma_origem_detectado": detectado,
                "texto_traduzido": traduzido,
            }
        )

    if novas_linhas:
        _persistir_cache(novas_linhas)

    return resultado


def _buscar_cache(hashes: list[str], idioma_destino: str) -> dict[str, str]:
    if not hashes:
        return {}
    try:
        with db_module.SessionLocal() as session:
            rows = (
                session.execute(
                    select(TraducaoConteudoRow).where(
                        TraducaoConteudoRow.texto_original_hash.in_(hashes),
                        TraducaoConteudoRow.idioma_destino == idioma_destino,
                    )
                )
                .scalars()
                .all()
            )
        return {row.texto_original_hash: row.texto_traduzido for row in rows}
    except Exception as e:
        logger.exception("Erro ao consultar cache de tradução: %s", e)
        return {}


def _persistir_cache(novas_linhas: list[dict[str, Any]]) -> None:
    try:
        with db_module.SessionLocal() as session, session.begin():
            stmt = (
                pg_insert(TraducaoConteudoRow)
                .values(novas_linhas)
                .on_conflict_do_nothing(index_elements=["texto_original_hash", "idioma_destino"])
            )
            session.execute(stmt)
    except Exception as e:
        logger.exception("Erro ao persistir cache de tradução: %s", e)


_ACOES_CONVERSA = ("resposta_solicitante", "resposta_responsavel")


def _textos_traduziveis_historico(h: Any) -> list[str]:
    """Extrai os textos livres de um Historico que fazem sentido mandar pro
    LibreTranslate — mesma regra condicional que historico.html usa pra
    decidir entre valor ESTRUTURADO (já traduzido pelo i18n estático via
    translate_status/translate_category — ex.: nome de status, de área, de
    setor) e texto LIVRE digitado por alguém (motivo, nota, mensagem de
    conversa). Nunca os dois pro mesmo campo — evitaria dupla tradução e o
    risco de o LibreTranslate "traduzir" um nome próprio de setor/área."""
    textos: list[str] = []
    if h.detalhe and h.campo_alterado not in ("anexo", "novo anexo"):
        textos.append(h.detalhe)

    eh_nota_status = h.acao in ("alteracao_status", "reabertura") and h.campo_alterado != "status"
    eh_edicao_descricao = h.acao == "edicao_descricao"
    eh_dados_descricao = h.acao == "alteracao_dados" and h.campo_alterado == "descrição"
    if eh_nota_status or eh_edicao_descricao or eh_dados_descricao:
        textos += [h.valor_anterior, h.valor_novo]
    elif h.acao in _ACOES_CONVERSA:
        textos.append(h.valor_novo)

    return [t for t in textos if isinstance(t, str) and t.strip()]


def montar_traducoes_chamado(chamado: Any, historico: list, idioma_destino: str) -> dict:
    """Monta o dicionário de traduções pra tela de detalhe do chamado num
    lote ÚNICO (descrição/motivo_* do chamado + todo o histórico) — chamar
    UMA vez antes do render_template (app/routes/dashboard.py), nunca dentro
    do loop do template, senão vira 1 chamada HTTP por entrada do histórico."""
    textos = [
        chamado.descricao,
        getattr(chamado, "motivo_cancelamento", None),
        getattr(chamado, "motivo_previsao_atendimento", None),
        getattr(chamado, "motivo_ultima_escalacao", None),
    ]
    for h in historico:
        textos.extend(_textos_traduziveis_historico(h))
    textos = [t for t in textos if isinstance(t, str) and t.strip()]
    return traduzir_varios(textos, idioma_destino)


def _traduzir_via_libretranslate(
    textos: list[str], lt_target: str, url: str, timeout: int
) -> tuple[list[str] | None, list[str | None]]:
    """Chama POST {url}/translate em lote (q como array). Retorna
    (traduzidos, idiomas_detectados) ou (None, []) em qualquer falha."""
    try:
        payload = json.dumps(
            {"q": textos, "source": "auto", "target": lt_target, "format": "text"}
        ).encode("utf-8")
        req = urllib.request.Request(
            url.rstrip("/") + "/translate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            data = json.loads(resp.read().decode())

        traduzidos = data.get("translatedText")
        if not isinstance(traduzidos, list) or len(traduzidos) != len(textos):
            logger.warning("Resposta inesperada do LibreTranslate: %r", data)
            return None, []

        detectado_raw = data.get("detectedLanguage")
        if isinstance(detectado_raw, list) and len(detectado_raw) == len(textos):
            detectados = [
                (d or {}).get("language") if isinstance(d, dict) else None for d in detectado_raw
            ]
        else:
            detectados = [None] * len(textos)
        return traduzidos, detectados
    except Exception as e:
        logger.warning("LibreTranslate indisponível: %s", e)
        return None, []
