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
    files.getlist.return_value = []

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
    arq = MagicMock()
    arq.filename = "doc.pdf"
    files = MagicMock()
    files.get.return_value = MagicMock()
    files.getlist.return_value = [arq]

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
    files.getlist.return_value = []
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


def test_criar_chamado_nao_notifica_inapp_quando_responsavel_e_solicitante(app):
    """Quando responsavel_id == solicitante_id, criar_notificacao não deve ser chamado."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Chamado criado pelo próprio responsável.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
    }
    files = MagicMock()
    files.get.return_value = None
    files.getlist.return_value = []

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-555"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.execute_with_retry") as mock_retry,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.criar_notificacao") as mock_criar_notif,
        patch("app.services.chamados_criacao_service.enviar_webpush_usuario") as mock_webpush,
        patch("app.services.chamados_criacao_service.threading.Thread", side_effect=_FakeThread),
    ):
        # Atribuição fallback: responsavel retorna o próprio solicitante
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sol_auto", "nome": "Auto Solicitante"},
            "motivo": "",
        }
        mock_ref = MagicMock()
        mock_ref.id = "chamado_id_555"
        mock_retry.return_value = (None, mock_ref)

        with app.app_context():
            chamado_id, numero, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol_auto",
                solicitante_nome="Auto Solicitante",
                area_solicitante="Manutencao",
                solicitante_email="auto@test.com",
            )

    assert erro is None
    assert chamado_id == "chamado_id_555"
    # Responsável == solicitante → sem notificação in-app nem web push
    mock_criar_notif.assert_not_called()
    mock_webpush.assert_not_called()


def test_criar_chamado_persiste_categoria_e_solicitante_nome_na_notificacao(app):
    """criar_notificacao deve receber categoria e solicitante_nome para i18n na leitura."""
    form = {
        "categoria": "Nao Aplicavel",
        "tipo": "Manutencao",
        "descricao": "Descrição de teste para metadados i18n.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
    }
    files = MagicMock()
    files.get.return_value = None
    files.getlist.return_value = []
    responsavel_usuario = MagicMock()
    responsavel_usuario.email = "resp@dtx.aero"

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="CHM-0006"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.execute_with_retry") as mock_retry,
        patch("app.services.chamados_criacao_service.Historico"),
        patch(
            "app.services.chamados_criacao_service.Usuario.get_by_id",
            return_value=responsavel_usuario,
        ),
        patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado"),
        patch("app.services.chamados_criacao_service.criar_notificacao") as mock_criar_notif,
        patch("app.services.chamados_criacao_service.enviar_webpush_usuario"),
        patch("app.services.chamados_criacao_service.threading.Thread", side_effect=_FakeThread),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup_meta", "nome": "Supervisor Meta"},
            "motivo": "",
        }
        mock_ref = MagicMock()
        mock_ref.id = "chamado_meta_01"
        mock_retry.return_value = (None, mock_ref)

        with app.app_context():
            chamado_id, numero, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol_meta",
                solicitante_nome="Solicitante Teste",
                area_solicitante="Manutencao",
                solicitante_email="sol@test.com",
            )

    assert erro is None
    mock_criar_notif.assert_called_once()
    kwargs = mock_criar_notif.call_args.kwargs
    assert kwargs.get("categoria") == "Nao Aplicavel"
    assert kwargs.get("solicitante_nome") == "Solicitante Teste"


# ── Testes anti-self-ticket (TDD RED → GREEN) ────────────────────────────────


def test_criar_chamado_ignora_responsavel_form_igual_ao_solicitante(app):
    """
    RED: se responsavel_id_form == solicitante_id, o sistema deve ignorar
    a escolha manual e usar auto-atribuição — nunca deixar alguém ser
    responsável do próprio chamado via form.
    """
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Chamado com self-assignment tentado.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
        # Solicitante tenta se auto-atribuir
        "responsavel_id": "sol1",
        "responsavel_nome": "Solicitante Teste",
    }
    files = MagicMock()
    files.getlist.return_value = []

    # Usuário "sol1" é supervisor — tecnicamente válido no perfil, mas é o próprio solicitante
    usuario_sup = MagicMock()
    usuario_sup.id = "sol1"
    usuario_sup.perfil = "supervisor"

    chamado_capturado = {}

    def _fake_add(dados):
        chamado_capturado.update(dados)
        ref = MagicMock()
        ref.id = "chamado_self_block"
        return (None, ref)

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-400"
        ),
        patch("app.services.chamados_criacao_service.Usuario.get_by_id", return_value=usuario_sup),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch(
            "app.services.chamados_criacao_service.execute_with_retry",
            side_effect=lambda fn, dados, **kw: _fake_add(dados),
        ),
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
    ):
        # Auto-atribuição devolve um supervisor diferente
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup_outro", "nome": "Outro Supervisor"},
            "motivo": "",
        }

        with app.app_context():
            chamado_id, numero, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante Teste",
                area_solicitante="Manutencao",
            )

    assert erro is None
    # O responsável NÃO pode ser o próprio solicitante (self-assignment ignorado)
    assert chamado_capturado.get("responsavel_id") != "sol1", (
        "Self-assignment não foi bloqueado: responsavel_id == solicitante_id"
    )
    assert chamado_capturado.get("responsavel_id") == "sup_outro"


# ── Testes multi-anexo (TDD RED → GREEN) ─────────────────────────────────────


def _arq_mock(nome: str) -> MagicMock:
    arq = MagicMock()
    arq.filename = nome
    return arq


def test_criar_chamado_dois_anexos_salva_ambos(app):
    """getlist com 2 arquivos → salvar_anexo chamado 2x; Chamado tem anexo + anexos(2 itens)."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Chamado com dois anexos.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
    }
    arq1, arq2 = _arq_mock("a.pdf"), _arq_mock("b.xlsx")
    files = MagicMock()
    files.getlist.return_value = [arq1, arq2]

    chamado_capturado = {}

    def _fake_add(dados):
        chamado_capturado.update(dados)
        ref = MagicMock()
        ref.id = "chamado_multi_001"
        return (None, ref)

    with (
        patch(
            "app.services.chamados_criacao_service.salvar_anexo",
            side_effect=["caminho/a.pdf", "caminho/b.xlsx"],
        ) as mock_salvar,
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-300"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch(
            "app.services.chamados_criacao_service.execute_with_retry",
            side_effect=lambda fn, dados, **kw: _fake_add(dados),
        ),
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor"},
            "motivo": "",
        }

        with app.app_context():
            chamado_id, numero, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante",
                area_solicitante="Manutencao",
            )

    assert erro is None
    assert chamado_id == "chamado_multi_001"
    assert mock_salvar.call_count == 2
    assert chamado_capturado.get("anexo") == "caminho/a.pdf"
    assert chamado_capturado.get("anexos") == ["caminho/a.pdf", "caminho/b.xlsx"]


def test_criar_chamado_falha_segundo_anexo_retorna_erro_sem_persistir(app):
    """Falha no 2º salvar_anexo → retorna erro; Firestore add NÃO chamado."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Dois arquivos, segundo falha.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
    }
    arq1, arq2 = _arq_mock("ok.pdf"), _arq_mock("bad.exe")
    files = MagicMock()
    files.getlist.return_value = [arq1, arq2]

    with (
        patch(
            "app.services.chamados_criacao_service.salvar_anexo",
            side_effect=["caminho/ok.pdf", ValueError("Extensão não permitida")],
        ),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-301"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.execute_with_retry") as mock_retry,
        patch("app.services.chamados_criacao_service.Historico"),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor"},
            "motivo": "",
        }

        with app.app_context():
            chamado_id, numero, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante",
                area_solicitante="Manutencao",
            )

    assert chamado_id is None
    assert erro is not None
    mock_retry.assert_not_called()


def test_criar_chamado_sem_anexos_usa_none_e_lista_vazia(app):
    """Sem arquivos → Chamado criado com anexo=None e anexos=[]."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Chamado sem anexos.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
    }
    files = MagicMock()
    files.getlist.return_value = []

    chamado_capturado = {}

    def _fake_add(dados):
        chamado_capturado.update(dados)
        ref = MagicMock()
        ref.id = "chamado_sem_arq"
        return (None, ref)

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo") as mock_salvar,
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-302"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch(
            "app.services.chamados_criacao_service.execute_with_retry",
            side_effect=lambda fn, dados, **kw: _fake_add(dados),
        ),
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor"},
            "motivo": "",
        }

        with app.app_context():
            chamado_id, numero, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante",
                area_solicitante="Manutencao",
            )

    assert erro is None
    mock_salvar.assert_not_called()
    assert chamado_capturado.get("anexo") is None
    assert chamado_capturado.get("anexos") == []
