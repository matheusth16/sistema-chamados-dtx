"""Testes da rota GET /gestor/dashboard e decoradores @requer_gestor / @requer_gestor_ou_admin."""

from unittest.mock import ANY, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures de usuário gestor
# ---------------------------------------------------------------------------


def _mock_gestor(uid="gest_1", perfil="supervisor", nivel_gestao="gestor_setor"):
    """MagicMock de usuário com is_gestor=True e is_gestor_only baseado no perfil."""
    u = MagicMock()
    u.id = uid
    u.email = f"{uid}@dtx.aero"
    u.nome = "Gestor Teste"
    u.perfil = perfil
    u.area = "Geral"
    u.areas = ["Geral"]
    u.nivel_gestao = nivel_gestao
    u.is_authenticated = True
    u.get_id = lambda: str(uid)
    u.must_change_password = False
    u.mfa_enabled = True
    u.is_admin_or_above = perfil in ("admin", "admin_global")
    u.is_supervisor_or_above = perfil in ("supervisor", "admin", "admin_global")
    u.is_gestor = nivel_gestao is not None
    u.is_gestor_only = u.is_gestor and not u.is_admin_or_above
    u.onboarding_perfis_vistos = [perfil]
    u.onboarding_passo = 0
    u.ativo = True
    return u


@pytest.fixture
def client_logado_gestor(client, app):
    """Cliente com usuário supervisor gestor_setor já logado."""
    user = _mock_gestor()
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=user),
        patch("app.models_usuario.Usuario.get_by_id", return_value=user),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
    ):
        client.post("/login", data={"email": user.email, "senha": "ok"}, follow_redirects=False)
        yield client


@pytest.fixture
def client_logado_gestor_setor_dual_role(client, app):
    """Cliente com supervisor + gestor_setor real (Nível 3: is_gestor_only=False,
    diferente de client_logado_gestor que fixa is_gestor_only=True pra testar o
    caso legado de gestor 100% read-only)."""
    user = _mock_gestor(uid="dual_1")
    user.is_gestor_only = False
    user.areas = ["Geral"]
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=user),
        patch("app.models_usuario.Usuario.get_by_id", return_value=user),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
    ):
        client.post("/login", data={"email": user.email, "senha": "ok"}, follow_redirects=False)
        yield client


@pytest.fixture
def client_logado_admin_gestor(client, app):
    """Cliente com usuário admin + nivel_gestao (acesso total)."""
    user = _mock_gestor(uid="admin_gest_1", perfil="admin", nivel_gestao="gm")
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=user),
        patch("app.models_usuario.Usuario.get_by_id", return_value=user),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
    ):
        client.post("/login", data={"email": user.email, "senha": "ok"}, follow_redirects=False)
        yield client


# ---------------------------------------------------------------------------
# Testes da rota /gestor/dashboard
# ---------------------------------------------------------------------------


def test_gestor_acessa_dashboard(client_logado_gestor):
    """Gestor (supervisor com nivel_gestao) obtém 200 em /gestor/dashboard."""
    ctx_mock = {
        "contadores": {
            "total": 0,
            "atrasados": 0,
            "aberto_sem_resposta": 0,
            "multi_setor_travado": 0,
        },
        "chamados": [],
        "filtro_ativo": "todos",
        "insights": {
            "area_critica": None,
            "tempo_medio_sem_resposta_min": None,
            "saude_percentual": 100,
        },
        "grupos": [
            {
                "chave": "atrasados",
                "titulo": "Atrasados",
                "cor": "danger",
                "total": 0,
                "chamados": [],
            },
            {
                "chave": "aberto_sem_resposta",
                "titulo": "Sem resposta",
                "cor": "warn",
                "total": 0,
                "chamados": [],
            },
            {
                "chave": "multi_setor",
                "titulo": "Multi-setor travado",
                "cor": "purple",
                "total": 0,
                "chamados": [],
            },
        ],
    }
    with patch("app.routes.dashboard.obter_contexto_gestor_dashboard", return_value=ctx_mock):
        resp = client_logado_gestor.get("/gestor/dashboard")
    assert resp.status_code == 200
    assert b"gestor" in resp.data.lower() or b"dashboard" in resp.data.lower()


def test_gestor_dashboard_mostra_nivel_gestao_traduzido(client, app):
    """Bug real (auditoria QA 2026-08-14): o badge de nivel_gestao no Painel
    Gerencial usava `nivel_gestao | replace("_", " ") | title`, que produzia
    rótulos crus e errados — "Gerente Producao" sem acento, "Assistente Gm"
    com a sigla mal capitalizada — em vez das traduções management_level_*
    já usadas no cadastro de usuário (usuario_form.html)."""
    ctx_mock = {
        "contadores": {
            "total": 0,
            "atrasados": 0,
            "aberto_sem_resposta": 0,
            "multi_setor_travado": 0,
        },
        "chamados": [],
        "filtro_ativo": "todos",
        "insights": {
            "area_critica": None,
            "tempo_medio_sem_resposta_min": None,
            "saude_percentual": 100,
            "em_risco_total": 0,
        },
        "grupos": [],
    }
    casos = {
        "gestor_setor": "Gestor de Setor",
        "gerente_producao": "Gerente de Produção",
        "assistente_gm": "Assistente GM",
        "gm": "GM (Diretor Geral)",
    }
    for nivel, esperado in casos.items():
        user = _mock_gestor(uid=f"gest_{nivel}", nivel_gestao=nivel)
        with (
            patch("app.routes.auth.Usuario.get_by_email", return_value=user),
            patch("app.models_usuario.Usuario.get_by_id", return_value=user),
            patch("app.routes.auth._dispositivo_confiavel", return_value=True),
            patch("app.routes.dashboard.obter_contexto_gestor_dashboard", return_value=ctx_mock),
        ):
            client.post("/login", data={"email": user.email, "senha": "ok"}, follow_redirects=False)
            resp = client.get("/gestor/dashboard?lang=pt_BR")
            body = resp.get_data(as_text=True)
            assert esperado in body, f"nivel_gestao={nivel} esperava {esperado!r} no HTML"


def test_admin_acessa_gestor_dashboard(client_logado_admin_gestor):
    """Admin com nivel_gestao acessa /gestor/dashboard com 200."""
    ctx_mock = {
        "contadores": {
            "total": 0,
            "atrasados": 0,
            "aberto_sem_resposta": 0,
            "multi_setor_travado": 0,
        },
        "chamados": [],
        "filtro_ativo": "todos",
        "insights": {
            "area_critica": None,
            "tempo_medio_sem_resposta_min": None,
            "saude_percentual": 100,
        },
        "grupos": [
            {
                "chave": "atrasados",
                "titulo": "Atrasados",
                "cor": "danger",
                "total": 0,
                "chamados": [],
            },
            {
                "chave": "aberto_sem_resposta",
                "titulo": "Sem resposta",
                "cor": "warn",
                "total": 0,
                "chamados": [],
            },
            {
                "chave": "multi_setor",
                "titulo": "Multi-setor travado",
                "cor": "purple",
                "total": 0,
                "chamados": [],
            },
        ],
    }
    with patch("app.routes.dashboard.obter_contexto_gestor_dashboard", return_value=ctx_mock):
        resp = client_logado_admin_gestor.get("/gestor/dashboard")
    assert resp.status_code == 200


def test_supervisor_sem_nivel_gestao_bloqueado(client_logado_supervisor):
    """Supervisor sem nivel_gestao é redirecionado (302) ao tentar /gestor/dashboard."""
    resp = client_logado_supervisor.get("/gestor/dashboard", follow_redirects=False)
    assert resp.status_code == 302


def test_solicitante_bloqueado_gestor_dashboard(client_logado_solicitante):
    """Solicitante é redirecionado (302) ao tentar /gestor/dashboard."""
    resp = client_logado_solicitante.get("/gestor/dashboard", follow_redirects=False)
    assert resp.status_code == 302


def test_gestor_dashboard_filtro_atrasados(client_logado_gestor):
    """Gestor pode filtrar por atrasados via query string."""
    ctx_mock = {
        "contadores": {
            "total": 5,
            "atrasados": 2,
            "aberto_sem_resposta": 1,
            "multi_setor_travado": 0,
        },
        "chamados": [],
        "filtro_ativo": "atrasados",
        "insights": {
            "area_critica": None,
            "tempo_medio_sem_resposta_min": None,
            "saude_percentual": 100,
        },
        "grupos": [],
    }
    with patch(
        "app.routes.dashboard.obter_contexto_gestor_dashboard", return_value=ctx_mock
    ) as mock_svc:
        resp = client_logado_gestor.get("/gestor/dashboard?filtro=atrasados")
    assert resp.status_code == 200
    mock_svc.assert_called_once_with(filtro="atrasados", usuario=ANY)


def test_gestor_nao_pode_mudar_status_via_api(client_logado_gestor, db_session):
    """POST /api/atualizar-status retorna 403 para gestor read-only."""
    from tests.factories import make_chamado

    chamado = make_chamado(status="Aberto")

    with patch(
        "app.routes.api_chamados.verificar_permissao_mudanca_status",
        return_value=(False, "Acesso negado: gestores têm visão read-only"),
    ):
        resp = client_logado_gestor.post(
            "/api/atualizar-status",
            json={"chamado_id": str(chamado.id), "novo_status": "Em Atendimento"},
        )
    assert resp.status_code == 403


def test_gestor_setor_dual_role_nao_muda_status_de_chamado_do_colega(
    client_logado_gestor_setor_dual_role, db_session
):
    """QA (Nível 3): supervisor + gestor_setor enxerga chamado do colega na própria
    área (leitura ampliada), mas POST /api/atualizar-status continua bloqueado —
    enxergar não é igual a poder editar."""
    from tests.factories import make_chamado

    chamado = make_chamado(
        area="Geral",
        status="Em Atendimento",
        solicitante_id="outro_solicitante",
        responsavel_id="colega_supervisor",
        numero_chamado="CHM-9999",
        categoria="Geral",
        tipo_solicitacao="Outros",
        descricao="chamado do colega",
        responsavel="Colega",
    )

    resp = client_logado_gestor_setor_dual_role.post(
        "/api/atualizar-status",
        json={"chamado_id": str(chamado.id), "novo_status": "Concluído"},
    )

    assert resp.status_code == 403


def test_gestor_setor_puro_ve_js_de_decisao_de_previsao_mesmo_sem_escalonar(
    client_logado_gestor, db_session, app
):
    """Bug real (auditoria QA 2026-08-14): os botões "Aprovar"/"Rejeitar" de
    previsão de atendimento são renderizados fora do bloco `pode_escalonar`
    de propósito (comentário no template explica: um gestor_setor "puro",
    is_gestor_only=True, pode decidir sem poder editar/escalonar o chamado).
    Só que a função JS decidirPrevisaoAtendimento (e CHAMADO_ID/CSRF_TOKEN/
    mostrarErro/esconderErro de que ela depende) estava definida só dentro
    do <script> gated por `pode_escalonar` — pra esse gestor puro (que é
    exatamente o caso que o comentário diz que devia funcionar) os botões
    apareciam mas o clique não fazia nada: sem request, sem erro, silêncio
    total. Reproduzido ao vivo no browser antes desta correção."""
    from datetime import datetime, timedelta

    from app.services.previsao_atendimento_service import solicitar_previsao_atendimento
    from tests.factories import make_chamado

    chamado = make_chamado(area="Geral", responsavel_id="resp1")

    solicitante = MagicMock()
    solicitante.id = "resp1"
    solicitante.nome = "Responsável Teste"
    solicitante.perfil = "supervisor"
    solicitante.is_admin_or_above = False
    with app.app_context():
        resultado = solicitar_previsao_atendimento(
            chamado.id,
            datetime.now() + timedelta(days=10),
            "Motivo de teste",
            solicitante,
        )
    assert resultado["sucesso"] is True, resultado.get("erro")

    with (
        patch("app.routes.dashboard.usuario_pode_ver_chamado", return_value=True),
        patch("app.routes.dashboard.get_static_cached", return_value=[]),
        patch("app.routes.dashboard.CategoriaSetor.get_all", return_value=[]),
    ):
        resp = client_logado_gestor.get(f"/chamado/{chamado.id}")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Botão renderizado (já funcionava antes)
    assert 'data-action="decidir-previsao-aprovar"' in body
    # A DEFINIÇÃO da função precisa estar presente — não basta o dispatcher
    # que só CHAMA decidirPrevisaoAtendimento (esse dispatcher já está fora
    # do bloco pode_escalonar e sempre aparece; o bug real é a ausência da
    # atribuição window.decidirPrevisaoAtendimento = function(...), que só
    # existia dentro do bloco pode_escalonar, False pra gestor_setor puro)
    assert "window.decidirPrevisaoAtendimento = function" in body


def test_gestor_setor_ve_acoes_de_escalonamento_em_chamado_do_time(
    client_logado_gestor, db_session, app
):
    """Ações de Escalonamento (decisão de escopo 2026-08-20): gestor_setor da
    própria área ganha o painel de Escalation Actions (Transferir Área,
    Transferir para Colega, Incluir Participantes) num chamado do time que
    não é dele — antes ficava 100% read-only nessa tela. client_logado_gestor
    é nivel_gestao='gestor_setor', áreas=['Geral']."""
    from tests.factories import make_chamado

    chamado = make_chamado(
        area="Geral",
        status="Em Atendimento",
        solicitante_id="outro_solicitante",
        responsavel_id="colega_supervisor",
        responsavel="Colega",
    )

    with (
        patch("app.routes.dashboard.usuario_pode_ver_chamado", return_value=True),
        patch("app.routes.dashboard.get_static_cached", return_value=[]),
        patch("app.routes.dashboard.CategoriaSetor.get_all", return_value=[]),
    ):
        resp = client_logado_gestor.get(f"/chamado/{chamado.id}")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'data-target="modal-transferir-area"' in body
    assert 'data-action="carregar-colegas-e-abrir-modal"' in body
    assert 'data-target="modal-incluir-participantes"' in body


def test_gestor_setor_fora_da_area_nao_ve_acoes_de_escalonamento(
    client_logado_gestor, db_session, app
):
    """gestor_setor não tem nem leitura sobre chamado de área fora da sua —
    a rota já bloqueia antes de chegar no template (usuario_pode_ver_chamado
    real, sem patch aqui)."""
    from tests.factories import make_chamado

    chamado = make_chamado(
        area="Outra Area",
        status="Em Atendimento",
        solicitante_id="outro_solicitante",
        responsavel_id="colega_supervisor",
        responsavel="Colega",
    )

    with (
        patch("app.routes.dashboard.get_static_cached", return_value=[]),
        patch("app.routes.dashboard.CategoriaSetor.get_all", return_value=[]),
    ):
        resp = client_logado_gestor.get(f"/chamado/{chamado.id}")

    assert resp.status_code in (302, 403)


def test_previsao_pendente_exibe_data_formatada_nao_iso_bruto(
    client_logado_gestor, db_session, app
):
    """Bug real (auditoria QA 2026-08-14, mesma sessão do bug acima): a data
    da previsão pendente era impressa como string bruta do banco (ex.
    "2026-08-20 14:00:00-03:00") em vez do formato dd/mm/aaaa hh:mm usado no
    resto do sistema — inclusive na mesma tela, uma vez aprovada
    (chamado.previsao_atendimento_formatada()). Reproduzido ao vivo no
    browser: a tela "Aguardando aprovação" mostrava a data bruta."""
    from datetime import datetime, timedelta

    from app.services.previsao_atendimento_service import (
        obter_solicitacao_pendente,
        solicitar_previsao_atendimento,
    )
    from tests.factories import make_chamado

    chamado = make_chamado(area="Geral", responsavel_id="resp1")

    solicitante = MagicMock()
    solicitante.id = "resp1"
    solicitante.nome = "Responsável Teste"
    solicitante.perfil = "supervisor"
    solicitante.is_admin_or_above = False
    with app.app_context():
        resultado = solicitar_previsao_atendimento(
            chamado.id,
            datetime.now() + timedelta(days=10),
            "Motivo de teste",
            solicitante,
        )
        assert resultado["sucesso"] is True, resultado.get("erro")
        pendente = obter_solicitacao_pendente(chamado.id)
        esperado_formatado = pendente["previsao_solicitada"].strftime("%d/%m/%Y %H:%M")
        formato_bruto_iso = pendente["previsao_solicitada"].isoformat(sep=" ")

    with (
        patch("app.routes.dashboard.usuario_pode_ver_chamado", return_value=True),
        patch("app.routes.dashboard.get_static_cached", return_value=[]),
        patch("app.routes.dashboard.CategoriaSetor.get_all", return_value=[]),
    ):
        resp = client_logado_gestor.get(f"/chamado/{chamado.id}")

    body = resp.get_data(as_text=True)
    assert esperado_formatado in body
    assert formato_bruto_iso not in body


def test_gestor_visualizar_chamado_pode_editar_false(client_logado_gestor, db_session):
    """Gestor visualiza chamado com pode_editar=False no contexto do template."""
    from tests.factories import make_chamado

    chamado = make_chamado(area="Geral", responsavel_id=None, solicitante_id="outro")

    with (
        patch("app.routes.dashboard.usuario_pode_ver_chamado", return_value=True),
        patch("app.routes.dashboard.get_static_cached", return_value=[]),
        patch("app.routes.dashboard.CategoriaSetor.get_all", return_value=[]),
    ):
        resp = client_logado_gestor.get(f"/chamado/{chamado.id}")

    # Gestor pode ver o chamado (200) mas pode_editar=False no template
    assert resp.status_code == 200
    # Template não deve renderizar o formulário de edição ({% if pode_editar %} é False)
    assert b"form-status" not in resp.data
