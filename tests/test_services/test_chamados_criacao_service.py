"""Testes do serviço de criação de chamados (criar_chamado).

Fase 2 (Marco 7): a persistência do chamado roda contra Postgres real
(db_session) via Chamado.salvar() — substitui o antigo mock de
execute_with_retry/db.collection("chamados").add(). GrupoRL também já é
Postgres real (Marco 4): não mockamos GrupoRL.get_or_create nos testes que
usam rl_codigo, porque grupo_rl_id é FK real pra grupos_rl(id) — um id fake
violaria a constraint. Historico/notificações continuam mockados (ainda
Firestore / fora do escopo deste teste)."""

from unittest.mock import MagicMock, patch

import pytest

from app.models import Chamado
from app.services.chamados_criacao_service import criar_chamado

pytestmark = pytest.mark.usefixtures("db_session")


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
    """criar_chamado com form válido persiste no Postgres e retorna (id, numero, None, aviso)."""
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
        patch("app.services.chamados_criacao_service.Historico") as mock_hist,
        patch("app.services.chamados_criacao_service.threading.Thread") as mock_thread,
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor Teste"},
            "motivo": "",
        }
        with app.app_context():
            chamado_id, numero, erro, aviso = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante Teste",
                area_solicitante="Manutencao",
                solicitante_email="sol@test.com",
            )

    assert chamado_id is not None
    assert numero == "2026-099"
    assert erro is None
    assert Chamado.get_by_id(chamado_id) is not None
    mock_hist.return_value.save.assert_called_once()
    # O serviço dispara notificações em background; validamos que houve disparo.
    assert mock_thread.return_value.start.call_count >= 1


def test_criar_chamado_descricao_com_caractere_especial_nao_fica_escapada(app):
    """Regressão: bleach.clean() já retorna texto HTML-escapado ("->"" vira "-&gt;"") — sem
    desfazer esse escaping antes de salvar, o template (autoescape do Jinja) escapa de novo e
    o usuário vê "&gt;" literal na tela em vez de ">"."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Fluxo criar->editar->status corrigido.",
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
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-100"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor Teste"},
            "motivo": "",
        }
        with app.app_context():
            chamado_id, _numero, erro, _aviso = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante Teste",
                area_solicitante="Manutencao",
                solicitante_email="sol@test.com",
            )

    assert erro is None
    chamado = Chamado.get_by_id(chamado_id)
    assert chamado.descricao == "Fluxo criar->editar->status corrigido."


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
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
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
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor Teste"},
            "motivo": "",
        }

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
    assert chamado_id is not None
    assert numero == "2026-200"
    mock_hist.return_value.save.assert_called_once()
    mock_notif_setores.assert_called_once()
    kwargs = mock_notif_setores.call_args.kwargs
    assert kwargs["numero_chamado"] == "2026-200"
    assert kwargs["setores_novos"] == ["Engenharia", "Material"]
    # RL_codigo real gerou um GrupoRL real (Postgres), não mockado
    from app.models_grupo_rl import GrupoRL

    grupo = GrupoRL.get_by_rl_codigo("RL-001")
    assert grupo is not None
    assert Chamado.get_by_id(chamado_id).grupo_rl_id == grupo.id


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
    assert chamado_id is not None
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

        with app.app_context():
            criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol_meta",
                solicitante_nome="Solicitante Teste",
                area_solicitante="Manutencao",
                solicitante_email="sol@test.com",
            )

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
    anexos = Chamado.get_by_id(chamado_id).anexos
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
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor"},
            "motivo": "",
        }

        with app.app_context():
            chamado_id, _, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante",
            )

    assert erro is None
    anexos = Chamado.get_by_id(chamado_id).anexos
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
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor"},
            "motivo": "",
        }

        with app.app_context():
            chamado_id, _, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante",
            )

    assert erro is None
    anexos = Chamado.get_by_id(chamado_id).anexos
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
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor"},
            "motivo": "",
        }

        with app.app_context():
            chamado_id, _, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante",
            )

    assert erro is None
    anexos = Chamado.get_by_id(chamado_id).anexos
    assert f"onedrive:{link}" in anexos


# ── Testes anti-self-ticket ───────────────────────────────────────────────────


def test_criar_chamado_ignora_responsavel_form_igual_ao_solicitante(app):
    """
    Se responsavel_id_form == solicitante_id, o sistema deve ignorar a
    escolha manual e usar auto-atribuição — nunca deixar alguém ser
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

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-400"
        ),
        patch("app.services.chamados_criacao_service.Usuario.get_by_id", return_value=usuario_sup),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
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
    chamado = Chamado.get_by_id(chamado_id)
    # O responsável NÃO pode ser o próprio solicitante (self-assignment ignorado)
    assert chamado.responsavel_id != "sol1", (
        "Self-assignment não foi bloqueado: responsavel_id == solicitante_id"
    )
    assert chamado.responsavel_id == "sup_outro"


# ── Testes multi-anexo ────────────────────────────────────────────────────────


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

    with (
        patch(
            "app.services.chamados_criacao_service.salvar_anexo",
            side_effect=["caminho/a.pdf", "caminho/b.xlsx"],
        ) as mock_salvar,
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-300"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
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
    assert mock_salvar.call_count == 2
    chamado = Chamado.get_by_id(chamado_id)
    assert chamado.anexo == "caminho/a.pdf"
    assert chamado.anexos == ["caminho/a.pdf", "caminho/b.xlsx"]


def test_criar_chamado_falha_segundo_anexo_retorna_erro_sem_persistir(app):
    """Falha no 2º salvar_anexo → retorna erro; nada é persistido."""
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

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-500"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
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
    assert chamado_id is not None
    # Aviso deve conter "Awaiting manual assignment"
    assert aviso is not None
    assert "Awaiting manual assignment" in aviso
    # Responsável fallback = próprio solicitante
    assert Chamado.get_by_id(chamado_id).responsavel_id == "sol1"


def test_criar_chamado_falha_ao_salvar_retorna_mensagem_erro(app):
    """Quando Chamado.salvar() falha (retorna None), criar_chamado retorna (None, None, mensagem, None)."""
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
        patch("app.models.Chamado.salvar", return_value=None),
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

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo") as mock_salvar,
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-302"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
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
    chamado = Chamado.get_by_id(chamado_id)
    assert chamado.anexo is None
    assert chamado.anexos == []


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

    with patch(
        "app.services.chamados_criacao_service.Usuario.get_supervisores_por_area",
        return_value=[supervisor_mock],
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
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": False,
            "motivo": "Nenhum supervisor disponível",
        }

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
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
        app.app_context(),
    ):
        chamado_id, numero, erro, _ = criar_chamado(
            form=_form_base(responsavel_id="id_julia", responsavel_nome="Júlia"),
            files=_files_empty(),
            solicitante_id="sol1",
            solicitante_nome="Solicitante",
            area_solicitante="Manutencao",
        )

    assert erro is None
    assert chamado_id is not None


def test_criacao_falha_quando_responsavel_id_invalido_para_area(app):
    """responsavel_id fornecido mas não pertence aos supervisores da área → erro."""
    supervisor_valido = MagicMock()
    supervisor_valido.id = "id_julia"
    supervisor_valido.nome = "Júlia"
    supervisor_valido.perfil = "supervisor"

    with patch(
        "app.services.chamados_criacao_service.Usuario.get_supervisores_por_area",
        return_value=[supervisor_valido],
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
    """Criação com supervisor válido grava supervisor_ids_com_acesso no chamado."""
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
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-102"
        ),
        patch(
            "app.services.chamados_criacao_service.calcular_supervisor_ids_com_acesso",
            return_value=["id_julia"],
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
    assert "id_julia" in Chamado.get_by_id(chamado_id).supervisor_ids_com_acesso


# ---------------------------------------------------------------------------
# Compradores — setor de distribuição em grupo (sem dono único na criação)
# ---------------------------------------------------------------------------


def _tres_supervisores_compradores():
    supervisores = []
    for i, nome in enumerate(["Ana", "Bruno", "Carla"], start=1):
        sup = MagicMock()
        sup.id = f"id_compras_{i}"
        sup.nome = nome
        sup.perfil = "supervisor"
        supervisores.append(sup)
    return supervisores


def test_criacao_compras_nao_exige_responsavel_mesmo_com_supervisores(app):
    """Setor Compradores: form sem responsavel_id não falha mesmo com supervisores cadastrados."""
    from app.i18n import get_translation

    supervisores = _tres_supervisores_compradores()

    with (
        patch(
            "app.services.chamados_criacao_service.Usuario.get_supervisores_por_area",
            return_value=supervisores,
        ),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-200"
        ),
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado"),
        patch("app.services.chamados_criacao_service.criar_notificacao"),
        patch("app.services.chamados_criacao_service.enviar_webpush_usuario"),
        patch("app.services.chamados_criacao_service.threading.Thread", side_effect=_FakeThread),
        app.app_context(),
    ):
        chamado_id, numero, erro, aviso = criar_chamado(
            form=_form_base(responsavel_id="", tipo="Compradores"),
            files=_files_empty(),
            solicitante_id="sol1",
            solicitante_nome="Solicitante",
            area_solicitante="Compradores",
        )

    assert erro is None
    assert aviso is None
    assert chamado_id is not None
    chamado = Chamado.get_by_id(chamado_id)
    assert chamado.responsavel_id is None
    assert chamado.responsavel == get_translation("buyers_group_label", "en")


def test_criacao_compras_ignora_responsavel_id_enviado_no_form(app):
    """Setor Compradores: mesmo com responsavel_id no form, o chamado fica sem dono único."""
    supervisores = _tres_supervisores_compradores()

    with (
        patch(
            "app.services.chamados_criacao_service.Usuario.get_supervisores_por_area",
            return_value=supervisores,
        ),
        patch(
            "app.services.chamados_criacao_service.Usuario.get_by_id",
            return_value=supervisores[0],
        ),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-201"
        ),
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado"),
        patch("app.services.chamados_criacao_service.criar_notificacao"),
        patch("app.services.chamados_criacao_service.enviar_webpush_usuario"),
        patch("app.services.chamados_criacao_service.threading.Thread", side_effect=_FakeThread),
        app.app_context(),
    ):
        chamado_id, numero, erro, _ = criar_chamado(
            form=_form_base(
                responsavel_id="id_compradores_1", responsavel_nome="Ana", tipo="Compradores"
            ),
            files=_files_empty(),
            solicitante_id="sol1",
            solicitante_nome="Solicitante",
            area_solicitante="Compradores",
        )

    assert erro is None
    assert chamado_id is not None
    assert Chamado.get_by_id(chamado_id).responsavel_id is None


def test_criacao_compras_grava_supervisor_ids_com_acesso_para_todos(app):
    """Setor Compradores: supervisor_ids_com_acesso grava os 3 supervisores da área (fila sem owner)."""
    supervisores = _tres_supervisores_compradores()

    with (
        patch(
            "app.services.chamados_criacao_service.Usuario.get_supervisores_por_area",
            return_value=supervisores,
        ),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-202"
        ),
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado"),
        patch("app.services.chamados_criacao_service.criar_notificacao"),
        patch("app.services.chamados_criacao_service.enviar_webpush_usuario"),
        patch("app.services.chamados_criacao_service.threading.Thread", side_effect=_FakeThread),
        app.app_context(),
    ):
        chamado_id, numero, erro, _ = criar_chamado(
            form=_form_base(responsavel_id="", tipo="Compradores"),
            files=_files_empty(),
            solicitante_id="sol1",
            solicitante_nome="Solicitante",
            area_solicitante="Compradores",
        )

    assert erro is None
    ids_com_acesso = Chamado.get_by_id(chamado_id).supervisor_ids_com_acesso
    for sup in supervisores:
        assert sup.id in ids_com_acesso


def test_criacao_compras_notifica_todos_supervisores_da_area(app):
    """Setor Compradores: abertura notifica os 3 supervisores (email + in-app + web push), não só 1."""
    supervisores = _tres_supervisores_compradores()

    with (
        patch(
            "app.services.chamados_criacao_service.Usuario.get_supervisores_por_area",
            return_value=supervisores,
        ),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-203"
        ),
        patch("app.services.chamados_criacao_service.Historico"),
        patch(
            "app.services.chamados_criacao_service.notificar_aprovador_novo_chamado"
        ) as mock_email,
        patch("app.services.chamados_criacao_service.criar_notificacao") as mock_inapp,
        patch("app.services.chamados_criacao_service.enviar_webpush_usuario") as mock_webpush,
        patch("app.services.chamados_criacao_service.threading.Thread", side_effect=_FakeThread),
        app.app_context(),
    ):
        chamado_id, numero, erro, _ = criar_chamado(
            form=_form_base(responsavel_id="", tipo="Compradores"),
            files=_files_empty(),
            solicitante_id="sol1",
            solicitante_nome="Solicitante",
            area_solicitante="Compradores",
        )

    assert erro is None
    assert mock_email.call_count == 3
    ids_notificados_email = {
        call.kwargs["responsavel_usuario"].id for call in mock_email.call_args_list
    }
    assert ids_notificados_email == {sup.id for sup in supervisores}

    assert mock_inapp.call_count == 3
    ids_notificados_inapp = {call.kwargs["usuario_id"] for call in mock_inapp.call_args_list}
    assert ids_notificados_inapp == {sup.id for sup in supervisores}

    assert mock_webpush.call_count == 3
    ids_notificados_webpush = {call.args[0] for call in mock_webpush.call_args_list}
    assert ids_notificados_webpush == {sup.id for sup in supervisores}


# ── AOG — abertura já grava nível 4 e dispara broadcast pros 4 gestores ──────


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
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.Usuario.get_by_id", return_value=None),
        patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado"),
        patch(
            "app.services.chamados_criacao_service.notificar_abertura_aog_todos_gestores"
        ) as mock_notif_aog,
        patch("app.services.chamados_criacao_service.criar_notificacao"),
        patch("app.services.chamados_criacao_service.enviar_webpush_usuario"),
        patch("app.services.chamados_criacao_service.threading.Thread", side_effect=_FakeThread),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor Teste"},
            "motivo": "",
        }

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
    assert chamado_id is not None
    assert Chamado.get_by_id(chamado_id).escalacao_resposta_nivel == 4
    mock_notif_aog.assert_called_once()
    kwargs = mock_notif_aog.call_args.kwargs
    assert kwargs["chamado_id"] == chamado_id
    assert kwargs["chamado_data"]["numero_chamado"] == "2026-300"


def test_criar_chamado_aog_grava_rl_codigo_e_cria_grupo_rl(app):
    """AOG, assim como Projetos, grava rl_codigo no chamado e cria/reusa GrupoRL (Postgres real)."""
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
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.Usuario.get_by_id", return_value=None),
        patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado"),
        patch("app.services.chamados_criacao_service.notificar_abertura_aog_todos_gestores"),
        patch("app.services.chamados_criacao_service.criar_notificacao"),
        patch("app.services.chamados_criacao_service.enviar_webpush_usuario"),
        patch("app.services.chamados_criacao_service.threading.Thread", side_effect=_FakeThread),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor Teste"},
            "motivo": "",
        }

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
    assert chamado_id is not None
    from app.models_grupo_rl import GrupoRL

    grupo = GrupoRL.get_by_rl_codigo("AOG-777")
    assert grupo is not None

    chamado = Chamado.get_by_id(chamado_id)
    assert chamado.rl_codigo == "AOG-777"
    assert chamado.grupo_rl_id == grupo.id


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
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.Usuario.get_by_id", return_value=None),
        patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado"),
        patch(
            "app.services.chamados_criacao_service.notificar_abertura_aog_todos_gestores"
        ) as mock_notif_aog,
        patch("app.services.chamados_criacao_service.criar_notificacao"),
        patch("app.services.chamados_criacao_service.enviar_webpush_usuario"),
        patch("app.services.chamados_criacao_service.threading.Thread", side_effect=_FakeThread),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor Teste"},
            "motivo": "",
        }

        with app.app_context():
            chamado_id, _, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante Teste",
                area_solicitante="Manutencao",
                solicitante_email="sol@test.com",
            )

    assert Chamado.get_by_id(chamado_id).escalacao_resposta_nivel == 0
    mock_notif_aog.assert_not_called()


# ── Gate de cobertura: ramos ainda não exercitados ────────────────────────────


def test_criar_chamado_setores_adicionais_string_unica_sem_getlist(app):
    """form sem .getlist (dict simples) com setores_adicionais como string única
    (não-lista, truthy) vira lista de 1 item."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Descrição válida para teste de setor único.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
        "setores_adicionais": "Engenharia",
    }
    files = MagicMock()
    files.get.return_value = None
    files.getlist.return_value = []

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-400"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor"},
            "motivo": "",
        }

        with app.app_context():
            chamado_id, _, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante",
                area_solicitante="Manutencao",
            )

    assert erro is None
    assert Chamado.get_by_id(chamado_id).setores_adicionais == ["Engenharia"]


def test_criar_chamado_setores_adicionais_none_sem_getlist_fica_vazio(app):
    """form sem .getlist com setores_adicionais=None (não-lista, falsy) vira []."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Descrição válida sem setores adicionais.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
        "setores_adicionais": None,
    }
    files = MagicMock()
    files.get.return_value = None
    files.getlist.return_value = []

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-401"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor"},
            "motivo": "",
        }

        with app.app_context():
            chamado_id, _, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante",
                area_solicitante="Manutencao",
            )

    assert erro is None
    assert Chamado.get_by_id(chamado_id).setores_adicionais == []


def test_criar_chamado_anexo_sem_filename_e_ignorado(app):
    """Item de files.getlist("anexo") sem filename é pulado (continue), não chama salvar_anexo."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Chamado com um anexo vazio no meio da lista.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
    }
    arq_vazio = MagicMock()
    arq_vazio.filename = ""
    arq_valido = _arq_mock("valido.pdf")
    files = MagicMock()
    files.getlist.return_value = [arq_vazio, arq_valido]

    with (
        patch(
            "app.services.chamados_criacao_service.salvar_anexo",
            return_value="caminho/valido.pdf",
        ) as mock_salvar,
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-402"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor"},
            "motivo": "",
        }

        with app.app_context():
            chamado_id, _, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante",
                area_solicitante="Manutencao",
            )

    assert erro is None
    mock_salvar.assert_called_once_with(arq_valido)
    assert Chamado.get_by_id(chamado_id).anexos == ["caminho/valido.pdf"]


def test_criar_chamado_observadores_json_nao_lista_vira_lista_vazia(app):
    """observadores_json válido mas não é uma lista (ex.: objeto) → observadores_list = []."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Descrição válida com observadores_json malformado.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
        "observadores_json": '{"nao": "e uma lista"}',
    }
    files = MagicMock()
    files.get.return_value = None
    files.getlist.return_value = []

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-403"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor"},
            "motivo": "",
        }

        with app.app_context():
            chamado_id, _, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante",
                area_solicitante="Manutencao",
            )

    assert erro is None
    assert Chamado.get_by_id(chamado_id).observadores == []


def test_criar_chamado_observadores_invalidos_retorna_erro(app):
    """validar_observadores retornando erros bloqueia a criação (erros_obs[0])."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Descrição válida com observador inválido.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
        "observadores_json": '[{"usuario_id": "obs1", "nome": "Observador", "email": "o@b.com"}]',
    }
    files = MagicMock()
    files.get.return_value = None
    files.getlist.return_value = []

    with patch(
        "app.services.validators.validar_observadores",
        return_value=["Admin não pode ser observador"],
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
    assert erro == "Admin não pode ser observador"
    assert aviso is None


def test_criar_chamado_grupo_rl_falha_nao_impede_criacao(app):
    """GrupoRL.get_or_create lançando exceção é logado, mas o chamado é criado
    normalmente com grupo_rl_id=None."""
    form = {
        "categoria": "Projetos",
        "tipo": "Manutencao",
        "descricao": "Chamado com RL cujo grupo falha ao criar.",
        "rl_codigo": "RL-999",
        "impacto": "",
        "gate": "",
    }
    files = MagicMock()
    files.get.return_value = None
    files.getlist.return_value = []

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-404"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.Historico"),
        patch(
            "app.services.chamados_criacao_service.GrupoRL.get_or_create",
            side_effect=RuntimeError("banco indisponível"),
        ),
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
    assert chamado_id is not None
    assert Chamado.get_by_id(chamado_id).grupo_rl_id is None


def test_criar_chamado_aog_notificacao_falha_nao_impede_thread(app):
    """notificar_abertura_aog_todos_gestores lançando exceção é capturado e logado
    (warning) sem interromper o resto das notificações da thread."""
    form = {
        "categoria": "AOG",
        "tipo": "Manutencao",
        "descricao": "AOG cujo broadcast pros gestores falha.",
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
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-405"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.Usuario.get_by_id", return_value=None),
        patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado"),
        patch(
            "app.services.chamados_criacao_service.notificar_abertura_aog_todos_gestores",
            side_effect=RuntimeError("broadcast falhou"),
        ),
        patch("app.services.chamados_criacao_service.criar_notificacao"),
        patch("app.services.chamados_criacao_service.enviar_webpush_usuario"),
        patch("app.services.chamados_criacao_service.threading.Thread", side_effect=_FakeThread),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor Teste"},
            "motivo": "",
        }

        with app.app_context():
            chamado_id, _, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante Teste",
                area_solicitante="Manutencao",
                solicitante_email="sol@test.com",
            )

    assert erro is None
    assert chamado_id is not None


def test_criar_chamado_notificacao_inapp_falha_nao_impede_thread(app):
    """criar_notificacao lançando exceção dentro da thread de notificação é
    capturado e logado (debug), não propaga pro caller."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Chamado cuja notificação in-app falha.",
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
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-406"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.Historico"),
        patch(
            "app.services.chamados_criacao_service.Usuario.get_by_id",
            return_value=responsavel_usuario,
        ),
        patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado"),
        patch(
            "app.services.chamados_criacao_service.criar_notificacao",
            side_effect=RuntimeError("notificação in-app indisponível"),
        ),
        patch("app.services.chamados_criacao_service.enviar_webpush_usuario") as mock_webpush,
        patch("app.services.chamados_criacao_service.threading.Thread", side_effect=_FakeThread),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup_falha", "nome": "Supervisor Falha"},
            "motivo": "",
        }

        with app.app_context():
            chamado_id, _, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante Teste",
                area_solicitante="Manutencao",
                solicitante_email="sol@test.com",
            )

    assert erro is None
    assert chamado_id is not None
    # criar_notificacao lançou antes do webpush (mesmo bloco try) — webpush não é chamado
    mock_webpush.assert_not_called()


def test_criar_chamado_erro_generico_na_thread_notificacao_e_logado(app):
    """Exceção fora dos try/except internos (ex.: executar_com_retry) é capturada
    pelo except externo da thread de notificação, sem propagar pro caller."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Chamado cuja thread de notificação quebra de forma genérica.",
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
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-407"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.Usuario.get_by_id", return_value=None),
        patch(
            "app.services.chamados_criacao_service.executar_com_retry",
            side_effect=RuntimeError("falha genérica na thread"),
        ),
        patch("app.services.chamados_criacao_service.threading.Thread", side_effect=_FakeThread),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor Teste"},
            "motivo": "",
        }

        with app.app_context():
            chamado_id, _, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante Teste",
                area_solicitante="Manutencao",
                solicitante_email="sol@test.com",
            )

    # criar_chamado já retornou (id salvo) antes da thread rodar — erro da thread
    # fica só logado, não afeta o retorno da função.
    assert erro is None
    assert chamado_id is not None


def test_criar_chamado_observadores_dispara_e_falha_notificacao_e_logado(app):
    """observadores_list não-vazio dispara _notificar_observadores_inclusao numa
    thread própria; notificar_observadores_criacao lançando é capturado (warning)."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Chamado com observador cuja notificação falha.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
        "observadores_json": '[{"usuario_id": "obs1", "nome": "Observador Um", "email": "o1@b.com"}]',
    }
    files = MagicMock()
    files.get.return_value = None
    files.getlist.return_value = []

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-408"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.Usuario.get_by_id", return_value=None),
        patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado"),
        patch(
            "app.services.chamado_notificacao_service.notificar_observadores_criacao",
            side_effect=RuntimeError("falha ao notificar observador"),
        ),
        patch("app.services.chamados_criacao_service.threading.Thread", side_effect=_FakeThread),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor Teste"},
            "motivo": "",
        }

        with app.app_context():
            chamado_id, _, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante Teste",
                area_solicitante="Manutencao",
                solicitante_email="sol@test.com",
            )

    assert erro is None
    assert chamado_id is not None
    assert Chamado.get_by_id(chamado_id).observadores == [
        {"usuario_id": "obs1", "nome": "Observador Um", "email": "o1@b.com"}
    ]


def test_criar_chamado_observadores_json_malformado_ignora_e_segue(app):
    """observadores_json com JSON sintaticamente inválido é ignorado (não quebra a criação)."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Descrição válida com JSON quebrado nos observadores.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
        "observadores_json": "{isso nao e json valido",
    }
    files = MagicMock()
    files.get.return_value = None
    files.getlist.return_value = []

    with (
        patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None),
        patch(
            "app.services.chamados_criacao_service.gerar_numero_chamado", return_value="2026-409"
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
        patch("app.services.chamados_criacao_service.Historico"),
        patch("app.services.chamados_criacao_service.threading.Thread"),
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor"},
            "motivo": "",
        }

        with app.app_context():
            chamado_id, _, erro, _ = criar_chamado(
                form=form,
                files=files,
                solicitante_id="sol1",
                solicitante_nome="Solicitante",
                area_solicitante="Manutencao",
            )

    assert erro is None
    assert Chamado.get_by_id(chamado_id).observadores == []


def test_criar_chamado_excecao_inesperada_ao_persistir_retorna_erro_generico(app):
    """Exceção não prevista dentro do bloco de persistência (ex.: Chamado.salvar()
    lançando em vez de retornar None) é capturada pelo except externo."""
    form = {
        "categoria": "Manutencao",
        "tipo": "Manutencao",
        "descricao": "Descrição válida cuja persistência quebra de forma inesperada.",
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
            "app.services.chamados_criacao_service.gerar_numero_chamado",
            side_effect=RuntimeError("falha inesperada ao gerar número"),
        ),
        patch("app.services.chamados_criacao_service.atribuidor") as mock_atr,
    ):
        mock_atr.atribuir.return_value = {
            "sucesso": True,
            "supervisor": {"id": "sup1", "nome": "Supervisor"},
            "motivo": "",
        }

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
