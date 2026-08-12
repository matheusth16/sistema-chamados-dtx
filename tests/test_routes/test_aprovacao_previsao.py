"""Testes da rota pública GET/POST /aprovacao-previsao/<token> (sem login) —
ver app/routes/aprovacao_previsao.py e app/services/previsao_atendimento_service.py.

GET deve ser somente leitura (sem side-effect — evita prefetch de e-mail
disparando a decisão). POST efetiva a decisão via token.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models import Chamado

pytestmark = pytest.mark.usefixtures("db_session")

GESTOR_ENGENHARIA = MagicMock()
GESTOR_ENGENHARIA.id = "id_gestor_eng"
GESTOR_ENGENHARIA.nome = "Gestor Engenharia"
GESTOR_ENGENHARIA.email = "gestor@dtx.aero"
GESTOR_ENGENHARIA.areas = ["Engenharia"]
GESTOR_ENGENHARIA.nivel_gestao = "gestor_setor"
GESTOR_ENGENHARIA.ativo = True
GESTOR_ENGENHARIA.is_admin_or_above = False

JULIA = MagicMock()
JULIA.id = "id_julia"
JULIA.nome = "Julia Silva"
JULIA.perfil = "supervisor"
JULIA.areas = ["Engenharia"]
JULIA.is_admin_or_above = False


def _criar_chamado_com_pedido_pendente(app) -> tuple[int, int]:
    """Cria chamado + solicitação pendente reais (Postgres), retorna (chamado_id, solicitacao_id)."""
    chamado = Chamado(
        categoria="Manutencao",
        tipo_solicitacao="Corretiva",
        descricao="Descrição teste",
        responsavel="Julia Silva",
        responsavel_id="id_julia",
        area="Engenharia",
        status="Em Atendimento",
    )
    chamado_id = chamado.salvar()

    from app.services.previsao_atendimento_service import solicitar_previsao_atendimento

    with (
        app.app_context(),
        patch("app.models_usuario.Usuario.get_all", return_value=[GESTOR_ENGENHARIA]),
    ):
        resultado = solicitar_previsao_atendimento(
            chamado_id,
            datetime.now() + timedelta(days=3),
            "Preciso de mais tempo",
            JULIA,
        )
    assert resultado["sucesso"] is True
    return chamado_id, resultado["dados"]["solicitacao_id"]


def _token(app, solicitacao_id: int, acao: str) -> str:
    from app.services.previsao_atendimento_service import gerar_token_decisao

    with app.app_context():
        return gerar_token_decisao(solicitacao_id, acao)


class TestAprovacaoPrevisaoTokenInvalido:
    def test_token_invalido_retorna_400(self, client):
        resp = client.get("/aprovacao-previsao/token-lixo-invalido")
        assert resp.status_code == 400

    def test_token_de_solicitacao_inexistente_retorna_404(self, client, app):
        token = _token(app, 999999999, "aprovar")
        resp = client.get(f"/aprovacao-previsao/{token}")
        assert resp.status_code == 404


class TestAprovacaoPrevisaoGetSomenteLeitura:
    def test_get_nao_decide_nada(self, client, app):
        """GET não deve mudar o status da solicitação (sem side-effect)."""
        chamado_id, solicitacao_id = _criar_chamado_com_pedido_pendente(app)
        token = _token(app, solicitacao_id, "aprovar")

        resp = client.get(f"/aprovacao-previsao/{token}")

        assert resp.status_code == 200
        atualizado = Chamado.get_by_id(chamado_id)
        assert atualizado.previsao_atendimento is None

    def test_get_mostra_pagina_de_confirmacao(self, client, app):
        chamado_id, solicitacao_id = _criar_chamado_com_pedido_pendente(app)
        token = _token(app, solicitacao_id, "aprovar")

        resp = client.get(f"/aprovacao-previsao/{token}")

        assert resp.status_code == 200
        assert b"Julia Silva" in resp.data


class TestAprovacaoPrevisaoPost:
    def test_post_aprovar_aplica_no_chamado(self, client, app):
        chamado_id, solicitacao_id = _criar_chamado_com_pedido_pendente(app)
        token = _token(app, solicitacao_id, "aprovar")

        with patch(
            "app.routes.aprovacao_previsao.Usuario.get_by_id", return_value=GESTOR_ENGENHARIA
        ):
            resp = client.post(f"/aprovacao-previsao/{token}")

        assert resp.status_code == 200
        atualizado = Chamado.get_by_id(chamado_id)
        assert atualizado.previsao_atendimento is not None

    def test_post_rejeitar_nao_aplica_no_chamado(self, client, app):
        chamado_id, solicitacao_id = _criar_chamado_com_pedido_pendente(app)
        token = _token(app, solicitacao_id, "rejeitar")

        with patch(
            "app.routes.aprovacao_previsao.Usuario.get_by_id", return_value=GESTOR_ENGENHARIA
        ):
            resp = client.post(f"/aprovacao-previsao/{token}")

        assert resp.status_code == 200
        atualizado = Chamado.get_by_id(chamado_id)
        assert atualizado.previsao_atendimento is None

    def test_post_duas_vezes_segunda_retorna_409(self, client, app):
        chamado_id, solicitacao_id = _criar_chamado_com_pedido_pendente(app)
        token = _token(app, solicitacao_id, "aprovar")

        with patch(
            "app.routes.aprovacao_previsao.Usuario.get_by_id", return_value=GESTOR_ENGENHARIA
        ):
            primeira = client.post(f"/aprovacao-previsao/{token}")
            segunda = client.post(f"/aprovacao-previsao/{token}")

        assert primeira.status_code == 200
        assert segunda.status_code == 409

    def test_post_gestor_nao_encontrado_retorna_403(self, client, app):
        chamado_id, solicitacao_id = _criar_chamado_com_pedido_pendente(app)
        token = _token(app, solicitacao_id, "aprovar")

        with patch("app.routes.aprovacao_previsao.Usuario.get_by_id", return_value=None):
            resp = client.post(f"/aprovacao-previsao/{token}")

        assert resp.status_code == 403
        atualizado = Chamado.get_by_id(chamado_id)
        assert atualizado.previsao_atendimento is None

    def test_post_gestor_sem_permissao_hoje_retorna_erro(self, client, app):
        """Token válido, mas o gestor gravado no pedido não qualifica mais pra
        área do chamado (ex.: mudou de setor) — decisão é recusada mesmo assim."""
        chamado_id, solicitacao_id = _criar_chamado_com_pedido_pendente(app)
        token = _token(app, solicitacao_id, "aprovar")

        gestor_sem_permissao = MagicMock()
        gestor_sem_permissao.id = "id_gestor_eng"
        gestor_sem_permissao.nome = "Ex-Gestor"
        gestor_sem_permissao.nivel_gestao = None
        gestor_sem_permissao.areas = []
        gestor_sem_permissao.is_admin_or_above = False

        with patch(
            "app.routes.aprovacao_previsao.Usuario.get_by_id", return_value=gestor_sem_permissao
        ):
            resp = client.post(f"/aprovacao-previsao/{token}")

        assert resp.status_code == 403
        atualizado = Chamado.get_by_id(chamado_id)
        assert atualizado.previsao_atendimento is None
