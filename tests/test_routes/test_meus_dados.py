"""Testes da página de autovisualização de dados pessoais (LGPD — direito de acesso)."""


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
