"""Autoatendimento LGPD sobre a própria conta: exportação (portabilidade) e
solicitação de exclusão (direito de exclusão).

A exclusão em si NÃO é executada aqui — este serviço só registra o pedido.
Um admin revisa e executa via os fluxos já existentes (desativar + anonimizar
em app/routes/usuarios.py), mesmo padrão de segurança usado hoje para ações
administrativas irreversíveis sobre contas.
"""

import logging

from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.database import db
from app.services.historico_usuario_service import registrar_historico_usuario

logger = logging.getLogger(__name__)

COLLECTION_SOLICITACOES = "solicitacoes_lgpd"

# Um solicitante nunca terá mais que isso de chamados próprios — evita ler a
# coleção inteira; mesmo padrão de chamados_listagem_service._FALLBACK_LIMIT.
_LIMITE_CHAMADOS_EXPORT = 200

# Idem para solicitações de exclusão do próprio usuário (praticamente sempre 0 ou 1).
_LIMITE_SOLICITACOES_USUARIO = 20

# Teto de segurança para a listagem administrativa de solicitações pendentes.
_LIMITE_SOLICITACOES_PENDENTES = 1000


def exportar_dados_usuario(usuario) -> dict:
    """Monta o export LGPD (direito de portabilidade) dos dados do próprio usuário."""
    chamados_docs = (
        db.collection("chamados")
        .where(filter=FieldFilter("solicitante_id", "==", usuario.id))
        .limit(_LIMITE_CHAMADOS_EXPORT)
        .stream()
    )
    chamados = []
    for doc in chamados_docs:
        d = doc.to_dict() or {}
        chamados.append(
            {
                "id": doc.id,
                "numero_chamado": d.get("numero_chamado"),
                "titulo": d.get("titulo"),
                "categoria": d.get("categoria"),
                "status": d.get("status"),
                "data_criacao": str(d.get("data_criacao")) if d.get("data_criacao") else None,
            }
        )

    return {
        "conta": {
            "id": usuario.id,
            "nome": usuario.nome,
            "email": usuario.email,
            "perfil": usuario.perfil,
            "areas": getattr(usuario, "areas", None),
            "nivel_gestao": getattr(usuario, "nivel_gestao", None),
            "auth_provider": getattr(usuario, "auth_provider", "local"),
            "mfa_enabled": getattr(usuario, "mfa_enabled", False),
            "password_changed_at": str(getattr(usuario, "password_changed_at", None) or "") or None,
        },
        "chamados_criados": chamados,
    }


def possui_solicitacao_exclusao_pendente(usuario_id: str) -> bool:
    """Verifica se o usuário já tem uma solicitação de exclusão em aberto.

    Filtra 'status' em Python (não em query composta) para não depender de
    índice composto novo no Firestore — coleção pequena por natureza (no
    máximo algumas dezenas de solicitações por usuário ao longo da vida da conta).
    """
    try:
        docs = (
            db.collection(COLLECTION_SOLICITACOES)
            .where(filter=FieldFilter("usuario_id", "==", usuario_id))
            .limit(_LIMITE_SOLICITACOES_USUARIO)
            .stream()
        )
        return any((doc.to_dict() or {}).get("status") == "pendente" for doc in docs)
    except Exception:
        logger.exception(
            "Erro ao verificar solicitação de exclusão pendente: usuario_id=%s", usuario_id
        )
        return False


def solicitar_exclusao_propria(usuario) -> dict:
    """Registra uma solicitação de exclusão feita pelo próprio titular.

    Retorna {"sucesso": bool, "erro_key"?: str} — erro_key é uma CHAVE de
    tradução (não texto traduzido), pra rota resolver via flash_t.
    """
    if possui_solicitacao_exclusao_pendente(usuario.id):
        return {"sucesso": False, "erro_key": "lgpd_exclusion_request_already_pending"}

    try:
        db.collection(COLLECTION_SOLICITACOES).add(
            {
                "usuario_id": usuario.id,
                "usuario_nome": usuario.nome,
                "usuario_email": usuario.email,
                "tipo": "exclusao",
                "status": "pendente",
                "data_solicitacao": firestore.SERVER_TIMESTAMP,
            }
        )
        registrar_historico_usuario(
            usuario_alvo_id=usuario.id,
            usuario_alvo_nome=usuario.nome,
            admin_id=usuario.id,
            admin_nome=usuario.nome,
            acao="solicitacao_exclusao_lgpd",
            detalhe="Solicitação feita pelo próprio titular via /meus-dados",
        )
        return {"sucesso": True}
    except Exception:
        logger.exception(
            "Erro ao registrar solicitação de exclusão LGPD: usuario_id=%s", usuario.id
        )
        return {"sucesso": False, "erro_key": "internal_error_retry"}


def listar_usuarios_com_solicitacao_pendente() -> set[str]:
    """Retorna o conjunto de usuario_id com solicitação de exclusão LGPD pendente.

    Uso administrativo — sinaliza na listagem de usuários quem tem pedido em aberto.
    """
    try:
        docs = (
            db.collection(COLLECTION_SOLICITACOES)
            .where(filter=FieldFilter("status", "==", "pendente"))
            .limit(_LIMITE_SOLICITACOES_PENDENTES)
            .stream()
        )
        return {
            usuario_id for doc in docs if (usuario_id := (doc.to_dict() or {}).get("usuario_id"))
        }
    except Exception:
        logger.exception("Erro ao listar solicitações de exclusão LGPD pendentes")
        return set()


def resolver_solicitacoes_exclusao_pendentes(
    usuario_id: str, admin_id: str, admin_nome: str
) -> int:
    """Marca como concluídas as solicitações de exclusão LGPD pendentes de um usuário.

    Chamado quando um admin executa a ação que atende o pedido (deletar ou
    anonimizar a conta) — fecha o loop pra não deixar o badge em /admin/usuarios
    preso indefinidamente. Retorna quantas solicitações foram resolvidas.
    """
    try:
        docs = (
            db.collection(COLLECTION_SOLICITACOES)
            .where(filter=FieldFilter("usuario_id", "==", usuario_id))
            .limit(_LIMITE_SOLICITACOES_USUARIO)
            .stream()
        )
        resolvidas = 0
        for doc in docs:
            if (doc.to_dict() or {}).get("status") != "pendente":
                continue
            doc.reference.update(
                {
                    "status": "concluida",
                    "data_resolucao": firestore.SERVER_TIMESTAMP,
                    "admin_id": admin_id,
                    "admin_nome": admin_nome,
                }
            )
            resolvidas += 1
        return resolvidas
    except Exception:
        logger.exception(
            "Erro ao resolver solicitações de exclusão LGPD pendentes: usuario_id=%s", usuario_id
        )
        return 0
