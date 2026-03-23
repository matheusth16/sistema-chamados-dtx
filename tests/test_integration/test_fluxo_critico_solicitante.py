"""
Fluxo crítico do solicitante: login → acesso ao formulário → abertura de chamado → validação na lista.

Substitui o placeholder Playwright em tests/e2e/test_solicitante.py com um teste orientado a
comportamento usando o cliente Flask, executado na suite padrão (sem servidor externo).

Fluxo coberto:
1. Solicitante não logado é redirecionado para /login
2. Após login, acessa o formulário (GET /)
3. Chamado com dados inválidos não é criado (validação de formulário)
4. Chamado com dados válidos é criado e redireciona com sucesso
5. API retorna lista de chamados com estrutura correta para o solicitante
6. API retorna 403 ao solicitante que tenta acessar rota restrita a supervisor/admin
"""

from unittest.mock import patch

# ---------------------------------------------------------------------------
# 1. Proteção de rota sem autenticação
# ---------------------------------------------------------------------------


def test_acesso_formulario_sem_login_redireciona_para_login(client):
    """Solicitante não autenticado não acessa o formulário — redireciona para /login."""
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location


# ---------------------------------------------------------------------------
# 2. Acesso ao formulário após login
# ---------------------------------------------------------------------------


def test_acesso_formulario_apos_login_retorna_200(client_logado_solicitante):
    """Após login, GET / renderiza o formulário sem erros (status 200)."""
    with (
        patch("app.routes.chamados.get_static_cached", return_value=[]),
        patch("app.routes.chamados.obter_total_por_contagem", return_value=0),
    ):
        r = client_logado_solicitante.get("/")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# 3. Criação de chamado com dados inválidos (sem descrição)
# ---------------------------------------------------------------------------


def test_criar_chamado_descricao_vazia_nao_cria(client_logado_solicitante):
    """POST / com descrição vazia não cria chamado — permanece na página com feedback de erro."""
    with patch("app.routes.chamados.criar_chamado") as mock_criar:
        r = client_logado_solicitante.post(
            "/",
            data={
                "categoria": "Chamado",
                "tipo": "Manutencao",
                "gate": "Gate 1",
                "impacto": "Qualidade",
                "descricao": "",
            },
            follow_redirects=False,
        )
    # Validação no frontend → retorna 200 com formulário ou 302 para mesma página
    assert r.status_code in (200, 302)
    mock_criar.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Criação de chamado com dados válidos
# ---------------------------------------------------------------------------


def test_criar_chamado_valido_redireciona_e_chama_service(client_logado_solicitante):
    """POST / com dados válidos chama criar_chamado e redireciona (302) com sucesso."""
    with patch("app.routes.chamados.criar_chamado") as mock_criar:
        mock_criar.return_value = ("doc_id_01", "CHM-0001", None, None)
        r = client_logado_solicitante.post(
            "/",
            data={
                "categoria": "Chamado",
                "tipo": "Manutencao",
                "gate": "Gate 1",
                "impacto": "Qualidade",
                "descricao": "Equipamento parou de funcionar na linha 3",
            },
            follow_redirects=False,
        )

    assert r.status_code == 302
    assert r.location  # deve redirecionar para alguma página (meus-chamados ou confirmação)

    mock_criar.assert_called_once()
    kwargs = mock_criar.call_args[1]
    assert kwargs.get("solicitante_id") == "sol_1"
    assert kwargs.get("solicitante_nome") == "Solicitante Teste"
    # "descricao" está em form (ImmutableMultiDict), não em kwargs diretamente
    assert kwargs.get("form") is not None


# ---------------------------------------------------------------------------
# 5. API de listagem retorna estrutura correta para o solicitante
# ---------------------------------------------------------------------------


def test_api_chamados_paginar_retorna_estrutura_para_solicitante(client_logado_solicitante):
    """GET /api/chamados/paginar como solicitante retorna 200 com chamados e paginacao."""
    with patch(
        "app.routes.api.aplicar_filtros_dashboard_com_paginacao",
        return_value={"docs": [], "proximo_cursor": None, "tem_proxima": False},
    ):
        r = client_logado_solicitante.get("/api/chamados/paginar")

    assert r.status_code == 200
    data = r.get_json()
    assert data.get("sucesso") is True
    assert "chamados" in data
    assert "paginacao" in data
    paginacao = data["paginacao"]
    assert "tem_proxima" in paginacao and "cursor_proximo" in paginacao


# ---------------------------------------------------------------------------
# 6. Isolamento de perfil: solicitante não acessa rotas de supervisor
# ---------------------------------------------------------------------------


def test_solicitante_nao_pode_usar_bulk_status(client_logado_solicitante):
    """POST /api/bulk-status como solicitante retorna 403 — rota restrita a supervisor/admin."""
    r = client_logado_solicitante.post(
        "/api/bulk-status",
        json={"chamado_ids": ["ch1"], "novo_status": "Concluído"},
        content_type="application/json",
    )
    assert r.status_code == 403
    data = r.get_json()
    assert data is not None and data.get("erro")


def test_solicitante_nao_pode_editar_chamado(client_logado_solicitante):
    """POST /api/editar-chamado como solicitante retorna 403."""
    r = client_logado_solicitante.post(
        "/api/editar-chamado",
        data={"chamado_id": "ch1"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 403
