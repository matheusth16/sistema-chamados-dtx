"""TDD: inclusão automática de observadora quando Produção está envolvida no chamado.

Regra de negócio (2026-08-17, estendida em 2026-08-18): julia.salgado@dtx.aero
(supervisora de "Planejamento de Produção", área distinta de "Produção") entra
automaticamente como observadora — aparece em `chamado.observadores` e recebe
as notificações que qualquer observador já recebe (e-mail/in-app/Web Push, ver
_notificar_observadores_inclusao) — em dois sentidos:

1. Solicitante da área "Produção" abre chamado pra qualquer outro setor.
2. Solicitante de qualquer outro setor abre chamado com destino "Produção".

Nenhum dos dois sentidos dispara quando a área envolvida do outro lado é
"Produção" ou "Planejamento de Produção" (ela já tem visibilidade natural
desses chamados — evita notificação duplicada e ela virar observadora do
próprio chamado dela).
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.models import Chamado
from app.services.chamados_criacao_service import criar_chamado

pytestmark = pytest.mark.usefixtures("db_session")


@pytest.fixture(autouse=True)
def _patch_supervisores():
    with patch("app.models_usuario.Usuario.get_supervisores_por_area", return_value=[]):
        yield


class _FakeThread:
    def __init__(self, target=None, daemon=None, **kwargs):
        self._target = target

    def start(self):
        if self._target:
            self._target()


def _julia_mock():
    julia = MagicMock()
    julia.id = "user_b4c6c498b86a4bb6a97f8a0ad5bf902c"
    julia.nome = "Julia Salgado"
    julia.email = "julia.salgado@dtx.aero"
    return julia


def _base_form(tipo, observadores_json="[]"):
    return {
        "categoria": tipo,
        "tipo": tipo,
        "descricao": "Descrição com mais de 10 chars para passar na validação.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
        "observadores_json": observadores_json,
    }


def _files_mock():
    m = MagicMock()
    m.getlist.return_value = []
    m.get.return_value = None
    return m


def _fake_atribuidor_result():
    return {
        "sucesso": True,
        "supervisor": {"id": "sup_1", "nome": "Supervisor Teste"},
        "motivo": "",
    }


def _criar_chamado_patched(form, area_solicitante, get_by_email_return):
    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado",
            return_value="2026-777",
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread", _FakeThread),
        patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado"),
        patch("app.services.chamados_criacao_service.notificar_setores_adicionais_chamado"),
        patch("app.services.chamados_criacao_service._notificar_observadores_inclusao"),
        patch("app.services.chamados_criacao_service.criar_notificacao"),
        patch("app.services.chamados_criacao_service.enviar_webpush_usuario"),
        patch(
            "app.services.chamados_criacao_service.Usuario.get_by_email",
            return_value=get_by_email_return,
        ) as mock_get_by_email,
        patch(
            "app.services.chamados_criacao_service.Usuario.get_by_id",
            return_value=_fake_atribuidor_result()["supervisor"],
        ),
    ):
        mock_atr.atribuir.return_value = _fake_atribuidor_result()
        chamado_id, _, erro, _ = criar_chamado(
            form=form,
            files=_files_mock(),
            solicitante_id="sol_1",
            solicitante_nome="Solicitante",
            area_solicitante=area_solicitante,
        )
    return chamado_id, erro, mock_get_by_email


class TestObservadorAutomaticoProducao:
    def test_producao_abre_para_outro_setor_inclui_julia(self, app):
        """Solicitante de Produção abrindo chamado pra TI → Julia entra em cópia."""
        form = _base_form("TI")
        with app.app_context():
            chamado_id, erro, _ = _criar_chamado_patched(
                form, area_solicitante="Produção", get_by_email_return=_julia_mock()
            )

        assert erro is None
        observadores = Chamado.get_by_id(chamado_id).observadores
        ids = {o["usuario_id"] for o in observadores}
        assert "user_b4c6c498b86a4bb6a97f8a0ad5bf902c" in ids

    def test_producao_abre_para_producao_nao_inclui_julia(self, app):
        """Chamado de Produção pra ela mesma (mesmo setor) não dispara a inclusão."""
        form = _base_form("Produção")
        with app.app_context():
            chamado_id, erro, mock_get_by_email = _criar_chamado_patched(
                form, area_solicitante="Produção", get_by_email_return=_julia_mock()
            )

        assert erro is None
        assert Chamado.get_by_id(chamado_id).observadores == []
        mock_get_by_email.assert_not_called()

    def test_producao_abre_para_planejamento_producao_nao_inclui_julia(self, app):
        """Chamado de Produção pra 'Planejamento de Produção' (área da própria Julia,
        onde ela já é supervisora/responsável) não dispara a inclusão — evitaria
        notificação duplicada e ela aparecer como observadora do próprio chamado dela."""
        form = _base_form("Planejamento de Produção")
        with app.app_context():
            chamado_id, erro, mock_get_by_email = _criar_chamado_patched(
                form, area_solicitante="Produção", get_by_email_return=_julia_mock()
            )

        assert erro is None
        assert Chamado.get_by_id(chamado_id).observadores == []
        mock_get_by_email.assert_not_called()

    def test_outro_setor_abre_chamado_nao_inclui_julia(self, app):
        """Solicitante fora de Produção não dispara a inclusão automática."""
        form = _base_form("TI")
        with app.app_context():
            chamado_id, erro, mock_get_by_email = _criar_chamado_patched(
                form, area_solicitante="TI", get_by_email_return=_julia_mock()
            )

        assert erro is None
        assert Chamado.get_by_id(chamado_id).observadores == []
        mock_get_by_email.assert_not_called()

    def test_julia_ja_incluida_manualmente_nao_duplica(self, app):
        """Solicitante já colocou Julia manualmente em cópia → sem duplicata (violaria UNIQUE)."""
        obs_list = [
            {
                "usuario_id": "user_b4c6c498b86a4bb6a97f8a0ad5bf902c",
                "nome": "Julia Salgado",
                "email": "julia.salgado@dtx.aero",
            }
        ]
        form = _base_form("TI", json.dumps(obs_list))
        with app.app_context():
            chamado_id, erro, _ = _criar_chamado_patched(
                form, area_solicitante="Produção", get_by_email_return=_julia_mock()
            )

        assert erro is None
        observadores = Chamado.get_by_id(chamado_id).observadores
        ids = [o["usuario_id"] for o in observadores]
        assert ids.count("user_b4c6c498b86a4bb6a97f8a0ad5bf902c") == 1

    def test_conta_julia_ausente_nao_bloqueia_criacao(self, app):
        """Conta não encontrada (desativada/removida) → chamado criado normalmente, sem observador extra."""
        form = _base_form("TI")
        with app.app_context():
            chamado_id, erro, _ = _criar_chamado_patched(
                form, area_solicitante="Produção", get_by_email_return=None
            )

        assert erro is None
        assert Chamado.get_by_id(chamado_id).observadores == []

    def test_solicitante_com_multiplas_areas_incluindo_producao(self, app):
        """area_solicitante é string 'Produção, Comercial' (join de múltiplas áreas) → ainda dispara."""
        form = _base_form("TI")
        with app.app_context():
            chamado_id, erro, _ = _criar_chamado_patched(
                form, area_solicitante="Produção, Comercial", get_by_email_return=_julia_mock()
            )

        assert erro is None
        ids = {o["usuario_id"] for o in Chamado.get_by_id(chamado_id).observadores}
        assert "user_b4c6c498b86a4bb6a97f8a0ad5bf902c" in ids

    def test_outro_setor_abre_para_producao_inclui_julia(self, app):
        """Solicitante de TI abrindo chamado com destino Produção → Julia entra em cópia."""
        form = _base_form("Produção")
        with app.app_context():
            chamado_id, erro, _ = _criar_chamado_patched(
                form, area_solicitante="TI", get_by_email_return=_julia_mock()
            )

        assert erro is None
        ids = {o["usuario_id"] for o in Chamado.get_by_id(chamado_id).observadores}
        assert "user_b4c6c498b86a4bb6a97f8a0ad5bf902c" in ids

    def test_planejamento_producao_abre_para_producao_nao_inclui_julia(self, app):
        """Chamado originado no próprio time dela (Planejamento de Produção) com destino
        Produção não dispara a inclusão — mesma lógica de exclusão usada no sentido
        contrário (ela já tem visibilidade natural do chamado do próprio time)."""
        form = _base_form("Produção")
        with app.app_context():
            chamado_id, erro, mock_get_by_email = _criar_chamado_patched(
                form,
                area_solicitante="Planejamento de Produção",
                get_by_email_return=_julia_mock(),
            )

        assert erro is None
        assert Chamado.get_by_id(chamado_id).observadores == []
        mock_get_by_email.assert_not_called()
