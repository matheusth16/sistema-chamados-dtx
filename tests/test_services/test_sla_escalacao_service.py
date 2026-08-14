"""Testes do serviço sla_escalacao_service — motor de escalonamento unificado
(TAT único por categoria, contado de data_abertura) + avisos 50%/80%.

As funções de scan (processar_escalonamento/processar_avisos_resolucao) rodam
contra Postgres real (fixture db_session) via Chamado.salvar()/get_by_id()/
atualizar_campos(). data_abertura é imutável via API pública (server_default
no insert); os testes que precisam controlá-la usam _forcar_data_abertura(),
que escreve direto na linha (só em teste)."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app import db as db_module
from app.db.models.chamado import ChamadoRow
from app.models import Chamado
from app.services.sla_escalacao_service import (
    calcular_cadencia_minutos,
    calcular_deadline_inicial,
    processar_escalonamento,
)

pytestmark = pytest.mark.usefixtures("db_session")

_contador_numero = {"n": 0}


@pytest.fixture(autouse=True)
def _mapa_gestor_setor_vazio():
    """Autouse: evita que os testes desta suíte toquem o Firestore real via
    Usuario.get_all (usado por _construir_mapa_gestor_setor e
    _construir_mapa_niveis_superiores). Lista vazia por padrão, fazendo qualquer
    nível cair em "sem gestor cadastrado" (sem e-mail, sem fallback flat — fonte
    única de verdade é o cadastro real de usuários). Mocka a dependência
    (Usuario.get_all), não as funções em si, para que elas continuem rodando de
    verdade em todos os testes desta suíte. Testes que precisam de usuários
    específicos usam `with patch(...)` internamente no mesmo alvo (tem
    precedência sobre este autouse).

    _construir_mapa_gestor_setor cacheia Usuario.get_all via get_static_cached
    (F-XX economia de leituras no job de 10 em 10 min) — limpa a chave antes e
    depois de cada teste para que o `with patch(...)` interno de cada teste não
    seja mascarado por um resultado cacheado de um teste anterior.
    """
    from app.cache import static_cache_delete

    static_cache_delete("sla_gestores_usuarios")
    with patch("app.models_usuario.Usuario.get_all", return_value=[]):
        yield
    static_cache_delete("sla_gestores_usuarios")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dt(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """Datetime naive em BRT (America/Sao_Paulo) — convenção de teste DTX."""
    return datetime(year, month, day, hour, minute)


def _numero_unico() -> str:
    _contador_numero["n"] += 1
    return f"CH-TEST-{_contador_numero['n']:04d}"


def _forcar_data_abertura(chamado_id: int, dt: datetime) -> None:
    """data_abertura é server_default (imutável via to_row_kwargs/atualizar_campos)
    — os testes de janela útil precisam controlá-la, então escrevem direto na
    linha (só em teste; nunca faça isso em código de produção)."""
    with db_module.SessionLocal() as session, session.begin():
        row = session.get(ChamadoRow, chamado_id)
        row.data_abertura = dt


def _criar_chamado_aberto(
    *,
    nivel: int = 0,
    data_abertura: datetime | None = None,
    categoria: str = "Manutenção",
    area: str = "Engenharia",
    previsao_atendimento: datetime | None = None,
    status: str = "Aberto",
    proximo_tick_em: datetime | None = None,
    pre_aviso_nivel_enviado: int | None = None,
) -> int:
    chamado = Chamado(
        categoria=categoria,
        tipo_solicitacao="Corretiva",
        descricao="Teste",
        responsavel="Resp",
        area=area,
        status=status,
        numero_chamado=_numero_unico(),
        escalacao_nivel=nivel,
    )
    chamado_id = chamado.salvar()
    assert chamado_id is not None
    if data_abertura is not None:
        _forcar_data_abertura(chamado_id, data_abertura)
    updates: dict = {}
    if previsao_atendimento is not None:
        updates["previsao_atendimento"] = previsao_atendimento
    if proximo_tick_em is not None:
        updates["escalacao_proximo_tick_em"] = proximo_tick_em
    if pre_aviso_nivel_enviado is not None:
        updates["escalacao_pre_aviso_nivel_enviado"] = pre_aviso_nivel_enviado
    if updates:
        chamado.atualizar_campos(**updates)
    return chamado_id


_NAO_INFORMADO = object()


def _criar_chamado_em_atendimento(
    *,
    responsavel_id: str | None = "resp_1",
    data_em_atendimento=_NAO_INFORMADO,
    data_abertura: datetime | None = None,
    categoria: str = "Manutenção",
    area: str = "Engenharia",
    alerta_50: bool = False,
    alerta_80: bool = False,
    nivel: int = 0,
    previsao_atendimento: datetime | None = None,
    proximo_tick_em: datetime | None = None,
    pre_aviso_nivel_enviado: int | None = None,
) -> int:
    """data_em_atendimento default = _dt(2024, 6, 3, 9, 0) (equivalente ao antigo
    _make_doc_atendimento). Passe data_em_atendimento=None explicitamente pros
    testes que precisam do campo realmente vazio (coluna nullable). O TAT do
    motor de escalonamento é contado de data_abertura, não de
    data_em_atendimento — passe data_abertura explicitamente nos testes que
    dependem disso."""
    chamado = Chamado(
        categoria=categoria,
        tipo_solicitacao="Corretiva",
        descricao="Teste",
        responsavel="Resp",
        responsavel_id=responsavel_id or None,
        area=area,
        status="Em Atendimento",
        numero_chamado=_numero_unico(),
        escalacao_nivel=nivel,
        alerta_supervisor_50_enviado=alerta_50,
        alerta_supervisor_80_enviado=alerta_80,
    )
    chamado_id = chamado.salvar()
    assert chamado_id is not None
    if data_abertura is not None:
        _forcar_data_abertura(chamado_id, data_abertura)
    valor_data_em_atendimento = (
        _dt(2024, 6, 3, 9, 0) if data_em_atendimento is _NAO_INFORMADO else data_em_atendimento
    )
    updates: dict = {}
    if valor_data_em_atendimento is not None:
        updates["data_em_atendimento"] = valor_data_em_atendimento
    if previsao_atendimento is not None:
        updates["previsao_atendimento"] = previsao_atendimento
    if proximo_tick_em is not None:
        updates["escalacao_proximo_tick_em"] = proximo_tick_em
    if pre_aviso_nivel_enviado is not None:
        updates["escalacao_pre_aviso_nivel_enviado"] = pre_aviso_nivel_enviado
    if updates:
        chamado.atualizar_campos(**updates)
    return chamado_id


def _mock_usuario(email: str = "resp@dtx.aero"):
    u = MagicMock()
    u.email = email
    return u


# ---------------------------------------------------------------------------
# calcular_deadline_inicial / calcular_cadencia_minutos — unit puro
# ---------------------------------------------------------------------------


def test_calcular_deadline_inicial_normal_3_dias_uteis():
    """Não Aplicável: TAT = 3 dias úteis, contado de data_abertura."""
    abertura = _dt(2024, 6, 3, 9, 0)  # segunda
    resultado = calcular_deadline_inicial("Manutenção", "Aberto", abertura)
    assert resultado == _dt(2024, 6, 5, 16, 30)  # quarta 16:30


def test_calcular_deadline_inicial_projetos_2_dias_uteis():
    """Projetos: TAT = 2 dias úteis, contado de data_abertura."""
    abertura = _dt(2024, 6, 3, 9, 0)  # segunda
    resultado = calcular_deadline_inicial("Projetos", "Aberto", abertura)
    assert resultado == _dt(2024, 6, 4, 16, 30)  # terça 16:30


def test_calcular_deadline_inicial_aog_aberto_usa_limiar_claim_1h():
    """AOG ainda Aberto: usa o limiar de reivindicação (1h corrida), não o TAT de 24h."""
    abertura = _dt(2024, 6, 5, 22, 0)  # quarta 22:00
    resultado = calcular_deadline_inicial("AOG", "Aberto", abertura)
    assert resultado == _dt(2024, 6, 5, 23, 0)  # quarta 23:00 — 1h corrida depois


def test_calcular_deadline_inicial_aog_em_atendimento_usa_tat_24h():
    """AOG já Em Atendimento (assumido antes do limiar de 1h): usa o TAT de 24h
    corridas, não o limiar de reivindicação — o alvo muda de acordo com o status
    atual, não fica preso ao valor calculado quando nivel ainda era 0."""
    abertura = _dt(2024, 6, 5, 22, 20)  # quarta 22:20
    resultado = calcular_deadline_inicial("AOG", "Em Atendimento", abertura)
    assert resultado == _dt(2024, 6, 6, 22, 20)  # quinta 22:20 — 24h corridas depois


def test_calcular_cadencia_minutos_normal_nao_assumido_2h():
    assert calcular_cadencia_minutos("Manutenção", "Aberto") == 120


def test_calcular_cadencia_minutos_normal_assumido_1h():
    assert calcular_cadencia_minutos("Manutenção", "Em Atendimento") == 60


def test_calcular_cadencia_minutos_projetos_segue_mesma_regra_normal():
    assert calcular_cadencia_minutos("Projetos", "Aberto") == 120
    assert calcular_cadencia_minutos("Projetos", "Em Atendimento") == 60


def test_calcular_cadencia_minutos_aog_sempre_1h_mesmo_nao_assumido():
    """AOG usa sempre a cadência mais agressiva (assumido), nas duas fases —
    já é prioridade máxima, não faz sentido escalar mais devagar."""
    assert calcular_cadencia_minutos("AOG", "Aberto") == 60
    assert calcular_cadencia_minutos("AOG", "Em Atendimento") == 60


# ---------------------------------------------------------------------------
# _construir_mapa_gestor_setor — o gestor de setor é sempre um usuário do
# sistema (nivel_gestao == 'gestor_setor' + .areas), nunca e-mail solto.
# ---------------------------------------------------------------------------


def _make_usuario_gestor(email, areas, nivel_gestao="gestor_setor", ativo=True):
    u = MagicMock()
    u.email = email
    u.areas = areas
    u.nivel_gestao = nivel_gestao
    u.ativo = ativo
    return u


def test_mapa_gestor_setor_cacheia_usuario_get_all():
    """Duas chamadas seguidas a _construir_mapa_gestor_setor() (Escada A + Escada B
    no mesmo ciclo do job) devem ler Usuario.get_all apenas 1 vez, não 2 — o job
    roda a cada 10 min e a lista de gestores quase nunca muda (F-XX leituras)."""
    from app.services.sla_escalacao_service import _construir_mapa_gestor_setor

    usuarios = [_make_usuario_gestor("qualidade@dtx.aero", ["Qualidade"])]

    with patch("app.models_usuario.Usuario.get_all", return_value=usuarios) as mock_get_all:
        _construir_mapa_gestor_setor()
        _construir_mapa_gestor_setor()

    assert mock_get_all.call_count == 1, (
        "_construir_mapa_gestor_setor não está cacheando Usuario.get_all — "
        f"chamado {mock_get_all.call_count}x em 2 chamadas seguidas"
    )


def test_mapa_gestor_setor_mapeia_areas_do_gestor():
    """Usuário com nivel_gestao=gestor_setor mapeia cada área dele pro seu e-mail."""
    from app.services.sla_escalacao_service import _construir_mapa_gestor_setor

    usuarios = [_make_usuario_gestor("qualidade@dtx.aero", ["Qualidade"])]

    with patch("app.models_usuario.Usuario.get_all", return_value=usuarios):
        mapa = _construir_mapa_gestor_setor()

    assert mapa == {"Qualidade": "qualidade@dtx.aero"}


def test_mapa_gestor_setor_usuario_com_multiplas_areas():
    """Um gestor_setor com várias áreas aparece em todas elas no mapa."""
    from app.services.sla_escalacao_service import _construir_mapa_gestor_setor

    usuarios = [_make_usuario_gestor("multi@dtx.aero", ["Qualidade", "TI"])]

    with patch("app.models_usuario.Usuario.get_all", return_value=usuarios):
        mapa = _construir_mapa_gestor_setor()

    assert mapa == {"Qualidade": "multi@dtx.aero", "TI": "multi@dtx.aero"}


def test_mapa_gestor_setor_ignora_usuario_sem_nivel_gestao():
    """Supervisor comum (sem nivel_gestao) não entra no mapa mesmo tendo áreas."""
    from app.services.sla_escalacao_service import _construir_mapa_gestor_setor

    usuarios = [_make_usuario_gestor("supervisor@dtx.aero", ["Qualidade"], nivel_gestao=None)]

    with patch("app.models_usuario.Usuario.get_all", return_value=usuarios):
        mapa = _construir_mapa_gestor_setor()

    assert mapa == {}


def test_mapa_gestor_setor_ignora_outros_niveis_de_gestao():
    """Usuário com nivel_gestao de outro nível (ex.: gm) não entra no mapa do nível 1."""
    from app.services.sla_escalacao_service import _construir_mapa_gestor_setor

    usuarios = [_make_usuario_gestor("gm@dtx.aero", ["Qualidade"], nivel_gestao="gm")]

    with patch("app.models_usuario.Usuario.get_all", return_value=usuarios):
        mapa = _construir_mapa_gestor_setor()

    assert mapa == {}


def test_mapa_gestor_setor_ignora_usuario_inativo():
    """Gestor de setor desativado não deve continuar recebendo escalações."""
    from app.services.sla_escalacao_service import _construir_mapa_gestor_setor

    usuarios = [_make_usuario_gestor("ex-gestor@dtx.aero", ["Qualidade"], ativo=False)]

    with patch("app.models_usuario.Usuario.get_all", return_value=usuarios):
        mapa = _construir_mapa_gestor_setor()

    assert mapa == {}


def test_mapa_gestor_setor_conflito_mantem_primeiro_e_loga_warning():
    """Duas pessoas marcadas como gestoras da mesma área (config inconsistente):
    mantém a primeira encontrada e loga warning, não quebra o job."""
    from app.services.sla_escalacao_service import _construir_mapa_gestor_setor

    usuarios = [
        _make_usuario_gestor("primeiro@dtx.aero", ["Qualidade"]),
        _make_usuario_gestor("segundo@dtx.aero", ["Qualidade"]),
    ]

    with (
        patch("app.models_usuario.Usuario.get_all", return_value=usuarios),
        patch("app.services.gestor_escalonamento_service.logger") as mock_logger,
    ):
        mapa = _construir_mapa_gestor_setor()

    assert mapa == {"Qualidade": "primeiro@dtx.aero"}
    mock_logger.warning.assert_called_once()


def test_mapa_gestor_setor_firestore_erro_retorna_vazio():
    """Erro ao buscar usuários não derruba o job — cai no fallback flat (mapa vazio)."""
    from app.services.sla_escalacao_service import _construir_mapa_gestor_setor

    with patch("app.models_usuario.Usuario.get_all", side_effect=Exception("boom")):
        mapa = _construir_mapa_gestor_setor()

    assert mapa == {}


# ---------------------------------------------------------------------------
# processar_escalonamento — motor unificado
# ---------------------------------------------------------------------------


def test_escalonamento_regressao_tat_conta_da_abertura_nao_do_atendimento():
    """Chamado aberto segunda, só assumido quarta — o TAT (Manutenção=3 dias
    úteis) já venceu quarta 16:30 (contado da ABERTURA), mesmo o chamado tendo
    sido assumido só quarta 09:00 (o que, no motor antigo, teria dado deadline
    sexta ~09:00 contando de data_em_atendimento). Regressão-chave da
    reformulação: TAT nunca reinicia ao assumir."""
    chamado_id = _criar_chamado_em_atendimento(
        data_abertura=_dt(2024, 6, 3, 9, 0),  # segunda
        data_em_atendimento=_dt(2024, 6, 5, 9, 0),  # quarta — assumido tarde
        categoria="Manutenção",
        nivel=0,
    )
    agora = _dt(2024, 6, 6, 9, 0)  # quinta 09:00 — após o TAT (qua 16:30), no expediente

    with (
        patch("app.services.sla_escalacao_service.notificar_escalada_gerencial") as mock_notif,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Engenharia": "gestor@dtx.aero"},
        ),
    ):
        resultado = processar_escalonamento(agora=agora)

    assert resultado["escalados"] == 1
    assert resultado["emails"] == 1
    mock_notif.assert_called_once()
    assert mock_notif.call_args.kwargs["assumido"] is True
    assert Chamado.get_by_id(chamado_id).escalacao_nivel == 1


def test_escalonamento_nao_dispara_antes_do_tat():
    abertura = _dt(2024, 6, 3, 9, 0)  # segunda — TAT (3 dias úteis) vence quarta 16:30
    agora = _dt(2024, 6, 4, 10, 0)  # terça 10:00 — bem antes

    chamado_id = _criar_chamado_aberto(data_abertura=abertura)

    with patch("app.services.sla_escalacao_service.notificar_escalada_gerencial") as mock_notif:
        resultado = processar_escalonamento(agora=agora)

    assert resultado["escalados"] == 0
    assert resultado["emails"] == 0
    assert resultado["pre_avisos"] == 0
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_nivel == 0


def test_escalonamento_aberto_no_tat_escala_cadencia_2h():
    """Ainda 'Aberto' quando o TAT vence → cadência 2h (não assumido) pro próximo tick."""
    abertura = _dt(2024, 6, 3, 9, 0)  # segunda — TAT vence quarta 16:30
    agora = _dt(2024, 6, 6, 9, 0)  # quinta 09:00 — após o TAT, no expediente

    chamado_id = _criar_chamado_aberto(data_abertura=abertura)

    with (
        patch("app.services.sla_escalacao_service.notificar_escalada_gerencial") as mock_notif,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Engenharia": "gestor@dtx.aero"},
        ),
    ):
        resultado = processar_escalonamento(agora=agora)

    assert resultado["escalados"] == 1
    mock_notif.assert_called_once()
    assert mock_notif.call_args.kwargs["assumido"] is False
    atualizado = Chamado.get_by_id(chamado_id)
    assert atualizado.escalacao_nivel == 1
    assert atualizado.escalacao_proximo_tick_em.replace(tzinfo=None) == agora + timedelta(
        minutes=120
    )


def test_escalonamento_nivel_1_usa_email_da_area_do_chamado_nao_da_categoria():
    """Regressão (2026-08-14): nível 1 deve resolver o e-mail pela ÁREA do chamado,
    nunca pela categoria — categoria só pode ser Rotina/Projetos/AOG, nenhuma bate
    com nome de área real, então usar categoria como chave nunca resolve na prática.
    categoria e área propositalmente diferentes aqui pra provar que é a área que
    importa, não a categoria."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 6, 9, 0)

    chamado_id = _criar_chamado_aberto(data_abertura=abertura, categoria="Rotina", area="Qualidade")

    with (
        patch("app.services.sla_escalacao_service.notificar_escalada_gerencial") as mock_notif,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Qualidade": "qualidade@dtx.aero"},
        ),
    ):
        resultado = processar_escalonamento(agora=agora)

    assert resultado["emails"] == 1
    mock_notif.assert_called_once()
    kwargs = mock_notif.call_args.kwargs
    assert kwargs["chamado_id"] == chamado_id
    assert kwargs["nivel"] == 1
    assert kwargs["email_dest"] == "qualidade@dtx.aero"
    assert kwargs["chamado_data"]["categoria"] == "Rotina"
    assert kwargs["chamado_data"]["area"] == "Qualidade"


def test_escalonamento_nivel_1_sem_fallback_quando_area_sem_gestor_cadastrado():
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 6, 9, 0)

    _criar_chamado_aberto(data_abertura=abertura, categoria="Rotina", area="Manutencao")

    with (
        patch("app.services.sla_escalacao_service.notificar_escalada_gerencial") as mock_notif,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Qualidade": "qualidade@dtx.aero"},  # não tem "Manutencao"
        ),
    ):
        resultado = processar_escalonamento(agora=agora)

    assert resultado["emails"] == 0
    assert resultado["escalados"] == 1  # nível incrementa mesmo sem e-mail
    mock_notif.assert_not_called()


def test_escalonamento_nivel_2_ignora_mapa_de_setor():
    """Nível 2+: usa o mapa de níveis superiores (company-wide) — mapa de setor
    (nível 1) é construído (uma vez por execução), mas seu valor não é usado."""
    abertura = _dt(2024, 6, 3, 9, 0)
    # Chamado já no nível 1, próximo tick agendado — cadência 2h (ainda Aberto)
    proximo_tick = _dt(2024, 6, 6, 9, 0)
    agora = proximo_tick

    _criar_chamado_aberto(
        nivel=1,
        data_abertura=abertura,
        categoria="Qualidade",
        proximo_tick_em=proximo_tick,
    )

    with (
        patch("app.services.sla_escalacao_service.notificar_escalada_gerencial"),
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Qualidade": "qualidade@dtx.aero"},
        ) as mock_mapa,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_niveis_superiores",
            return_value={"gerente_producao": "producao@dtx.aero"},
        ) as mock_superiores,
    ):
        resultado = processar_escalonamento(agora=agora)

    assert resultado["emails"] == 1
    mock_superiores.assert_called_once()
    mock_mapa.assert_called_once()  # construído (uma vez por execução), mas o valor não é usado p/ nível 2


def test_processar_escalonamento_monta_mapa_gestor_setor_uma_vez_por_execucao():
    """Múltiplos chamados na mesma execução → _construir_mapa_gestor_setor roda 1 vez só (evita N+1)."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 6, 9, 0)

    _criar_chamado_aberto(data_abertura=abertura, categoria="Qualidade")
    _criar_chamado_aberto(data_abertura=abertura, categoria="TI")

    with (
        patch("app.services.sla_escalacao_service.notificar_escalada_gerencial"),
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={},
        ) as mock_mapa,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_niveis_superiores",
            return_value={},
        ) as mock_superiores,
    ):
        resultado = processar_escalonamento(agora=agora)

    assert resultado["processados"] == 2
    mock_mapa.assert_called_once()
    mock_superiores.assert_called_once()


def test_escalonamento_idempotente_nao_reescala_antes_do_proximo_tick():
    """Nível 1, próximo tick agendado no futuro → não escala de novo, sem notificação."""
    abertura = _dt(2024, 6, 3, 9, 0)
    proximo_tick = _dt(2024, 6, 6, 9, 0)
    agora = _dt(2024, 6, 6, 7, 0)  # antes do próximo tick, e fora da janela de aviso (30min)

    chamado_id = _criar_chamado_aberto(
        nivel=1, data_abertura=abertura, proximo_tick_em=proximo_tick
    )

    with patch("app.services.sla_escalacao_service.notificar_escalada_gerencial") as mock_notif:
        resultado = processar_escalonamento(agora=agora)

    assert resultado["escalados"] == 0
    assert resultado["emails"] == 0
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_nivel == 1


def test_escalonamento_um_nivel_por_execucao():
    """Chama processar_escalonamento duas vezes, com o relógio avançando — cada
    chamada sobe exatamente 1 nível (nunca pula)."""
    abertura = _dt(2024, 6, 3, 9, 0)
    primeira_passagem = _dt(2024, 6, 6, 9, 0)  # após o TAT

    chamado_id = _criar_chamado_aberto(data_abertura=abertura)

    with (
        patch("app.services.sla_escalacao_service.notificar_escalada_gerencial"),
        patch("app.services.sla_escalacao_service._construir_mapa_gestor_setor", return_value={}),
        patch(
            "app.services.sla_escalacao_service._construir_mapa_niveis_superiores",
            return_value={},
        ),
    ):
        resultado_1 = processar_escalonamento(agora=primeira_passagem)
        assert Chamado.get_by_id(chamado_id).escalacao_nivel == 1

        segunda_passagem = primeira_passagem + timedelta(
            hours=2
        )  # cadência 2h, ainda no expediente
        resultado_2 = processar_escalonamento(agora=segunda_passagem)

    assert resultado_1["escalados"] == 1
    assert resultado_2["escalados"] == 1
    assert Chamado.get_by_id(chamado_id).escalacao_nivel == 2  # não pula pra 3+


def test_escalonamento_sem_email_config_incrementa_sem_enviar():
    """Nenhum usuário cadastrado com nivel_gestao (autouse desta suíte já garante
    Usuario.get_all=[]) → nível incrementado mas sem e-mail (evitar loop infinito)."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 6, 9, 0)

    chamado_id = _criar_chamado_aberto(data_abertura=abertura)

    with patch("app.services.sla_escalacao_service.notificar_escalada_gerencial") as mock_notif:
        resultado = processar_escalonamento(agora=agora)

    assert resultado["escalados"] == 1
    assert resultado["emails"] == 0
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_nivel == 1


def test_escalonamento_erro_consulta_retorna_stats_com_erro():
    agora = _dt(2024, 6, 6, 9, 0)

    with patch("app.services.sla_escalacao_service.db_module") as mock_db_module:
        mock_db_module.SessionLocal.side_effect = Exception("Postgres unavailable")
        resultado = processar_escalonamento(agora=agora)

    assert resultado["erros"] == 1
    assert resultado["escalados"] == 0


def test_escalonamento_excecao_por_chamado_nao_para_processamento():
    """Exceção em um chamado não interrompe o processamento dos demais."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 6, 9, 0)

    _criar_chamado_aberto(data_abertura=abertura)
    _criar_chamado_aberto(data_abertura=abertura)

    chamadas = {"n": 0}

    def _deadline_side_effect(*a, **kw):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise RuntimeError("erro simulado")
        return _dt(2024, 6, 5, 16, 30)  # já vencido

    with (
        patch("app.services.sla_escalacao_service.notificar_escalada_gerencial"),
        patch(
            "app.services.sla_escalacao_service.calcular_deadline_inicial",
            side_effect=_deadline_side_effect,
        ),
    ):
        resultado = processar_escalonamento(agora=agora)

    assert resultado["erros"] == 1
    assert resultado["escalados"] == 1
    assert resultado["processados"] == 2


def test_escalonamento_fora_da_janela_de_expediente_nao_incrementa():
    """TAT vencido mas job roda fora da janela → pulados_fora_janela++, sem incremento
    (Não Aplicável/Projetos respeitam expediente; AOG não — ver teste específico)."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 5, 17, 0)  # quarta 17:00 — após o TAT (16:30), mas fora do expediente

    chamado_id = _criar_chamado_aberto(data_abertura=abertura)

    with patch("app.services.sla_escalacao_service.notificar_escalada_gerencial") as mock_notif:
        resultado = processar_escalonamento(agora=agora)

    assert resultado["escalados"] == 0
    assert resultado["emails"] == 0
    assert resultado["pulados_fora_janela"] == 1
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_nivel == 0


def test_escalonamento_aog_claim_threshold_1h_dispara_antes_do_tat():
    """AOG ainda Aberto após 1h (bem antes do TAT de 24h) já escala — limiar de
    reivindicação é separado e mais cedo que o TAT."""
    abertura = _dt(2024, 6, 5, 22, 0)  # quarta 22:00 — limiar de claim: 23:00
    agora = _dt(2024, 6, 5, 23, 30)  # quarta 23:30 — após o limiar, bem antes do TAT (24h)

    chamado_id = _criar_chamado_aberto(data_abertura=abertura, categoria="AOG")

    with (
        patch("app.services.sla_escalacao_service.notificar_escalada_gerencial") as mock_notif,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Engenharia": "gestor@dtx.aero"},
        ),
    ):
        resultado = processar_escalonamento(agora=agora)

    assert resultado["escalados"] == 1
    mock_notif.assert_called_once()
    assert mock_notif.call_args.kwargs["assumido"] is False
    atualizado = Chamado.get_by_id(chamado_id)
    assert atualizado.escalacao_nivel == 1
    # cadência AOG é sempre 60min (assumido), mesmo não tendo sido reivindicado
    assert atualizado.escalacao_proximo_tick_em.replace(tzinfo=None) == agora + timedelta(
        minutes=60
    )


def test_escalonamento_aog_assumido_antes_do_claim_usa_tat_24h():
    """AOG assumido antes do limiar de 1h → escada de reivindicação nunca dispara;
    só volta a escalar se não resolvido dentro do TAT de 24h."""
    abertura = _dt(2024, 6, 5, 22, 0)  # quarta 22:00
    agora_dentro_do_claim = _dt(2024, 6, 5, 22, 40)  # 22:40 — antes do limiar de 1h (23:00)

    chamado_id = _criar_chamado_em_atendimento(
        data_abertura=abertura,
        data_em_atendimento=_dt(2024, 6, 5, 22, 30),
        categoria="AOG",
    )

    with patch("app.services.sla_escalacao_service.notificar_escalada_gerencial") as mock_notif:
        resultado = processar_escalonamento(agora=agora_dentro_do_claim)

    assert resultado["escalados"] == 0
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_nivel == 0

    # 24h depois da abertura (TAT), ainda não resolvido → agora sim escala, do zero
    agora_apos_tat = abertura + timedelta(hours=24, minutes=5)
    with (
        patch("app.services.sla_escalacao_service.notificar_escalada_gerencial") as mock_notif_2,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Engenharia": "gestor@dtx.aero"},
        ),
    ):
        resultado_2 = processar_escalonamento(agora=agora_apos_tat)

    assert resultado_2["escalados"] == 1
    mock_notif_2.assert_called_once()
    assert mock_notif_2.call_args.kwargs["assumido"] is True
    assert Chamado.get_by_id(chamado_id).escalacao_nivel == 1


def test_escalonamento_aog_ignora_janela_de_expediente():
    """AOG escala fora do expediente (madrugada/fim de semana) — ao contrário de
    Não Aplicável/Projetos."""
    abertura = _dt(2024, 6, 8, 0, 0)  # sábado 00:00 — limiar de claim: sábado 01:00
    agora = _dt(2024, 6, 8, 5, 0)  # sábado 05:00 — fora de qualquer expediente

    chamado_id = _criar_chamado_aberto(data_abertura=abertura, categoria="AOG")

    with (
        patch("app.services.sla_escalacao_service.notificar_escalada_gerencial") as mock_notif,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Engenharia": "gestor@dtx.aero"},
        ),
    ):
        resultado = processar_escalonamento(agora=agora)

    assert resultado["pulados_fora_janela"] == 0
    assert resultado["escalados"] == 1
    mock_notif.assert_called_once()
    assert Chamado.get_by_id(chamado_id).escalacao_nivel == 1


def test_escalonamento_nivel_4_nao_e_mais_processado():
    """Chamado já no nível máximo (4) não aparece mais na query — sem novos ticks."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 6, 9, 0)

    chamado_id = _criar_chamado_aberto(
        nivel=4, data_abertura=abertura, proximo_tick_em=_dt(2024, 6, 3, 10, 0)
    )

    with patch("app.services.sla_escalacao_service.notificar_escalada_gerencial") as mock_notif:
        resultado = processar_escalonamento(agora=agora)

    assert resultado["processados"] == 0
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_nivel == 4


def test_escalonamento_pre_aviso_dispara_dentro_da_janela_30min():
    abertura = _dt(2024, 6, 3, 9, 0)  # TAT vence quarta 16:30
    agora = _dt(2024, 6, 5, 16, 5)  # 25 min antes do TAT

    chamado_id = _criar_chamado_aberto(data_abertura=abertura)

    with patch(
        "app.services.sla_escalacao_service.notificar_pre_aviso_escalonamento"
    ) as mock_pre_aviso:
        resultado = processar_escalonamento(agora=agora)

    assert resultado["pre_avisos"] == 1
    assert resultado["escalados"] == 0  # tick ainda não venceu
    mock_pre_aviso.assert_called_once()
    assert mock_pre_aviso.call_args.kwargs["nivel_alvo"] == 1
    assert Chamado.get_by_id(chamado_id).escalacao_pre_aviso_nivel_enviado == 1


def test_escalonamento_pre_aviso_nao_duplica_na_mesma_janela():
    """Já avisado pro nível-alvo 1 → nova passagem do job dentro da mesma janela
    de 30min não manda de novo."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 5, 16, 10)  # ainda dentro da janela de 30min

    _criar_chamado_aberto(
        data_abertura=abertura,
        pre_aviso_nivel_enviado=1,  # já avisado pro nível-alvo 1
    )

    with patch(
        "app.services.sla_escalacao_service.notificar_pre_aviso_escalonamento"
    ) as mock_pre_aviso:
        resultado = processar_escalonamento(agora=agora)

    assert resultado["pre_avisos"] == 0
    mock_pre_aviso.assert_not_called()


def test_escalonamento_pre_aviso_reseta_pro_proximo_nivel_alvo():
    """Depois que o tick do nível 1 dispara, o dedup do aviso prévio é reavaliado
    pro nível-alvo 2 (não fica travado no valor antigo)."""
    abertura = _dt(2024, 6, 3, 9, 0)
    # Nível 1 já escalado; próximo tick (nível 2) daqui a 25 min
    proximo_tick = _dt(2024, 6, 6, 9, 25)
    agora = _dt(2024, 6, 6, 9, 0)

    _criar_chamado_aberto(
        nivel=1,
        data_abertura=abertura,
        proximo_tick_em=proximo_tick,
        pre_aviso_nivel_enviado=1,  # aviso do nível-alvo 1 (já disparado antes)
    )

    with patch(
        "app.services.sla_escalacao_service.notificar_pre_aviso_escalonamento"
    ) as mock_pre_aviso:
        resultado = processar_escalonamento(agora=agora)

    assert resultado["pre_avisos"] == 1
    mock_pre_aviso.assert_called_once()
    assert mock_pre_aviso.call_args.kwargs["nivel_alvo"] == 2


# ---------------------------------------------------------------------------
# Histórico completo — ações automáticas do motor de SLA também deixam rastro
# (achado em auditoria, 2026-08-12: só as ações manuais gravavam Histórico).
# ---------------------------------------------------------------------------


def test_escalonamento_automatico_grava_historico():
    from app.models_historico import Historico

    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 6, 9, 0)
    chamado_id = _criar_chamado_aberto(data_abertura=abertura)

    with (
        patch("app.services.sla_escalacao_service.notificar_escalada_gerencial"),
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Engenharia": "gestor@dtx.aero"},
        ),
    ):
        processar_escalonamento(agora=agora)

    eventos = Historico.get_by_chamado_id(chamado_id)
    automaticos = [e for e in eventos if e.acao == "escalonamento_automatico"]
    assert len(automaticos) == 1
    assert automaticos[0].usuario_id == "sistema"
    assert automaticos[0].valor_anterior == "0"
    assert automaticos[0].valor_novo == "1"


def test_pre_aviso_escalonamento_grava_historico():
    from app.models_historico import Historico

    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 5, 16, 5)  # 25 min antes do TAT
    chamado_id = _criar_chamado_aberto(data_abertura=abertura)

    with patch("app.services.sla_escalacao_service.notificar_pre_aviso_escalonamento"):
        processar_escalonamento(agora=agora)

    eventos = Historico.get_by_chamado_id(chamado_id)
    pre_avisos = [e for e in eventos if e.acao == "aviso_previo_escalonamento"]
    assert len(pre_avisos) == 1
    assert pre_avisos[0].usuario_id == "sistema"
    assert pre_avisos[0].valor_novo == "1"


# ---------------------------------------------------------------------------
# processar_avisos_resolucao (Fase 7 — avisos 50%/80%)
# ---------------------------------------------------------------------------


def test_aviso_50_enviado_quando_percentual_50():
    """percentual=0.5, alerta_50=False → notificado 50% e flag gravada."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)
    chamado_id = _criar_chamado_em_atendimento()

    with (
        patch("app.services.sla_escalacao_service.percentual_prazo_resolucao", return_value=0.5),
        patch(
            "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
        ) as mock_notif,
        patch("app.models_usuario.Usuario.get_by_id", return_value=_mock_usuario()),
    ):
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["notificados_50"] == 1
    assert resultado["notificados_80"] == 0
    assert resultado["erros"] == 0
    mock_notif.assert_called_once()
    assert mock_notif.call_args.kwargs["marco"] == 50
    assert Chamado.get_by_id(chamado_id).alerta_supervisor_50_enviado is True


def test_aviso_resolucao_50_grava_historico():
    from app.models_historico import Historico
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)
    chamado_id = _criar_chamado_em_atendimento()

    with (
        patch("app.services.sla_escalacao_service.percentual_prazo_resolucao", return_value=0.5),
        patch("app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"),
        patch("app.models_usuario.Usuario.get_by_id", return_value=_mock_usuario()),
    ):
        processar_avisos_resolucao(agora=agora)

    eventos = Historico.get_by_chamado_id(chamado_id)
    avisos = [e for e in eventos if e.acao == "aviso_resolucao_prazo"]
    assert len(avisos) == 1
    assert avisos[0].usuario_id == "sistema"
    assert avisos[0].valor_novo == "50%"


def test_aviso_80_enviado_quando_percentual_80():
    """percentual=0.85, ambas flags False → notificados 50% e 80% (dois envios)."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)
    _criar_chamado_em_atendimento()

    with (
        patch("app.services.sla_escalacao_service.percentual_prazo_resolucao", return_value=0.85),
        patch(
            "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
        ) as mock_notif,
        patch("app.models_usuario.Usuario.get_by_id", return_value=_mock_usuario()),
    ):
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["notificados_50"] == 1
    assert resultado["notificados_80"] == 1
    assert mock_notif.call_count == 2


def test_aviso_50_nao_reenviado_se_ja_enviado():
    """alerta_50=True, percentual=0.6 → idempotente: nenhuma nova notificação."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)
    _criar_chamado_em_atendimento(alerta_50=True)

    with (
        patch("app.services.sla_escalacao_service.percentual_prazo_resolucao", return_value=0.6),
        patch(
            "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
        ) as mock_notif,
        patch("app.models_usuario.Usuario.get_by_id", return_value=_mock_usuario()),
    ):
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["notificados_50"] == 0
    mock_notif.assert_not_called()


def test_aviso_80_nao_reenviado_se_ja_enviado():
    """alerta_50=True e alerta_80=True, percentual=0.9 → nenhuma notificação (idempotente)."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)
    _criar_chamado_em_atendimento(alerta_50=True, alerta_80=True)

    with (
        patch("app.services.sla_escalacao_service.percentual_prazo_resolucao", return_value=0.9),
        patch(
            "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
        ) as mock_notif,
        patch("app.models_usuario.Usuario.get_by_id", return_value=_mock_usuario()),
    ):
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["notificados_80"] == 0
    assert resultado["notificados_50"] == 0
    mock_notif.assert_not_called()


def test_aviso_abaixo_50_nao_notifica():
    """percentual=0.3 (abaixo de 50%) → nenhum aviso enviado."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)
    chamado_id = _criar_chamado_em_atendimento()

    with (
        patch("app.services.sla_escalacao_service.percentual_prazo_resolucao", return_value=0.3),
        patch(
            "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
        ) as mock_notif,
    ):
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["notificados_50"] == 0
    assert resultado["notificados_80"] == 0
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).alerta_supervisor_50_enviado is False


def test_aviso_sem_responsavel_id_pula():
    """Chamado sem responsavel_id é ignorado — sem notificação, sem update."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)
    _criar_chamado_em_atendimento(responsavel_id="")

    with (
        patch("app.services.sla_escalacao_service.percentual_prazo_resolucao", return_value=0.6),
        patch(
            "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
        ) as mock_notif,
    ):
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["processados"] == 1
    assert resultado["notificados_50"] == 0
    mock_notif.assert_not_called()


def test_aviso_sem_data_em_atendimento_pula():
    """Chamado sem data_em_atendimento é ignorado com log warning."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)
    # data_em_atendimento não é setada → permanece None (coluna nullable)
    _criar_chamado_em_atendimento(data_em_atendimento=None)

    with patch(
        "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
    ) as mock_notif:
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["processados"] == 1
    assert resultado["notificados_50"] == 0
    mock_notif.assert_not_called()


def test_aviso_firestore_erro_retorna_stats_com_erro():
    """Erro na consulta ao banco → stats['erros']=1, sem notificações."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)

    with patch("app.services.sla_escalacao_service.db_module") as mock_db_module:
        mock_db_module.SessionLocal.side_effect = Exception("Postgres unavailable")
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["erros"] == 1
    assert resultado["notificados_50"] == 0
    assert resultado["notificados_80"] == 0


def test_aviso_nao_dispara_fora_janela_util():
    """percentual >= 50% mas agora fora da janela DTX → sem notificação, sem flag, pulados_fora_janela++."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    # 17:00 é após 16:30 — fora do expediente
    agora = _dt(2024, 6, 3, 17, 0)  # segunda 17:00
    chamado_id = _criar_chamado_em_atendimento()

    with (
        patch("app.services.sla_escalacao_service.percentual_prazo_resolucao", return_value=0.6),
        patch(
            "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
        ) as mock_notif,
    ):
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["notificados_50"] == 0
    assert resultado["notificados_80"] == 0
    assert resultado["pulados_fora_janela"] >= 1
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).alerta_supervisor_50_enviado is False


def test_aviso_dispara_dentro_janela_util():
    """percentual >= 50% e agora dentro da janela DTX → notificação + flag gravada."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)  # segunda 10:00 — dentro da janela
    chamado_id = _criar_chamado_em_atendimento()

    with (
        patch("app.services.sla_escalacao_service.percentual_prazo_resolucao", return_value=0.6),
        patch(
            "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
        ) as mock_notif,
        patch("app.models_usuario.Usuario.get_by_id", return_value=_mock_usuario()),
    ):
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["notificados_50"] == 1
    assert resultado["pulados_fora_janela"] == 0
    mock_notif.assert_called_once()
    assert Chamado.get_by_id(chamado_id).alerta_supervisor_50_enviado is True


def test_aviso_50_sem_email_dispara_inapp_webpush_e_grava_flag():
    """Usuario sem email → notificar_aviso_resolucao_supervisor chamado; flag 50% gravada."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)  # dentro da janela
    chamado_id = _criar_chamado_em_atendimento()

    u_sem_email = _mock_usuario(email="")

    with (
        patch("app.services.sla_escalacao_service.percentual_prazo_resolucao", return_value=0.6),
        patch(
            "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
        ) as mock_notif,
        patch("app.models_usuario.Usuario.get_by_id", return_value=u_sem_email),
    ):
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["notificados_50"] == 1
    mock_notif.assert_called_once()
    assert mock_notif.call_args.kwargs["marco"] == 50
    # email_dest deve ser None quando usuário não tem email
    assert mock_notif.call_args.kwargs.get("email_dest") is None
    assert Chamado.get_by_id(chamado_id).alerta_supervisor_50_enviado is True


# ---------------------------------------------------------------------------
# Previsão de atendimento — gate no motor de escalonamento unificado
# ---------------------------------------------------------------------------


def test_escalonamento_com_previsao_atendimento_futura_nao_escala():
    """Chamado com TAT vencido mas previsao_atendimento no futuro deve ser
    pulado inteiro: sem incrementar nível, sem e-mail, sem aviso prévio."""
    agora = _dt(2024, 6, 6, 9, 0)  # após o TAT (quarta 16:30)
    chamado_id = _criar_chamado_aberto(
        nivel=0,
        data_abertura=_dt(2024, 6, 3, 9, 0),
        previsao_atendimento=_dt(2024, 6, 10, 9, 0),  # semana seguinte, futuro
    )

    with (
        patch("app.services.sla_escalacao_service.notificar_escalada_gerencial") as mock_notif,
        patch(
            "app.services.sla_escalacao_service.notificar_pre_aviso_escalonamento"
        ) as mock_pre_aviso,
    ):
        resultado = processar_escalonamento(agora=agora)

    assert resultado["adiados"] == 1
    assert resultado["escalados"] == 0
    mock_notif.assert_not_called()
    mock_pre_aviso.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_nivel == 0


def test_escalonamento_com_previsao_atendimento_ja_vencida_escala_normal():
    """previsao_atendimento no passado não deve impedir a escalada normal."""
    agora = _dt(2024, 6, 6, 9, 0)
    _criar_chamado_aberto(
        nivel=0,
        data_abertura=_dt(2024, 6, 3, 9, 0),
        previsao_atendimento=_dt(2024, 6, 1, 9, 0),  # sábado, passado
    )

    with (
        patch("app.services.sla_escalacao_service.notificar_escalada_gerencial"),
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Engenharia": "gestor@dtx.aero"},
        ),
    ):
        resultado = processar_escalonamento(agora=agora)

    assert resultado["adiados"] == 0
    assert resultado["escalados"] == 1


def test_escalonamento_em_atendimento_com_previsao_futura_nao_escala():
    """Mesmo gate vale pro chamado já assumido (fase 'resolução')."""
    agora = _dt(2024, 6, 6, 9, 0)
    chamado_id = _criar_chamado_em_atendimento(
        data_abertura=_dt(2024, 6, 3, 9, 0),
        categoria="Projetos",
        previsao_atendimento=_dt(2024, 6, 10, 9, 0),
    )

    with patch("app.services.sla_escalacao_service.notificar_escalada_gerencial") as mock_notif:
        resultado = processar_escalonamento(agora=agora)

    assert resultado["adiados"] == 1
    assert resultado["escalados"] == 0
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_nivel == 0
