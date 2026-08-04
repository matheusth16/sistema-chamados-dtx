"""Autoatendimento LGPD sobre a própria conta: exportação (portabilidade) e
solicitação de exclusão (direito de exclusão).

A exclusão em si NÃO é executada aqui — este serviço só registra o pedido.
Um admin revisa e executa via os fluxos já existentes (desativar + anonimizar
em app/routes/usuarios.py), mesmo padrão de segurança usado hoje para ações
administrativas irreversíveis sobre contas.

Fase 2 (Marco 10): exportar_dados_usuario() lê a tabela `chamados` do
Postgres via ChamadoRow — nenhuma função deste módulo toca Firestore.
"""

import csv
import io
import logging

from sqlalchemy import func, select, update

from app import db as db_module
from app.db.models.apoio import SolicitacaoLgpdRow
from app.db.models.chamado import ChamadoRow
from app.services.historico_usuario_service import registrar_historico_usuario

logger = logging.getLogger(__name__)

# Neutraliza CSV/Excel formula injection — mesma lista de excel_export_service._safe_cell.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# Um solicitante nunca terá mais que isso de chamados próprios — evita ler a
# coleção inteira; mesmo padrão de chamados_listagem_service._FALLBACK_LIMIT.
_LIMITE_CHAMADOS_EXPORT = 200

# Idem para solicitações de exclusão do próprio usuário (praticamente sempre 0 ou 1).
_LIMITE_SOLICITACOES_USUARIO = 20

# Teto de segurança para a listagem administrativa de solicitações pendentes.
_LIMITE_SOLICITACOES_PENDENTES = 1000


def exportar_dados_usuario(usuario) -> dict:
    """Monta o export LGPD (direito de portabilidade) dos dados do próprio usuário."""
    with db_module.SessionLocal() as session:
        rows = (
            session.execute(
                select(ChamadoRow)
                .where(ChamadoRow.solicitante_id == usuario.id)
                .limit(_LIMITE_CHAMADOS_EXPORT)
            )
            .scalars()
            .all()
        )
    chamados = [
        {
            "id": row.id,
            "numero_chamado": row.numero_chamado,
            "tipo_solicitacao": row.tipo_solicitacao,
            "descricao": row.descricao,
            "categoria": row.categoria,
            "status": row.status,
            "data_criacao": str(row.data_abertura) if row.data_abertura else None,
        }
        for row in rows
    ]

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


def _safe_cell(valor):
    """Previne CSV/Excel formula injection — prefixa aspa simples em valores
    que começam com caractere de fórmula (Excel/Sheets interpretam como texto)."""
    if isinstance(valor, str) and valor.startswith(_FORMULA_PREFIXES):
        return "'" + valor
    return valor


def exportar_dados_usuario_csv(usuario) -> str:
    """Mesmos dados de exportar_dados_usuario(), em CSV (LGPD — portabilidade)."""
    dados = exportar_dados_usuario(usuario)
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Conta"])
    for chave, valor in dados["conta"].items():
        writer.writerow([chave, _safe_cell(valor)])

    writer.writerow([])
    writer.writerow(["Chamados Criados"])
    colunas = [
        "id",
        "numero_chamado",
        "tipo_solicitacao",
        "descricao",
        "categoria",
        "status",
        "data_criacao",
    ]
    writer.writerow(colunas)
    for chamado in dados["chamados_criados"]:
        writer.writerow([_safe_cell(chamado.get(coluna)) for coluna in colunas])

    return output.getvalue()


def possui_solicitacao_exclusao_pendente(usuario_id: str) -> bool:
    """Verifica se o usuário já tem uma solicitação de exclusão em aberto."""
    try:
        with db_module.SessionLocal() as session:
            return (
                session.execute(
                    select(SolicitacaoLgpdRow.id)
                    .where(SolicitacaoLgpdRow.usuario_id == usuario_id)
                    .where(SolicitacaoLgpdRow.status == "pendente")
                    .limit(1)
                ).first()
                is not None
            )
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
        with db_module.SessionLocal() as session, session.begin():
            row = SolicitacaoLgpdRow(
                usuario_id=usuario.id,
                usuario_nome=usuario.nome,
                usuario_email=usuario.email,
                tipo="exclusao",
                status="pendente",
            )
            session.add(row)
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
        with db_module.SessionLocal() as session:
            rows = (
                session.execute(
                    select(SolicitacaoLgpdRow.usuario_id)
                    .where(SolicitacaoLgpdRow.status == "pendente")
                    .limit(_LIMITE_SOLICITACOES_PENDENTES)
                )
                .scalars()
                .all()
            )
            return set(rows)
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
        with db_module.SessionLocal() as session, session.begin():
            resultado = session.execute(
                update(SolicitacaoLgpdRow)
                .where(SolicitacaoLgpdRow.usuario_id == usuario_id)
                .where(SolicitacaoLgpdRow.status == "pendente")
                .values(
                    status="concluida",
                    data_resolucao=func.now(),
                    admin_id=admin_id,
                    admin_nome=admin_nome,
                )
            )
            return resultado.rowcount
    except Exception:
        logger.exception(
            "Erro ao resolver solicitações de exclusão LGPD pendentes: usuario_id=%s", usuario_id
        )
        return 0
