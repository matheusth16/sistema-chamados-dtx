"""Testes do serviço de criação de chamados (criar_chamado)."""

from unittest.mock import MagicMock, patch

from app.services.chamados_criacao_service import criar_chamado


class _FakeThread:
    """Thread fake para executar target imediatamente nos testes."""

    def __init__(self, target=None, daemon=None, **kwargs):
        self._target = target
        self.daemon = daemon

    def start(self):
        if self._target:
            self._target()


def test_criar_chamado_com_dados_validos_retorna_id_e_numero(app):
    """criar_chamado com form válido e mocks retorna (chamado_id, numero_chamado, None, aviso)."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Descrição com mais de 3 caracteres para passar na validação.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
    }
    files = MagicMock()
    files.get.return_value = None

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-099"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.execute_with_retry") as mock_retry,
        patch("app.services.chamados_criacao_service.Historico") as mock_hist,
        patch("app.services.chamados_criacao_service.threading.Thread") as mock_thread,
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor Teste"},
            "motivo": "",
        }
        mock_ref = MagicMock()
        mock_ref.id = "chamado_id_123"
        mock_retry.return_value = (None, mock_ref)
        # threading.Thread mockado para não disparar thread real no teste
        with app.app_context():
            chamado_id, numero, erro, aviso = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante Teste",
                area_solicitante="Manutencao",
                solicitante_email="sol@test.com",
            )

    assert chamado_id == "chamado_id_123"
    assert numero == "2026-099"
    assert erro is None
    mock_retry.assert_called_once()
    mock_hist.return_value.save.assert_called_once()
    # O serviço dispara notificações em background; validamos que houve disparo.
    assert mock_thread.return_value.start.call_count >= 1


def test_criar_chamado_anexo_invalido_retorna_erro():
    """criar_chamado quando salvar_anexo levanta ValueError retorna (None, None, mensagem, None)."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Descrição válida.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
    }
    files = MagicMock()
    files.get.return_value = MagicMock()

    with patch(
        "app.services.chamados_criacao_service.salvar_anexo",
        side_effect=ValueError("Extensão não permitida"),
    ):
        chamado_id, numero, erro, aviso = criar_chamado(
            form=form,
            files=files,
            solicitante_id="sol1",
            solicitante_nome="Solicitante",
            area_solicitante="Manutencao",
        )

    assert chamado_id is None
    assert numero is None
    assert erro == "Extensão não permitida"
    assert aviso is None


def test_criar_chamado_com_setores_adicionais_dispara_notificacao_setores(app):
    """Na criação com setores adicionais, deve disparar notificação específica de setores."""

    class _FormComGetlist(dict):
        def getlist(self, key):
            if key == "setores_adicionais":
                return ["Engenharia", "Material"]
            return []

    form = _FormComGetlist(
        {
            "categoria": "Projetos",
            "tipo": "Manutencao",
            "descricao": "Descrição válida com setores adicionais.",
            "rl_codigo": "RL-001",
            "impacto": "",
            "gate": "",
        }
    )
    files = MagicMock()
    files.get.return_value = None
    responsavel_usuario = MagicMock()
    responsavel_usuario.email = "resp@dtx.aero"

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-200"
        ),
        patch("app.services.chamados_criacao_service.GrupoRL.get_or_create") as mock_grupo,
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.execute_with_retry") as mock_retry,
        patch("app.services.chamados_criacao_service.Historico") as mock_hist,
        patch(
            "app.services.chamados_criacao_service.Usuario.get_by_id",
            return_value=responsavel_usuario,
        ),
        patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado"),
        patch(
            "app.services.chamados_criacao_service.notificar_setores_adicionais_chamado"
        ) as mock_notif_setores,
        patch("app.services.chamados_criacao_service.threading.Thread", side_effect=_FakeThread),
    ):
        mock_grupo.return_value = MagicMock(id="grupo_1")
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor Teste"},
            "motivo": "",
        }
        mock_ref = MagicMock()
        mock_ref.id = "chamado_id_200"
        mock_retry.return_value = (None, mock_ref)

        with app.app_context():
            chamado_id, numero, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante Teste",
                area_solicitante="Manutencao",
                solicitante_email="sol@test.com",
            )

    assert erro is None
    assert chamado_id == "chamado_id_200"
    assert numero == "2026-200"
    mock_hist.return_value.save.assert_called_once()
    mock_notif_setores.assert_called_once()
    kwargs = mock_notif_setores.call_args.kwargs
    assert kwargs["numero_chamado"] == "2026-200"
    assert kwargs["setores_novos"] == ["Engenharia", "Material"]
