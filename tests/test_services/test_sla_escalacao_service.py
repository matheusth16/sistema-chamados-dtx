"""Testes do serviço sla_escalacao_service (Fase 6 — Escada A / Fase 7 — Escada B).

Fase 2 (Marco 7): as 3 funções de scan (processar_escada_a/processar_avisos_
resolucao/processar_escada_b) rodam contra Postgres real (fixture db_session)
via Chamado.salvar()/get_by_id()/atualizar_campos() — substitui o antigo mock
de db.collection("chamados").where(...).stream(). data_abertura é imutável
via API pública (server_default no insert); os testes que precisam controlá-la
usam _forcar_data_abertura(), que escreve direto na linha (só em teste)."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app import db as db_module
from app.db.models.chamado import ChamadoRow
from app.models import Chamado
from app.services.sla_escalacao_service import (
    calcular_nivel_esperado_escada_a,
    processar_escada_a,
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
    previsao_atendimento: datetime | None = None,
    status: str = "Aberto",
) -> int:
    chamado = Chamado(
        categoria=categoria,
        tipo_solicitacao="Corretiva",
        descricao="Teste",
        responsavel="Resp",
        area="Engenharia",
        status=status,
        numero_chamado=_numero_unico(),
        escalacao_resposta_nivel=nivel,
    )
    chamado_id = chamado.salvar()
    assert chamado_id is not None
    if data_abertura is not None:
        _forcar_data_abertura(chamado_id, data_abertura)
    if previsao_atendimento is not None:
        chamado.atualizar_campos(previsao_atendimento=previsao_atendimento)
    return chamado_id


_NAO_INFORMADO = object()


def _criar_chamado_em_atendimento(
    *,
    responsavel_id: str | None = "resp_1",
    data_em_atendimento=_NAO_INFORMADO,
    categoria: str = "Manutenção",
    alerta_50: bool = False,
    alerta_80: bool = False,
    nivel_b: int = 0,
    previsao_atendimento: datetime | None = None,
) -> int:
    """data_em_atendimento default = _dt(2024, 6, 3, 9, 0) (equivalente ao antigo
    _make_doc_atendimento). Passe data_em_atendimento=None explicitamente pros
    testes que precisam do campo realmente vazio (coluna nullable)."""
    chamado = Chamado(
        categoria=categoria,
        tipo_solicitacao="Corretiva",
        descricao="Teste",
        responsavel="Resp",
        responsavel_id=responsavel_id or None,
        area="Engenharia",
        status="Em Atendimento",
        numero_chamado=_numero_unico(),
        escalacao_resolucao_nivel=nivel_b,
        alerta_supervisor_50_enviado=alerta_50,
        alerta_supervisor_80_enviado=alerta_80,
    )
    chamado_id = chamado.salvar()
    assert chamado_id is not None
    valor_data_em_atendimento = (
        _dt(2024, 6, 3, 9, 0) if data_em_atendimento is _NAO_INFORMADO else data_em_atendimento
    )
    if valor_data_em_atendimento is not None:
        chamado.atualizar_campos(data_em_atendimento=valor_data_em_atendimento)
    if previsao_atendimento is not None:
        chamado.atualizar_campos(previsao_atendimento=previsao_atendimento)
    return chamado_id


def _mock_usuario(email: str = "resp@dtx.aero"):
    u = MagicMock()
    u.email = email
    return u


# ---------------------------------------------------------------------------
# calcular_nivel_esperado_escada_a — unit puro
# ---------------------------------------------------------------------------


def test_calcular_nivel_esperado_limites():
    """Testa todos os limites dos thresholds (0/59/60/119/120/179/180/239/240 min)."""
    assert calcular_nivel_esperado_escada_a(0) == 0
    assert calcular_nivel_esperado_escada_a(59) == 0
    assert calcular_nivel_esperado_escada_a(60) == 1
    assert calcular_nivel_esperado_escada_a(119) == 1
    assert calcular_nivel_esperado_escada_a(120) == 2
    assert calcular_nivel_esperado_escada_a(179) == 2
    assert calcular_nivel_esperado_escada_a(180) == 3
    assert calcular_nivel_esperado_escada_a(239) == 3
    assert calcular_nivel_esperado_escada_a(240) == 4
    assert calcular_nivel_esperado_escada_a(999) == 4


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
# processar_escada_a
# ---------------------------------------------------------------------------


def test_escada_a_dispara_nivel_1_apos_1h_util():
    """Aberto 09:00 segunda → agora 10:01 (61 min úteis) → nível 1 + e-mail gestor_setor."""
    abertura = _dt(2024, 6, 3, 9, 0)  # segunda-feira
    agora = _dt(2024, 6, 3, 10, 1)  # 61 min úteis

    chamado_id = _criar_chamado_aberto(data_abertura=abertura)

    with (
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
        ) as mock_notif,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Manutenção": "gestor@dtx.aero"},
        ),
    ):
        resultado = processar_escada_a(agora=agora)

    assert resultado["escalados"] == 1
    assert resultado["emails"] == 1
    assert resultado["erros"] == 0
    mock_notif.assert_called_once()
    assert Chamado.get_by_id(chamado_id).escalacao_resposta_nivel == 1


def test_escada_a_nivel_1_usa_email_do_setor_do_chamado():
    """Nível 1: quando o setor do chamado está no mapa, usa o e-mail DAQUELE setor."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 3, 10, 1)  # 61 min úteis → nível 1

    chamado_id = _criar_chamado_aberto(data_abertura=abertura, categoria="Qualidade")

    with (
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
        ) as mock_notif,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Qualidade": "qualidade@dtx.aero"},
        ),
    ):
        resultado = processar_escada_a(agora=agora)

    assert resultado["emails"] == 1
    mock_notif.assert_called_once()
    kwargs = mock_notif.call_args.kwargs
    assert kwargs["chamado_id"] == chamado_id
    assert kwargs["nivel"] == 1
    assert kwargs["email_dest"] == "qualidade@dtx.aero"
    assert kwargs["chamado_data"]["categoria"] == "Qualidade"


def test_escada_a_nivel_1_sem_fallback_quando_setor_sem_gestor_cadastrado():
    """Nível 1: setor do chamado não tem gestor_setor cadastrado → sem e-mail (sem
    fallback flat — fonte única de verdade é o cadastro real de usuários)."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 3, 10, 1)

    _criar_chamado_aberto(data_abertura=abertura, categoria="Manutenção")

    with (
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
        ) as mock_notif,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Qualidade": "qualidade@dtx.aero"},  # não tem "Manutenção"
        ),
    ):
        resultado = processar_escada_a(agora=agora)

    assert resultado["emails"] == 0
    assert resultado["escalados"] == 1  # nível incrementa mesmo sem e-mail
    mock_notif.assert_not_called()


def test_escada_a_nivel_2_ignora_mapa_de_setor():
    """Nível 2+: usa o mapa de níveis superiores (company-wide) — mapa de setor
    (nível 1) é construído (uma vez por execução), mas seu valor não é usado."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 3, 11, 1)  # 121 min úteis, nivel_atual=1 → sobe pra 2

    _criar_chamado_aberto(nivel=1, data_abertura=abertura, categoria="Qualidade")

    with (
        patch("app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"),
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Qualidade": "qualidade@dtx.aero"},
        ) as mock_mapa,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_niveis_superiores",
            return_value={"gerente_producao": "producao@dtx.aero"},
        ) as mock_superiores,
    ):
        resultado = processar_escada_a(agora=agora)

    assert resultado["emails"] == 1
    mock_superiores.assert_called_once()
    mock_mapa.assert_called_once()  # construído (uma vez por execução), mas o valor não é usado p/ nível 2


def test_processar_escada_a_monta_mapa_gestor_setor_uma_vez_por_execucao():
    """Múltiplos chamados na mesma execução → _construir_mapa_gestor_setor roda 1 vez só (evita N+1)."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 3, 10, 1)

    _criar_chamado_aberto(data_abertura=abertura, categoria="Qualidade")
    _criar_chamado_aberto(data_abertura=abertura, categoria="TI")

    with (
        patch("app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"),
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={},
        ) as mock_mapa,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_niveis_superiores",
            return_value={},
        ) as mock_superiores,
    ):
        resultado = processar_escada_a(agora=agora)

    assert resultado["processados"] == 2
    mock_mapa.assert_called_once()
    mock_superiores.assert_called_once()


def test_escada_a_nao_dispara_durante_almoco():
    """Aberto 11:00 → agora 12:00 (30 min úteis — almoço não conta) → sem escalada."""
    # 11:00-11:30 = 30 min úteis; 11:30-12:00 = almoço
    abertura = _dt(2024, 6, 3, 11, 0)
    agora = _dt(2024, 6, 3, 12, 0)

    chamado_id = _criar_chamado_aberto(data_abertura=abertura)

    with patch(
        "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
    ) as mock_notif:
        resultado = processar_escada_a(agora=agora)

    assert resultado["escalados"] == 0
    assert resultado["emails"] == 0
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_resposta_nivel == 0


def test_escada_a_nao_dispara_fora_janela_1645():
    """Sexta 16:00 abertura → 16:45 (30 min úteis, fora do expediente) → sem escalada."""
    # 16:00-16:30 = 30 min úteis; 16:30-16:45 = fora do expediente
    abertura = _dt(2024, 6, 7, 16, 0)  # sexta-feira
    agora = _dt(2024, 6, 7, 16, 45)  # após 16:30

    chamado_id = _criar_chamado_aberto(data_abertura=abertura)

    with patch(
        "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
    ) as mock_notif:
        resultado = processar_escada_a(agora=agora)

    assert resultado["escalados"] == 0
    assert resultado["emails"] == 0
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_resposta_nivel == 0


def test_escada_a_ignora_em_atendimento():
    """Chamado Em Atendimento não escala (guard defensivo em _processar_chamado_escada_a
    — a query real já filtra por status='Aberto', então este é um teste direto da
    função interna, não do scan completo)."""
    from app.services.sla_escalacao_service import _processar_chamado_escada_a

    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 3, 10, 5)

    chamado_id = _criar_chamado_aberto(status="Em Atendimento", data_abertura=abertura)
    row = Chamado.get_by_id(chamado_id)

    stats = {"escalados": 0, "emails": 0, "adiados": 0, "pulados_fora_janela": 0}
    with patch(
        "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
    ) as mock_notif:
        # Passa o próprio Chamado (tem .to_dict()/.id, mesma interface usada pela função)
        _processar_chamado_escada_a(row, agora, stats, {}, {})

    assert stats["escalados"] == 0
    mock_notif.assert_not_called()


def test_escada_a_idempotente_nao_reescala_mesmo_nivel():
    """Nível 1, 90 min úteis (>60, <120) → permanece no nível 1; sem nova notificação."""
    # 09:00 → 10:30 = 90 min úteis — nivel_esperado=1, nivel_atual=1 → skip
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 3, 10, 30)

    chamado_id = _criar_chamado_aberto(nivel=1, data_abertura=abertura)

    with patch(
        "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
    ) as mock_notif:
        resultado = processar_escada_a(agora=agora)

    assert resultado["escalados"] == 0
    assert resultado["emails"] == 0
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_resposta_nivel == 1


def test_escada_a_um_nivel_por_execucao():
    """150 min úteis, nível 0 → sobe apenas para nível 1 (não pula para 2)."""
    # 08:00 → 10:30 = 150 min úteis — nivel_esperado=2, nivel_atual=0 → apenas +1 = nível 1
    abertura = _dt(2024, 6, 3, 8, 0)
    agora = _dt(2024, 6, 3, 10, 30)  # 150 min (tudo antes do almoço)

    chamado_id = _criar_chamado_aberto(nivel=0, data_abertura=abertura)

    with patch("app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"):
        resultado = processar_escada_a(agora=agora)

    assert resultado["escalados"] == 1
    assert Chamado.get_by_id(chamado_id).escalacao_resposta_nivel == 1  # não pula para 2


def test_escada_a_nivel_2_apos_2h_util():
    """09:00 → 11:01 (121 min úteis), nível atual 1 → sobe para nível 2."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 3, 11, 1)  # 121 min úteis (antes do almoço 11:30)

    chamado_id = _criar_chamado_aberto(nivel=1, data_abertura=abertura)

    with (
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
        ) as mock_notif,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_niveis_superiores",
            return_value={"gerente_producao": "prod@dtx.aero"},
        ),
    ):
        resultado = processar_escada_a(agora=agora)

    assert resultado["escalados"] == 1
    assert resultado["emails"] == 1
    mock_notif.assert_called_once()
    assert Chamado.get_by_id(chamado_id).escalacao_resposta_nivel == 2


def test_escada_a_sem_email_config_incrementa_sem_enviar():
    """Nenhum usuário cadastrado com nivel_gestao (autouse desta suíte já garante
    Usuario.get_all=[]) → nível incrementado mas sem e-mail (evitar loop infinito)."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 3, 10, 5)  # 65 min úteis → nivel_esperado=1

    chamado_id = _criar_chamado_aberto(nivel=0, data_abertura=abertura)

    with patch(
        "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
    ) as mock_notif:
        resultado = processar_escada_a(agora=agora)

    assert resultado["escalados"] == 1
    assert resultado["emails"] == 0
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_resposta_nivel == 1


# Guard defensivo "chamado sem data_abertura" (código antigo do serviço) ficou
# inalcançável nesta migração: Chamado.__init__ faz
# `self.data_abertura = data_abertura or firestore.SERVER_TIMESTAMP`, então
# passar data_abertura=None sempre vira o sentinel SERVER_TIMESTAMP — não tem
# como construir (nem via _from_row/duck-typing, nem via Postgres real, já
# que a coluna é NOT NULL) um Chamado com data_abertura genuinamente None.
# Teste removido; guard mantido no código como defesa em profundidade inerte.


def test_escada_a_firestore_erro_retorna_stats_com_erro():
    """Erro na consulta ao banco → stats["erros"]=1, sem escalada."""
    agora = _dt(2024, 6, 3, 10, 5)

    with patch("app.services.sla_escalacao_service.db_module") as mock_db_module:
        mock_db_module.SessionLocal.side_effect = Exception("Postgres unavailable")
        resultado = processar_escada_a(agora=agora)

    assert resultado["erros"] == 1
    assert resultado["escalados"] == 0


def test_escada_a_excecao_por_chamado_nao_para_processamento():
    """Exceção em um chamado não interrompe o processamento dos demais."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 3, 10, 5)

    _criar_chamado_aberto(data_abertura=abertura)
    _criar_chamado_aberto(data_abertura=abertura)

    chamadas = {"n": 0}

    def _minutos_side_effect(*a, **kw):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise RuntimeError("erro simulado")
        return 65

    with (
        patch("app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"),
        patch(
            "app.services.sla_escalacao_service.minutos_uteis_entre",
            side_effect=_minutos_side_effect,
        ),
    ):
        resultado = processar_escada_a(agora=agora)

    assert resultado["erros"] == 1
    assert resultado["escalados"] == 1
    assert resultado["processados"] == 2


def test_escada_a_fora_janela_threshold_atingido_nao_incrementa():
    """Threshold atingido mas job roda fora da janela → pulados_fora_janela++, sem incremento."""
    # Abertura segunda 09:00; agora segunda 17:00 (após 16:30 = fora do expediente)
    # Minutos úteis: 09:00–11:30 + 13:00–16:30 = 360 min
    # nivel_esperado=4, nivel_atual=3 → threshold atingido
    # agora (17:00) fora da janela → pulados_fora_janela++, sem update
    abertura = _dt(2024, 6, 3, 9, 0)  # segunda 09:00
    agora = _dt(2024, 6, 3, 17, 0)  # segunda 17:00 (fora do expediente)

    chamado_id = _criar_chamado_aberto(nivel=3, data_abertura=abertura)

    with patch(
        "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
    ) as mock_notif:
        resultado = processar_escada_a(agora=agora)

    assert resultado["escalados"] == 0
    assert resultado["emails"] == 0
    assert resultado["pulados_fora_janela"] == 1
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_resposta_nivel == 3


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
# calcular_nivel_esperado_escada_b + processar_escada_b (Fase 7)
# ---------------------------------------------------------------------------


def test_calcular_nivel_esperado_escada_b_limites():
    """Testa todos os limites dos thresholds B: 0/239/240/479/480/719/720 min úteis."""
    from app.services.sla_escalacao_service import calcular_nivel_esperado_escada_b

    assert calcular_nivel_esperado_escada_b(0) == 1  # >= 0 min → nível 1
    assert calcular_nivel_esperado_escada_b(239) == 1  # < 240 → nível 1
    assert calcular_nivel_esperado_escada_b(240) == 2  # >= 240 (4h úteis) → nível 2
    assert calcular_nivel_esperado_escada_b(479) == 2  # < 480 → nível 2
    assert calcular_nivel_esperado_escada_b(480) == 3  # >= 480 (8h úteis) → nível 3
    assert calcular_nivel_esperado_escada_b(719) == 3  # < 720 → nível 3
    assert calcular_nivel_esperado_escada_b(720) == 4  # >= 720 (12h úteis) → nível 4
    assert calcular_nivel_esperado_escada_b(999) == 4  # teto


def test_escada_b_projetos_deadline_2_dias_uteis():
    """Projetos: deadline = 2 dias úteis. Chamado aberto segunda 09:00, agora quarta 10:00.
    Deadline = terça 16:30 → agora > deadline → minutos_uteis_apos_deadline > 0 → nível 1."""
    from app.services.sla_escalacao_service import processar_escada_b

    # segunda 09:00 → deadline = terça 16:30 (2 dias úteis)
    segunda_09h = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 5, 10, 0)  # quarta 10:00 > terça 16:30

    chamado_id = _criar_chamado_em_atendimento(
        data_em_atendimento=segunda_09h,
        categoria="Projetos",
        nivel_b=0,
    )

    with (
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
        ) as mock_notif,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Projetos": "gestor@dtx.aero"},
        ),
    ):
        resultado = processar_escada_b(agora=agora)

    assert resultado["escalados"] >= 1
    assert resultado["erros"] == 0
    mock_notif.assert_called_once()
    assert Chamado.get_by_id(chamado_id).escalacao_resolucao_nivel == 1


def test_escada_b_padrao_deadline_3_dias_uteis():
    """Não-Projetos: deadline = 3 dias úteis. Chamado aberto segunda 09:00, agora quarta 10:00.
    Deadline = quarta 16:30 → agora < deadline → sem escalada."""
    from app.services.sla_escalacao_service import processar_escada_b

    segunda_09h = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 5, 10, 0)  # quarta 10:00 < quarta 16:30

    chamado_id = _criar_chamado_em_atendimento(
        data_em_atendimento=segunda_09h,
        categoria="Manutenção",
        nivel_b=0,
    )

    with patch(
        "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
    ) as mock_notif:
        resultado = processar_escada_b(agora=agora)

    assert resultado["escalados"] == 0
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_resolucao_nivel == 0


def test_calcular_deadline_resolucao_aog_usa_minutos_corridos():
    """AOG: deadline = data_em_atendimento + SLA_AOG_MINUTOS_RESOLUCAO_DEADLINE minutos
    corridos (calendário), não dias úteis — aeronave parada não espera expediente."""
    from datetime import timedelta

    from app.services.sla_escalacao_service import calcular_deadline_resolucao
    from config import Config

    inicio = _dt(2024, 6, 3, 9, 0)  # segunda 09:00
    resultado = calcular_deadline_resolucao(inicio, "AOG")

    assert resultado == inicio + timedelta(minutes=Config.SLA_AOG_MINUTOS_RESOLUCAO_DEADLINE)


def test_escada_b_aog_escala_fora_da_janela_de_expediente():
    """AOG: prazo (240min corridos) vencido num sábado de madrugada ainda deve escalar —
    ignora pode_enviar_notificacao_agora, ao contrário de um chamado normal."""
    from app.services.sla_escalacao_service import processar_escada_b

    # sábado 00:00 em atendimento -> deadline AOG = sábado 04:00 (240 min corridos)
    sabado_00h = _dt(2024, 6, 8, 0, 0)
    agora = _dt(2024, 6, 8, 5, 0)  # sábado 05:00, 1h após deadline — fora de qualquer expediente

    chamado_id = _criar_chamado_em_atendimento(
        data_em_atendimento=sabado_00h,
        categoria="AOG",
        nivel_b=0,
    )

    with (
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
        ) as mock_notif,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"AOG": "gestor@dtx.aero"},
        ),
    ):
        resultado = processar_escada_b(agora=agora)

    assert resultado["pulados_fora_janela"] == 0
    assert resultado["escalados"] == 1
    mock_notif.assert_called_once()
    assert Chamado.get_by_id(chamado_id).escalacao_resolucao_nivel == 1


def test_escada_b_idempotente_nao_reescala_mesmo_nivel():
    """Nível 1 já gravado e minutos_uteis_apos_deadline == 100 → nivel_esperado=1 → skip."""
    from app.services.sla_escalacao_service import processar_escada_b

    agora = _dt(2024, 6, 5, 10, 0)
    chamado_id = _criar_chamado_em_atendimento(
        data_em_atendimento=_dt(2024, 6, 3, 9, 0),
        categoria="Projetos",
        nivel_b=1,
    )

    with (
        patch("app.services.sla_escalacao_service.minutos_uteis_entre", return_value=100),
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
        ) as mock_notif,
        patch("app.services.sla_escalacao_service.calcular_deadline_resolucao") as mock_deadline,
    ):
        # deadline no passado (já vencido)
        mock_deadline.return_value = _dt(2024, 6, 4, 16, 30)
        resultado = processar_escada_b(agora=agora)

    assert resultado["escalados"] == 0
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_resolucao_nivel == 1


def test_escada_b_nivel_1_usa_email_do_setor_do_chamado():
    """Escada B nível 1: usa o e-mail do setor do chamado quando presente no mapa."""
    from app.services.sla_escalacao_service import processar_escada_b

    agora = _dt(2024, 6, 5, 10, 0)
    chamado_id = _criar_chamado_em_atendimento(
        data_em_atendimento=_dt(2024, 6, 3, 9, 0),
        categoria="Projetos",  # deadline de 2 dias úteis — já vencido em 'agora'
        nivel_b=0,
    )

    with (
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
        ) as mock_notif,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Projetos": "projetos@dtx.aero"},
        ),
    ):
        resultado = processar_escada_b(agora=agora)

    assert resultado["emails"] == 1
    mock_notif.assert_called_once()
    kwargs = mock_notif.call_args.kwargs
    assert kwargs["chamado_id"] == chamado_id
    assert kwargs["nivel"] == 1
    assert kwargs["email_dest"] == "projetos@dtx.aero"


def test_escada_b_nivel_1_sem_fallback_quando_setor_sem_gestor_cadastrado():
    """Escada B nível 1: setor do chamado sem gestor_setor cadastrado → sem e-mail
    (sem fallback flat — fonte única de verdade é o cadastro real de usuários)."""
    from app.services.sla_escalacao_service import processar_escada_b

    agora = _dt(2024, 6, 5, 10, 0)
    _criar_chamado_em_atendimento(
        data_em_atendimento=_dt(2024, 6, 3, 9, 0),
        categoria="Projetos",  # deadline de 2 dias úteis — já vencido em 'agora'
        nivel_b=0,
    )

    with (
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
        ) as mock_notif,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Qualidade": "qualidade@dtx.aero"},  # não tem "Projetos"
        ),
    ):
        resultado = processar_escada_b(agora=agora)

    assert resultado["emails"] == 0
    assert resultado["escalados"] == 1  # nível incrementa mesmo sem e-mail
    mock_notif.assert_not_called()


def test_escada_b_sem_email_config_incrementa_sem_notificar():
    """Nenhum usuário cadastrado com nivel_gestao (autouse desta suíte já garante
    Usuario.get_all=[]) → nível incrementado, sem e-mail."""
    from app.services.sla_escalacao_service import processar_escada_b

    agora = _dt(2024, 6, 5, 10, 0)
    chamado_id = _criar_chamado_em_atendimento(
        data_em_atendimento=_dt(2024, 6, 3, 9, 0),
        categoria="Projetos",
        nivel_b=0,
    )

    with patch(
        "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
    ) as mock_notif:
        resultado = processar_escada_b(agora=agora)

    assert resultado["escalados"] == 1
    assert resultado["emails"] == 0
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_resolucao_nivel == 1


def test_escada_b_sem_data_em_atendimento_pula():
    """Chamado sem data_em_atendimento é ignorado com log warning."""
    from app.services.sla_escalacao_service import processar_escada_b

    agora = _dt(2024, 6, 5, 10, 0)
    chamado_id = _criar_chamado_em_atendimento(
        data_em_atendimento=None, categoria="Projetos", nivel_b=0
    )

    with patch(
        "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
    ) as mock_notif:
        resultado = processar_escada_b(agora=agora)

    assert resultado["processados"] == 1
    assert resultado["escalados"] == 0
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_resolucao_nivel == 0


def test_escada_b_fora_janela_nao_escala():
    """Threshold B atingido mas agora fora da janela útil → pulados_fora_janela++, sem escalada."""
    from app.services.sla_escalacao_service import processar_escada_b

    # Data em atendimento: segunda 09:00; agora: quarta 17:00 (fora do expediente após 16:30)
    segunda_09h = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 5, 17, 0)  # quarta 17:00 — fora da janela

    chamado_id = _criar_chamado_em_atendimento(
        data_em_atendimento=segunda_09h,
        categoria="Projetos",
        nivel_b=0,
    )

    with patch(
        "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
    ) as mock_notif:
        resultado = processar_escada_b(agora=agora)

    assert resultado["escalados"] == 0
    assert resultado["pulados_fora_janela"] == 1
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_resolucao_nivel == 0


def test_escada_b_firestore_erro_retorna_stats_com_erro():
    """Erro na consulta ao banco → stats['erros']=1, sem escaladas."""
    from app.services.sla_escalacao_service import processar_escada_b

    agora = _dt(2024, 6, 5, 10, 0)

    with patch("app.services.sla_escalacao_service.db_module") as mock_db_module:
        mock_db_module.SessionLocal.side_effect = Exception("Postgres unavailable")
        resultado = processar_escada_b(agora=agora)

    assert resultado["erros"] == 1
    assert resultado["escalados"] == 0


# ── Previsão de atendimento — gate nas Escadas A e B ───────────────────────────


def test_escada_a_com_previsao_atendimento_futura_nao_escala():
    """Chamado Aberto há 3h úteis (nível esperado 3) mas com previsao_atendimento
    no futuro deve ser pulado inteiro: sem incrementar nível, sem e-mail."""
    from app.services.sla_escalacao_service import processar_escada_a

    agora = _dt(2024, 6, 3, 12, 0)  # segunda 12h -> 3h uteis desde abertura 09h (almoco 11:30-13)
    chamado_id = _criar_chamado_aberto(
        nivel=0,
        data_abertura=_dt(2024, 6, 3, 9, 0),
        previsao_atendimento=_dt(2024, 6, 5, 9, 0),  # quarta, futuro
    )

    with patch(
        "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
    ) as mock_notif:
        resultado = processar_escada_a(agora=agora)

    assert resultado["adiados"] == 1
    assert resultado["escalados"] == 0
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_resposta_nivel == 0


def test_escada_a_com_previsao_atendimento_ja_vencida_escala_normal():
    """previsao_atendimento no passado não deve impedir a escalada normal."""
    from app.services.sla_escalacao_service import processar_escada_a

    agora = _dt(2024, 6, 3, 14, 0)  # tarde (fora do almoço 11:30-13:00)
    _criar_chamado_aberto(
        nivel=0,
        data_abertura=_dt(2024, 6, 3, 9, 0),
        previsao_atendimento=_dt(2024, 6, 1, 9, 0),  # sábado, passado
    )

    with patch("app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"):
        resultado = processar_escada_a(agora=agora)

    assert resultado["adiados"] == 0
    assert resultado["escalados"] == 1


def test_escada_b_com_previsao_atendimento_futura_nao_escala():
    """Chamado com prazo de resolução vencido, mas previsao_atendimento no futuro
    deve ser pulado inteiro: sem incrementar nível, sem e-mail."""
    from app.services.sla_escalacao_service import processar_escada_b

    segunda_09h = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 5, 10, 0)  # quarta 10:00, deadline (Projetos: 2 dias uteis) ja vencido

    chamado_id = _criar_chamado_em_atendimento(
        data_em_atendimento=segunda_09h,
        categoria="Projetos",
        nivel_b=0,
        previsao_atendimento=_dt(2024, 6, 10, 9, 0),  # semana seguinte
    )

    with patch(
        "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
    ) as mock_notif:
        resultado = processar_escada_b(agora=agora)

    assert resultado["adiados"] == 1
    assert resultado["escalados"] == 0
    mock_notif.assert_not_called()
    assert Chamado.get_by_id(chamado_id).escalacao_resolucao_nivel == 0


def test_escada_b_com_previsao_atendimento_ja_vencida_escala_normal():
    """previsao_atendimento no passado não deve impedir a escalada normal da Escada B."""
    from app.services.sla_escalacao_service import processar_escada_b

    segunda_09h = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 5, 10, 0)

    _criar_chamado_em_atendimento(
        data_em_atendimento=segunda_09h,
        categoria="Projetos",
        nivel_b=0,
        previsao_atendimento=_dt(2024, 6, 4, 9, 0),  # terça, passado
    )

    with (
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
        ) as mock_notif,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Projetos": "gestor@dtx.aero"},
        ),
    ):
        resultado = processar_escada_b(agora=agora)

    assert resultado["adiados"] == 0
    assert resultado["escalados"] == 1
    mock_notif.assert_called_once()
