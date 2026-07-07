"""Testes IDOR para GET /api/download-anexo.

Verifica que o endpoint rejeita acesso a anexos de chamados alheios
e exige autenticação. Os testes usam a lógica real de usuario_pode_ver_chamado
(sem mock da função de permissão), garantindo que o contrato de segurança
seja testado de ponta a ponta.

O fixture client_logado_solicitante usa user.id = "sol_1" (ver conftest.py).
"""

from unittest.mock import patch


def _make_chamado_doc(chaves=None, solicitante_id="dono_1"):
    """Cria mock de documento Firestore para um chamado."""
    from unittest.mock import MagicMock

    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "titulo": "Chamado Teste",
        "solicitante_id": solicitante_id,
        "area": "TI",
        "status": "Aberto",
        "descricao": "Descricao de teste",
        "categoria": "Nao Aplicavel",
        "tipo_solicitacao": "Manutencao",
        "responsavel": "Supervisor",
        "prioridade": 1,
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
    doc = _make_chamado_doc(chaves=["r2:original.pdf"], solicitante_id="sol_1")

    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.get(
            "/api/download-anexo?chamado_id=ch1&chave=r2:outro_arquivo.pdf"
        )

    assert r.status_code == 403


# ── IDOR: solicitante não é dono do chamado ───────────────────────────────────


def test_download_anexo_rejeita_usuario_sem_permissao(client_logado_solicitante):
    """GET de solicitante para chamado alheio retorna 403 (sem mock de permissão).

    Usa a lógica real de usuario_pode_ver_chamado:
    - solicitante_id = "outro_usuario" ≠ user.id = "sol_1" → 403
    Funciona tanto antes quanto depois do fix de permissions.py:
      - Antes: retornava False para todo solicitante (bug).
      - Depois: retorna False por IDs diferentes (comportamento correto).
    """
    doc = _make_chamado_doc(chaves=["r2:arq.pdf"], solicitante_id="outro_usuario")

    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.get("/api/download-anexo?chamado_id=ch1&chave=r2:arq.pdf")

    assert r.status_code == 403


# ── Acesso autorizado: solicitante acessa o próprio chamado ──────────────────


def test_download_anexo_redireciona_usuario_autorizado(client_logado_solicitante):
    """GET de solicitante para o próprio chamado redireciona para URL pré-assinada.

    Usa a lógica real de usuario_pode_ver_chamado (sem mock):
    - solicitante_id = "sol_1" == user.id = "sol_1" → True → 302

    RED antes do fix de permissions.py:
      A função retornava False para todo solicitante → abort(403).
    GREEN depois do fix:
      Retorna True quando IDs coincidem → redirect 302.
    """
    # solicitante_id alinhado ao user.id do fixture client_logado_solicitante
    doc = _make_chamado_doc(chaves=["r2:arq.pdf"], solicitante_id="sol_1")

    with (
        patch("app.routes.api.db") as mock_db,
        patch(
            "app.services.upload.gerar_url_presignada",
            return_value="https://r2.example.com/arq.pdf",
        ),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.get("/api/download-anexo?chamado_id=ch1&chave=r2:arq.pdf")

    assert r.status_code == 302
    assert "r2.example.com" in (r.location or "")


def test_download_anexo_sucesso_loga_acesso(client_logado_solicitante, caplog):
    """Download bem-sucedido de anexo gera log de auditoria (não só falha)."""
    import logging

    doc = _make_chamado_doc(chaves=["r2:arq.pdf"], solicitante_id="sol_1")

    with (
        patch("app.routes.api.db") as mock_db,
        patch(
            "app.services.upload.gerar_url_presignada",
            return_value="https://r2.example.com/arq.pdf",
        ),
        caplog.at_level(logging.INFO, logger="app.routes.api"),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        client_logado_solicitante.get("/api/download-anexo?chamado_id=ch1&chave=r2:arq.pdf")

    mensagens = [r.message for r in caplog.records]
    assert any("ch1" in m and "r2:arq.pdf" in m for m in mensagens)
