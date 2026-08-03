"""
Fase 4 — cancelamento de chamado pelo solicitante.

Regras:
- Só o solicitante dono pode cancelar
- Motivo obrigatório (mín 10 chars)
- Só statuses canceláveis: Aberto, Em Atendimento, Aguardando Informação
- Concluído e Cancelado → 403
- Observadores NÃO podem cancelar
- Notificação deve ser disparada (responsável + observadores)

Fase 2 (Marco 7): persistência real contra Postgres (fixture db_session) via
Chamado.salvar()/get_by_id() — substitui o antigo mock de
db.collection("chamados").document(id).get()/.update(...).
"""

from unittest.mock import MagicMock, patch

import pytest

from app.models import Chamado

pytestmark = pytest.mark.usefixtures("db_session")

_ID_INEXISTENTE = 999999999


def _usuario_mock(uid="sol_1", perfil="solicitante"):
    u = MagicMock()
    u.id = uid
    u.nome = "Solicitante Teste"
    u.perfil = perfil
    u.email = "sol@test.com"
    u.is_admin_or_above = perfil in ("admin", "admin_global")
    return u


class _UsuarioContextoLimitado:
    """Simula o current_user do Flask-Login (LocalProxy ligado ao request context).

    Fora do request context original (dentro da thread de notificação em
    background, que só empurra app_context) o proxy real deixa de resolver e
    vira None — acessar .nome nesse momento explode com AttributeError.
    """

    def __init__(self, uid="sol_1", nome="Solicitante Teste", perfil="solicitante"):
        self.id = uid
        self.perfil = perfil
        self.email = "sol@test.com"
        self.is_admin_or_above = perfil in ("admin", "admin_global")
        self._nome = nome
        self.contexto_ativo = True

    @property
    def nome(self):
        if not self.contexto_ativo:
            raise AttributeError("'NoneType' object has no attribute 'nome'")
        return self._nome


def _criar_chamado_real(
    solicitante_id="sol_1",
    status="Aberto",
    responsavel_id="sup_1",
    numero_chamado="CH-001",
    categoria="TI",
    observadores=None,
) -> int:
    chamado = Chamado(
        categoria=categoria,
        tipo_solicitacao="Suporte",
        descricao="Descrição de teste",
        responsavel="Responsável",
        responsavel_id=responsavel_id,
        solicitante_id=solicitante_id,
        solicitante_nome="Solicitante Teste",
        numero_chamado=numero_chamado,
        status=status,
        observadores=observadores or [],
    )
    chamado_id = chamado.salvar()
    assert chamado_id is not None
    return chamado_id


class TestCancelarChamadoSolicitante:
    def test_owner_cancela_aberto_com_motivo(self):
        """Dono + motivo + status Aberto → sucesso."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()
        chamado_id = _criar_chamado_real()

        with (
            patch("app.services.cancelamento_solicitante_service.Historico") as mock_hist,
            patch("app.services.cancelamento_solicitante_service._notificar_cancelamento"),
        ):
            mock_hist.return_value.save.return_value = True

            resultado = cancelar_chamado_solicitante(
                chamado_id=chamado_id,
                motivo="Problema resolvido por outra via",
                usuario=user,
            )

        assert resultado["sucesso"] is True

    def test_owner_cancela_em_atendimento(self):
        """Status Em Atendimento → também pode cancelar."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()
        chamado_id = _criar_chamado_real(status="Em Atendimento")

        with (
            patch("app.services.cancelamento_solicitante_service.Historico") as mock_hist,
            patch("app.services.cancelamento_solicitante_service._notificar_cancelamento"),
        ):
            mock_hist.return_value.save.return_value = True

            resultado = cancelar_chamado_solicitante(
                chamado_id=chamado_id,
                motivo="Problema resolvido por outra via",
                usuario=user,
            )

        assert resultado["sucesso"] is True

    def test_nao_owner_bloqueado(self):
        """Outro usuário (não dono) → 403."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock(uid="outro")
        chamado_id = _criar_chamado_real(solicitante_id="dono_real")

        resultado = cancelar_chamado_solicitante(
            chamado_id=chamado_id,
            motivo="Motivo válido aqui",
            usuario=user,
        )

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 403

    def test_motivo_vazio_bloqueado(self):
        """Motivo vazio → 400."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()
        chamado_id = _criar_chamado_real()

        resultado = cancelar_chamado_solicitante(
            chamado_id=chamado_id,
            motivo="",
            usuario=user,
        )

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 400

    def test_status_concluido_bloqueado(self):
        """Status Concluído → não pode cancelar (403)."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()
        chamado_id = _criar_chamado_real(status="Concluído")

        resultado = cancelar_chamado_solicitante(
            chamado_id=chamado_id,
            motivo="Motivo suficientemente longo",
            usuario=user,
        )

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 403

    def test_status_cancelado_bloqueado(self):
        """Chamado já Cancelado → 403."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()
        chamado_id = _criar_chamado_real(status="Cancelado")

        resultado = cancelar_chamado_solicitante(
            chamado_id=chamado_id,
            motivo="Motivo suficientemente longo",
            usuario=user,
        )

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 403

    def test_notificacao_disparada_apos_cancelamento(self):
        """Após cancelar, _notificar_cancelamento deve ser chamado."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()
        chamado_id = _criar_chamado_real()

        with (
            patch("app.services.cancelamento_solicitante_service.Historico") as mock_hist,
            patch(
                "app.services.cancelamento_solicitante_service._notificar_cancelamento"
            ) as mock_notif,
        ):
            mock_hist.return_value.save.return_value = True

            cancelar_chamado_solicitante(
                chamado_id=chamado_id,
                motivo="Cancelamento justificado",
                usuario=user,
            )

        mock_notif.assert_called_once()

    def test_historico_registra_motivo(self):
        """Historico deve conter o motivo no campo detalhe."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()
        chamado_id = _criar_chamado_real()
        historicos = []

        def capturar(**kwargs):
            historicos.append(kwargs)
            h = MagicMock()
            h.save.return_value = True
            return h

        with (
            patch(
                "app.services.cancelamento_solicitante_service.Historico",
                side_effect=capturar,
            ),
            patch("app.services.cancelamento_solicitante_service._notificar_cancelamento"),
        ):
            cancelar_chamado_solicitante(
                chamado_id=chamado_id,
                motivo="Cancelamento justificado",
                usuario=user,
            )

        assert len(historicos) >= 1
        detalhe = historicos[0].get("detalhe") or ""
        assert "Cancelamento justificado" in detalhe


class TestCancelarDataCancelamento:
    def test_data_cancelamento_gravada(self):
        """CT-REQ-11: data_cancelamento deve ser persistida no Postgres."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()
        chamado_id = _criar_chamado_real()

        with (
            patch("app.services.cancelamento_solicitante_service.Historico") as mock_hist,
            patch("app.services.cancelamento_solicitante_service._notificar_cancelamento"),
        ):
            mock_hist.return_value.save.return_value = True

            resultado = cancelar_chamado_solicitante(
                chamado_id=chamado_id,
                motivo="Cancelamento justificado",
                usuario=user,
            )

        assert resultado["sucesso"] is True
        assert Chamado.get_by_id(chamado_id).data_cancelamento is not None


class TestCancelarCoverage:
    def test_chamado_nao_encontrado_retorna_404(self):
        """Chamado inexistente → 404."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()

        resultado = cancelar_chamado_solicitante(_ID_INEXISTENTE, "motivo válido aqui", user)

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 404

    def test_excecao_retorna_500(self):
        """Exceção durante criação do Historico → 500."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()
        chamado_id = _criar_chamado_real()

        with patch(
            "app.services.cancelamento_solicitante_service.Historico",
            side_effect=RuntimeError("boom"),
        ):
            resultado = cancelar_chamado_solicitante(chamado_id, "motivo suficiente aqui", user)

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 500

    def test_notificar_cancelamento_executa_thread(self, app):
        """_notificar_cancelamento dispara daemon thread."""
        from app.services.cancelamento_solicitante_service import _notificar_cancelamento

        user = _usuario_mock()
        dados = {"numero_chamado": "CH-001", "categoria": "TI", "observadores": []}

        mock_thread = MagicMock()
        with (
            patch("threading.Thread", return_value=mock_thread) as mock_thread_cls,
            app.app_context(),
        ):
            _notificar_cancelamento(
                chamado_id="ch_1", dados=dados, motivo="motivo válido", usuario=user
            )

        mock_thread_cls.assert_called_once()
        mock_thread.start.assert_called_once()

    def test_nome_do_solicitante_capturado_antes_da_thread(self, app):
        """Regressão: usuario.nome deve ser lido ANTES de _run() ser agendado.

        _run() só reabre app_context (não request context) dentro da thread,
        então o current_user real fica None nesse ponto e usuario.nome
        explodiria — a notificação de cancelamento teria que sair mesmo
        assim, com o nome capturado enquanto o request context ainda existia.
        """
        from app.services.cancelamento_solicitante_service import _notificar_cancelamento

        user = _UsuarioContextoLimitado(nome="Fulano de Tal")
        dados = {"numero_chamado": "CH-001", "categoria": "TI", "observadores": []}
        closures = []

        def fake_thread(target, daemon=True):
            closures.append(target)
            m = MagicMock()
            m.start = lambda: None
            return m

        with patch("threading.Thread", side_effect=fake_thread), app.app_context():
            _notificar_cancelamento(
                chamado_id="ch_1", dados=dados, motivo="motivo válido", usuario=user
            )

        # Simula a thread rodando fora do request context original
        user.contexto_ativo = False

        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[],
            ),
            patch(
                "app.services.chamado_notificacao_service.notificar_cancelamento_chamado"
            ) as mock_notificar,
        ):
            closures[0]()

        mock_notificar.assert_called_once()
        assert mock_notificar.call_args.kwargs["solicitante_nome"] == "Fulano de Tal"
