"""Helpers de criação de dados de teste contra Postgres real (Fase 2).

Usados pelos testes que precisam de um Chamado persistido de verdade (não mock
de query Firestore) — ex.: rotas que fazem Chamado.get_by_id(chamado_id) e
esperam um ID numérico real. Requer a fixture `db_session` no teste chamador.
"""

from app.models import Chamado


def make_chamado(
    *,
    solicitante_id: str = "solicitante_teste",
    solicitante_nome: str = "Solicitante Teste",
    categoria: str = "Manutencao",
    tipo_solicitacao: str = "Manutencao",
    descricao: str = "Descrição de teste",
    responsavel: str = "Responsável Teste",
    responsavel_id: str | None = "resp1",
    area: str | None = None,
    status: str = "Aberto",
    prioridade: int | None = 1,
    gate: str | None = None,
    rl_codigo: str | None = None,
    numero_chamado: str | None = None,
    supervisor_ids_com_acesso: list | None = None,
    participantes: list | None = None,
    observadores: list | None = None,
    **overrides,
) -> Chamado:
    """Cria e persiste um Chamado real no banco de teste; retorna o objeto recarregado."""
    chamado = Chamado(
        categoria=categoria,
        tipo_solicitacao=tipo_solicitacao,
        descricao=descricao,
        responsavel=responsavel,
        responsavel_id=responsavel_id,
        solicitante_id=solicitante_id,
        solicitante_nome=solicitante_nome,
        area=area,
        status=status,
        prioridade=prioridade,
        gate=gate,
        rl_codigo=rl_codigo,
        numero_chamado=numero_chamado,
        supervisor_ids_com_acesso=supervisor_ids_com_acesso,
        participantes=participantes,
        observadores=observadores,
        **overrides,
    )
    chamado_id = chamado.salvar()
    assert chamado_id is not None, "Chamado.salvar() retornou None — falha ao persistir"
    return Chamado.get_by_id(chamado_id)
