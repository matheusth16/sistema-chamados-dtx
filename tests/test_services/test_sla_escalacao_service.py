"""TDD: Testes unitários do serviço sla_escalacao_service (Fase 6 — Escada A)."""

from datetime import datetime
from unittest.mock import patch

import pytest

from app.services.sla_escalacao_service import (
    calcular_nivel_esperado_escada_a,
    processar_escada_a,
)


@pytest.fixture(autouse=True)
def _mapa_gestor_setor_vazio():
    """Autouse: evita que os testes desta suíte toquem o Firestore real via
    Usuario.get_all (usado por _construir_mapa_gestor_setor). Lista vazia por
    padrão, fazendo o nível 1 cair no fallback flat Config.get_gestor_email —
    igual ao comportamento anterior à resolução por setor. Mocka a dependência
    (Usuario.get_all), não a função em si, para que _construir_mapa_gestor_setor
    continue rodando de verdade em todos os testes desta suíte. Testes que
    precisam de usuários específicos usam `with patch(...)` internamente no
    mesmo alvo (tem precedência sobre este autouse).

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


def _make_doc(
    chamado_id: str = "ch_1",
    status: str = "Aberto",
    nivel: int = 0,
    data_abertura: datetime | None = None,
    numero_chamado: str = "CH-001",
    categoria: str = "Manutenção",
):
    """Cria um mock de documento Firestore."""
    from unittest.mock import MagicMock

    doc = MagicMock()
    doc.id = chamado_id
    doc.to_dict.return_value = {
        "status": status,
        "escalacao_resposta_nivel": nivel,
        "data_abertura": data_abertura or _dt(2024, 6, 3, 9, 0),
        "numero_chamado": numero_chamado,
        "categoria": categoria,
    }
    return doc


def _setup_query(mock_db, docs):
    """Configura o mock da query Firestore de processar_escada_a."""
    q = mock_db.collection.return_value.where.return_value.where.return_value
    q.limit.return_value.stream.return_value = iter(docs)


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
    from unittest.mock import MagicMock

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
        patch("app.services.sla_escalacao_service.logger") as mock_logger,
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

    doc = _make_doc(data_abertura=abertura)

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
        ) as mock_notif,
        patch(
            "app.services.sla_escalacao_service.Config.get_gestor_email",
            return_value="gestor@dtx.aero",
        ),
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_a(agora=agora)

    assert resultado["escalados"] == 1
    assert resultado["emails"] == 1
    assert resultado["erros"] == 0
    mock_notif.assert_called_once()
    # Verifica que gravou nivel 1 no Firestore
    update_call = mock_db.collection.return_value.document.return_value.update
    update_call.assert_called_once()
    payload = update_call.call_args[0][0]
    assert payload["escalacao_resposta_nivel"] == 1


def test_escada_a_nivel_1_usa_email_do_setor_do_chamado():
    """Nível 1: quando o setor do chamado está no mapa, usa o e-mail DAQUELE setor."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 3, 10, 1)  # 61 min úteis → nível 1

    doc = _make_doc(data_abertura=abertura, categoria="Qualidade")

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
        ) as mock_notif,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Qualidade": "qualidade@dtx.aero"},
        ),
        patch("app.services.sla_escalacao_service.Config.get_gestor_email") as mock_flat,
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_a(agora=agora)

    assert resultado["emails"] == 1
    mock_notif.assert_called_once_with(
        chamado_data=doc.to_dict.return_value,
        chamado_id=doc.id,
        nivel=1,
        email_dest="qualidade@dtx.aero",
    )
    mock_flat.assert_not_called()  # e-mail do setor resolveu; fallback flat nem foi consultado


def test_escada_a_nivel_1_fallback_quando_setor_sem_email():
    """Nível 1: setor do chamado não está no mapa → cai no fallback flat Config.get_gestor_email."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 3, 10, 1)

    doc = _make_doc(data_abertura=abertura, categoria="Manutenção")

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
        ) as mock_notif,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Qualidade": "qualidade@dtx.aero"},  # não tem "Manutenção"
        ),
        patch(
            "app.services.sla_escalacao_service.Config.get_gestor_email",
            return_value="fallback@dtx.aero",
        ),
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_a(agora=agora)

    assert resultado["emails"] == 1
    mock_notif.assert_called_once_with(
        chamado_data=doc.to_dict.return_value,
        chamado_id=doc.id,
        nivel=1,
        email_dest="fallback@dtx.aero",
    )


def test_escada_a_nivel_2_ignora_mapa_de_setor():
    """Nível 2+: usa só Config.get_gestor_email — mapa de setor não é nem consultado."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 3, 11, 1)  # 121 min úteis, nivel_atual=1 → sobe pra 2

    doc = _make_doc(nivel=1, data_abertura=abertura, categoria="Qualidade")

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch("app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"),
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Qualidade": "qualidade@dtx.aero"},
        ) as mock_mapa,
        patch(
            "app.services.sla_escalacao_service.Config.get_gestor_email",
            return_value="producao@dtx.aero",
        ) as mock_flat,
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_a(agora=agora)

    assert resultado["emails"] == 1
    mock_flat.assert_called_once_with("gerente_producao")
    mock_mapa.assert_called_once()  # construído (uma vez por execução), mas o valor não é usado p/ nível 2


def test_processar_escada_a_monta_mapa_gestor_setor_uma_vez_por_execucao():
    """Múltiplos chamados na mesma execução → _construir_mapa_gestor_setor roda 1 vez só (evita N+1)."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 3, 10, 1)

    docs = [
        _make_doc(chamado_id="ch_1", data_abertura=abertura, categoria="Qualidade"),
        _make_doc(chamado_id="ch_2", data_abertura=abertura, categoria="TI"),
    ]

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch("app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"),
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={},
        ) as mock_mapa,
        patch(
            "app.services.sla_escalacao_service.Config.get_gestor_email", return_value="x@dtx.aero"
        ),
    ):
        _setup_query(mock_db, docs)
        resultado = processar_escada_a(agora=agora)

    assert resultado["processados"] == 2
    mock_mapa.assert_called_once()


def test_escada_a_nao_dispara_durante_almoco():
    """Aberto 11:00 → agora 12:00 (30 min úteis — almoço não conta) → sem escalada."""
    # 11:00-11:30 = 30 min úteis; 11:30-12:00 = almoço
    abertura = _dt(2024, 6, 3, 11, 0)
    agora = _dt(2024, 6, 3, 12, 0)

    doc = _make_doc(data_abertura=abertura)

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
        ) as mock_notif,
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_a(agora=agora)

    assert resultado["escalados"] == 0
    assert resultado["emails"] == 0
    mock_notif.assert_not_called()
    mock_db.collection.return_value.document.return_value.update.assert_not_called()


def test_escada_a_nao_dispara_fora_janela_1645():
    """Sexta 16:00 abertura → 16:45 (30 min úteis, fora do expediente) → sem escalada."""
    # 16:00-16:30 = 30 min úteis; 16:30-16:45 = fora do expediente
    abertura = _dt(2024, 6, 7, 16, 0)  # sexta-feira
    agora = _dt(2024, 6, 7, 16, 45)  # após 16:30

    doc = _make_doc(data_abertura=abertura)

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
        ) as mock_notif,
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_a(agora=agora)

    assert resultado["escalados"] == 0
    assert resultado["emails"] == 0
    mock_notif.assert_not_called()
    mock_db.collection.return_value.document.return_value.update.assert_not_called()


def test_escada_a_ignora_em_atendimento():
    """Chamado Em Atendimento não escala mesmo que a query (mockada) o retorne."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 3, 10, 5)

    doc = _make_doc(status="Em Atendimento", data_abertura=abertura)

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
        ) as mock_notif,
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_a(agora=agora)

    assert resultado["escalados"] == 0
    mock_notif.assert_not_called()
    mock_db.collection.return_value.document.return_value.update.assert_not_called()


def test_escada_a_idempotente_nao_reescala_mesmo_nivel():
    """Nível 1, 90 min úteis (>60, <120) → permanece no nível 1; sem nova notificação."""
    # 09:00 → 10:30 = 90 min úteis — nivel_esperado=1, nivel_atual=1 → skip
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 3, 10, 30)

    doc = _make_doc(nivel=1, data_abertura=abertura)

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
        ) as mock_notif,
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_a(agora=agora)

    assert resultado["escalados"] == 0
    assert resultado["emails"] == 0
    mock_notif.assert_not_called()
    mock_db.collection.return_value.document.return_value.update.assert_not_called()


def test_escada_a_um_nivel_por_execucao():
    """150 min úteis, nível 0 → sobe apenas para nível 1 (não pula para 2)."""
    # 08:00 → 10:30 = 150 min úteis — nivel_esperado=2, nivel_atual=0 → apenas +1 = nível 1
    abertura = _dt(2024, 6, 3, 8, 0)
    agora = _dt(2024, 6, 3, 10, 30)  # 150 min (tudo antes do almoço)

    doc = _make_doc(nivel=0, data_abertura=abertura)

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch("app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"),
        patch(
            "app.services.sla_escalacao_service.Config.get_gestor_email",
            return_value="gestor@dtx.aero",
        ),
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_a(agora=agora)

    assert resultado["escalados"] == 1
    update_call = mock_db.collection.return_value.document.return_value.update
    payload = update_call.call_args[0][0]
    assert payload["escalacao_resposta_nivel"] == 1  # não pula para 2


def test_escada_a_nivel_2_apos_2h_util():
    """09:00 → 11:01 (121 min úteis), nível atual 1 → sobe para nível 2."""
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 3, 11, 1)  # 121 min úteis (antes do almoço 11:30)

    doc = _make_doc(nivel=1, data_abertura=abertura)

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
        ) as mock_notif,
        patch(
            "app.services.sla_escalacao_service.Config.get_gestor_email",
            return_value="prod@dtx.aero",
        ),
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_a(agora=agora)

    assert resultado["escalados"] == 1
    assert resultado["emails"] == 1
    mock_notif.assert_called_once()
    payload = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert payload["escalacao_resposta_nivel"] == 2


def test_escada_a_sem_email_config_incrementa_sem_enviar():
    """GESTOR_EMAILS vazio → nível incrementado mas sem e-mail (evitar loop infinito)."""
    # Config.get_gestor_email retorna None por padrão em ambiente de teste (GESTOR_EMAILS={})
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 3, 10, 5)  # 65 min úteis → nivel_esperado=1

    doc = _make_doc(nivel=0, data_abertura=abertura)

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
        ) as mock_notif,
        # Garante explicitamente que nenhum e-mail está configurado
        patch("config.Config.get_gestor_email", return_value=None),
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_a(agora=agora)

    assert resultado["escalados"] == 1
    assert resultado["emails"] == 0
    mock_notif.assert_not_called()
    update_call = mock_db.collection.return_value.document.return_value.update
    update_call.assert_called_once()
    payload = update_call.call_args[0][0]
    assert payload["escalacao_resposta_nivel"] == 1


def test_escada_a_sem_data_abertura_e_ignorado():
    """Chamado sem data_abertura é ignorado silenciosamente (warning logado)."""
    from unittest.mock import MagicMock

    doc = MagicMock()
    doc.id = "ch_sem_data"
    doc.to_dict.return_value = {
        "status": "Aberto",
        "escalacao_resposta_nivel": 0,
        "data_abertura": None,
    }

    agora = _dt(2024, 6, 3, 10, 5)

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
        ) as mock_notif,
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_a(agora=agora)

    assert resultado["escalados"] == 0
    assert resultado["processados"] == 1
    mock_notif.assert_not_called()
    mock_db.collection.return_value.document.return_value.update.assert_not_called()


def test_escada_a_firestore_erro_retorna_stats_com_erro():
    """Erro na query Firestore → stats["erros"]=1, sem escalada."""
    agora = _dt(2024, 6, 3, 10, 5)

    with patch("app.services.sla_escalacao_service.db") as mock_db:
        mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value.stream.side_effect = Exception(
            "Firestore unavailable"
        )
        resultado = processar_escada_a(agora=agora)

    assert resultado["erros"] == 1
    assert resultado["escalados"] == 0


def test_escada_a_excecao_por_chamado_nao_para_processamento():
    """Exceção em um chamado não interrompe o processamento dos demais."""
    from unittest.mock import MagicMock

    # doc_bom: deve ser escalado normalmente
    abertura = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 3, 10, 5)

    doc_bom = _make_doc(chamado_id="ch_bom", data_abertura=abertura)
    # doc_ruim: to_dict() levanta exceção
    doc_ruim = MagicMock()
    doc_ruim.id = "ch_ruim"
    doc_ruim.to_dict.side_effect = RuntimeError("doc corrompido")

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch("app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"),
        patch(
            "app.services.sla_escalacao_service.Config.get_gestor_email",
            return_value="gestor@dtx.aero",
        ),
    ):
        _setup_query(mock_db, [doc_ruim, doc_bom])
        resultado = processar_escada_a(agora=agora)

    assert resultado["erros"] == 1
    assert resultado["escalados"] == 1
    assert resultado["processados"] == 2


def test_escada_a_fora_janela_threshold_atingido_nao_incrementa():
    """Threshold atingido mas job roda fora da janela → pulados_fora_janela++, sem incremento."""
    # Abertura segunda 09:00; agora segunda 17:00 (após 16:30 = fora do expediente)
    # Minutos úteis: 07:00–11:30 (não conta antes de abertura) + 09:00–11:30 + 13:00–16:30 = 360 min
    # nivel_esperado=4, nivel_atual=3 → threshold atingido
    # agora (17:00) fora da janela → pulados_fora_janela++, sem update
    abertura = _dt(2024, 6, 3, 9, 0)  # segunda 09:00
    agora = _dt(2024, 6, 3, 17, 0)  # segunda 17:00 (fora do expediente)

    doc = _make_doc(nivel=3, data_abertura=abertura)

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
        ) as mock_notif,
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_a(agora=agora)

    assert resultado["escalados"] == 0
    assert resultado["emails"] == 0
    assert resultado["pulados_fora_janela"] == 1
    mock_notif.assert_not_called()
    mock_db.collection.return_value.document.return_value.update.assert_not_called()


# ---------------------------------------------------------------------------
# Helpers compartilhados — Fase 7 (avisos resolução + Escada B)
# ---------------------------------------------------------------------------


def _make_doc_atendimento(
    chamado_id: str = "ch_at_1",
    responsavel_id: str = "resp_1",
    data_em_atendimento: datetime | None = None,
    categoria: str = "Manutenção",
    alerta_50: bool = False,
    alerta_80: bool = False,
    nivel_b: int = 0,
    numero_chamado: str = "CH-AT-001",
):
    """Cria um mock de documento Firestore (Em Atendimento)."""
    from unittest.mock import MagicMock

    doc = MagicMock()
    doc.id = chamado_id
    doc.to_dict.return_value = {
        "status": "Em Atendimento",
        "responsavel_id": responsavel_id,
        "data_em_atendimento": data_em_atendimento or _dt(2024, 6, 3, 9, 0),
        "categoria": categoria,
        "alerta_supervisor_50_enviado": alerta_50,
        "alerta_supervisor_80_enviado": alerta_80,
        "escalacao_resolucao_nivel": nivel_b,
        "numero_chamado": numero_chamado,
        "area": "Engenharia",
        "tipo_solicitacao": "Corretiva",
        "descricao": "Teste",
    }
    return doc


def _setup_query_aviso(mock_db, docs):
    """Configura o mock da query Firestore single .where() (processar_avisos_resolucao)."""
    q = mock_db.collection.return_value.where.return_value
    q.limit.return_value.stream.return_value = iter(docs)


def _mock_usuario(email: str = "resp@dtx.aero"):
    from unittest.mock import MagicMock

    u = MagicMock()
    u.email = email
    return u


# ---------------------------------------------------------------------------
# processar_avisos_resolucao (Fase 7 — avisos 50%/80%)
# ---------------------------------------------------------------------------


def test_aviso_50_enviado_quando_percentual_50():
    """percentual=0.5, alerta_50=False → notificado 50% e flag gravada no Firestore."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)
    doc = _make_doc_atendimento()

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch("app.services.sla_escalacao_service.percentual_prazo_resolucao", return_value=0.5),
        patch(
            "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
        ) as mock_notif,
        patch("app.models_usuario.Usuario.get_by_id", return_value=_mock_usuario()),
    ):
        _setup_query_aviso(mock_db, [doc])
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["notificados_50"] == 1
    assert resultado["notificados_80"] == 0
    assert resultado["erros"] == 0
    mock_notif.assert_called_once()
    assert mock_notif.call_args.kwargs["marco"] == 50
    payload = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert payload.get("alerta_supervisor_50_enviado") is True


def test_aviso_80_enviado_quando_percentual_80():
    """percentual=0.85, ambas flags False → notificados 50% e 80% (dois envios)."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)
    doc = _make_doc_atendimento()

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch("app.services.sla_escalacao_service.percentual_prazo_resolucao", return_value=0.85),
        patch(
            "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
        ) as mock_notif,
        patch("app.models_usuario.Usuario.get_by_id", return_value=_mock_usuario()),
    ):
        _setup_query_aviso(mock_db, [doc])
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["notificados_50"] == 1
    assert resultado["notificados_80"] == 1
    assert mock_notif.call_count == 2


def test_aviso_50_nao_reenviado_se_ja_enviado():
    """alerta_50=True, percentual=0.6 → idempotente: nenhuma nova notificação."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)
    doc = _make_doc_atendimento(alerta_50=True)

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch("app.services.sla_escalacao_service.percentual_prazo_resolucao", return_value=0.6),
        patch(
            "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
        ) as mock_notif,
        patch("app.models_usuario.Usuario.get_by_id", return_value=_mock_usuario()),
    ):
        _setup_query_aviso(mock_db, [doc])
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["notificados_50"] == 0
    mock_notif.assert_not_called()
    mock_db.collection.return_value.document.return_value.update.assert_not_called()


def test_aviso_80_nao_reenviado_se_ja_enviado():
    """alerta_50=True e alerta_80=True, percentual=0.9 → nenhuma notificação (idempotente)."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)
    doc = _make_doc_atendimento(alerta_50=True, alerta_80=True)

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch("app.services.sla_escalacao_service.percentual_prazo_resolucao", return_value=0.9),
        patch(
            "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
        ) as mock_notif,
        patch("app.models_usuario.Usuario.get_by_id", return_value=_mock_usuario()),
    ):
        _setup_query_aviso(mock_db, [doc])
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["notificados_80"] == 0
    assert resultado["notificados_50"] == 0
    mock_notif.assert_not_called()
    mock_db.collection.return_value.document.return_value.update.assert_not_called()


def test_aviso_abaixo_50_nao_notifica():
    """percentual=0.3 (abaixo de 50%) → nenhum aviso enviado, sem update."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)
    doc = _make_doc_atendimento()

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch("app.services.sla_escalacao_service.percentual_prazo_resolucao", return_value=0.3),
        patch(
            "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
        ) as mock_notif,
    ):
        _setup_query_aviso(mock_db, [doc])
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["notificados_50"] == 0
    assert resultado["notificados_80"] == 0
    mock_notif.assert_not_called()
    mock_db.collection.return_value.document.return_value.update.assert_not_called()


def test_aviso_sem_responsavel_id_pula():
    """Chamado sem responsavel_id é ignorado — sem notificação, sem update."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)
    doc = _make_doc_atendimento(responsavel_id="")

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch("app.services.sla_escalacao_service.percentual_prazo_resolucao", return_value=0.6),
        patch(
            "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
        ) as mock_notif,
    ):
        _setup_query_aviso(mock_db, [doc])
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["processados"] == 1
    assert resultado["notificados_50"] == 0
    mock_notif.assert_not_called()
    mock_db.collection.return_value.document.return_value.update.assert_not_called()


def test_aviso_sem_data_em_atendimento_pula():
    """Chamado sem data_em_atendimento é ignorado com log warning."""
    from unittest.mock import MagicMock

    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)
    doc = MagicMock()
    doc.id = "ch_sem_data_at"
    doc.to_dict.return_value = {
        "status": "Em Atendimento",
        "responsavel_id": "resp_1",
        "data_em_atendimento": None,
        "categoria": "Manutenção",
        "alerta_supervisor_50_enviado": False,
        "alerta_supervisor_80_enviado": False,
    }

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
        ) as mock_notif,
    ):
        _setup_query_aviso(mock_db, [doc])
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["processados"] == 1
    assert resultado["notificados_50"] == 0
    mock_notif.assert_not_called()
    mock_db.collection.return_value.document.return_value.update.assert_not_called()


def test_aviso_firestore_erro_retorna_stats_com_erro():
    """Erro na query Firestore → stats['erros']=1, sem notificações."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)

    with patch("app.services.sla_escalacao_service.db") as mock_db:
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.side_effect = (
            Exception("Firestore unavailable")
        )
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["erros"] == 1
    assert resultado["notificados_50"] == 0
    assert resultado["notificados_80"] == 0


def test_aviso_nao_dispara_fora_janela_util():
    """percentual >= 50% mas agora fora da janela DTX → sem notificação, sem flag, pulados_fora_janela++."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    # 17:00 é após 16:30 — fora do expediente
    agora = _dt(2024, 6, 3, 17, 0)  # segunda 17:00
    doc = _make_doc_atendimento()

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch("app.services.sla_escalacao_service.percentual_prazo_resolucao", return_value=0.6),
        patch(
            "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
        ) as mock_notif,
    ):
        _setup_query_aviso(mock_db, [doc])
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["notificados_50"] == 0
    assert resultado["notificados_80"] == 0
    assert resultado["pulados_fora_janela"] >= 1
    mock_notif.assert_not_called()
    mock_db.collection.return_value.document.return_value.update.assert_not_called()


def test_aviso_dispara_dentro_janela_util():
    """percentual >= 50% e agora dentro da janela DTX → notificação + flag gravada."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)  # segunda 10:00 — dentro da janela
    doc = _make_doc_atendimento()

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch("app.services.sla_escalacao_service.percentual_prazo_resolucao", return_value=0.6),
        patch(
            "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
        ) as mock_notif,
        patch("app.models_usuario.Usuario.get_by_id", return_value=_mock_usuario()),
    ):
        _setup_query_aviso(mock_db, [doc])
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["notificados_50"] == 1
    assert resultado["pulados_fora_janela"] == 0
    mock_notif.assert_called_once()
    mock_db.collection.return_value.document.return_value.update.assert_called_once()


def test_aviso_50_sem_email_dispara_inapp_webpush_e_grava_flag():
    """Usuario sem email → notificar_aviso_resolucao_supervisor chamado; flag 50% gravada."""
    from app.services.sla_escalacao_service import processar_avisos_resolucao

    agora = _dt(2024, 6, 3, 10, 0)  # dentro da janela
    doc = _make_doc_atendimento()

    u_sem_email = _mock_usuario(email="")

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch("app.services.sla_escalacao_service.percentual_prazo_resolucao", return_value=0.6),
        patch(
            "app.services.sla_escalacao_service.notificar_aviso_resolucao_supervisor"
        ) as mock_notif,
        patch("app.models_usuario.Usuario.get_by_id", return_value=u_sem_email),
    ):
        _setup_query_aviso(mock_db, [doc])
        resultado = processar_avisos_resolucao(agora=agora)

    assert resultado["notificados_50"] == 1
    mock_notif.assert_called_once()
    assert mock_notif.call_args.kwargs["marco"] == 50
    # email_dest deve ser None quando usuário não tem email
    assert mock_notif.call_args.kwargs.get("email_dest") is None
    payload = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert payload.get("alerta_supervisor_50_enviado") is True


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

    doc = _make_doc_atendimento(
        chamado_id="ch_proj_1",
        data_em_atendimento=segunda_09h,
        categoria="Projetos",
        nivel_b=0,
    )

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
        ) as mock_notif,
        patch(
            "app.services.sla_escalacao_service.Config.get_gestor_email",
            return_value="gestor@dtx.aero",
        ),
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_b(agora=agora)

    assert resultado["escalados"] >= 1
    assert resultado["erros"] == 0
    mock_notif.assert_called_once()
    payload = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert payload["escalacao_resolucao_nivel"] == 1


def test_escada_b_padrao_deadline_3_dias_uteis():
    """Não-Projetos: deadline = 3 dias úteis. Chamado aberto segunda 09:00, agora quarta 10:00.
    Deadline = quarta 16:30 → agora < deadline → sem escalada."""
    from app.services.sla_escalacao_service import processar_escada_b

    segunda_09h = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 5, 10, 0)  # quarta 10:00 < quarta 16:30

    doc = _make_doc_atendimento(
        chamado_id="ch_man_1",
        data_em_atendimento=segunda_09h,
        categoria="Manutenção",
        nivel_b=0,
    )

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
        ) as mock_notif,
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_b(agora=agora)

    assert resultado["escalados"] == 0
    mock_notif.assert_not_called()
    mock_db.collection.return_value.document.return_value.update.assert_not_called()


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

    doc = _make_doc_atendimento(
        chamado_id="ch_aog_1",
        data_em_atendimento=sabado_00h,
        categoria="AOG",
        nivel_b=0,
    )

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
        ) as mock_notif,
        patch(
            "app.services.sla_escalacao_service.Config.get_gestor_email",
            return_value="gestor@dtx.aero",
        ),
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_b(agora=agora)

    assert resultado["pulados_fora_janela"] == 0
    assert resultado["escalados"] == 1
    mock_notif.assert_called_once()
    payload = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert payload["escalacao_resolucao_nivel"] == 1


def test_escada_b_idempotente_nao_reescala_mesmo_nivel():
    """Nível 1 já gravado e minutos_uteis_apos_deadline == 100 → nivel_esperado=1 → skip."""
    from app.services.sla_escalacao_service import processar_escada_b

    agora = _dt(2024, 6, 5, 10, 0)
    doc = _make_doc_atendimento(
        data_em_atendimento=_dt(2024, 6, 3, 9, 0),
        categoria="Projetos",
        nivel_b=1,
    )

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch("app.services.sla_escalacao_service.minutos_uteis_entre", return_value=100),
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
        ) as mock_notif,
        patch("app.services.sla_escalacao_service.calcular_deadline_resolucao") as mock_deadline,
    ):
        # deadline no passado (já vencido)
        mock_deadline.return_value = _dt(2024, 6, 4, 16, 30)
        _setup_query(mock_db, [doc])
        resultado = processar_escada_b(agora=agora)

    assert resultado["escalados"] == 0
    mock_notif.assert_not_called()
    mock_db.collection.return_value.document.return_value.update.assert_not_called()


def test_escada_b_nivel_1_usa_email_do_setor_do_chamado():
    """Escada B nível 1: usa o e-mail do setor do chamado quando presente no mapa."""
    from app.services.sla_escalacao_service import processar_escada_b

    agora = _dt(2024, 6, 5, 10, 0)
    doc = _make_doc_atendimento(
        data_em_atendimento=_dt(2024, 6, 3, 9, 0),
        categoria="Projetos",  # deadline de 2 dias úteis — já vencido em 'agora'
        nivel_b=0,
    )

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
        ) as mock_notif,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Projetos": "projetos@dtx.aero"},
        ),
        patch("app.services.sla_escalacao_service.Config.get_gestor_email") as mock_flat,
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_b(agora=agora)

    assert resultado["emails"] == 1
    mock_notif.assert_called_once_with(
        chamado_data=doc.to_dict.return_value,
        chamado_id=doc.id,
        nivel=1,
        email_dest="projetos@dtx.aero",
    )
    mock_flat.assert_not_called()


def test_escada_b_nivel_1_fallback_quando_setor_sem_email():
    """Escada B nível 1: setor fora do mapa → cai no fallback flat Config.get_gestor_email."""
    from app.services.sla_escalacao_service import processar_escada_b

    agora = _dt(2024, 6, 5, 10, 0)
    doc = _make_doc_atendimento(
        data_em_atendimento=_dt(2024, 6, 3, 9, 0),
        categoria="Projetos",  # deadline de 2 dias úteis — já vencido em 'agora'
        nivel_b=0,
    )

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
        ) as mock_notif,
        patch(
            "app.services.sla_escalacao_service._construir_mapa_gestor_setor",
            return_value={"Qualidade": "qualidade@dtx.aero"},  # não tem "Projetos"
        ),
        patch(
            "app.services.sla_escalacao_service.Config.get_gestor_email",
            return_value="fallback@dtx.aero",
        ),
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_b(agora=agora)

    assert resultado["emails"] == 1
    mock_notif.assert_called_once_with(
        chamado_data=doc.to_dict.return_value,
        chamado_id=doc.id,
        nivel=1,
        email_dest="fallback@dtx.aero",
    )


def test_escada_b_sem_email_config_incrementa_sem_notificar():
    """Config.get_gestor_email retorna None → nível incrementado, sem e-mail."""
    from app.services.sla_escalacao_service import processar_escada_b

    agora = _dt(2024, 6, 5, 10, 0)
    doc = _make_doc_atendimento(
        data_em_atendimento=_dt(2024, 6, 3, 9, 0),
        categoria="Projetos",
        nivel_b=0,
    )

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
        ) as mock_notif,
        patch("config.Config.get_gestor_email", return_value=None),
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_b(agora=agora)

    assert resultado["escalados"] == 1
    assert resultado["emails"] == 0
    mock_notif.assert_not_called()
    payload = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert payload["escalacao_resolucao_nivel"] == 1


def test_escada_b_sem_data_em_atendimento_pula():
    """Chamado sem data_em_atendimento é ignorado com log warning."""
    from unittest.mock import MagicMock

    from app.services.sla_escalacao_service import processar_escada_b

    agora = _dt(2024, 6, 5, 10, 0)
    doc = MagicMock()
    doc.id = "ch_sem_data_b"
    doc.to_dict.return_value = {
        "status": "Em Atendimento",
        "responsavel_id": "resp_1",
        "data_em_atendimento": None,
        "categoria": "Projetos",
        "escalacao_resolucao_nivel": 0,
    }

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
        ) as mock_notif,
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_b(agora=agora)

    assert resultado["processados"] == 1
    assert resultado["escalados"] == 0
    mock_notif.assert_not_called()
    mock_db.collection.return_value.document.return_value.update.assert_not_called()


def test_escada_b_fora_janela_nao_escala():
    """Threshold B atingido mas agora fora da janela útil → pulados_fora_janela++, sem escalada."""
    from app.services.sla_escalacao_service import processar_escada_b

    # Data em atendimento: segunda 09:00; agora: quarta 17:00 (fora do expediente após 16:30)
    segunda_09h = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 5, 17, 0)  # quarta 17:00 — fora da janela

    doc = _make_doc_atendimento(
        data_em_atendimento=segunda_09h,
        categoria="Projetos",
        nivel_b=0,
    )

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
        ) as mock_notif,
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_b(agora=agora)

    assert resultado["escalados"] == 0
    assert resultado["pulados_fora_janela"] == 1
    mock_notif.assert_not_called()
    mock_db.collection.return_value.document.return_value.update.assert_not_called()


def test_escada_b_firestore_erro_retorna_stats_com_erro():
    """Erro na query Firestore → stats['erros']=1, sem escaladas."""
    from app.services.sla_escalacao_service import processar_escada_b

    agora = _dt(2024, 6, 5, 10, 0)

    with patch("app.services.sla_escalacao_service.db") as mock_db:
        mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value.stream.side_effect = Exception(
            "Firestore unavailable"
        )
        resultado = processar_escada_b(agora=agora)

    assert resultado["erros"] == 1
    assert resultado["escalados"] == 0


# ── Previsão de atendimento — gate nas Escadas A e B ───────────────────────────


def test_escada_a_com_previsao_atendimento_futura_nao_escala():
    """Chamado Aberto há 3h úteis (nível esperado 3) mas com previsao_atendimento
    no futuro deve ser pulado inteiro: sem incrementar nível, sem e-mail."""
    from app.services.sla_escalacao_service import processar_escada_a

    agora = _dt(2024, 6, 3, 12, 0)  # segunda 12h -> 3h uteis desde abertura 09h (almoco 11:30-13)
    doc = _make_doc(
        chamado_id="ch_previsao_a",
        status="Aberto",
        nivel=0,
        data_abertura=_dt(2024, 6, 3, 9, 0),
    )
    doc.to_dict.return_value["previsao_atendimento"] = _dt(2024, 6, 5, 9, 0)  # quarta, futuro

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"
        ) as mock_notif,
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_a(agora=agora)

    assert resultado["adiados"] == 1
    assert resultado["escalados"] == 0
    mock_notif.assert_not_called()
    mock_db.collection.return_value.document.return_value.update.assert_not_called()


def test_escada_a_com_previsao_atendimento_ja_vencida_escala_normal():
    """previsao_atendimento no passado não deve impedir a escalada normal."""
    from app.services.sla_escalacao_service import processar_escada_a

    agora = _dt(2024, 6, 3, 14, 0)  # tarde (fora do almoço 11:30-13:00)
    doc = _make_doc(
        chamado_id="ch_previsao_a_vencida",
        status="Aberto",
        nivel=0,
        data_abertura=_dt(2024, 6, 3, 9, 0),
    )
    doc.to_dict.return_value["previsao_atendimento"] = _dt(2024, 6, 1, 9, 0)  # sábado, passado

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch("app.services.sla_escalacao_service.notificar_escalada_resposta_gerencial"),
        patch(
            "app.services.sla_escalacao_service.Config.get_gestor_email",
            return_value="gestor@dtx.aero",
        ),
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_a(agora=agora)

    assert resultado["adiados"] == 0
    assert resultado["escalados"] == 1


def test_escada_b_com_previsao_atendimento_futura_nao_escala():
    """Chamado com prazo de resolução vencido, mas previsao_atendimento no futuro
    deve ser pulado inteiro: sem incrementar nível, sem e-mail."""
    from app.services.sla_escalacao_service import processar_escada_b

    segunda_09h = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 5, 10, 0)  # quarta 10:00, deadline (Projetos: 2 dias uteis) ja vencido

    doc = _make_doc_atendimento(
        chamado_id="ch_previsao_b",
        data_em_atendimento=segunda_09h,
        categoria="Projetos",
        nivel_b=0,
    )
    doc.to_dict.return_value["previsao_atendimento"] = _dt(2024, 6, 10, 9, 0)  # semana seguinte

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
        ) as mock_notif,
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_b(agora=agora)

    assert resultado["adiados"] == 1
    assert resultado["escalados"] == 0
    mock_notif.assert_not_called()
    mock_db.collection.return_value.document.return_value.update.assert_not_called()


def test_escada_b_com_previsao_atendimento_ja_vencida_escala_normal():
    """previsao_atendimento no passado não deve impedir a escalada normal da Escada B."""
    from app.services.sla_escalacao_service import processar_escada_b

    segunda_09h = _dt(2024, 6, 3, 9, 0)
    agora = _dt(2024, 6, 5, 10, 0)

    doc = _make_doc_atendimento(
        chamado_id="ch_previsao_b_vencida",
        data_em_atendimento=segunda_09h,
        categoria="Projetos",
        nivel_b=0,
    )
    doc.to_dict.return_value["previsao_atendimento"] = _dt(2024, 6, 4, 9, 0)  # terça, passado

    with (
        patch("app.services.sla_escalacao_service.db") as mock_db,
        patch(
            "app.services.sla_escalacao_service.notificar_escalada_resolucao_gerencial"
        ) as mock_notif,
        patch(
            "app.services.sla_escalacao_service.Config.get_gestor_email",
            return_value="gestor@dtx.aero",
        ),
    ):
        _setup_query(mock_db, [doc])
        resultado = processar_escada_b(agora=agora)

    assert resultado["adiados"] == 0
    assert resultado["escalados"] == 1
    mock_notif.assert_called_once()
