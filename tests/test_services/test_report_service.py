"""Testes para alertas de prazo e relatório semanal no report_service."""

from unittest.mock import MagicMock, patch

import pytest

from app.models import Chamado
from app.services.report_service import enviar_alertas_prazo_24h

pytestmark = pytest.mark.usefixtures("db_session")

# ── Helpers ───────────────────────────────────────────────────────────────────


def _criar_chamado_real(numero="CH-001", status="Aberto", responsavel_id="sup1") -> int:
    chamado = Chamado(
        categoria="Projetos",
        tipo_solicitacao="Manutenção",
        descricao="Descrição de teste",
        responsavel="Supervisor",
        responsavel_id=responsavel_id,
        area="Manutenção",
        solicitante_nome="Solicitante",
        status=status,
        numero_chamado=numero,
    )
    chamado_id = chamado.salvar()
    assert chamado_id is not None
    return chamado_id


def _make_usuario(email="sup@test.com", nome="Supervisor", perfil="supervisor"):
    u = MagicMock()
    u.email = email
    u.nome = nome
    u.perfil = perfil
    return u


def test_alerta_24h_nao_reenvia_quando_ja_marcado():
    """Chamado já marcado com alerta enviado deve ser ignorado."""
    chamado_marcado = {
        "id": "c1",
        "numero": "2026-001",
        "sla_label": "Em risco",
        "responsavel_id": "sup1",
        "alerta_prazo_24h_enviado_em": "2026-03-19T10:00:00Z",
    }
    with (
        patch(
            "app.services.report_service.buscar_chamados_abertos",
            return_value=[chamado_marcado],
        ),
        patch("app.services.report_service.notificar_responsavel_prazo_24h") as mock_notificar,
    ):
        resultado = enviar_alertas_prazo_24h()

    assert resultado["elegiveis"] == 0
    assert resultado["enviados"] == 0
    mock_notificar.assert_not_called()


def test_alerta_24h_marca_chamado_apos_envio():
    """Após envio do alerta 24h, deve marcar o chamado para evitar duplicidade."""
    chamado_id = _criar_chamado_real(numero="2026-002", responsavel_id="sup2")
    chamado = {
        "id": chamado_id,
        "numero": "2026-002",
        "categoria": "Projetos",
        "tipo": "Manutencao",
        "area": "Manutencao",
        "solicitante": "Solicitante",
        "sla_label": "Em risco",
        "responsavel_id": "sup2",
        "alerta_prazo_24h_enviado_em": None,
    }
    usuario = MagicMock()
    usuario.email = "sup2@dtx.aero"

    with (
        patch("app.services.report_service.buscar_chamados_abertos", return_value=[chamado]),
        patch("app.services.report_service.Usuario.get_by_id", return_value=usuario),
        patch("app.services.report_service.notificar_responsavel_prazo_24h") as mock_notificar,
    ):
        resultado = enviar_alertas_prazo_24h()

    assert resultado["elegiveis"] == 1
    assert resultado["enviados"] == 1
    mock_notificar.assert_called_once()
    assert Chamado.get_by_id(chamado_id).alerta_prazo_24h_enviado_em is not None


def test_alerta_24h_grava_historico():
    """Alerta automático de prazo 24h deixa rastro no Histórico (achado em
    auditoria, 2026-08-12)."""
    from app.models_historico import Historico

    chamado_id = _criar_chamado_real(numero="2026-003", responsavel_id="sup3")
    chamado = {
        "id": chamado_id,
        "numero": "2026-003",
        "categoria": "Projetos",
        "tipo": "Manutencao",
        "area": "Manutencao",
        "solicitante": "Solicitante",
        "sla_label": "Em risco",
        "responsavel_id": "sup3",
        "alerta_prazo_24h_enviado_em": None,
    }
    usuario = MagicMock()
    usuario.email = "sup3@dtx.aero"

    with (
        patch("app.services.report_service.buscar_chamados_abertos", return_value=[chamado]),
        patch("app.services.report_service.Usuario.get_by_id", return_value=usuario),
        patch("app.services.report_service.notificar_responsavel_prazo_24h"),
    ):
        enviar_alertas_prazo_24h()

    eventos = Historico.get_by_chamado_id(chamado_id)
    alertas = [e for e in eventos if e.acao == "alerta_prazo_24h"]
    assert len(alertas) == 1
    assert alertas[0].usuario_id == "sistema"


# ── _tabela_html ─────────────────────────────────────────────────────────────


def test_tabela_html_mostra_responsavel_do_chamado():
    """Achado no preview manual (2026-08-20): a tabela mostrava o Requester
    (solicitante) mas não quem estava responsável pelo chamado — em relatórios
    que cruzam vários responsáveis (gestor de área, níveis superiores), sem essa
    coluna não dá pra saber quem está tratando cada ticket."""
    from app.services.report_service import _tabela_html

    chamado = {
        "id": "c1",
        "numero": "CH-001",
        "categoria": "Projects",
        "tipo": "Manutenção",
        "responsavel": "Heraldo Andrade",
        "solicitante": "Bruna Eloy",
        "status": "Aberto",
        "data_abertura_fmt": "01/01/2026",
        "dias_aberto": 5,
        "sla_label": "Ok",
        "atrasado": False,
        "sla_dias": 3,
    }

    html = _tabela_html([chamado], "")

    assert "Assignee" in html
    assert "Heraldo Andrade" in html


# ── _cards_resumo_html ───────────────────────────────────────────────────────


def test_cards_resumo_html_mostra_cancelados():
    """O card de resumo do topo (níveis superiores) deve trazer também a
    contagem de cancelados da semana, ao lado de total/atrasados/setores."""
    from app.services.report_service import _cards_resumo_html

    html = _cards_resumo_html(
        total=10, atrasados=3, num_setores=2, setor_critico="IT", cancelados=4
    )

    assert ">4<" in html
    assert "Cancelled" in html


# ── buscar_chamados_abertos ───────────────────────────────────────────────────


def test_buscar_chamados_abertos_retorna_lista():
    """buscar_chamados_abertos retorna lista de dicts enriquecidos."""
    from app.services.report_service import buscar_chamados_abertos

    _criar_chamado_real()

    with patch("app.services.report_service.obter_sla_para_exibicao", return_value={"label": "Ok"}):
        result = buscar_chamados_abertos()

    assert isinstance(result, list)
    assert len(result) >= 1
    assert result[0]["numero"] == "CH-001"


def test_buscar_chamados_abertos_traduz_categoria_para_ingles():
    """categoria 'Rotina' deve vir traduzida ('Routine') — regressão do bug de
    relatório semanal em PT-BR achado em QA manual (2026-08-13): buscar_chamados_abertos
    devolvia chamado.categoria cru, sem passar por get_translated_category."""
    from app.services.report_service import buscar_chamados_abertos

    _criar_chamado_real()  # categoria="Projetos" -- também deve traduzir

    with patch("app.services.report_service.obter_sla_para_exibicao", return_value={"label": "Ok"}):
        result = buscar_chamados_abertos()

    assert result[0]["categoria"] == "Projects"


def test_buscar_chamados_abertos_retorna_vazio_sem_docs():
    """buscar_chamados_abertos retorna [] quando não há chamados."""
    from app.services.report_service import buscar_chamados_abertos

    result = buscar_chamados_abertos()

    assert result == []


def test_buscar_chamados_abertos_tolera_excecao():
    """buscar_chamados_abertos retorna [] se a consulta ao banco lançar exceção."""
    from app.services.report_service import buscar_chamados_abertos

    with patch("app.services.report_service.db_module") as mock_db_module:
        mock_db_module.SessionLocal.side_effect = Exception("Postgres error")
        result = buscar_chamados_abertos()

    assert result == []


# ── enviar_relatorio_semanal ──────────────────────────────────────────────────


def test_enviar_relatorio_semanal_sem_chamados_retorna_zeros(app):
    """Com zero chamados abertos, retorna zeros sem enviar e-mail."""
    from app.services.report_service import enviar_relatorio_semanal

    with (
        app.app_context(),
        patch("app.services.report_service.buscar_chamados_abertos", return_value=[]),
        patch("app.services.report_service.enviar_email") as mock_send,
    ):
        resultado = enviar_relatorio_semanal()

    assert resultado["enviados"] == 0
    assert resultado["total_chamados"] == 0
    mock_send.assert_not_called()


def test_enviar_relatorio_semanal_envia_para_supervisor(app):
    """Com chamados atribuídos, envia e-mail diretamente para o supervisor."""
    from app.services.report_service import enviar_relatorio_semanal

    chamados = [
        {
            "id": "c1",
            "numero": "CH-001",
            "categoria": "Projetos",
            "tipo": "Manutenção",
            "area": "Manutenção",
            "responsavel": "Supervisor",
            "responsavel_id": "sup1",
            "solicitante": "Solicitante",
            "status": "Aberto",
            "data_abertura_fmt": "01/01/2026",
            "dias_aberto": 5,
            "sla_label": "Ok",
            "atrasado": False,
            "sla_dias": 3,
            "alerta_prazo_24h_enviado_em": None,
        }
    ]
    supervisor = _make_usuario("sup@test.com", "Supervisor", "supervisor")

    with (
        app.app_context(),
        patch("app.services.report_service.buscar_chamados_abertos", return_value=chamados),
        patch("app.services.report_service.Usuario.get_by_ids", return_value={"sup1": supervisor}),
        patch("app.services.report_service.Usuario.get_all", return_value=[]),
        patch("app.services.report_service.enviar_email", return_value=(True, None)) as mock_send,
    ):
        resultado = enviar_relatorio_semanal()

    assert resultado["enviados"] == 1
    assert resultado["total_chamados"] == 1
    assert mock_send.called
    destinatario = mock_send.call_args[0][0]
    assert destinatario == "sup@test.com"


def test_enviar_relatorio_semanal_ignora_sem_responsavel(app):
    """Chamados sem responsavel_id são ignorados (não geram e-mail)."""
    from app.services.report_service import enviar_relatorio_semanal

    chamados = [
        {
            "id": "c2",
            "numero": "CH-002",
            "categoria": "Projetos",
            "tipo": "Manutenção",
            "area": "Manutenção",
            "responsavel": "",
            "responsavel_id": "",
            "solicitante": "Solicitante",
            "status": "Aberto",
            "data_abertura_fmt": "01/01/2026",
            "dias_aberto": 5,
            "sla_label": "Ok",
            "atrasado": False,
            "sla_dias": None,
            "alerta_prazo_24h_enviado_em": None,
        }
    ]

    with (
        app.app_context(),
        patch("app.services.report_service.buscar_chamados_abertos", return_value=chamados),
        patch("app.services.report_service.Usuario.get_all", return_value=[]),
        patch("app.services.report_service.enviar_email", return_value=(True, None)) as mock_send,
    ):
        resultado = enviar_relatorio_semanal()

    assert resultado["ignorados"] >= 1
    mock_send.assert_not_called()


def test_enviar_relatorio_semanal_envia_para_admin(app):
    """Admins recebem resumo consolidado diretamente via Graph API."""
    from app.services.report_service import enviar_relatorio_semanal

    chamados = [
        {
            "id": "c3",
            "numero": "CH-003",
            "categoria": "TI",
            "tipo": "Suporte",
            "area": "TI",
            "responsavel": "Supervisor",
            "responsavel_id": "sup2",
            "solicitante": "Req",
            "status": "Em Atendimento",
            "data_abertura_fmt": "01/01/2026",
            "dias_aberto": 2,
            "sla_label": "Atrasado",
            "atrasado": True,
            "sla_dias": 3,
            "alerta_prazo_24h_enviado_em": None,
        }
    ]
    supervisor = _make_usuario("sup2@test.com", "Sup2", "supervisor")
    admin = _make_usuario("admin@test.com", "Admin", "admin")

    with (
        app.app_context(),
        patch("app.services.report_service.buscar_chamados_abertos", return_value=chamados),
        patch("app.services.report_service.Usuario.get_by_ids", return_value={"sup2": supervisor}),
        patch("app.services.report_service.Usuario.get_all", return_value=[admin]),
        patch("app.services.report_service.enviar_email", return_value=(True, None)) as mock_send,
    ):
        resultado = enviar_relatorio_semanal()

    assert resultado["total_atrasados"] == 1
    assert mock_send.call_count >= 2
    destinos = [call[0][0] for call in mock_send.call_args_list]
    assert "sup2@test.com" in destinos
    assert "admin@test.com" in destinos


def test_enviar_relatorio_semanal_envia_para_admin_global(app):
    """Regressão (achado ao vivo, 2026-08-21): _enviar_resumo_admins filtrava
    perfil == "admin" estritamente, excluindo admin_global -- os 2 admin_global
    de produção (sem nivel_gestao) não recebiam o relatório semanal nenhum,
    diferente do resto do app, que trata admin_global como "admin ou mais"
    (ver Usuario.is_admin_or_above). admin_global também não cai nos outros 2
    grupos (gestor_setor / níveis superiores), que dependem de nivel_gestao,
    um eixo ortogonal a perfil."""
    from app.services.report_service import enviar_relatorio_semanal

    chamados = [
        {
            "id": "c3",
            "numero": "CH-003",
            "categoria": "TI",
            "tipo": "Suporte",
            "area": "TI",
            "responsavel": "Supervisor",
            "responsavel_id": "sup2",
            "solicitante": "Req",
            "status": "Em Atendimento",
            "data_abertura_fmt": "01/01/2026",
            "dias_aberto": 2,
            "sla_label": "Atrasado",
            "atrasado": True,
            "sla_dias": 3,
            "alerta_prazo_24h_enviado_em": None,
        }
    ]
    supervisor = _make_usuario("sup2@test.com", "Sup2", "supervisor")
    admin_global = _make_usuario("global@test.com", "Admin Global", "admin_global")

    with (
        app.app_context(),
        patch("app.services.report_service.buscar_chamados_abertos", return_value=chamados),
        patch("app.services.report_service.Usuario.get_by_ids", return_value={"sup2": supervisor}),
        patch("app.services.report_service.Usuario.get_all", return_value=[admin_global]),
        patch("app.services.report_service.enviar_email", return_value=(True, None)) as mock_send,
    ):
        enviar_relatorio_semanal()

    destinos = [call[0][0] for call in mock_send.call_args_list]
    assert "global@test.com" in destinos


def test_relatorio_semanal_usa_get_by_ids_e_nao_get_by_id(app):
    """F-24: com 3+ responsáveis distintos, deve chamar get_by_ids 1× e get_by_id 0×."""
    from app.services.report_service import enviar_relatorio_semanal

    def _make_chamado(resp_id, numero):
        return {
            "id": numero,
            "numero": numero,
            "categoria": "TI",
            "tipo": "Suporte",
            "area": "TI",
            "responsavel": f"Sup {resp_id}",
            "responsavel_id": resp_id,
            "solicitante": "Req",
            "status": "Em Atendimento",
            "data_abertura_fmt": "01/01/2026",
            "dias_aberto": 1,
            "sla_label": "No prazo",
            "atrasado": False,
            "sla_dias": None,
            "alerta_prazo_24h_enviado_em": None,
        }

    chamados = [
        _make_chamado("sup-a", "CH-001"),
        _make_chamado("sup-b", "CH-002"),
        _make_chamado("sup-c", "CH-003"),
    ]
    supervisores = {
        "sup-a": _make_usuario("supa@test.com", "Sup A", "supervisor"),
        "sup-b": _make_usuario("supb@test.com", "Sup B", "supervisor"),
        "sup-c": _make_usuario("supc@test.com", "Sup C", "supervisor"),
    }

    with (
        app.app_context(),
        patch("app.services.report_service.buscar_chamados_abertos", return_value=chamados),
        patch(
            "app.services.report_service.Usuario.get_by_ids", return_value=supervisores
        ) as mock_batch,
        patch("app.services.report_service.Usuario.get_by_id") as mock_single,
        patch("app.services.report_service.Usuario.get_all", return_value=[]),
        patch("app.services.report_service.enviar_email", return_value=(True, None)),
    ):
        resultado = enviar_relatorio_semanal()

    assert resultado["enviados"] == 3
    mock_batch.assert_called_once()
    ids_passados = set(mock_batch.call_args[0][0])
    assert ids_passados == {"sup-a", "sup-b", "sup-c"}
    mock_single.assert_not_called()


def test_enviar_relatorio_semanal_envia_para_gestor_da_area(app):
    """Achado da auditoria 2026-08-06: gestor_setor da área não recebia o
    relatório semanal (só o responsável do chamado e os admins recebiam).
    Com um chamado na área 'Manutenção' e um gestor_setor cadastrado pra essa
    área, o gestor deve receber e-mail também."""
    from app.services.report_service import enviar_relatorio_semanal

    chamados = [
        {
            "id": "c1",
            "numero": "CH-001",
            "categoria": "Projetos",
            "tipo": "Manutenção",
            "area": "Manutenção",
            "responsavel": "Supervisor",
            "responsavel_id": "sup1",
            "solicitante": "Solicitante",
            "status": "Aberto",
            "data_abertura_fmt": "01/01/2026",
            "dias_aberto": 5,
            "sla_label": "Ok",
            "atrasado": False,
            "sla_dias": 3,
            "alerta_prazo_24h_enviado_em": None,
        }
    ]
    supervisor = _make_usuario("sup@test.com", "Supervisor", "supervisor")

    with (
        app.app_context(),
        patch("app.services.report_service.buscar_chamados_abertos", return_value=chamados),
        patch("app.services.report_service.Usuario.get_by_ids", return_value={"sup1": supervisor}),
        patch("app.services.report_service.Usuario.get_all", return_value=[]),
        patch(
            "app.services.report_service.construir_mapa_gestor_setor",
            return_value={"Manutenção": "gestor.manutencao@dtx.aero"},
        ),
        patch("app.services.report_service.enviar_email", return_value=(True, None)) as mock_send,
    ):
        resultado = enviar_relatorio_semanal()

    assert resultado["enviados"] == 1  # só conta supervisores, gestor de área é à parte
    destinos = [call[0][0] for call in mock_send.call_args_list]
    assert "gestor.manutencao@dtx.aero" in destinos


def test_enviar_relatorio_semanal_nao_envia_gestor_area_sem_mapeamento(app):
    """Área sem gestor_setor cadastrado não deve gerar tentativa de envio nem erro."""
    from app.services.report_service import enviar_relatorio_semanal

    chamados = [
        {
            "id": "c1",
            "numero": "CH-001",
            "categoria": "Projetos",
            "tipo": "Manutenção",
            "area": "Área Sem Gestor",
            "responsavel": "Supervisor",
            "responsavel_id": "sup1",
            "solicitante": "Solicitante",
            "status": "Aberto",
            "data_abertura_fmt": "01/01/2026",
            "dias_aberto": 5,
            "sla_label": "Ok",
            "atrasado": False,
            "sla_dias": 3,
            "alerta_prazo_24h_enviado_em": None,
        }
    ]
    supervisor = _make_usuario("sup@test.com", "Supervisor", "supervisor")

    with (
        app.app_context(),
        patch("app.services.report_service.buscar_chamados_abertos", return_value=chamados),
        patch("app.services.report_service.Usuario.get_by_ids", return_value={"sup1": supervisor}),
        patch("app.services.report_service.Usuario.get_all", return_value=[]),
        patch("app.services.report_service.construir_mapa_gestor_setor", return_value={}),
        patch("app.services.report_service.enviar_email", return_value=(True, None)) as mock_send,
    ):
        enviar_relatorio_semanal()

    destinos = [call[0][0] for call in mock_send.call_args_list]
    assert destinos == ["sup@test.com"]


def test_enviar_relatorio_semanal_envia_para_niveis_superiores(app):
    """Gerente de Produção, Assistente de GM e GM (nivel_gestao company-wide)
    devem receber um resumo consolidado de todas as áreas, quebrado por setor
    no mesmo e-mail — diferente do gestor_setor, que só vê a própria área."""
    from app.services.report_service import enviar_relatorio_semanal

    chamados = [
        {
            "id": "c1",
            "numero": "CH-001",
            "categoria": "Projetos",
            "tipo": "Manutenção",
            "area": "Manutenção",
            "responsavel": "Supervisor",
            "responsavel_id": "sup1",
            "solicitante": "Solicitante",
            "status": "Aberto",
            "data_abertura_fmt": "01/01/2026",
            "dias_aberto": 5,
            "sla_label": "Ok",
            "atrasado": False,
            "sla_dias": 3,
            "alerta_prazo_24h_enviado_em": None,
        },
        {
            "id": "c2",
            "numero": "CH-002",
            "categoria": "TI",
            "tipo": "Suporte",
            "area": "TI",
            "responsavel": "Supervisor",
            "responsavel_id": "sup1",
            "solicitante": "Solicitante",
            "status": "Aberto",
            "data_abertura_fmt": "01/01/2026",
            "dias_aberto": 2,
            "sla_label": "Atrasado",
            "atrasado": True,
            "sla_dias": 3,
            "alerta_prazo_24h_enviado_em": None,
        },
    ]
    supervisor = _make_usuario("sup@test.com", "Supervisor", "supervisor")

    with (
        app.app_context(),
        patch("app.services.report_service.buscar_chamados_abertos", return_value=chamados),
        patch("app.services.report_service.Usuario.get_by_ids", return_value={"sup1": supervisor}),
        patch("app.services.report_service.Usuario.get_all", return_value=[]),
        patch("app.services.report_service.construir_mapa_gestor_setor", return_value={}),
        patch(
            "app.services.report_service.construir_mapa_niveis_superiores",
            return_value={
                "gerente_producao": "geprod@dtx.aero",
                "gm": "gm@dtx.aero",
            },
        ),
        patch("app.services.report_service.enviar_email", return_value=(True, None)) as mock_send,
    ):
        resultado = enviar_relatorio_semanal()

    assert resultado["enviados"] == 1  # só conta supervisores; níveis superiores são à parte
    destinos = [call[0][0] for call in mock_send.call_args_list]
    assert "geprod@dtx.aero" in destinos
    assert "gm@dtx.aero" in destinos

    # e-mail dos níveis superiores deve trazer as duas áreas no mesmo corpo
    for call in mock_send.call_args_list:
        if call[0][0] in ("geprod@dtx.aero", "gm@dtx.aero"):
            html_corpo = call[0][2]
            assert "Manut" in html_corpo
            assert "IT" in html_corpo or "TI" in html_corpo


def test_niveis_superiores_email_tem_saudacao_e_resumo_estatistico(app):
    """O e-mail dos níveis superiores deve saudar o destinatário pelo nome
    (como o do supervisor já faz) e trazer um resumo estatístico no topo:
    total aberto, total atrasado, nº de setores e o setor mais crítico."""
    from app.services.report_service import enviar_relatorio_semanal

    chamados = [
        {
            "id": "c1",
            "numero": "CH-001",
            "categoria": "Projetos",
            "tipo": "Manutenção",
            "area": "Manutenção",
            "responsavel": "Supervisor",
            "responsavel_id": "sup1",
            "solicitante": "Solicitante",
            "status": "Aberto",
            "data_abertura_fmt": "01/01/2026",
            "dias_aberto": 5,
            "sla_label": "Ok",
            "atrasado": False,
            "sla_dias": 3,
            "alerta_prazo_24h_enviado_em": None,
        },
        {
            "id": "c2",
            "numero": "CH-002",
            "categoria": "TI",
            "tipo": "Suporte",
            "area": "TI",
            "responsavel": "Supervisor",
            "responsavel_id": "sup1",
            "solicitante": "Solicitante",
            "status": "Aberto",
            "data_abertura_fmt": "01/01/2026",
            "dias_aberto": 2,
            "sla_label": "Atrasado",
            "atrasado": True,
            "sla_dias": 3,
            "alerta_prazo_24h_enviado_em": None,
        },
    ]
    supervisor = _make_usuario("sup@test.com", "Supervisor", "supervisor")
    gm = _make_usuario("gm@dtx.aero", "Ana Torres", "supervisor")

    with (
        app.app_context(),
        patch("app.services.report_service.buscar_chamados_abertos", return_value=chamados),
        patch("app.services.report_service.Usuario.get_by_ids", return_value={"sup1": supervisor}),
        patch("app.services.report_service.Usuario.get_all", return_value=[]),
        patch("app.services.report_service.construir_mapa_gestor_setor", return_value={}),
        patch(
            "app.services.report_service.construir_mapa_niveis_superiores",
            return_value={"gm": "gm@dtx.aero"},
        ),
        patch("app.services.report_service.Usuario.get_by_email", return_value=gm),
        patch("app.services.report_service.enviar_email", return_value=(True, None)) as mock_send,
    ):
        enviar_relatorio_semanal()

    chamada_gm = next(c for c in mock_send.call_args_list if c[0][0] == "gm@dtx.aero")
    html_corpo = chamada_gm[0][2]
    assert "Ana Torres" in html_corpo
    assert "GM" in html_corpo
    assert ">2<" in html_corpo  # total aberto
    assert ">1<" in html_corpo  # total atrasado
    assert ">2<" in html_corpo  # nº de setores (Manutenção + TI)


def test_niveis_superiores_email_linka_para_gestor_dashboard_nao_admin(app):
    """Achado: o botão do e-mail apontava pra /admin — rota que exige
    perfil supervisor/admin/admin_global (@requer_supervisor_area). Um
    gerente_producao/assistente_gm/gm "puro" (sem perfil operacional) não tem
    acesso lá, só em /gestor/dashboard (@requer_gestor_ou_admin). O botão deve
    apontar pra /gestor/dashboard nesse e-mail."""
    from app.services.report_service import enviar_relatorio_semanal

    chamados = [
        {
            "id": "c1",
            "numero": "CH-001",
            "categoria": "Projetos",
            "tipo": "Manutenção",
            "area": "Manutenção",
            "responsavel": "Supervisor",
            "responsavel_id": "sup1",
            "solicitante": "Solicitante",
            "status": "Aberto",
            "data_abertura_fmt": "01/01/2026",
            "dias_aberto": 5,
            "sla_label": "Ok",
            "atrasado": False,
            "sla_dias": 3,
            "alerta_prazo_24h_enviado_em": None,
        }
    ]
    supervisor = _make_usuario("sup@test.com", "Supervisor", "supervisor")

    with (
        app.app_context(),
        patch("app.services.report_service.buscar_chamados_abertos", return_value=chamados),
        patch("app.services.report_service.Usuario.get_by_ids", return_value={"sup1": supervisor}),
        patch("app.services.report_service.Usuario.get_all", return_value=[]),
        patch("app.services.report_service.construir_mapa_gestor_setor", return_value={}),
        patch(
            "app.services.report_service.construir_mapa_niveis_superiores",
            return_value={"gm": "gm@dtx.aero"},
        ),
        patch(
            "app.services.report_service._base_url",
            return_value="http://10.20.0.199:8080",
        ),
        patch("app.services.report_service.enviar_email", return_value=(True, None)) as mock_send,
    ):
        enviar_relatorio_semanal()

    chamada_gm = next(c for c in mock_send.call_args_list if c[0][0] == "gm@dtx.aero")
    html_corpo = chamada_gm[0][2]
    assert "/gestor/dashboard" in html_corpo
    assert "/admin" not in html_corpo


def test_niveis_superiores_email_inclui_cancelados_da_semana(app):
    """Chamados cancelados na semana devem aparecer no resumo dos níveis
    superiores (visão executiva completa aberto+cancelado) — pedido do
    usuário, 2026-08-20. Não deve vazar pro e-mail do supervisor, que continua
    só com os chamados abertos dele."""
    from app.services.report_service import enviar_relatorio_semanal

    chamados = [
        {
            "id": "c1",
            "numero": "CH-001",
            "categoria": "Projetos",
            "tipo": "Manutenção",
            "area": "Manutenção",
            "responsavel": "Supervisor",
            "responsavel_id": "sup1",
            "solicitante": "Solicitante",
            "status": "Aberto",
            "data_abertura_fmt": "01/01/2026",
            "dias_aberto": 5,
            "sla_label": "Ok",
            "atrasado": False,
            "sla_dias": 3,
            "alerta_prazo_24h_enviado_em": None,
        }
    ]
    cancelado = {
        "id": "c9",
        "numero": "CH-009",
        "categoria": "TI",
        "tipo": "Suporte",
        "area": "TI",
        "responsavel": "Supervisor",
        "responsavel_id": "sup1",
        "solicitante": "Solicitante",
        "status": "Cancelado",
        "data_abertura_fmt": "01/01/2026",
        "dias_aberto": 3,
        "sla_label": "",
        "atrasado": False,
        "sla_dias": None,
    }
    supervisor = _make_usuario("sup@test.com", "Supervisor", "supervisor")

    with (
        app.app_context(),
        patch("app.services.report_service.buscar_chamados_abertos", return_value=chamados),
        patch(
            "app.services.report_service.buscar_chamados_cancelados_semana",
            return_value=[cancelado],
        ),
        patch("app.services.report_service.Usuario.get_by_ids", return_value={"sup1": supervisor}),
        patch("app.services.report_service.Usuario.get_all", return_value=[]),
        patch("app.services.report_service.construir_mapa_gestor_setor", return_value={}),
        patch(
            "app.services.report_service.construir_mapa_niveis_superiores",
            return_value={"gm": "gm@dtx.aero"},
        ),
        patch("app.services.report_service.enviar_email", return_value=(True, None)) as mock_send,
    ):
        enviar_relatorio_semanal()

    chamada_gm = next(c for c in mock_send.call_args_list if c[0][0] == "gm@dtx.aero")
    html_gm = chamada_gm[0][2]
    assert "CH-009" in html_gm
    # "Cancelled" tem que aparecer no cartão de resumo lá em cima, na seção
    # com a tabela e no badge da linha — não só nos últimos dois.
    assert html_gm.count("Cancelled") >= 3

    chamada_sup = next(c for c in mock_send.call_args_list if c[0][0] == "sup@test.com")
    html_sup = chamada_sup[0][2]
    assert "CH-009" not in html_sup


def test_enviar_relatorio_semanal_nao_envia_niveis_superiores_sem_mapeamento(app):
    """Sem ninguém com nivel_gestao company-wide cadastrado, não deve tentar
    enviar nem gerar erro."""
    from app.services.report_service import enviar_relatorio_semanal

    chamados = [
        {
            "id": "c1",
            "numero": "CH-001",
            "categoria": "Projetos",
            "tipo": "Manutenção",
            "area": "Manutenção",
            "responsavel": "Supervisor",
            "responsavel_id": "sup1",
            "solicitante": "Solicitante",
            "status": "Aberto",
            "data_abertura_fmt": "01/01/2026",
            "dias_aberto": 5,
            "sla_label": "Ok",
            "atrasado": False,
            "sla_dias": 3,
            "alerta_prazo_24h_enviado_em": None,
        }
    ]
    supervisor = _make_usuario("sup@test.com", "Supervisor", "supervisor")

    with (
        app.app_context(),
        patch("app.services.report_service.buscar_chamados_abertos", return_value=chamados),
        patch("app.services.report_service.Usuario.get_by_ids", return_value={"sup1": supervisor}),
        patch("app.services.report_service.Usuario.get_all", return_value=[]),
        patch("app.services.report_service.construir_mapa_gestor_setor", return_value={}),
        patch("app.services.report_service.construir_mapa_niveis_superiores", return_value={}),
        patch("app.services.report_service.enviar_email", return_value=(True, None)) as mock_send,
    ):
        enviar_relatorio_semanal()

    destinos = [call[0][0] for call in mock_send.call_args_list]
    assert destinos == ["sup@test.com"]


def test_enviar_relatorio_semanal_loga_warning_quando_responsavel_sem_email(app, caplog):
    """Achado da auditoria 2026-08-06: responsável sem e-mail cadastrado era
    tratado como caso normal (logger.debug). Todo responsável DEVE ter e-mail
    (é o identificador de login) — se esse branch dispara de verdade, é sinal
    de dado inconsistente e merece warning, não silêncio."""
    import logging

    from app.services.report_service import enviar_relatorio_semanal

    chamados = [
        {
            "id": "c1",
            "numero": "CH-001",
            "categoria": "Projetos",
            "tipo": "Manutenção",
            "area": "Manutenção",
            "responsavel": "Supervisor Sem Email",
            "responsavel_id": "sup_sem_email",
            "solicitante": "Solicitante",
            "status": "Aberto",
            "data_abertura_fmt": "01/01/2026",
            "dias_aberto": 5,
            "sla_label": "Ok",
            "atrasado": False,
            "sla_dias": 3,
            "alerta_prazo_24h_enviado_em": None,
        }
    ]
    supervisor_sem_email = _make_usuario(email=None, nome="Supervisor Sem Email")

    with (
        app.app_context(),
        caplog.at_level(logging.WARNING, logger="app.services.report_service"),
        patch("app.services.report_service.buscar_chamados_abertos", return_value=chamados),
        patch(
            "app.services.report_service.Usuario.get_by_ids",
            return_value={"sup_sem_email": supervisor_sem_email},
        ),
        patch("app.services.report_service.Usuario.get_all", return_value=[]),
        patch("app.services.report_service.construir_mapa_gestor_setor", return_value={}),
        patch("app.services.report_service.enviar_email", return_value=(True, None)),
    ):
        resultado = enviar_relatorio_semanal()

    assert resultado["ignorados"] == 1
    assert any(
        record.levelno == logging.WARNING and "sup_sem_email" in record.getMessage()
        for record in caplog.records
    )
