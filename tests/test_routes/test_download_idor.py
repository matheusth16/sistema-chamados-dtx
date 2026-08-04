"""Testes IDOR para GET /api/download-anexo.

Verifica que o endpoint rejeita acesso a anexos de chamados alheios
e exige autenticação. Os testes usam a lógica real de usuario_pode_ver_chamado
(sem mock da função de permissão), garantindo que o contrato de segurança
seja testado de ponta a ponta.

O fixture client_logado_solicitante usa user.id = "sol_1" (ver conftest.py).
Persistência roda contra Postgres real (db_session) via tests.factories.make_chamado
— Fase 2, Marco 10.
"""

from unittest.mock import patch

import pytest

from tests.factories import make_chamado

pytestmark = pytest.mark.usefixtures("db_session")


def _criar_chamado(chaves=None, solicitante_id="dono_1"):
    """Cria um Chamado real no Postgres de teste com os anexos dados."""
    anexos = chaves or ["r2:arquivo.pdf"]
    return make_chamado(
        solicitante_id=solicitante_id,
        area="TI",
        status="Aberto",
        descricao="Descricao de teste",
        categoria="Nao Aplicavel",
        tipo_solicitacao="Manutencao",
        responsavel="Supervisor",
        anexos=anexos,
        anexo=None,
    )


# ── Autenticação ───────────────────────────────────────────────────────────────


def test_download_anexo_requer_autenticacao(client):
    """GET /api/download-anexo sem sessão redireciona para login."""
    r = client.get("/api/download-anexo?chamado_id=1&chave=r2:arq.pdf")
    assert r.status_code in (302, 401)
    if r.status_code == 302:
        assert "login" in (r.location or "").lower()


# ── Parâmetros inválidos ───────────────────────────────────────────────────────


def test_download_anexo_sem_chamado_id_retorna_400(client_logado_solicitante):
    """GET sem chamado_id retorna 400."""
    r = client_logado_solicitante.get("/api/download-anexo?chave=r2:arq.pdf")
    assert r.status_code == 400


def test_download_anexo_chamado_inexistente_retorna_404(client_logado_solicitante):
    """GET com chamado_id que não existe no banco retorna 404."""
    r = client_logado_solicitante.get("/api/download-anexo?chamado_id=999999999&chave=r2:arq.pdf")
    assert r.status_code == 404


def test_download_anexo_url_publica_nao_proxeada_retorna_400(client_logado_solicitante):
    """Chave https:// (Firebase) pertence ao chamado mas não é proxeada por este
    endpoint -> 400 (o template já linka direto para a URL pública)."""
    chamado = _criar_chamado(
        chaves=["https://storage.googleapis.com/x.pdf"], solicitante_id="sol_1"
    )

    with patch("app.routes.api_solicitante.usuario_pode_ver_chamado", return_value=True):
        r = client_logado_solicitante.get(
            f"/api/download-anexo?chamado_id={chamado.id}&chave=https://storage.googleapis.com/x.pdf"
        )

    assert r.status_code == 400


# ── IDOR: chave não pertence ao chamado ───────────────────────────────────────


def test_download_anexo_rejeita_chave_fora_dos_anexos(client_logado_solicitante):
    """GET com chave que não está nos anexos do chamado retorna 403 (IDOR)."""
    chamado = _criar_chamado(chaves=["r2:original.pdf"], solicitante_id="sol_1")

    r = client_logado_solicitante.get(
        f"/api/download-anexo?chamado_id={chamado.id}&chave=r2:outro_arquivo.pdf"
    )

    assert r.status_code == 403


# ── IDOR: solicitante não é dono do chamado ───────────────────────────────────


def test_download_anexo_rejeita_usuario_sem_permissao(client_logado_solicitante):
    """GET de solicitante para chamado alheio retorna 403 (sem mock de permissão).

    Usa a lógica real de usuario_pode_ver_chamado:
    - solicitante_id = "outro_usuario" ≠ user.id = "sol_1" → 403
    """
    chamado = _criar_chamado(chaves=["r2:arq.pdf"], solicitante_id="outro_usuario")

    r = client_logado_solicitante.get(
        f"/api/download-anexo?chamado_id={chamado.id}&chave=r2:arq.pdf"
    )

    assert r.status_code == 403


# ── Acesso autorizado: solicitante acessa o próprio chamado ──────────────────


def test_download_anexo_redireciona_usuario_autorizado(client_logado_solicitante):
    """GET de solicitante para o próprio chamado redireciona para URL pré-assinada.

    Usa a lógica real de usuario_pode_ver_chamado (sem mock):
    - solicitante_id = "sol_1" == user.id = "sol_1" → True → 302
    """
    # solicitante_id alinhado ao user.id do fixture client_logado_solicitante
    chamado = _criar_chamado(chaves=["r2:arq.pdf"], solicitante_id="sol_1")

    with patch(
        "app.services.upload.gerar_url_presignada",
        return_value="https://r2.example.com/arq.pdf",
    ):
        r = client_logado_solicitante.get(
            f"/api/download-anexo?chamado_id={chamado.id}&chave=r2:arq.pdf"
        )

    assert r.status_code == 302
    assert "r2.example.com" in (r.location or "")


def test_download_anexo_sucesso_loga_acesso(client_logado_solicitante, caplog):
    """Download bem-sucedido de anexo gera log de auditoria (não só falha)."""
    import logging

    chamado = _criar_chamado(chaves=["r2:arq.pdf"], solicitante_id="sol_1")

    with (
        patch(
            "app.services.upload.gerar_url_presignada",
            return_value="https://r2.example.com/arq.pdf",
        ),
        caplog.at_level(logging.INFO, logger="app.routes.api_solicitante"),
    ):
        client_logado_solicitante.get(
            f"/api/download-anexo?chamado_id={chamado.id}&chave=r2:arq.pdf"
        )

    mensagens = [r.message for r in caplog.records]
    assert any(str(chamado.id) in m and "r2:arq.pdf" in m for m in mensagens)


# ── Prefixo local: (Fase 1 on-premise) ────────────────────────────────────────


def test_download_anexo_local_autorizado_serve_arquivo(client_logado_solicitante, app, tmp_path):
    """GET com chave local: e usuário dono do chamado -> 200, serve o arquivo."""
    app.config["ANEXO_LOCAL_DIR"] = str(tmp_path)
    (tmp_path / "20260101_doc.pdf").write_bytes(b"conteudo")
    chamado = _criar_chamado(chaves=["local:20260101_doc.pdf"], solicitante_id="sol_1")

    r = client_logado_solicitante.get(
        f"/api/download-anexo?chamado_id={chamado.id}&chave=local:20260101_doc.pdf"
    )

    assert r.status_code == 200


def test_download_anexo_local_idor_chave_fora_dos_anexos(client_logado_solicitante):
    """IDOR: chave local: que não pertence ao chamado -> 403."""
    chamado = _criar_chamado(chaves=["local:original.pdf"], solicitante_id="sol_1")

    r = client_logado_solicitante.get(
        f"/api/download-anexo?chamado_id={chamado.id}&chave=local:outro.pdf"
    )

    assert r.status_code == 403


def test_download_anexo_local_usuario_sem_permissao_403(client_logado_solicitante):
    """GET de solicitante para chamado alheio com chave local: -> 403 (sem mock de permissão)."""
    chamado = _criar_chamado(chaves=["local:doc.pdf"], solicitante_id="outro_usuario")

    r = client_logado_solicitante.get(
        f"/api/download-anexo?chamado_id={chamado.id}&chave=local:doc.pdf"
    )

    assert r.status_code == 403


def test_download_anexo_local_path_traversal_rejeitado(client_logado_solicitante, app):
    """Chave local: com tentativa de path traversal, mesmo pertencendo ao doc, é rejeitada."""
    app.config["ANEXO_LOCAL_DIR"] = "/tmp/test_anexos_local_traversal"
    chamado = _criar_chamado(chaves=["local:../../etc/passwd"], solicitante_id="sol_1")

    r = client_logado_solicitante.get(
        f"/api/download-anexo?chamado_id={chamado.id}&chave=local:../../etc/passwd"
    )

    assert r.status_code == 400


# ── Legado (sem prefixo, fecha o gap de app/static/uploads público) ──────────


def test_download_anexo_legado_sem_prefixo_autorizado(client_logado_solicitante, app, tmp_path):
    """Anexo legado sem prefixo, dono autorizado -> 200 via rota autenticada."""
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    (tmp_path / "old_doc.pdf").write_bytes(b"conteudo")
    chamado = _criar_chamado(chaves=["old_doc.pdf"], solicitante_id="sol_1")

    r = client_logado_solicitante.get(
        f"/api/download-anexo?chamado_id={chamado.id}&chave=old_doc.pdf"
    )

    assert r.status_code == 200


def test_download_anexo_legado_idor_403(client_logado_solicitante):
    """Anexo legado sem prefixo de chamado alheio -> 403 (fecha o gap de segurança)."""
    chamado = _criar_chamado(chaves=["old_doc.pdf"], solicitante_id="outro_usuario")

    r = client_logado_solicitante.get(
        f"/api/download-anexo?chamado_id={chamado.id}&chave=old_doc.pdf"
    )

    assert r.status_code == 403
