"""CWI 2.3 parcial — Auditoria respostas API: sem senha_hash, sem stack trace.
CWI 3.2 — Erros genéricos: 500 usa ERRO_INTERNO_MSG; bulk-status usa mensagem genérica por item.
"""

import json
from unittest.mock import MagicMock, patch

ERRO_INTERNO_MSG = "Internal error. Please try again."

CAMPOS_INTERNOS_PROIBIDOS = [
    "senha_hash",
    "password_hash",
    "encryption_key",
    "Traceback",
    "Firestore",
    "Google",
    "firebase",
    "Exception",
]


# ── CWI 2.3 — Auditoria to_public_dict ───────────────────────────────────────


def test_to_public_dict_nao_contem_senha_hash():
    """to_public_dict() nunca inclui senha_hash ou campos internos."""
    from app.models_usuario import Usuario

    u = Usuario(id="u1", email="test@dtx.aero", nome="Test", perfil="supervisor")
    u.set_password("minha_senha_secreta")

    pub = u.to_public_dict()
    serializado = json.dumps(pub)

    assert "senha_hash" not in pub, "senha_hash não deve estar em to_public_dict()"
    assert "minha_senha_secreta" not in serializado, "plaintext de senha não deve aparecer"
    assert "id" in pub
    assert "email" in pub
    assert "nome" in pub
    assert "perfil" in pub


def test_to_dict_contem_senha_hash_uso_interno():
    """to_dict() inclui senha_hash — é para uso interno/Firestore apenas."""
    from app.models_usuario import Usuario

    u = Usuario(id="u2", email="x@dtx.aero", nome="X")
    u.set_password("pass123")

    interno = u.to_dict()
    assert "senha_hash" in interno
    assert interno["senha_hash"] is not None


# ── CWI 2.3 — API /api/chamado/<id> sem campos internos ──────────────────────


def test_api_chamado_por_id_resposta_sem_campos_internos(client_logado_supervisor, db_session):
    """/api/chamado/<id> não expõe senha_hash, Traceback ou outros campos internos."""
    from tests.factories import make_chamado

    chamado = make_chamado(
        numero_chamado="CH-001",
        rl_codigo="RL-001",
        categoria="Manutenção",
        tipo_solicitacao="Corretiva",
        gate="Gate 1",
        responsavel="Supervisor",
        responsavel_id="sup_1",
        descricao="Problema na bomba",
        status="Aberto",
        area="Manutencao",
        solicitante_id="sol_1",
    )

    with (
        patch("app.routes.api_chamados.usuario_pode_ver_chamado", return_value=True),
        patch("app.routes.api_chamados.obter_sla_para_exibicao", return_value={}),
    ):
        r = client_logado_supervisor.get(f"/api/chamado/{chamado.id}")

    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="replace")

    for campo in CAMPOS_INTERNOS_PROIBIDOS:
        assert campo not in body, f"Campo interno '{campo}' encontrado na resposta"

    data = r.get_json()
    chamado_resp = data.get("chamado", {})
    assert "senha_hash" not in chamado_resp
    assert "encryption_key" not in chamado_resp
    assert chamado_resp.get("status") == "Aberto"


def test_api_chamado_por_id_campos_esperados_presentes(client_logado_supervisor, db_session):
    """/api/chamado/<id> retorna os campos esperados (whitelist explícita)."""
    from tests.factories import make_chamado

    chamado = make_chamado(
        numero_chamado="CH-042",
        rl_codigo="RL-X",
        categoria="Projetos",
        tipo_solicitacao="Nova funcionalidade",
        gate="Gate 2",
        responsavel="Ana",
        responsavel_id="sup_2",
        descricao="Desc do chamado",
        status="Em Atendimento",
        area="Manutencao",
        solicitante_id="sol_1",
    )

    with (
        patch("app.routes.api_chamados.usuario_pode_ver_chamado", return_value=True),
        patch("app.routes.api_chamados.obter_sla_para_exibicao", return_value={"status": "ok"}),
    ):
        r = client_logado_supervisor.get(f"/api/chamado/{chamado.id}")

    assert r.status_code == 200
    chamado_resp = r.get_json().get("chamado", {})
    for campo in ("id", "status", "categoria", "descricao", "responsavel"):
        assert campo in chamado_resp, f"Campo esperado '{campo}' ausente da resposta"


# ── CWI 3.2 — Erros genéricos em handlers 500 ────────────────────────────────


def test_api_chamado_por_id_500_usa_mensagem_generica(client_logado_supervisor, db_session):
    """Quando uma dependência interna lança exceção em /api/chamado/<id>, resposta 500 usa ERRO_INTERNO_MSG."""
    from tests.factories import make_chamado

    chamado = make_chamado(area="Manutencao", responsavel_id="sup_1")

    with (
        patch("app.routes.api_chamados.usuario_pode_ver_chamado", return_value=True),
        patch(
            "app.routes.api_chamados.obter_sla_para_exibicao",
            side_effect=RuntimeError("Firestore connection timeout — credenciais inválidas"),
        ),
    ):
        r = client_logado_supervisor.get(f"/api/chamado/{chamado.id}")

    assert r.status_code == 500
    data = r.get_json()
    assert data is not None
    assert data.get("erro") == ERRO_INTERNO_MSG
    body = r.data.decode("utf-8", errors="replace")
    assert "Firestore" not in body
    assert "Traceback" not in body
    assert "RuntimeError" not in body
    assert "credenciais" not in body


def test_api_chamados_paginar_500_usa_mensagem_generica(client_logado_supervisor):
    """Quando aplicar_filtros_dashboard lança exceção em /api/chamados/paginar, resposta usa ERRO_INTERNO_MSG."""
    with patch(
        "app.routes.api_chamados.aplicar_filtros_dashboard_com_paginacao",
        side_effect=RuntimeError("Google Cloud quota exceeded"),
    ):
        r = client_logado_supervisor.get("/api/chamados/paginar")

    assert r.status_code == 500
    data = r.get_json()
    assert data is not None
    assert data.get("erro") == ERRO_INTERNO_MSG
    body = r.data.decode("utf-8", errors="replace")
    assert "Google" not in body
    assert "quota" not in body


def test_bulk_status_erro_por_item_usa_mensagem_generica(client_logado_supervisor, db_session):
    """bulk_atualizar_status: falha em item individual retorna mensagem genérica, não str(exception)."""
    from tests.factories import make_chamado

    chamado_ok = make_chamado(status="Aberto", area="Manutencao", responsavel_id="sup_1")
    chamado_erro = make_chamado(status="Aberto", area="Manutencao", responsavel_id="sup_1")

    with (
        patch("app.routes.api_chamados.usuario_pode_operar_chamado", return_value=True),
        patch(
            "app.routes.api_chamados.atualizar_status_chamado",
            side_effect=[
                {"sucesso": True, "mensagem": "ok", "novo_status": "Em Atendimento"},
                RuntimeError("Firestore: UNAVAILABLE — could not connect to database"),
            ],
        ),
    ):
        r = client_logado_supervisor.post(
            "/api/bulk-status",
            json={
                "chamado_ids": [str(chamado_ok.id), str(chamado_erro.id)],
                "novo_status": "Em Atendimento",
            },
            content_type="application/json",
        )

    assert r.status_code == 200
    data = r.get_json()
    assert data is not None
    erros = data.get("erros", [])
    body = r.data.decode("utf-8", errors="replace")
    assert "Firestore" not in body, "Stack trace/nome interno não deve vazar"
    assert "UNAVAILABLE" not in body
    for item_erro in erros:
        erro_msg = item_erro.get("erro", "")
        assert "Firestore" not in erro_msg
        assert "UNAVAILABLE" not in erro_msg
        assert "Exception" not in erro_msg


def test_notificacoes_marcar_lida_500_usa_erro_interno(client_logado_supervisor):
    """Falha em marcar notificação como lida retorna 500 com ERRO_INTERNO_MSG."""
    with patch(
        "app.routes.api_notificacoes.marcar_como_lida", side_effect=RuntimeError("db error")
    ):
        r = client_logado_supervisor.post("/api/notificacoes/notif_123/ler")

    assert r.status_code == 500
    data = r.get_json()
    assert data is not None
    assert data.get("erro") == ERRO_INTERNO_MSG
    assert "db error" not in r.data.decode()


def test_notificacoes_ler_todas_500_usa_erro_interno(client_logado_supervisor):
    """Falha em marcar todas as notificações retorna 500 com ERRO_INTERNO_MSG."""
    with patch(
        "app.routes.api_notificacoes.marcar_todas_como_lidas", side_effect=RuntimeError("timeout")
    ):
        r = client_logado_supervisor.post("/api/notificacoes/ler-todas")

    assert r.status_code == 500
    data = r.get_json()
    assert data is not None
    assert data.get("erro") == ERRO_INTERNO_MSG
    assert "timeout" not in r.data.decode()


def test_push_subscribe_500_usa_erro_interno(client_logado_supervisor):
    """Falha ao salvar inscrição push retorna 500 com ERRO_INTERNO_MSG."""
    with patch(
        "app.routes.api_notificacoes.salvar_inscricao", side_effect=RuntimeError("redis down")
    ):
        r = client_logado_supervisor.post(
            "/api/push-subscribe",
            json={"subscription": {"endpoint": "https://example.com/push", "keys": {}}},
            content_type="application/json",
        )

    assert r.status_code == 500
    data = r.get_json()
    assert data is not None
    assert data.get("erro") == ERRO_INTERNO_MSG
    assert "redis" not in r.data.decode()


def test_atualizar_status_exception_em_service_nao_vaza_internals(
    client_logado_supervisor, db_session
):
    """CWI 3.2 — status_service lança exceção: atualizar_status_ajax não expõe str(e) ao cliente.

    Gap corrigido em Onda 3b: status_service.py retornava {"erro": str(e)}.
    A rota repassa resultado.get("erro") diretamente — fix aplicado no service.
    """
    from tests.factories import make_chamado

    chamado = make_chamado(
        status="Aberto",
        area="Manutencao",
        responsavel_id="sup_1",
        solicitante_id="sol_1",
        numero_chamado="CH-001",
    )

    with (
        patch(
            "app.routes.api_chamados.verificar_permissao_mudanca_status", return_value=(True, None)
        ),
        patch(
            "app.routes.api_chamados.atualizar_status_chamado",
            return_value={
                "sucesso": False,
                "erro": "Erro interno. Tente novamente.",
                "codigo": 500,
            },
        ),
    ):
        r = client_logado_supervisor.post(
            "/api/atualizar-status",
            json={"chamado_id": str(chamado.id), "novo_status": "Em Atendimento"},
            content_type="application/json",
        )

    assert r.status_code in (500, 404)
    body = r.data.decode("utf-8", errors="replace")
    assert "Firestore" not in body
    assert "UNAVAILABLE" not in body
    assert "Traceback" not in body
    data = r.get_json()
    if data and data.get("erro"):
        assert "Firestore" not in data["erro"]
        assert "UNAVAILABLE" not in data["erro"]


# ── L4 Polish — CWI 2.3: /api/supervisores/lista não expõe senha_hash ────────


def test_api_supervisores_lista_nao_expoe_senha_hash(client_logado_solicitante):
    """L4 / CWI 2.3 — GET /api/supervisores/lista não inclui senha_hash nem email na resposta JSON.

    O endpoint serializa apenas {id, nome} — email removido para evitar enumeração
    de PII por solicitantes; senha_hash nunca deve vazar.
    """
    sup_com_hash = MagicMock()
    sup_com_hash.id = "sup_externo"
    sup_com_hash.nome = "Supervisor Externo"
    sup_com_hash.email = "ext@dtx.aero"
    sup_com_hash.senha_hash = "scrypt:32768:8:1:HASH_SECRETO"
    sup_com_hash.nivel_gestao = None

    with patch(
        "app.routes.api_chamados.Usuario.get_supervisores_por_area", return_value=[sup_com_hash]
    ):
        r = client_logado_solicitante.get("/api/supervisores/lista?area=Planejamento")

    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="replace")
    assert "senha_hash" not in body, "senha_hash não deve aparecer na resposta de supervisores"
    assert "HASH_SECRETO" not in body
    assert "ext@dtx.aero" not in body, "email não deve ser exposto a solicitantes"

    data = r.get_json()
    assert data is not None
    assert data["sucesso"] is True
    supervisores = data.get("supervisores", [])
    assert len(supervisores) == 1
    sup = supervisores[0]
    assert set(sup.keys()) == {"id", "nome", "gestor"}, (
        f"Campos inesperados na resposta: {set(sup.keys())}"
    )
