"""
Fase 3 — TDD: solicitante_edicao_service (edição texto + anexo tardio).

Testes escritos ANTES da implementação (Red → Green → Refactor).
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytz

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BRASILIA = pytz.timezone("America/Sao_Paulo")
JANELA_MIN = 30  # constante do service


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

    Fora do request context original (ex.: dentro da thread de notificação em
    background, que só empurra app_context) o proxy real deixa de resolver e
    vira None — acessar .nome nesse momento explode com AttributeError. Este
    fake reproduz esse comportamento via a flag `contexto_ativo`.
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


def _data_chamado(
    solicitante_id="sol_1",
    status="Aberto",
    descricao="Desc original",
    minutos_atras=10,
    observadores=None,
    responsavel_id="sup_1",
    numero_chamado="CH-001",
    categoria="TI",
):
    """Retorna dict simulando dados do Firestore."""
    agora = datetime.now(_BRASILIA)
    abertura = agora - timedelta(minutes=minutos_atras)
    return {
        "solicitante_id": solicitante_id,
        "status": status,
        "descricao": descricao,
        "data_abertura": abertura,
        "observadores": observadores or [],
        "responsavel_id": responsavel_id,
        "numero_chamado": numero_chamado,
        "categoria": categoria,
    }


# ---------------------------------------------------------------------------
# editar_descricao_solicitante
# ---------------------------------------------------------------------------


class TestEditarDescricaoSolicitante:
    def test_edicao_dentro_de_30_min_sucede(self):
        """Dentro da janela e status Aberto → sucesso + histórico."""
        from app.services.solicitante_edicao_service import editar_descricao_solicitante

        user = _usuario_mock()
        chamado_data = _data_chamado(minutos_atras=5)

        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = chamado_data

        with (
            patch("app.services.solicitante_edicao_service.db") as mock_db,
            patch("app.services.solicitante_edicao_service.Historico") as mock_hist,
            patch("app.services.solicitante_edicao_service._notificar_edicao_descricao"),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            mock_db.collection.return_value.document.return_value.update.return_value = None
            mock_hist.return_value.save.return_value = True

            resultado = editar_descricao_solicitante(
                chamado_id="ch_1",
                novo_texto="Nova descrição editada pelo solicitante",
                usuario=user,
            )

        assert resultado["sucesso"] is True
        # Histórico deve ter sido salvo
        mock_hist.return_value.save.assert_called_once()

    def test_edicao_apos_30_min_bloqueada(self):
        """Após 30 min → erro 403 (janela expirada)."""
        from app.services.solicitante_edicao_service import editar_descricao_solicitante

        user = _usuario_mock()
        chamado_data = _data_chamado(minutos_atras=35)

        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = chamado_data

        with patch("app.services.solicitante_edicao_service.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            resultado = editar_descricao_solicitante(
                chamado_id="ch_1",
                novo_texto="Texto novo",
                usuario=user,
            )

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 403

    def test_edicao_status_em_atendimento_bloqueada(self):
        """Status Em Atendimento → não pode editar texto."""
        from app.services.solicitante_edicao_service import editar_descricao_solicitante

        user = _usuario_mock()
        chamado_data = _data_chamado(status="Em Atendimento", minutos_atras=5)

        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = chamado_data

        with patch("app.services.solicitante_edicao_service.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            resultado = editar_descricao_solicitante(
                chamado_id="ch_1",
                novo_texto="Texto novo",
                usuario=user,
            )

        assert resultado["sucesso"] is False

    def test_observador_nao_pode_editar_descricao(self):
        """Usuário que é só observador não pode editar — solicitante_id diferente."""
        from app.services.solicitante_edicao_service import editar_descricao_solicitante

        user = _usuario_mock(uid="outro_usuario")
        chamado_data = _data_chamado(solicitante_id="dono_real", minutos_atras=5)

        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = chamado_data

        with patch("app.services.solicitante_edicao_service.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            resultado = editar_descricao_solicitante(
                chamado_id="ch_1",
                novo_texto="Texto novo",
                usuario=user,
            )

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 403

    def test_historico_tem_valor_anterior_e_novo(self):
        """Histórico da edição deve registrar valor_anterior e valor_novo."""
        from app.services.solicitante_edicao_service import editar_descricao_solicitante

        user = _usuario_mock()
        chamado_data = _data_chamado(descricao="Texto original", minutos_atras=5)

        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = chamado_data

        historicos_criados = []

        def capturar_historico(*args, **kwargs):
            historicos_criados.append(kwargs)
            h = MagicMock()
            h.save.return_value = True
            return h

        with (
            patch("app.services.solicitante_edicao_service.db") as mock_db,
            patch(
                "app.services.solicitante_edicao_service.Historico",
                side_effect=capturar_historico,
            ),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            mock_db.collection.return_value.document.return_value.update.return_value = None
            editar_descricao_solicitante(
                chamado_id="ch_1",
                novo_texto="Texto editado",
                usuario=user,
            )

        assert len(historicos_criados) >= 1
        hist = historicos_criados[0]
        assert hist.get("valor_anterior") == "Texto original"
        assert hist.get("valor_novo") == "Texto editado"


# ---------------------------------------------------------------------------
# adicionar_anexo_tardio
# ---------------------------------------------------------------------------


class TestAdicionarAnexoTardio:
    def test_anexo_sem_motivo_bloqueado(self):
        """Motivo obrigatório mínimo 10 chars."""
        from app.services.solicitante_edicao_service import adicionar_anexo_tardio

        user = _usuario_mock()
        chamado_data = _data_chamado(status="Aberto", minutos_atras=5)

        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = chamado_data

        with patch("app.services.solicitante_edicao_service.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            resultado = adicionar_anexo_tardio(
                chamado_id="ch_1",
                caminho_anexo="path/arquivo.pdf",
                motivo="",
                usuario=user,
            )

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 400

    def test_anexo_em_concluido_bloqueado(self):
        """Status Concluído → não pode adicionar anexo tardio."""
        from app.services.solicitante_edicao_service import adicionar_anexo_tardio

        user = _usuario_mock()
        chamado_data = _data_chamado(status="Concluído", minutos_atras=5)

        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = chamado_data

        with patch("app.services.solicitante_edicao_service.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            resultado = adicionar_anexo_tardio(
                chamado_id="ch_1",
                caminho_anexo="path/arquivo.pdf",
                motivo="Motivo suficientemente longo",
                usuario=user,
            )

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 403

    def test_anexo_em_aberto_com_motivo_sucede(self):
        """Status Aberto + motivo válido → sucesso."""
        from app.services.solicitante_edicao_service import adicionar_anexo_tardio

        user = _usuario_mock()
        chamado_data = _data_chamado(status="Aberto", minutos_atras=5)
        chamado_data["anexos"] = []

        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = chamado_data

        with (
            patch("app.services.solicitante_edicao_service.db") as mock_db,
            patch("app.services.solicitante_edicao_service.Historico") as mock_hist,
            patch("app.services.solicitante_edicao_service._notificar_anexo_tardio"),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            mock_db.collection.return_value.document.return_value.update.return_value = None
            mock_hist.return_value.save.return_value = True

            resultado = adicionar_anexo_tardio(
                chamado_id="ch_1",
                caminho_anexo="path/arquivo.pdf",
                motivo="Documento esquecido no primeiro envio",
                usuario=user,
            )

        assert resultado["sucesso"] is True

    def test_anexo_em_em_atendimento_com_motivo_sucede(self):
        """Status Em Atendimento + motivo → também permitido."""
        from app.services.solicitante_edicao_service import adicionar_anexo_tardio

        user = _usuario_mock()
        chamado_data = _data_chamado(status="Em Atendimento", minutos_atras=120)
        chamado_data["anexos"] = []

        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = chamado_data

        with (
            patch("app.services.solicitante_edicao_service.db") as mock_db,
            patch("app.services.solicitante_edicao_service.Historico") as mock_hist,
            patch("app.services.solicitante_edicao_service._notificar_anexo_tardio"),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            mock_db.collection.return_value.document.return_value.update.return_value = None
            mock_hist.return_value.save.return_value = True

            resultado = adicionar_anexo_tardio(
                chamado_id="ch_1",
                caminho_anexo="path/arquivo.pdf",
                motivo="Documento requisitado pelo responsável",
                usuario=user,
            )

        assert resultado["sucesso"] is True

    def test_nao_owner_bloqueado(self):
        """Só o owner (solicitante_id) pode adicionar anexo tardio."""
        from app.services.solicitante_edicao_service import adicionar_anexo_tardio

        user = _usuario_mock(uid="nao_owner")
        chamado_data = _data_chamado(solicitante_id="dono_real", status="Aberto")

        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = chamado_data

        with patch("app.services.solicitante_edicao_service.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            resultado = adicionar_anexo_tardio(
                chamado_id="ch_1",
                caminho_anexo="path/arquivo.pdf",
                motivo="Motivo suficientemente longo",
                usuario=user,
            )

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 403


# ---------------------------------------------------------------------------
# segundos_restantes_janela_edicao
# ---------------------------------------------------------------------------


class TestSegundosRestantesJanelaEdicao:
    def test_retorna_positivo_dentro_da_janela(self):
        """Datetime há 5 min → retorna ~1500 segundos."""
        from app.services.solicitante_edicao_service import segundos_restantes_janela_edicao

        agora = datetime.now(_BRASILIA)
        abertura = agora - timedelta(minutes=5)
        resultado = segundos_restantes_janela_edicao(abertura)

        assert resultado > 0
        assert resultado <= 25 * 60

    def test_retorna_zero_apos_janela_expirar(self):
        """Datetime há 35 min → janela encerrada, retorna 0."""
        from app.services.solicitante_edicao_service import segundos_restantes_janela_edicao

        agora = datetime.now(_BRASILIA)
        abertura = agora - timedelta(minutes=35)
        resultado = segundos_restantes_janela_edicao(abertura)

        assert resultado == 0

    def test_retorna_zero_para_nao_datetime(self):
        """Entrada inválida → retorna 0 sem exceção."""
        from app.services.solicitante_edicao_service import segundos_restantes_janela_edicao

        assert segundos_restantes_janela_edicao("nao_eh_datetime") == 0
        assert segundos_restantes_janela_edicao(None) == 0

    def test_aceita_datetime_sem_timezone(self):
        """Datetime timezone-naive há 5 min → retorna segundos positivos."""
        from app.services.solicitante_edicao_service import segundos_restantes_janela_edicao

        abertura_naive = datetime.now() - timedelta(minutes=5)
        resultado = segundos_restantes_janela_edicao(abertura_naive)

        assert resultado > 0


# ---------------------------------------------------------------------------
# Gaps de cobertura — chamado não encontrado e exceções
# ---------------------------------------------------------------------------


class TestCoberturaGaps:
    def _mock_doc_nao_encontrado(self):
        m = MagicMock()
        m.exists = False
        return m

    def test_editar_chamado_nao_encontrado_retorna_404(self):
        from app.services.solicitante_edicao_service import editar_descricao_solicitante

        user = _usuario_mock()
        with patch("app.services.solicitante_edicao_service.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = (
                self._mock_doc_nao_encontrado()
            )
            resultado = editar_descricao_solicitante("ch_x", "texto novo válido", user)

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 404

    def test_editar_excecao_retorna_500(self):
        from app.services.solicitante_edicao_service import editar_descricao_solicitante

        user = _usuario_mock()
        chamado_data = _data_chamado(minutos_atras=5)
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = chamado_data

        with (
            patch("app.services.solicitante_edicao_service.db") as mock_db,
            patch(
                "app.services.solicitante_edicao_service.Historico",
                side_effect=RuntimeError("boom"),
            ),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            mock_db.collection.return_value.document.return_value.update.return_value = None
            resultado = editar_descricao_solicitante("ch_1", "texto válido aqui", user)

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 500

    def test_adicionar_anexo_chamado_nao_encontrado_retorna_404(self):
        from app.services.solicitante_edicao_service import adicionar_anexo_tardio

        user = _usuario_mock()
        with patch("app.services.solicitante_edicao_service.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = (
                self._mock_doc_nao_encontrado()
            )
            resultado = adicionar_anexo_tardio("ch_x", "arquivo.pdf", "motivo suficiente", user)

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 404

    def test_adicionar_anexo_excecao_retorna_500(self):
        from app.services.solicitante_edicao_service import adicionar_anexo_tardio

        user = _usuario_mock()
        chamado_data = _data_chamado(status="Aberto", minutos_atras=5)
        chamado_data["anexos"] = []
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = chamado_data

        with (
            patch("app.services.solicitante_edicao_service.db") as mock_db,
            patch(
                "app.services.solicitante_edicao_service.Historico",
                side_effect=RuntimeError("boom"),
            ),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            mock_db.collection.return_value.document.return_value.update.return_value = None
            resultado = adicionar_anexo_tardio(
                "ch_1", "arquivo.pdf", "motivo suficiente aqui", user
            )

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 500


# ---------------------------------------------------------------------------
# Lacuna 2 — Notificação pós edição de descrição
# ---------------------------------------------------------------------------


class TestNotificacaoEdicaoDescricao:
    def test_edicao_sucedida_dispara_notificacao_em_thread(self):
        """CT-REQ-05: editar_descricao_solicitante dispara _notificar_edicao_descricao após sucesso."""
        from app.services.solicitante_edicao_service import editar_descricao_solicitante

        user = _usuario_mock()
        chamado_data = _data_chamado(minutos_atras=5)
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = chamado_data

        with (
            patch("app.services.solicitante_edicao_service.db") as mock_db,
            patch("app.services.solicitante_edicao_service.Historico") as mock_hist,
            patch(
                "app.services.solicitante_edicao_service._notificar_edicao_descricao"
            ) as mock_notif,
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            mock_db.collection.return_value.document.return_value.update.return_value = None
            mock_hist.return_value.save.return_value = True

            resultado = editar_descricao_solicitante(
                chamado_id="ch_1",
                novo_texto="Texto editado com detalhe",
                usuario=user,
            )

        assert resultado["sucesso"] is True
        mock_notif.assert_called_once()

    def test_edicao_falha_nao_dispara_notificacao(self):
        """Edição dentro da janela, mas exceção no update → notificação NÃO é chamada."""
        from app.services.solicitante_edicao_service import editar_descricao_solicitante

        user = _usuario_mock()
        chamado_data = _data_chamado(minutos_atras=5)
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = chamado_data

        with (
            patch("app.services.solicitante_edicao_service.db") as mock_db,
            patch(
                "app.services.solicitante_edicao_service.Historico",
                side_effect=RuntimeError("db fail"),
            ),
            patch(
                "app.services.solicitante_edicao_service._notificar_edicao_descricao"
            ) as mock_notif,
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            mock_db.collection.return_value.document.return_value.update.return_value = None

            resultado = editar_descricao_solicitante(
                chamado_id="ch_1",
                novo_texto="Texto editado",
                usuario=user,
            )

        assert resultado["sucesso"] is False
        mock_notif.assert_not_called()


# ---------------------------------------------------------------------------
# Lacuna 1 — Notificação pós anexo tardio
# ---------------------------------------------------------------------------


class TestNotificacaoEdicaoDescricaoClosure:
    def test_closure_run_chama_notificar_edicao(self, app):
        """Executa o _run() interno de _notificar_edicao_descricao."""
        from app.services.solicitante_edicao_service import _notificar_edicao_descricao

        user = _usuario_mock()
        dados = {"numero_chamado": "CH-001", "categoria": "TI", "observadores": []}
        closures = []

        def fake_thread(target, daemon=True):
            closures.append(target)
            m = MagicMock()
            m.start = lambda: None
            return m

        with (
            patch("threading.Thread", side_effect=fake_thread),
            app.app_context(),
        ):
            _notificar_edicao_descricao("ch_1", dados, user, "anterior", "novo")

        assert len(closures) == 1
        with patch(
            "app.services.chamado_notificacao_service.destinatarios_do_chamado", return_value=[]
        ):
            closures[0]()

    def test_closure_run_captura_excecao(self, app):
        """_run() captura exceções sem propagar."""
        from app.services.solicitante_edicao_service import _notificar_edicao_descricao

        user = _usuario_mock()
        dados = {}
        closures = []

        def fake_thread(target, daemon=True):
            closures.append(target)
            m = MagicMock()
            m.start = lambda: None
            return m

        with (
            patch("threading.Thread", side_effect=fake_thread),
            app.app_context(),
        ):
            _notificar_edicao_descricao("ch_1", dados, user, "a", "b")

        with patch(
            "app.services.chamado_notificacao_service.destinatarios_do_chamado",
            side_effect=RuntimeError("fail"),
        ):
            closures[0]()  # Should not raise

    def test_nome_do_solicitante_capturado_antes_da_thread(self, app):
        """Regressão: usuario.nome deve ser lido ANTES de _run() ser agendado.

        _run() só reabre app_context (não request context) dentro da thread,
        então o current_user real fica None nesse ponto e usuario.nome
        explodiria — a notificação teria que sair mesmo assim, com o nome
        capturado enquanto o request context ainda existia.
        """
        from app.services.solicitante_edicao_service import _notificar_edicao_descricao

        user = _UsuarioContextoLimitado(nome="Fulano de Tal")
        dados = {"numero_chamado": "CH-001", "categoria": "TI", "observadores": []}
        closures = []

        def fake_thread(target, daemon=True):
            closures.append(target)
            m = MagicMock()
            m.start = lambda: None
            return m

        with patch("threading.Thread", side_effect=fake_thread), app.app_context():
            _notificar_edicao_descricao("ch_1", dados, user, "antes", "depois")

        # Simula a thread rodando fora do request context original
        user.contexto_ativo = False

        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[],
            ),
            patch(
                "app.services.chamado_notificacao_service.notificar_edicao_descricao_solicitante"
            ) as mock_notificar,
        ):
            closures[0]()

        mock_notificar.assert_called_once()
        assert mock_notificar.call_args.kwargs["solicitante_nome"] == "Fulano de Tal"


class TestNotificacaoAnexoTardio:
    def test_anexo_sucedido_dispara_notificacao(self):
        """CT-REQ-06: adicionar_anexo_tardio dispara _notificar_anexo_tardio após sucesso."""
        from app.services.solicitante_edicao_service import adicionar_anexo_tardio

        user = _usuario_mock()
        chamado_data = _data_chamado(status="Aberto", minutos_atras=5)
        chamado_data["anexos"] = []
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = chamado_data

        with (
            patch("app.services.solicitante_edicao_service.db") as mock_db,
            patch("app.services.solicitante_edicao_service.Historico") as mock_hist,
            patch("app.services.solicitante_edicao_service._notificar_anexo_tardio") as mock_notif,
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            mock_db.collection.return_value.document.return_value.update.return_value = None
            mock_hist.return_value.save.return_value = True

            resultado = adicionar_anexo_tardio(
                chamado_id="ch_1",
                caminho_anexo="path/relatorio.pdf",
                motivo="Documento esquecido no envio inicial",
                usuario=user,
            )

        assert resultado["sucesso"] is True
        mock_notif.assert_called_once()

    def test_anexo_falha_nao_dispara_notificacao(self):
        """Exceção no update → _notificar_anexo_tardio NÃO é chamada."""
        from app.services.solicitante_edicao_service import adicionar_anexo_tardio

        user = _usuario_mock()
        chamado_data = _data_chamado(status="Aberto", minutos_atras=5)
        chamado_data["anexos"] = []
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = chamado_data

        with (
            patch("app.services.solicitante_edicao_service.db") as mock_db,
            patch(
                "app.services.solicitante_edicao_service.Historico",
                side_effect=RuntimeError("db fail"),
            ),
            patch("app.services.solicitante_edicao_service._notificar_anexo_tardio") as mock_notif,
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            mock_db.collection.return_value.document.return_value.update.return_value = None

            resultado = adicionar_anexo_tardio(
                chamado_id="ch_1",
                caminho_anexo="path/relatorio.pdf",
                motivo="Motivo suficientemente longo",
                usuario=user,
            )

        assert resultado["sucesso"] is False
        mock_notif.assert_not_called()


# ---------------------------------------------------------------------------
# Cobertura de _dentro_da_janela (linhas 36, 40)
# ---------------------------------------------------------------------------


class TestDentroJanelaCoverage:
    def test_data_abertura_naive_datetime_sucede(self):
        """Naive datetime (tzinfo=None) recente → linha 36 coberta, edição permitida."""
        from datetime import datetime, timedelta

        from app.services.solicitante_edicao_service import editar_descricao_solicitante

        user = _usuario_mock()
        abertura_naive = datetime.now() - timedelta(minutes=5)
        chamado_data = {
            "solicitante_id": "sol_1",
            "status": "Aberto",
            "descricao": "Desc original",
            "data_abertura": abertura_naive,
            "observadores": [],
            "responsavel_id": "sup_1",
            "numero_chamado": "CH-001",
            "categoria": "TI",
        }
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = chamado_data

        with (
            patch("app.services.solicitante_edicao_service.db") as mock_db,
            patch("app.services.solicitante_edicao_service.Historico") as mock_hist,
            patch("app.services.solicitante_edicao_service._notificar_edicao_descricao"),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            mock_db.collection.return_value.document.return_value.update.return_value = None
            mock_hist.return_value.save.return_value = True

            resultado = editar_descricao_solicitante("ch_1", "Novo texto editado", user)

        assert resultado["sucesso"] is True

    def test_data_abertura_nao_datetime_bloqueia(self):
        """data_abertura=None → linha 40 coberta (_dentro_da_janela retorna False → 403)."""
        from app.services.solicitante_edicao_service import editar_descricao_solicitante

        user = _usuario_mock()
        chamado_data = {
            "solicitante_id": "sol_1",
            "status": "Aberto",
            "descricao": "Desc original",
            "data_abertura": None,
            "observadores": [],
        }
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = chamado_data

        with patch("app.services.solicitante_edicao_service.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            resultado = editar_descricao_solicitante("ch_1", "Novo texto", user)

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 403


# ---------------------------------------------------------------------------
# Cobertura do closure _run() de _notificar_anexo_tardio (linhas 224-249)
# ---------------------------------------------------------------------------


class TestNotificacaoAnexoTardioClosure:
    def test_closure_run_chama_notificar_anexo(self, app):
        """Executa o _run() interno de _notificar_anexo_tardio."""
        from app.services.solicitante_edicao_service import _notificar_anexo_tardio

        user = _usuario_mock()
        dados = {"numero_chamado": "CH-001", "categoria": "TI", "observadores": []}
        closures = []

        def fake_thread(target, daemon=True):
            closures.append(target)
            m = MagicMock()
            m.start = lambda: None
            return m

        with (
            patch("threading.Thread", side_effect=fake_thread),
            app.app_context(),
        ):
            _notificar_anexo_tardio("ch_1", dados, user, "docs/file.pdf", "motivo")

        assert len(closures) == 1
        with patch(
            "app.services.chamado_notificacao_service.destinatarios_do_chamado", return_value=[]
        ):
            closures[0]()

    def test_closure_run_captura_excecao(self, app):
        """_run() de _notificar_anexo_tardio captura exceções sem propagar."""
        from app.services.solicitante_edicao_service import _notificar_anexo_tardio

        user = _usuario_mock()
        dados = {}
        closures = []

        def fake_thread(target, daemon=True):
            closures.append(target)
            m = MagicMock()
            m.start = lambda: None
            return m

        with (
            patch("threading.Thread", side_effect=fake_thread),
            app.app_context(),
        ):
            _notificar_anexo_tardio("ch_1", dados, user, "file.pdf", "motivo")

        with patch(
            "app.services.chamado_notificacao_service.destinatarios_do_chamado",
            side_effect=RuntimeError("fail"),
        ):
            closures[0]()  # Should not raise

    def test_nome_do_solicitante_capturado_antes_da_thread(self, app):
        """Regressão: mesmo caso da edição de descrição, mas para anexo tardio."""
        from app.services.solicitante_edicao_service import _notificar_anexo_tardio

        user = _UsuarioContextoLimitado(nome="Fulano de Tal")
        dados = {"numero_chamado": "CH-001", "categoria": "TI", "observadores": []}
        closures = []

        def fake_thread(target, daemon=True):
            closures.append(target)
            m = MagicMock()
            m.start = lambda: None
            return m

        with patch("threading.Thread", side_effect=fake_thread), app.app_context():
            _notificar_anexo_tardio("ch_1", dados, user, "docs/file.pdf", "motivo")

        user.contexto_ativo = False

        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[],
            ),
            patch(
                "app.services.chamado_notificacao_service.notificar_anexo_tardio_chamado"
            ) as mock_notificar,
        ):
            closures[0]()

        mock_notificar.assert_called_once()
        assert mock_notificar.call_args.kwargs["solicitante_nome"] == "Fulano de Tal"
