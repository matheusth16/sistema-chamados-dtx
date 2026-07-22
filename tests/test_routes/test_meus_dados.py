"""Testes da página de autovisualização de dados pessoais (LGPD — direito de acesso)."""

from unittest.mock import patch


def test_meus_dados_sem_login_redireciona_para_login(client):
    r = client.get("/meus-dados", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in (r.location or "")


def test_meus_dados_solicitante_retorna_200_com_dados(client_logado_solicitante):
    r = client_logado_solicitante.get("/meus-dados")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Solicitante Teste" in body
    assert "sol@test.com" in body


def test_meus_dados_supervisor_retorna_200(client_logado_supervisor):
    r = client_logado_supervisor.get("/meus-dados")
    assert r.status_code == 200
    assert "Supervisor Teste" in r.get_data(as_text=True)


def test_meus_dados_admin_retorna_200(client_logado_admin):
    r = client_logado_admin.get("/meus-dados")
    assert r.status_code == 200
    assert "Admin Teste" in r.get_data(as_text=True)


def test_meus_dados_nao_expoe_senha_hash(client_logado_solicitante):
    r = client_logado_solicitante.get("/meus-dados")
    body = r.get_data(as_text=True)
    assert "senha_hash" not in body


# ── /meus-dados/exportar (LGPD — portabilidade) ──────────────────────────────


def test_exportar_meus_dados_sem_login_redireciona_para_login(client):
    r = client.get("/meus-dados/exportar", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in (r.location or "")


def test_exportar_meus_dados_retorna_json_para_download(client_logado_solicitante):
    with patch(
        "app.services.lgpd_self_service.exportar_dados_usuario",
        return_value={"conta": {"id": "sol_1"}, "chamados_criados": []},
    ) as mock_export:
        r = client_logado_solicitante.get("/meus-dados/exportar")

    assert r.status_code == 200
    assert r.mimetype == "application/json"
    assert "attachment" in r.headers.get("Content-Disposition", "")
    assert b'"id": "sol_1"' in r.data
    mock_export.assert_called_once()


def test_exportar_meus_dados_csv_retorna_csv_para_download(client_logado_solicitante):
    with patch(
        "app.services.lgpd_self_service.exportar_dados_usuario_csv",
        return_value="Conta\nid,sol_1\n",
    ) as mock_export_csv:
        r = client_logado_solicitante.get("/meus-dados/exportar?formato=csv")

    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    assert "attachment" in r.headers.get("Content-Disposition", "")
    assert b"sol_1" in r.data
    mock_export_csv.assert_called_once()


def test_exportar_meus_dados_formato_invalido_retorna_json(client_logado_solicitante):
    """formato desconhecido cai no padrão (JSON), não quebra."""
    with patch(
        "app.services.lgpd_self_service.exportar_dados_usuario",
        return_value={"conta": {"id": "sol_1"}, "chamados_criados": []},
    ) as mock_export:
        r = client_logado_solicitante.get("/meus-dados/exportar?formato=xml")

    assert r.status_code == 200
    assert r.mimetype == "application/json"
    mock_export.assert_called_once()


def test_exportar_meus_dados_erro_interno_redireciona_com_flash(client_logado_solicitante):
    with patch(
        "app.services.lgpd_self_service.exportar_dados_usuario",
        side_effect=Exception("falha"),
    ):
        r = client_logado_solicitante.get("/meus-dados/exportar", follow_redirects=True)

    assert r.status_code == 200
    assert "/meus-dados" in r.request.path


# ── /meus-dados/solicitar-exclusao (LGPD — exclusão) ─────────────────────────


def test_solicitar_exclusao_sem_login_redireciona_para_login(client):
    r = client.post("/meus-dados/solicitar-exclusao", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in (r.location or "")


def test_solicitar_exclusao_sucesso_redireciona_para_meus_dados(client_logado_solicitante):
    with patch(
        "app.services.lgpd_self_service.solicitar_exclusao_propria",
        return_value={"sucesso": True},
    ) as mock_solicitar:
        r = client_logado_solicitante.post("/meus-dados/solicitar-exclusao", follow_redirects=False)

    assert r.status_code == 302
    assert "/meus-dados" in r.location
    mock_solicitar.assert_called_once()


def test_solicitar_exclusao_pedido_duplicado_redireciona_com_flash(client_logado_solicitante):
    with patch(
        "app.services.lgpd_self_service.solicitar_exclusao_propria",
        return_value={"sucesso": False, "erro_key": "lgpd_exclusion_request_already_pending"},
    ):
        r = client_logado_solicitante.post("/meus-dados/solicitar-exclusao", follow_redirects=False)

    assert r.status_code == 302
    assert "/meus-dados" in r.location
