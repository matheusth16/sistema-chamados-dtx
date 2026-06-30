"""
Fase 4 — TDD: cancelamento de chamado pelo solicitante.

Regras:
- Só o solicitante dono pode cancelar
- Motivo obrigatório (mín 10 chars)
- Só statuses canceláveis: Aberto, Em Atendimento, Aguardando Informação
- Concluído e Cancelado → 403
- Observadores NÃO podem cancelar
- Notificação deve ser disparada (responsável + observadores)
"""

from unittest.mock import MagicMock, patch


def _usuario_mock(uid="sol_1", perfil="solicitante"):
    u = MagicMock()
    u.id = uid
    u.nome = "Solicitante Teste"
    u.perfil = perfil
    u.email = "sol@test.com"
    u.is_admin_or_above = perfil in ("admin", "admin_global")
    return u


def _mock_doc(
    solicitante_id="sol_1",
    status="Aberto",
    responsavel_id="sup_1",
    numero_chamado="CH-001",
    categoria="TI",
    observadores=None,
):
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "solicitante_id": solicitante_id,
        "status": status,
        "responsavel_id": responsavel_id,
        "numero_chamado": numero_chamado,
        "categoria": categoria,
        "observadores": observadores or [],
    }
    return doc


class TestCancelarChamadoSolicitante:
    def test_owner_cancela_aberto_com_motivo(self):
        """Dono + motivo + status Aberto → sucesso."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()

        with (
            patch("app.services.cancelamento_solicitante_service.db") as mock_db,
            patch("app.services.cancelamento_solicitante_service.Historico") as mock_hist,
            patch("app.services.cancelamento_solicitante_service._notificar_cancelamento"),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = _mock_doc()
            mock_db.collection.return_value.document.return_value.update.return_value = None
            mock_hist.return_value.save.return_value = True

            resultado = cancelar_chamado_solicitante(
                chamado_id="ch_1",
                motivo="Problema resolvido por outra via",
                usuario=user,
            )

        assert resultado["sucesso"] is True

    def test_owner_cancela_em_atendimento(self):
        """Status Em Atendimento → também pode cancelar."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()

        with (
            patch("app.services.cancelamento_solicitante_service.db") as mock_db,
            patch("app.services.cancelamento_solicitante_service.Historico") as mock_hist,
            patch("app.services.cancelamento_solicitante_service._notificar_cancelamento"),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = _mock_doc(
                status="Em Atendimento"
            )
            mock_db.collection.return_value.document.return_value.update.return_value = None
            mock_hist.return_value.save.return_value = True

            resultado = cancelar_chamado_solicitante(
                chamado_id="ch_1",
                motivo="Problema resolvido por outra via",
                usuario=user,
            )

        assert resultado["sucesso"] is True

    def test_nao_owner_bloqueado(self):
        """Outro usuário (não dono) → 403."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock(uid="outro")

        with patch("app.services.cancelamento_solicitante_service.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = _mock_doc(
                solicitante_id="dono_real"
            )
            resultado = cancelar_chamado_solicitante(
                chamado_id="ch_1",
                motivo="Motivo válido aqui",
                usuario=user,
            )

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 403

    def test_motivo_vazio_bloqueado(self):
        """Motivo vazio → 400."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()

        with patch("app.services.cancelamento_solicitante_service.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = _mock_doc()
            resultado = cancelar_chamado_solicitante(
                chamado_id="ch_1",
                motivo="",
                usuario=user,
            )

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 400

    def test_status_concluido_bloqueado(self):
        """Status Concluído → não pode cancelar (403)."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()

        with patch("app.services.cancelamento_solicitante_service.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = _mock_doc(
                status="Concluído"
            )
            resultado = cancelar_chamado_solicitante(
                chamado_id="ch_1",
                motivo="Motivo suficientemente longo",
                usuario=user,
            )

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 403

    def test_status_cancelado_bloqueado(self):
        """Chamado já Cancelado → 403."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()

        with patch("app.services.cancelamento_solicitante_service.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = _mock_doc(
                status="Cancelado"
            )
            resultado = cancelar_chamado_solicitante(
                chamado_id="ch_1",
                motivo="Motivo suficientemente longo",
                usuario=user,
            )

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 403

    def test_notificacao_disparada_apos_cancelamento(self):
        """Após cancelar, _notificar_cancelamento deve ser chamado."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()

        with (
            patch("app.services.cancelamento_solicitante_service.db") as mock_db,
            patch("app.services.cancelamento_solicitante_service.Historico") as mock_hist,
            patch(
                "app.services.cancelamento_solicitante_service._notificar_cancelamento"
            ) as mock_notif,
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = _mock_doc()
            mock_db.collection.return_value.document.return_value.update.return_value = None
            mock_hist.return_value.save.return_value = True

            cancelar_chamado_solicitante(
                chamado_id="ch_1",
                motivo="Cancelamento justificado",
                usuario=user,
            )

        mock_notif.assert_called_once()

    def test_historico_registra_motivo(self):
        """Historico deve conter o motivo no campo detalhe."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()
        historicos = []

        def capturar(**kwargs):
            historicos.append(kwargs)
            h = MagicMock()
            h.save.return_value = True
            return h

        with (
            patch("app.services.cancelamento_solicitante_service.db") as mock_db,
            patch(
                "app.services.cancelamento_solicitante_service.Historico",
                side_effect=capturar,
            ),
            patch("app.services.cancelamento_solicitante_service._notificar_cancelamento"),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = _mock_doc()
            mock_db.collection.return_value.document.return_value.update.return_value = None

            cancelar_chamado_solicitante(
                chamado_id="ch_1",
                motivo="Cancelamento justificado",
                usuario=user,
            )

        assert len(historicos) >= 1
        detalhe = historicos[0].get("detalhe") or ""
        assert "Cancelamento justificado" in detalhe


class TestCancelarDataCancelamento:
    def test_data_cancelamento_gravada_no_update(self):
        """CT-REQ-11: update deve incluir data_cancelamento (SERVER_TIMESTAMP)."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()
        update_calls = []

        def capturar_update(payload):
            update_calls.append(payload)

        with (
            patch("app.services.cancelamento_solicitante_service.db") as mock_db,
            patch("app.services.cancelamento_solicitante_service.Historico") as mock_hist,
            patch("app.services.cancelamento_solicitante_service._notificar_cancelamento"),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = _mock_doc()
            mock_db.collection.return_value.document.return_value.update.side_effect = (
                capturar_update
            )
            mock_hist.return_value.save.return_value = True

            resultado = cancelar_chamado_solicitante(
                chamado_id="ch_1",
                motivo="Cancelamento justificado",
                usuario=user,
            )

        assert resultado["sucesso"] is True
        assert len(update_calls) == 1
        assert "data_cancelamento" in update_calls[0], (
            "data_cancelamento deve estar presente no payload do update"
        )


class TestCancelarCoverage:
    def test_chamado_nao_encontrado_retorna_404(self):
        """Chamado inexistente → 404."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()
        doc_nao_encontrado = MagicMock()
        doc_nao_encontrado.exists = False

        with patch("app.services.cancelamento_solicitante_service.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = (
                doc_nao_encontrado
            )
            resultado = cancelar_chamado_solicitante("ch_x", "motivo válido aqui", user)

        assert resultado["sucesso"] is False
        assert resultado.get("codigo") == 404

    def test_excecao_retorna_500(self):
        """Exceção durante update → 500."""
        from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

        user = _usuario_mock()

        with (
            patch("app.services.cancelamento_solicitante_service.db") as mock_db,
            patch(
                "app.services.cancelamento_solicitante_service.Historico",
                side_effect=RuntimeError("boom"),
            ),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = _mock_doc()
            mock_db.collection.return_value.document.return_value.update.return_value = None
            resultado = cancelar_chamado_solicitante("ch_1", "motivo suficiente aqui", user)

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
