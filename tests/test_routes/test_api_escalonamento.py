"""Testes das rotas POST /api/chamado/<id>/transferir-area e /escalonar-colega.

Segue padrão do projeto:
- patch('app.routes.api.db') para simular Firestore na rota
- patch do serviço importado inline pela rota
- Usa fixtures client_logado_supervisor, client_logado_admin, client_logado_solicitante
"""

from unittest.mock import MagicMock, patch

# ── helpers ───────────────────────────────────────────────────────────────────


def _chamado_doc_mock(
    area="Manutencao",
    responsavel_id="sup_1",
    participantes=None,
    status="Em Atendimento",
):
    """Retorna um mock de documento Firestore para um chamado."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "area": area,
        "responsavel_id": responsavel_id,
        "responsavel": "Supervisor Teste",
        "status": status,
        "participantes": participantes or [],
        "supervisor_ids_com_acesso": [responsavel_id] if responsavel_id else [],
        "motivo_ultima_escalacao": None,
        "categoria": "Manutencao",
        "tipo_solicitacao": "Corretiva",
        "descricao": "Descrição de teste",
    }
    return doc


def _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1", participantes=None):
    """Retorna um MagicMock de Chamado (objeto, não doc)."""
    c = MagicMock()
    c.id = "id_chamado_teste"
    c.area = area
    c.responsavel_id = responsavel_id
    c.solicitante_id = "sol_outro"
    c.participantes = participantes or []
    c.supervisor_ids_com_acesso = [responsavel_id] if responsavel_id else []
    return c


# ── POST /api/chamado/<id>/transferir-area ─────────────────────────────────────


class TestTransferirAreaRota:
    def test_transferir_area_sucesso_retorna_200(self, client_logado_supervisor):
        """Owner supervisor pode transferir com payload válido → 200 sucesso=True."""
        doc = _chamado_doc_mock(area="Manutencao", responsavel_id="sup_1")
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

        with (
            patch("app.routes.api_colaboracao.db") as mock_db,
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
            # Inline import — patch no módulo do serviço (padrão do projeto)
            patch(
                "app.services.escalonamento_service.transferir_area",
                return_value={
                    "sucesso": True,
                    "dados": {"area": "Planejamento", "responsavel_id": "id_dest"},
                },
            ),
            patch("app.routes.api_colaboracao.threading"),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = doc
            mock_chamado_cls.from_dict.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/transferir-area",
                json={
                    "area": "Planejamento",
                    "supervisor_id": "id_dest",
                    "motivo": "Precisa de PPCP",
                },
                content_type="application/json",
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data is not None
        assert data["sucesso"] is True

    def test_transferir_area_sem_motivo_retorna_400(self, client_logado_supervisor):
        """motivo vazio → 400."""
        doc = _chamado_doc_mock(area="Manutencao", responsavel_id="sup_1")
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

        with (
            patch("app.routes.api_colaboracao.db") as mock_db,
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = doc
            mock_chamado_cls.from_dict.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/transferir-area",
                json={"area": "Planejamento", "supervisor_id": "id_dest", "motivo": ""},
                content_type="application/json",
            )

        assert resp.status_code == 400
        data = resp.get_json()
        assert data["sucesso"] is False

    def test_transferir_area_sem_supervisor_id_retorna_400(self, client_logado_supervisor):
        """supervisor_id ausente → 400."""
        doc = _chamado_doc_mock(area="Manutencao", responsavel_id="sup_1")
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

        with (
            patch("app.routes.api_colaboracao.db") as mock_db,
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = doc
            mock_chamado_cls.from_dict.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/transferir-area",
                json={"area": "Planejamento", "supervisor_id": "", "motivo": "motivo válido"},
                content_type="application/json",
            )

        assert resp.status_code == 400

    def test_transferir_area_solicitante_retorna_403(self, client_logado_solicitante):
        """Solicitante não tem acesso à rota de supervisor → 403."""
        resp = client_logado_solicitante.post(
            "/api/chamado/id123/transferir-area",
            json={"area": "Planejamento", "supervisor_id": "id_dest", "motivo": "motivo"},
            content_type="application/json",
        )
        assert resp.status_code in (302, 403)

    def test_transferir_area_nao_owner_supervisor_retorna_403(self, client_logado_supervisor):
        """Supervisor que não é owner do chamado → 403."""
        doc = _chamado_doc_mock(
            area="Manutencao", responsavel_id="outro_sup"
        )  # responsavel != sup_1
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="outro_sup")
        chamado_mock.solicitante_id = "sol_outro"  # supervisor não é o solicitante

        with (
            patch("app.routes.api_colaboracao.db") as mock_db,
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = doc
            mock_chamado_cls.from_dict.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/transferir-area",
                json={"area": "Planejamento", "supervisor_id": "id_dest", "motivo": "motivo"},
                content_type="application/json",
            )

        assert resp.status_code == 403

    def test_transferir_area_idor_sem_acesso_retorna_403(self, client_logado_supervisor):
        """Supervisor sem acesso ao chamado (usuario_pode_ver_chamado=False) → 403."""
        doc = _chamado_doc_mock(area="TI", responsavel_id="outro_sup")
        chamado_mock = _mock_chamado_obj(area="TI", responsavel_id="outro_sup")

        with (
            patch("app.routes.api_colaboracao.db") as mock_db,
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch(
                "app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=False
            ),  # IDOR
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = doc
            mock_chamado_cls.from_dict.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/transferir-area",
                json={"area": "TI", "supervisor_id": "id_dest", "motivo": "motivo"},
                content_type="application/json",
            )

        assert resp.status_code == 403

    def test_transferir_area_chamado_nao_encontrado_retorna_404(self, client_logado_supervisor):
        """Chamado não encontrado no Firestore → 404."""
        doc_inexistente = MagicMock()
        doc_inexistente.exists = False

        with patch("app.routes.api_colaboracao.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = doc_inexistente
            resp = client_logado_supervisor.post(
                "/api/chamado/id_inexistente/transferir-area",
                json={"area": "Planejamento", "supervisor_id": "id_dest", "motivo": "motivo"},
                content_type="application/json",
            )

        assert resp.status_code == 404

    def test_notificacao_transferir_usa_area_destino(self, client_logado_supervisor):
        """Bug L1: notificação de transferência deve conter área destino, não origem.

        Antes do fix: dados_notif pegava area do doc original ("Manutencao").
        Após o fix: dados_notif["area"] == "Planejamento" (área do payload).
        """
        doc = _chamado_doc_mock(area="Manutencao", responsavel_id="sup_1")
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

        with (
            patch("app.routes.api_colaboracao.db") as mock_db,
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
            patch(
                "app.services.escalonamento_service.transferir_area",
                return_value={
                    "sucesso": True,
                    "dados": {"area": "Planejamento", "responsavel_id": "id_dest"},
                },
            ),
            patch("app.routes.api_colaboracao._notificar_escalonamento") as mock_notif,
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = doc
            mock_chamado_cls.from_dict.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/transferir-area",
                json={
                    "area": "Planejamento",
                    "supervisor_id": "id_dest",
                    "motivo": "Precisa de PPCP",
                },
                content_type="application/json",
            )

        assert resp.status_code == 200
        mock_notif.assert_called_once()
        _app, _chamado_id, dados_notif, tipo, _destino = mock_notif.call_args[0]
        assert tipo == "transferencia_area"
        assert dados_notif.get("area") == "Planejamento", (
            f"Esperado 'Planejamento' mas recebeu '{dados_notif.get('area')}' — área antiga no e-mail"
        )

    def test_notificacao_transferir_chamada_em_background(self, client_logado_supervisor):
        """L2: após transferência bem-sucedida, notificação é disparada em thread daemon."""
        doc = _chamado_doc_mock(area="Manutencao", responsavel_id="sup_1")
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

        with (
            patch("app.routes.api_colaboracao.db") as mock_db,
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
            patch(
                "app.services.escalonamento_service.transferir_area",
                return_value={
                    "sucesso": True,
                    "dados": {"area": "Planejamento", "responsavel_id": "id_dest"},
                },
            ),
            patch("app.routes.api_colaboracao.threading") as mock_threading,
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = doc
            mock_chamado_cls.from_dict.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/transferir-area",
                json={
                    "area": "Planejamento",
                    "supervisor_id": "id_dest",
                    "motivo": "Precisa de PPCP",
                },
                content_type="application/json",
            )

        assert resp.status_code == 200
        mock_threading.Thread.assert_called_once()
        mock_threading.Thread.return_value.start.assert_called_once()

    def test_transferir_area_admin_pode_transferir_chamado_alheio(self, client_logado_admin):
        """Admin pode transferir chamado de qualquer supervisor."""
        doc = _chamado_doc_mock(area="Manutencao", responsavel_id="outro_sup")
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="outro_sup")

        with (
            patch("app.routes.api_colaboracao.db") as mock_db,
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
            patch(
                "app.services.escalonamento_service.transferir_area",
                return_value={"sucesso": True, "dados": {}},
            ),
            patch("app.routes.api_colaboracao.threading"),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = doc
            mock_chamado_cls.from_dict.return_value = chamado_mock

            resp = client_logado_admin.post(
                "/api/chamado/id123/transferir-area",
                json={"area": "Planejamento", "supervisor_id": "id_dest", "motivo": "motivo"},
                content_type="application/json",
            )

        assert resp.status_code == 200
        assert resp.get_json()["sucesso"] is True


# ── POST /api/chamado/<id>/escalonar-colega ───────────────────────────────────


class TestEscalonarColegaRota:
    def test_escalonar_colega_sucesso_retorna_200(self, client_logado_supervisor):
        """Owner supervisor pode escalonar com payload válido → 200."""
        doc = _chamado_doc_mock(area="Manutencao", responsavel_id="sup_1")
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

        with (
            patch("app.routes.api_colaboracao.db") as mock_db,
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
            # Inline import — patch no módulo do serviço (padrão do projeto)
            patch(
                "app.services.escalonamento_service.escalonar_colega",
                return_value={"sucesso": True, "dados": {"responsavel_id": "id_colega"}},
            ),
            patch("app.routes.api_colaboracao.threading"),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = doc
            mock_chamado_cls.from_dict.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/escalonar-colega",
                json={"supervisor_id": "id_colega", "motivo": "Matheus tem especialidade X"},
                content_type="application/json",
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["sucesso"] is True

    def test_escalonar_colega_sem_motivo_retorna_400(self, client_logado_supervisor):
        """motivo vazio → 400."""
        doc = _chamado_doc_mock(area="Manutencao", responsavel_id="sup_1")
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

        with (
            patch("app.routes.api_colaboracao.db") as mock_db,
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = doc
            mock_chamado_cls.from_dict.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/escalonar-colega",
                json={"supervisor_id": "id_colega", "motivo": ""},
                content_type="application/json",
            )

        assert resp.status_code == 400
        assert resp.get_json()["sucesso"] is False

    def test_escalonar_colega_sem_supervisor_id_retorna_400(self, client_logado_supervisor):
        """supervisor_id ausente → 400."""
        doc = _chamado_doc_mock(area="Manutencao", responsavel_id="sup_1")
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

        with (
            patch("app.routes.api_colaboracao.db") as mock_db,
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = doc
            mock_chamado_cls.from_dict.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/escalonar-colega",
                json={"supervisor_id": "", "motivo": "motivo válido"},
                content_type="application/json",
            )

        assert resp.status_code == 400

    def test_escalonar_colega_solicitante_retorna_403(self, client_logado_solicitante):
        """Solicitante não tem permissão para escalonar → 403."""
        resp = client_logado_solicitante.post(
            "/api/chamado/id123/escalonar-colega",
            json={"supervisor_id": "id_colega", "motivo": "motivo"},
            content_type="application/json",
        )
        assert resp.status_code in (302, 403)

    def test_escalonar_colega_idor_sem_acesso_retorna_403(self, client_logado_supervisor):
        """Supervisor sem acesso ao chamado → 403 (IDOR protection)."""
        doc = _chamado_doc_mock(area="TI", responsavel_id="outro_sup")
        chamado_mock = _mock_chamado_obj(area="TI", responsavel_id="outro_sup")

        with (
            patch("app.routes.api_colaboracao.db") as mock_db,
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=False),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = doc
            mock_chamado_cls.from_dict.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/escalonar-colega",
                json={"supervisor_id": "id_colega", "motivo": "motivo"},
                content_type="application/json",
            )

        assert resp.status_code == 403

    def test_escalonar_colega_nao_owner_retorna_403(self, client_logado_supervisor):
        """Supervisor que não é owner do chamado → 403."""
        doc = _chamado_doc_mock(area="Manutencao", responsavel_id="outro_sup")
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="outro_sup")

        with (
            patch("app.routes.api_colaboracao.db") as mock_db,
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = doc
            mock_chamado_cls.from_dict.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/escalonar-colega",
                json={"supervisor_id": "id_colega", "motivo": "motivo"},
                content_type="application/json",
            )

        assert resp.status_code == 403

    def test_escalonar_colega_servico_retorna_erro_propaga_400(self, client_logado_supervisor):
        """Quando o serviço retorna sucesso=False (ex: destino inválido), a rota retorna 400."""
        doc = _chamado_doc_mock(area="Manutencao", responsavel_id="sup_1")
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

        with (
            patch("app.routes.api_colaboracao.db") as mock_db,
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
            patch(
                "app.services.escalonamento_service.escalonar_colega",
                return_value={"sucesso": False, "erro": "Supervisor destino não pertence à área"},
            ),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = doc
            mock_chamado_cls.from_dict.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/escalonar-colega",
                json={"supervisor_id": "id_outra_area", "motivo": "motivo válido"},
                content_type="application/json",
            )

        assert resp.status_code == 400
        assert resp.get_json()["sucesso"] is False

    def test_notificacao_escalonar_chamada_em_background(self, client_logado_supervisor):
        """Após escalonamento bem-sucedido, notificação é disparada em thread separada."""
        doc = _chamado_doc_mock(area="Manutencao", responsavel_id="sup_1")
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

        with (
            patch("app.routes.api_colaboracao.db") as mock_db,
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
            patch(
                "app.services.escalonamento_service.escalonar_colega",
                return_value={"sucesso": True, "dados": {"responsavel_id": "id_colega"}},
            ),
            patch("app.routes.api_colaboracao.threading") as mock_threading,
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = doc
            mock_chamado_cls.from_dict.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/escalonar-colega",
                json={"supervisor_id": "id_colega", "motivo": "motivo válido"},
                content_type="application/json",
            )

        assert resp.status_code == 200
        # Thread foi iniciada para notificação em background
        mock_threading.Thread.assert_called_once()
        mock_threading.Thread.return_value.start.assert_called_once()


# ── Regressão: contrato de erro inconsistente pra perfil sem permissão ────────
#
# Estas 3 rotas são só consumidas via fetch() do JS (ver visualizar_chamado.html)
# e são protegidas por @requer_supervisor_area, que SEMPRE redireciona (302) em
# vez de responder JSON — diferente do resto de /api/*, que responde
# `{"sucesso": false, "erro": ...}` com 403 (ver decoradores.py::requer_supervisor_area).
# Sem risco de segurança: a ação é bloqueada antes de qualquer lógica de negócio
# rodar. Mas o fetch() do frontend recebe um redirect pra HTML onde esperava JSON,
# e `response.json()` estoura em vez de cair no `.catch()` com mensagem clara.


class TestContratoErroSolicitanteSemPermissao:
    def test_transferir_area_solicitante_recebe_redirect_nao_json_403(
        self, client_logado_solicitante
    ):
        """Solicitante chamando transferir-area recebe 302 (redirect do decorador),
        não o JSON 403 padrão do resto da API."""
        resp = client_logado_solicitante.post(
            "/api/chamado/id123/transferir-area",
            json={"area": "Engenharia", "supervisor_id": "sup_x", "motivo": "motivo válido"},
            content_type="application/json",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.content_type != "application/json"

    def test_escalonar_colega_solicitante_recebe_redirect_nao_json_403(
        self, client_logado_solicitante
    ):
        """Solicitante chamando escalonar-colega recebe 302, não JSON 403."""
        resp = client_logado_solicitante.post(
            "/api/chamado/id123/escalonar-colega",
            json={"supervisor_id": "sup_x", "motivo": "motivo válido"},
            content_type="application/json",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.content_type != "application/json"

    def test_incluir_participantes_solicitante_recebe_redirect_nao_json_403(
        self, client_logado_solicitante
    ):
        """Solicitante chamando incluir-participantes recebe 302, não JSON 403."""
        resp = client_logado_solicitante.post(
            "/api/chamado/id123/incluir-participantes",
            json={"participantes": [{"supervisor_id": "sup_x", "area": "Engenharia"}]},
            content_type="application/json",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.content_type != "application/json"
