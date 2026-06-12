"""Testes IDOR para GET /api/download-anexo.

Verifica que o endpoint rejeita acesso a anexos de chamados alheios
e exige autenticação, conforme controle de acesso em usuario_pode_ver_chamado.
"""

from unittest.mock import MagicMock, patch


def _make_chamado_doc(chaves=None, solicitante_id="dono_1"):
    """Cria mock de documento Firestore para um chamado."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "titulo": "Chamado Teste",
        "solicitante_id": solicitante_id,
        "area": "TI",
        "status": "Aberto",
        "anexos": chaves or ["r2:arquivo.pdf"],
        "anexo": None,
    }
    return doc


# ── Autenticação ───────────────────────────────────────────────────────────────


def test_download_anexo_requer_autenticacao(client):
    """GET /api/download-anexo sem sessão redireciona para login."""
    r = client.get("/api/download-anexo?chamado_id=ch1&chave=r2:arq.pdf")
    assert r.status_code in (302, 401)
    if r.status_code == 302:
        assert "login" in (r.location or "").lower()


# ── Parâmetros inválidos ───────────────────────────────────────────────────────


def test_download_anexo_sem_chamado_id_retorna_400(client_logado_solicitante):
    """GET sem chamado_id retorna 400."""
    r = client_logado_solicitante.get("/api/download-anexo?chave=r2:arq.pdf")
    assert r.status_code == 400


def test_download_anexo_sem_chave_r2_retorna_400(client_logado_solicitante):
    """GET com chave sem prefixo 'r2:' retorna 400."""
    r = client_logado_solicitante.get(
        "/api/download-anexo?chamado_id=ch1&chave=arquivo_sem_prefixo.pdf"
    )
    assert r.status_code == 400


# ── IDOR: chave não pertence ao chamado ───────────────────────────────────────


def test_download_anexo_rejeita_chave_fora_dos_anexos(client_logado_solicitante):
    """GET com chave que não está nos anexos do chamado retorna 403 (IDOR)."""
    doc = _make_chamado_doc(chaves=["r2:original.pdf"])

    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.get(
            "/api/download-anexo?chamado_id=ch1&chave=r2:outro_arquivo.pdf"
        )

    assert r.status_code == 403


# ── IDOR: usuário sem permissão no chamado ────────────────────────────────────


def test_download_anexo_rejeita_usuario_sem_permissao(client_logado_solicitante):
    """GET de solicitante que não tem acesso ao chamado retorna 403."""
    doc = _make_chamado_doc(chaves=["r2:arq.pdf"], solicitante_id="outro_usuario")

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado.from_dict", return_value=MagicMock()),
        patch("app.routes.api.usuario_pode_ver_chamado", return_value=False),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.get("/api/download-anexo?chamado_id=ch1&chave=r2:arq.pdf")

    assert r.status_code == 403


# ── Acesso autorizado ─────────────────────────────────────────────────────────


def test_download_anexo_redireciona_usuario_autorizado(client_logado_solicitante):
    """GET de usuário com permissão redireciona para URL pré-assinada."""
    doc = _make_chamado_doc(chaves=["r2:arq.pdf"])

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado.from_dict", return_value=MagicMock()),
        patch("app.routes.api.usuario_pode_ver_chamado", return_value=True),
        patch(
            "app.services.upload.gerar_url_presignada",
            return_value="https://r2.example.com/arq.pdf",
        ),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.get("/api/download-anexo?chamado_id=ch1&chave=r2:arq.pdf")

    assert r.status_code == 302
    assert "r2.example.com" in (r.location or "")
