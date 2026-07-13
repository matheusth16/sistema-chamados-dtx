"""Testes do serviço de criação de chamados (criar_chamado)."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.chamados_criacao_service import criar_chamado


@pytest.fixture(autouse=True)
def _patch_get_supervisores_default():
    """Retorna lista vazia — simula área sem supervisores cadastrados.

    Testes que precisam de supervisores sobrepõem este patch com seu próprio
    `patch(..., return_value=[supervisor_mock])` dentro do corpo do teste.
    """
    with patch(
        "app.models_usuario.Usuario.get_supervisores_por_area",
        return_value=[],
    ):
        yield


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
        patch("app.services.chamados_criacao_service.criar_notificacao"),
        patch("app.services.chamados_criacao_service.enviar_webpush_usuario"),
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
        patch("app.services.chamados_criacao_service.Usuario.get_by_id", return_value=MagicMock()),
        patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado"),
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


# ── links externos OneDrive/SharePoint ────────────────────────────────────────


class _FormComLinks(dict):
    """Form dict que simula request.form com getlist para links_externos e setores."""

    def __init__(self, base, links_externos=None, setores_adicionais=None):
        super().__init__(base)
        self._links = links_externos or []
        self._setores = setores_adicionais or []

    def getlist(self, key):
        if key == "links_externos":
            return self._links
        if key == "setores_adicionais":
            return self._setores
        return []


def _chamado_dict_capturado(mock_retry):
    """Extrai o dict do chamado passado para execute_with_retry."""
    return mock_retry.call_args[0][1]


def test_criar_chamado_com_link_externo_salva_onedrive_prefix(app):
    """Links externos válidos são adicionados aos anexos com prefixo 'onedrive:'."""
    link = "https://empresa.sharepoint.com/sites/chamados/documento.xlsx"
    form = _FormComLinks(
        {
            "categoria": "Manutencao",
            "tipo": "Manutencao",
            "descricao": "Problema com arquivo grande no SharePoint.",
            "rl_codigo": "",
            "impacto": "",
            "gate": "",
        },
        links_externos=[link],
    )
    files = MagicMock()
    files.getlist.return_value = []

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-300"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.execute_with_retry") as mock_retry,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor"},
            "motivo": "",
        }
        mock_ref = MagicMock()
        mock_ref.id = "chamado_300"
        mock_retry.return_value = (None, mock_ref)

        with app.app_context():
            chamado_id, numero, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante",
                area_solicitante="Manutencao",
            )

    assert erro is None
    chamado_dict = _chamado_dict_capturado(mock_retry)
    anexos = chamado_dict.get("anexos", [])
    assert f"onedrive:{link}" in anexos


def test_criar_chamado_com_multiplos_links_externos(app):
    """Múltiplos links externos são todos salvos com prefixo 'onedrive:'."""
    links = [
        "https://empresa.sharepoint.com/doc1.pdf",
        "https://1drv.ms/b/s!AkXY",
    ]
    form = _FormComLinks(
        {
            "categoria": "Manutencao",
            "tipo": "Manutencao",
            "descricao": "Dois documentos no SharePoint.",
            "rl_codigo": "",
            "impacto": "",
            "gate": "",
        },
        links_externos=links,
    )
    files = MagicMock()
    files.getlist.return_value = []

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-301"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.execute_with_retry") as mock_retry,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor"},
            "motivo": "",
        }
        mock_ref = MagicMock()
        mock_ref.id = "chamado_301"
        mock_retry.return_value = (None, mock_ref)

        with app.app_context():
            _, _, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante",
            )

    assert erro is None
    anexos = _chamado_dict_capturado(mock_retry).get("anexos", [])
    assert "onedrive:https://empresa.sharepoint.com/doc1.pdf" in anexos
    assert "onedrive:https://1drv.ms/b/s!AkXY" in anexos


def test_criar_chamado_sem_links_externos_nao_adiciona_onedrive(app):
    """Sem links_externos no form, nenhum 'onedrive:' é adicionado aos anexos."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Chamado sem links externos.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
    }
    files = MagicMock()
    files.getlist.return_value = []

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-302"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.execute_with_retry") as mock_retry,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor"},
            "motivo": "",
        }
        mock_ref = MagicMock()
        mock_ref.id = "chamado_302"
        mock_retry.return_value = (None, mock_ref)

        with app.app_context():
            _, _, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante",
            )

    assert erro is None
    anexos = _chamado_dict_capturado(mock_retry).get("anexos", [])
    assert not any(a.startswith("onedrive:") for a in anexos)


def test_criar_chamado_link_externo_via_dict_simples(app):
    """form como dict simples (sem getlist) ainda processa links_externos."""
    link = "https://empresa.sharepoint.com/doc.pdf"
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Form simples com link externo.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
        "links_externos": link,
    }
    files = MagicMock()
    files.getlist.return_value = []

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-303"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.execute_with_retry") as mock_retry,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor"},
            "motivo": "",
        }
        mock_ref = MagicMock()
        mock_ref.id = "chamado_303"
        mock_retry.return_value = (None, mock_ref)

        with app.app_context():
            _, _, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante",
            )

    assert erro is None
    anexos = _chamado_dict_capturado(mock_retry).get("anexos", [])
    assert f"onedrive:{link}" in anexos


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


# ── Fallback atribuição manual ────────────────────────────────────────────────


def test_criar_chamado_atribuicao_manual_retorna_aviso_e_responsavel_fallback(app):
    """Quando atribuidor não encontra supervisor, chamado é criado com aviso e responsável = solicitante."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Chamado sem supervisor disponível.",
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
        ref.id = "chamado_manual_001"
        return (None, ref)

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-500"
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
            "sucesso": False,
            "motivo": "Sem supervisores disponíveis",
        }

        with app.app_context():
            chamado_id, numero, erro, aviso = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante Teste",
                area_solicitante="Manutencao",
            )

    assert erro is None
    assert chamado_id == "chamado_manual_001"
    # Aviso deve conter "Awaiting manual assignment"
    assert aviso is not None
    assert "Awaiting manual assignment" in aviso
    # Responsável fallback = próprio solicitante
    assert chamado_capturado.get("responsavel_id") == "sol1"


def test_criar_chamado_excecao_persistencia_retorna_mensagem_erro(app):
    """Quando execute_with_retry levanta exceção, retorna (None, None, mensagem, None)."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Chamado que vai falhar na persistência.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
    }
    files = MagicMock()
    files.getlist.return_value = []

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-999"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch(
            "app.services.chamados_criacao_service.execute_with_retry",
            side_effect=Exception("Firestore unavailable"),
        ),
        patch("app.services.chamados_criacao_service.Historico"),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor"},
            "motivo": "",
        }

        with app.app_context():
            chamado_id, numero, erro, aviso = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante",
                area_solicitante="Manutencao",
            )

    assert chamado_id is None
    assert numero is None
    assert erro is not None
    assert aviso is None


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


# ---------------------------------------------------------------------------
# Fase 2 — Supervisor obrigatório na criação
# ---------------------------------------------------------------------------


def _form_base(responsavel_id="", responsavel_nome="", tipo="Manutencao"):
    return {
        "categoria": "Manutencao",
        "tipo": tipo,
        "descricao": "Descrição válida para teste de supervisor obrigatório.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
        "responsavel_id": responsavel_id,
        "responsavel_nome": responsavel_nome,
    }


def _files_empty():
    f = MagicMock()
    f.getlist.return_value = []
    return f


def test_criacao_falha_sem_supervisor_quando_area_tem_supervisores(app):
    """Área com supervisor cadastrado e form sem responsavel_id → erro."""
    supervisor_mock = MagicMock()
    supervisor_mock.id = "id_julia"
    supervisor_mock.nome = "Júlia"
    supervisor_mock.perfil = "supervisor"

    with (
        patch(
            "app.services.chamados_criacao_service.Usuario.get_supervisores_por_area",
            return_value=[supervisor_mock],
        ),
    ):
        chamado_id, numero, erro, _ = criar_chamado(
            form=_form_base(responsavel_id=""),
            files=_files_empty(),
            solicitante_id="sol1",
            solicitante_nome="Solicitante",
            area_solicitante="Manutencao",
        )

    assert chamado_id is None
    assert numero is None
    assert erro is not None
    assert "supervisor" in erro.lower()


def test_criacao_ok_sem_supervisores_na_area(app):
    """Área sem supervisores → criação permitida sem responsavel_id."""
    with (
        patch(
            "app.services.chamados_criacao_service.Usuario.get_supervisores_por_area",
            return_value=[],
        ),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-100"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.execute_with_retry") as mock_retry,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": False,
            "motivo": "Nenhum supervisor disponível",
        }
        mock_ref = MagicMock()
        mock_ref.id = "chamado_novo_id"
        mock_retry.return_value = (None, mock_ref)

        with app.app_context():
            chamado_id, numero, erro, _ = criar_chamado(
                form=_form_base(responsavel_id=""),
                files=_files_empty(),
                solicitante_id="sol1",
                solicitante_nome="Solicitante",
                area_solicitante="Manutencao",
            )

    assert erro is None
    assert chamado_id is not None


def test_criacao_ok_com_supervisor_valido_escolhido(app):
    """Área com supervisores e responsavel_id válido → criação bem-sucedida."""
    supervisor_mock = MagicMock()
    supervisor_mock.id = "id_julia"
    supervisor_mock.nome = "Júlia"
    supervisor_mock.perfil = "supervisor"

    with (
        patch(
            "app.services.chamados_criacao_service.Usuario.get_supervisores_por_area",
            return_value=[supervisor_mock],
        ),
        patch(
            "app.services.chamados_criacao_service.Usuario.get_by_id",
            return_value=supervisor_mock,
        ),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-101"
        ),
        patch(
            "app.services.chamados_criacao_service.calcular_supervisor_ids_com_acesso",
            return_value=["id_julia"],
        ),
        patch("app.services.chamados_criacao_service.execute_with_retry") as mock_retry,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
    ):
        mock_ref = MagicMock()
        mock_ref.id = "chamado_com_sup_id"
        mock_retry.return_value = (None, mock_ref)

        with app.app_context():
            chamado_id, numero, erro, _ = criar_chamado(
                form=_form_base(responsavel_id="id_julia", responsavel_nome="Júlia"),
                files=_files_empty(),
                solicitante_id="sol1",
                solicitante_nome="Solicitante",
                area_solicitante="Manutencao",
            )

    assert erro is None
    assert chamado_id == "chamado_com_sup_id"


def test_criacao_falha_quando_responsavel_id_invalido_para_area(app):
    """Lacuna 3: responsavel_id fornecido mas não pertence aos supervisores da área → erro."""
    supervisor_valido = MagicMock()
    supervisor_valido.id = "id_julia"
    supervisor_valido.nome = "Júlia"
    supervisor_valido.perfil = "supervisor"

    with (
        patch(
            "app.services.chamados_criacao_service.Usuario.get_supervisores_por_area",
            return_value=[supervisor_valido],
        ),
    ):
        chamado_id, numero, erro, _ = criar_chamado(
            form=_form_base(responsavel_id="id_outra_area", responsavel_nome="Outro"),
            files=_files_empty(),
            solicitante_id="sol1",
            solicitante_nome="Solicitante",
            area_solicitante="Manutencao",
        )

    assert chamado_id is None
    assert numero is None
    assert erro is not None
    assert "invalid" in erro.lower() or "supervisor" in erro.lower()


def test_criacao_grava_supervisor_ids_com_acesso(app):
    """Criação com supervisor válido grava supervisor_ids_com_acesso no documento."""
    supervisor_mock = MagicMock()
    supervisor_mock.id = "id_julia"
    supervisor_mock.nome = "Júlia"
    supervisor_mock.perfil = "supervisor"

    chamado_capturado = {}

    def _capture_add(fn, data, **_kw):
        # execute_with_retry(collection.add, to_dict_result, max_retries=N)
        chamado_capturado.update(data)
        ref = MagicMock()
        ref.id = "chamado_ids_id"
        return (None, ref)

    with (
        patch(
            "app.services.chamados_criacao_service.Usuario.get_supervisores_por_area",
            return_value=[supervisor_mock],
        ),
        patch(
            "app.services.chamados_criacao_service.Usuario.get_by_id",
            return_value=supervisor_mock,
        ),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-102"
        ),
        patch(
            "app.services.chamados_criacao_service.calcular_supervisor_ids_com_acesso",
            return_value=["id_julia"],
        ),
        patch(
            "app.services.chamados_criacao_service.execute_with_retry",
            side_effect=_capture_add,
        ),
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
        app.app_context(),
    ):
        chamado_id, _, erro, _ = criar_chamado(
            form=_form_base(responsavel_id="id_julia", responsavel_nome="Júlia"),
            files=_files_empty(),
            solicitante_id="sol1",
            solicitante_nome="Solicitante",
            area_solicitante="Manutencao",
        )

    assert erro is None
    assert "id_julia" in chamado_capturado.get("supervisor_ids_com_acesso", [])


# ── AOG — abertura já grava nível 4 e dispara broadcast pros 4 gestores ────────────────────────


def test_criar_chamado_aog_grava_nivel_4_e_notifica_todos_gestores(app):
    """categoria='AOG': escalacao_resposta_nivel=4 direto (Escada A já esgotada) e
    dispara notificar_abertura_aog_todos_gestores pros 4 níveis, síncrono na criação."""
    form = {
        "categoria": "AOG",
        "tipo": "Manutencao",
        "descricao": "Aeronave PR-XYZ em solo, hidráulica falhou.",
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
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-300"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.execute_with_retry") as mock_retry,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.Usuario.get_by_id", return_value=None),
        patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado"),
        patch(
            "app.services.chamados_criacao_service.notificar_abertura_aog_todos_gestores"
        ) as mock_notif_aog,
        patch("app.services.chamados_criacao_service.threading.Thread", side_effect=_FakeThread),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor Teste"},
            "motivo": "",
        }
        mock_ref = MagicMock()
        mock_ref.id = "chamado_id_300"
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
    assert chamado_id == "chamado_id_300"
    chamado_dict_salvo = mock_retry.call_args[0][1]
    assert chamado_dict_salvo["escalacao_resposta_nivel"] == 4
    mock_notif_aog.assert_called_once()
    kwargs = mock_notif_aog.call_args.kwargs
    assert kwargs["chamado_id"] == "chamado_id_300"
    assert kwargs["chamado_data"]["numero_chamado"] == "2026-300"


def test_criar_chamado_aog_grava_rl_codigo_e_cria_grupo_rl(app):
    """AOG, assim como Projetos, grava rl_codigo no chamado e cria/reusa GrupoRL."""
    form = {
        "categoria": "AOG",
        "tipo": "Manutencao",
        "descricao": "Aeronave PR-ABC em solo, trem de pouso travado.",
        "rl_codigo": "AOG-777",
        "impacto": "",
        "gate": "",
    }
    files = MagicMock()
    files.get.return_value = None
    files.getlist.return_value = []

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-302"
        ),
        patch("app.services.chamados_criacao_service.GrupoRL.get_or_create") as mock_grupo,
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.execute_with_retry") as mock_retry,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.Usuario.get_by_id", return_value=None),
        patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado"),
        patch("app.services.chamados_criacao_service.notificar_abertura_aog_todos_gestores"),
        patch("app.services.chamados_criacao_service.threading.Thread", side_effect=_FakeThread),
    ):
        mock_grupo.return_value = MagicMock(id="grupo_aog_1")
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor Teste"},
            "motivo": "",
        }
        mock_ref = MagicMock()
        mock_ref.id = "chamado_id_302"
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
    assert chamado_id == "chamado_id_302"
    mock_grupo.assert_called_once()
    chamado_dict_salvo = mock_retry.call_args[0][1]
    assert chamado_dict_salvo["rl_codigo"] == "AOG-777"
    assert chamado_dict_salvo["grupo_rl_id"] == "grupo_aog_1"


def test_criar_chamado_normal_nao_grava_nivel_4_nem_notifica_aog(app):
    """categoria normal (não-AOG) mantém escalacao_resposta_nivel=0 e não dispara broadcast AOG."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Descrição normal, não é AOG.",
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
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-301"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.execute_with_retry") as mock_retry,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.Usuario.get_by_id", return_value=None),
        patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado"),
        patch(
            "app.services.chamados_criacao_service.notificar_abertura_aog_todos_gestores"
        ) as mock_notif_aog,
        patch("app.services.chamados_criacao_service.threading.Thread", side_effect=_FakeThread),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor Teste"},
            "motivo": "",
        }
        mock_ref = MagicMock()
        mock_ref.id = "chamado_id_301"
        mock_retry.return_value = (None, mock_ref)

        with app.app_context():
            criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante Teste",
                area_solicitante="Manutencao",
                solicitante_email="sol@test.com",
            )

    chamado_dict_salvo = mock_retry.call_args[0][1]
    assert chamado_dict_salvo["escalacao_resposta_nivel"] == 0
    mock_notif_aog.assert_not_called()
