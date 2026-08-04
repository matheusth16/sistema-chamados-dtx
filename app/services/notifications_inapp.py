"""
Notificações in-app (sino): criar, listar e marcar como lida.
Armazenamento no Postgres, tabela 'notificacoes' (Fase 2, Marco 8).
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update

from app import db as db_module
from app.db.models.notificacao import NotificacaoRow
from app.i18n import get_translated_category, get_translation

logger = logging.getLogger(__name__)


def _parse_legacy_novo_chamado(titulo: str, mensagem: str) -> tuple[str, str, str]:
    """
    Extrai (numero, categoria, solicitante) de notificações antigas sem metadados
    estruturados, a partir do texto pré-renderizado em português.
    Retorna strings vazias se o parse não for possível.
    """
    numero = ""
    if titulo.startswith("Novo chamado:"):
        numero = titulo.split(":", 1)[1].strip()
    categoria = ""
    solicitante = ""
    for sep in (" · Solicitante: ", " · Requester: ", " · Solicitante: "):
        if sep in mensagem:
            categoria, solicitante = mensagem.split(sep, 1)
            categoria = categoria.strip()
            solicitante = solicitante.strip()
            break
    return numero, categoria, solicitante


_TIPOS_SOLICITANTE = frozenset(
    {
        "status_em_atendimento",
        "status_concluido_confirmar",
        "lembrete_confirmacao_1",
        "lembrete_confirmacao_2",
    }
)

_TIPOS_OBSERVADOR = frozenset(
    {
        "observador_edicao_descricao",
        "observador_anexo_tardio",
        "observador_cancelamento",
        "observador_status_em_atendimento",
        "observador_status_concluido",
        "observador_incluido",
    }
)

_TIPOS_PARTICIPANTE = frozenset(
    {
        "participante_incluido",
        "todos_participantes_concluidos",
    }
)


def localizar_notificacao(doc: dict, language: str = "en") -> dict:
    """
    Retorna uma cópia do doc com titulo/mensagem traduzidos para o idioma dado.
    Funciona tanto para notificações novas (com categoria/solicitante_nome no doc)
    quanto para notificações legadas (parse do texto PT como fallback).
    Tipos desconhecidos são retornados sem alteração.
    """
    out = dict(doc)
    tipo = doc.get("tipo")

    if tipo == "novo_chamado":
        numero = doc.get("numero_chamado") or ""
        categoria_raw = doc.get("categoria") or ""
        solicitante = doc.get("solicitante_nome") or ""

        if not categoria_raw or not solicitante:
            n, c, s = _parse_legacy_novo_chamado(doc.get("titulo", ""), doc.get("mensagem", ""))
            numero = numero or n
            categoria_raw = categoria_raw or c
            solicitante = solicitante or s

        cat = get_translated_category(categoria_raw, language)
        out["titulo"] = get_translation("notification_new_ticket_title", language, numero=numero)
        out["mensagem"] = get_translation(
            "notification_new_ticket_message", language, categoria=cat, solicitante=solicitante
        )

    elif tipo in _TIPOS_OBSERVADOR:
        numero = doc.get("numero_chamado") or ""
        cat = get_translated_category(doc.get("categoria") or "", language)

        if tipo == "observador_edicao_descricao":
            out["titulo"] = get_translation(
                "notification_obs_edicao_titulo", language, numero=numero
            )
            out["mensagem"] = get_translation(
                "notification_obs_edicao_mensagem", language, categoria=cat
            )
        elif tipo == "observador_anexo_tardio":
            out["titulo"] = get_translation(
                "notification_obs_anexo_titulo", language, numero=numero
            )
            out["mensagem"] = get_translation(
                "notification_obs_anexo_mensagem", language, categoria=cat
            )
        elif tipo == "observador_cancelamento":
            out["titulo"] = get_translation(
                "notification_obs_cancelamento_titulo", language, numero=numero
            )
            out["mensagem"] = get_translation(
                "notification_obs_cancelamento_mensagem", language, categoria=cat
            )
        elif tipo == "observador_status_em_atendimento":
            out["titulo"] = get_translation(
                "notification_observer_status_in_progress_title", language, numero=numero
            )
            out["mensagem"] = get_translation(
                "notification_observer_status_in_progress_message", language, categoria=cat
            )
        elif tipo == "observador_status_concluido":
            out["titulo"] = get_translation(
                "notification_observer_status_completed_title", language, numero=numero
            )
            out["mensagem"] = get_translation(
                "notification_observer_status_completed_message", language, categoria=cat
            )
        elif tipo == "observador_incluido":
            out["titulo"] = get_translation(
                "notification_observer_added_title", language, numero=numero
            )
            out["mensagem"] = get_translation(
                "notification_observer_added_message", language, categoria=cat
            )

    elif tipo in _TIPOS_PARTICIPANTE:
        numero = doc.get("numero_chamado") or ""
        cat = get_translated_category(doc.get("categoria") or "", language)

        if tipo == "participante_incluido":
            out["titulo"] = get_translation(
                "notification_participant_included_title", language, numero=numero
            )
            out["mensagem"] = get_translation(
                "notification_participant_included_message", language, numero=numero, categoria=cat
            )
        else:
            out["titulo"] = get_translation(
                "notification_all_participants_done_title", language, numero=numero
            )
            out["mensagem"] = get_translation(
                "notification_all_participants_done_message", language, numero=numero, categoria=cat
            )

    elif tipo in _TIPOS_SOLICITANTE:
        numero = doc.get("numero_chamado") or ""
        cat = get_translated_category(doc.get("categoria") or "", language)

        if tipo == "status_em_atendimento":
            out["titulo"] = get_translation(
                "notification_status_in_progress_title", language, numero=numero
            )
            out["mensagem"] = get_translation(
                "notification_status_in_progress_message", language, categoria=cat
            )
        elif tipo == "status_concluido_confirmar":
            out["titulo"] = get_translation(
                "notification_status_completed_confirm_title", language, numero=numero
            )
            out["mensagem"] = get_translation(
                "notification_status_completed_confirm_message", language, categoria=cat
            )
        else:
            n = 1 if tipo == "lembrete_confirmacao_1" else 2
            out["titulo"] = get_translation(
                "notification_reminder_confirm_title", language, numero=numero, n=n
            )
            out["mensagem"] = get_translation(
                "notification_reminder_confirm_message", language, categoria=cat, n=n
            )

    return out


def texto_notificacao_status_solicitante(
    numero: str,
    categoria: str,
    tipo_evento: str,
    language: str = "en",
    numero_lembrete: int | None = None,
) -> tuple[str, str]:
    """
    Retorna (titulo, mensagem) para notificações de status destinadas ao solicitante.

    tipo_evento: 'status_em_atendimento' | 'status_concluido_confirmar' | 'lembrete_confirmacao'
    numero_lembrete: 1 ou 2, usado apenas quando tipo_evento == 'lembrete_confirmacao'
    """
    cat = get_translated_category(categoria, language)
    if tipo_evento == "status_em_atendimento":
        titulo = get_translation("notification_status_in_progress_title", language, numero=numero)
        mensagem = get_translation(
            "notification_status_in_progress_message", language, categoria=cat
        )
    elif tipo_evento == "status_concluido_confirmar":
        titulo = get_translation(
            "notification_status_completed_confirm_title", language, numero=numero
        )
        mensagem = get_translation(
            "notification_status_completed_confirm_message", language, categoria=cat
        )
    else:
        n = numero_lembrete or 1
        titulo = get_translation(
            "notification_reminder_confirm_title", language, numero=numero, n=n
        )
        mensagem = get_translation(
            "notification_reminder_confirm_message", language, categoria=cat, n=n
        )
    return titulo, mensagem


def criar_notificacao_solicitante(
    solicitante_id: str,
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    tipo: str,
    numero_lembrete: int | None = None,
    language: str = "en",
) -> int | None:
    """
    Cria notificação in-app para o solicitante em eventos de status/lembrete.

    tipo: 'status_em_atendimento' | 'status_concluido_confirmar'
          | 'lembrete_confirmacao_1' | 'lembrete_confirmacao_2'
    """
    if not solicitante_id or not chamado_id:
        return None

    # Mapeia tipo lembrete para o tipo_evento do helper de texto
    if tipo in ("lembrete_confirmacao_1", "lembrete_confirmacao_2"):
        n = 1 if tipo == "lembrete_confirmacao_1" else 2
        tipo_evento = "lembrete_confirmacao"
        numero_lembrete = n
    else:
        tipo_evento = tipo

    titulo, mensagem = texto_notificacao_status_solicitante(
        numero=numero_chamado,
        categoria=categoria,
        tipo_evento=tipo_evento,
        language=language,
        numero_lembrete=numero_lembrete,
    )
    return criar_notificacao(
        usuario_id=solicitante_id,
        chamado_id=chamado_id,
        numero_chamado=numero_chamado,
        titulo=titulo,
        mensagem=mensagem,
        tipo=tipo,
        categoria=categoria,
    )


def texto_notificacao_novo_chamado(
    numero: str, categoria_raw: str, solicitante_nome: str, language: str = "en"
) -> tuple[str, str]:
    """
    Retorna (titulo, mensagem) traduzidos para o idioma dado.
    Usado na criação do chamado para garantir que o texto salvo reflita o idioma padrão.
    """
    cat = get_translated_category(categoria_raw, language)
    titulo = get_translation("notification_new_ticket_title", language, numero=numero)
    mensagem = get_translation(
        "notification_new_ticket_message", language, categoria=cat, solicitante=solicitante_nome
    )
    return titulo, mensagem


def criar_notificacao(
    usuario_id: str,
    chamado_id: str,
    numero_chamado: str,
    titulo: str,
    mensagem: str,
    tipo: str = "novo_chamado",
    categoria: str = "",
    solicitante_nome: str = "",
) -> int | None:
    """
    Cria uma notificação in-app para o usuário (ex.: aprovador quando recebe novo chamado).
    Retorna o id do registro criado ou None em caso de erro.
    Os campos opcionais categoria/solicitante_nome são metadados estruturados que permitem
    traduzir a notificação na leitura para qualquer idioma.
    """
    if not usuario_id or not chamado_id:
        return None
    try:
        cid = int(chamado_id)
    except (TypeError, ValueError):
        logger.exception("chamado_id inválido ao criar notificação: %s", chamado_id)
        return None
    try:
        with db_module.SessionLocal() as session, session.begin():
            row = NotificacaoRow(
                usuario_id=usuario_id,
                chamado_id=cid,
                numero_chamado=numero_chamado,
                titulo=titulo,
                mensagem=mensagem,
                tipo=tipo,
                categoria=categoria or None,
                solicitante_nome=solicitante_nome or None,
                lida=False,
            )
            session.add(row)
            session.flush()
            notificacao_id = row.id
        logger.debug(
            "Notificação in-app criada: usuario=%s, chamado=%s", usuario_id, numero_chamado
        )
        return notificacao_id
    except Exception as e:
        logger.exception("Erro ao criar notificação in-app: %s", e)
        return None


def _serializar_row(row: NotificacaoRow) -> dict[str, Any]:
    """Serializa uma NotificacaoRow para dict JSON-safe."""
    ts = row.data_criacao
    return {
        "id": row.id,
        "usuario_id": row.usuario_id,
        "chamado_id": row.chamado_id,
        "numero_chamado": row.numero_chamado,
        "titulo": row.titulo,
        "mensagem": row.mensagem,
        "tipo": row.tipo,
        "categoria": row.categoria,
        "solicitante_nome": row.solicitante_nome,
        "lida": row.lida,
        "data_criacao": ts.isoformat() if isinstance(ts, datetime) else None,
    }


def listar_para_usuario(
    usuario_id: str,
    limite: int = 30,
    apenas_nao_lidas: bool = False,
    language: str | None = None,
) -> list[dict[str, Any]]:
    """
    Lista notificações do usuário, mais recentes primeiro.
    Retorna lista de dicts com id, chamado_id, numero_chamado, titulo, mensagem, lida, data_criacao.
    Quando language é fornecido, aplica localização dinâmica ao titulo/mensagem de cada notificação.
    """
    if not usuario_id:
        return []
    try:
        with db_module.SessionLocal() as session:
            query = select(NotificacaoRow).where(NotificacaoRow.usuario_id == usuario_id)
            if apenas_nao_lidas:
                query = query.where(NotificacaoRow.lida.is_(False))
            query = query.order_by(
                NotificacaoRow.data_criacao.desc(), NotificacaoRow.id.desc()
            ).limit(limite)
            rows = session.execute(query).scalars().all()

        result = [_serializar_row(row) for row in rows]
        if language:
            result = [localizar_notificacao(d, language) for d in result]
        return result
    except Exception as e:
        logger.exception("Erro ao listar notificações: %s", e)
        return []


def contar_nao_lidas(usuario_id: str) -> int:
    """Retorna a quantidade de notificações não lidas do usuário."""
    if not usuario_id:
        return 0
    try:
        with db_module.SessionLocal() as session:
            total = session.execute(
                select(func.count())
                .select_from(NotificacaoRow)
                .where(NotificacaoRow.usuario_id == usuario_id, NotificacaoRow.lida.is_(False))
            ).scalar()
        return total or 0
    except Exception as e:
        logger.exception("Erro ao contar notificações: %s", e)
        return 0


def marcar_como_lida(notificacao_id, usuario_id: str) -> bool:
    """Marca a notificação como lida. Retorna True se encontrou e pertence ao usuário."""
    if not notificacao_id or not usuario_id:
        return False
    try:
        nid = int(notificacao_id)
    except (TypeError, ValueError):
        return False
    try:
        with db_module.SessionLocal() as session, session.begin():
            row = session.get(NotificacaoRow, nid)
            if row is None or row.usuario_id != usuario_id:
                return False
            row.lida = True
        return True
    except Exception as e:
        logger.exception("Erro ao marcar notificação como lida: %s", e)
        return False


def marcar_todas_como_lidas(usuario_id: str) -> int:
    """Marca todas as notificações não lidas do usuário como lidas. Retorna quantidade atualizada."""
    if not usuario_id:
        return 0
    try:
        with db_module.SessionLocal() as session, session.begin():
            result = session.execute(
                update(NotificacaoRow)
                .where(NotificacaoRow.usuario_id == usuario_id, NotificacaoRow.lida.is_(False))
                .values(lida=True)
            )
            count = result.rowcount or 0
        if count:
            logger.debug(
                "Notificações marcadas como lidas: usuario=%s, count=%s", usuario_id, count
            )
        return count
    except Exception as e:
        logger.exception("Erro ao marcar todas notificações como lidas: %s", e)
        return 0
