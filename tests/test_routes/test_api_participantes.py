"""Testes das rotas POST /api/chamado/<id>/incluir-participantes e /concluir-minha-parte.

Segue padrão do projeto (Fase 2, Marco 10):
- patch('app.routes.api_colaboracao.Chamado') para simular Chamado.get_by_id() (Postgres)
- patch do serviço importado inline pela rota
- Usa fixtures do conftest.py
"""

from unittest.mock import MagicMock, patch

# ── helpers ───────────────────────────────────────────────────────────────────


def _mock_chamado_obj(
    area="Manutencao",
    responsavel_id="sup_1",
    participantes=None,
    status="Em Atendimento",
):
    """MagicMock de Chamado (retorno de Chamado.get_by_id()) com to_dict()
    coerente — a rota usa tanto os atributos do objeto quanto o dict
    (chamado.to_dict()) repassado às notificações em background."""
    c = MagicMock()
    c.id = "id_chamado_teste"
    c.area = area
    c.responsavel_id = responsavel_id
    c.solicitante_id = "sol_outro"
    c.participantes = participantes or []
    c.supervisor_ids_com_acesso = [responsavel_id] if responsavel_id else []
    c.to_dict.return_value = {
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
    return c


# ── POST /api/chamado/<id>/incluir-participantes ──────────────────────────────


class TestIncluirParticipantesRota:
    def test_incluir_sucesso_retorna_200(self, client_logado_supervisor):
        """Owner supervisor inclui participante válido → 200 sucesso=True."""
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

        with (
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
            patch(
                "app.services.escalonamento_service.incluir_participantes",
                return_value={
                    "sucesso": True,
                    "dados": {
                        "participantes": [
                            {
                                "supervisor_id": "id_dest",
                                "area": "Logistica",
                                "status": "pendente",
                                "concluido_em": None,
                            }
                        ],
                        "adicionados": [
                            {"supervisor_id": "id_dest", "area": "Logistica", "nome": "Dest"}
                        ],
                    },
                },
            ),
            patch("app.routes.api_colaboracao.threading"),
        ):
            mock_chamado_cls.get_by_id.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/incluir-participantes",
                json={"participantes": [{"supervisor_id": "id_dest", "area": "Logistica"}]},
                content_type="application/json",
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data is not None
        assert data["sucesso"] is True

    def test_incluir_sem_acesso_apos_dispara_flash_sucesso(self, client_logado_supervisor):
        """Ver docstring equivalente em test_api_escalonamento.py::TestTransferirAreaRota."""
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

        with (
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
            patch(
                "app.services.escalonamento_service.incluir_participantes",
                return_value={
                    "sucesso": True,
                    "dados": {
                        "participantes": [
                            {
                                "supervisor_id": "id_dest",
                                "area": "Logistica",
                                "status": "pendente",
                                "concluido_em": None,
                            }
                        ],
                        "adicionados": [
                            {"supervisor_id": "id_dest", "area": "Logistica", "nome": "Dest"}
                        ],
                        "ainda_tem_acesso": False,
                    },
                },
            ),
            patch("app.routes.api_colaboracao.threading"),
            patch("app.routes.api_colaboracao.flash_t") as mock_flash,
        ):
            mock_chamado_cls.get_by_id.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/incluir-participantes",
                json={"participantes": [{"supervisor_id": "id_dest", "area": "Logistica"}]},
                content_type="application/json",
            )

        assert resp.status_code == 200
        mock_flash.assert_called_once_with("acao_escalonamento_sucesso_sem_acesso", "success")

    def test_incluir_lista_vazia_retorna_400(self, client_logado_supervisor):
        """Lista de participantes vazia → 400."""
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

        with (
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
        ):
            mock_chamado_cls.get_by_id.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/incluir-participantes",
                json={"participantes": []},
                content_type="application/json",
            )

        assert resp.status_code == 400

    def test_incluir_sem_json_retorna_400(self, client_logado_supervisor):
        """Sem corpo JSON → 400."""
        resp = client_logado_supervisor.post(
            "/api/chamado/id123/incluir-participantes",
            data="",
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_incluir_nao_owner_supervisor_retorna_403(self, client_logado_supervisor):
        """Supervisor que não é owner → 403."""
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="outro_sup")

        with (
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
        ):
            mock_chamado_cls.get_by_id.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/incluir-participantes",
                json={"participantes": [{"supervisor_id": "id_dest", "area": "Logistica"}]},
                content_type="application/json",
            )

        assert resp.status_code == 403

    def test_incluir_gestor_setor_da_area_sem_ser_owner_retorna_200(self, client_logado_gestor):
        """Ações de Escalonamento (2026-08-20): gestor_setor da própria área
        pode incluir participantes em chamado do time mesmo sem ser owner."""
        chamado_mock = _mock_chamado_obj(area="Geral", responsavel_id="outro_sup")

        with (
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
            patch(
                "app.services.escalonamento_service.incluir_participantes",
                return_value={
                    "sucesso": True,
                    "dados": {
                        "participantes": [
                            {
                                "supervisor_id": "id_dest",
                                "area": "Logistica",
                                "status": "pendente",
                                "concluido_em": None,
                            }
                        ],
                        "adicionados": [
                            {"supervisor_id": "id_dest", "area": "Logistica", "nome": "Dest"}
                        ],
                    },
                },
            ),
            patch("app.routes.api_colaboracao.threading"),
        ):
            mock_chamado_cls.get_by_id.return_value = chamado_mock

            resp = client_logado_gestor.post(
                "/api/chamado/id123/incluir-participantes",
                json={"participantes": [{"supervisor_id": "id_dest", "area": "Logistica"}]},
                content_type="application/json",
            )

        assert resp.status_code == 200
        assert resp.get_json()["sucesso"] is True

    def test_incluir_solicitante_bloqueado(self, client_logado_solicitante):
        """Solicitante não tem acesso à rota e recebe JSON 403."""
        resp = client_logado_solicitante.post(
            "/api/chamado/id123/incluir-participantes",
            json={"participantes": [{"supervisor_id": "id_dest", "area": "Logistica"}]},
            content_type="application/json",
        )
        assert resp.status_code == 403
        assert resp.is_json

    def test_incluir_idor_supervisor_sem_acesso_retorna_403(self, client_logado_supervisor):
        """Supervisor sem acesso ao chamado (usuario_pode_ver_chamado=False) → 403."""
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="outro_sup")

        with (
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=False),
        ):
            mock_chamado_cls.get_by_id.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/incluir-participantes",
                json={"participantes": [{"supervisor_id": "id_dest", "area": "Logistica"}]},
                content_type="application/json",
            )

        assert resp.status_code == 403

    def test_incluir_admin_pode_incluir(self, client_logado_admin):
        """Admin pode incluir mesmo não sendo owner → 200."""
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="outro_sup")

        with (
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
            patch(
                "app.services.escalonamento_service.incluir_participantes",
                return_value={
                    "sucesso": True,
                    "dados": {"participantes": [], "adicionados": []},
                },
            ),
            patch("app.routes.api_colaboracao.threading"),
        ):
            mock_chamado_cls.get_by_id.return_value = chamado_mock
            # Admin: is_admin_or_above=True no mock conftest

            resp = client_logado_admin.post(
                "/api/chamado/id123/incluir-participantes",
                json={"participantes": [{"supervisor_id": "id_dest", "area": "Logistica"}]},
                content_type="application/json",
            )

        assert resp.status_code == 200


# ── POST /api/chamado/<id>/concluir-minha-parte ───────────────────────────────


class TestConcluirMinhaParteRota:
    def test_concluir_minha_parte_sucesso_retorna_200(self, client_logado_supervisor):
        """Participante conclui sua parte → 200 sucesso=True."""
        chamado_mock = _mock_chamado_obj(
            area="Manutencao",
            responsavel_id="outro_sup",
            participantes=[
                {
                    "supervisor_id": "sup_1",
                    "area": "Manutencao",
                    "status": "pendente",
                    "concluido_em": None,
                }
            ],
        )

        with (
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
            patch(
                "app.services.escalonamento_service.concluir_minha_parte",
                return_value={"sucesso": True, "dados": {"pode_concluir_global": False}},
            ),
        ):
            mock_chamado_cls.get_by_id.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/concluir-minha-parte",
                json={},
                content_type="application/json",
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["sucesso"] is True

    def test_concluir_quem_nao_e_participante_retorna_403(self, client_logado_supervisor):
        """Usuário que não é participante → 403."""
        chamado_mock = _mock_chamado_obj(
            area="Manutencao",
            responsavel_id="outro_sup",
            participantes=[],
        )

        with (
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
        ):
            mock_chamado_cls.get_by_id.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/concluir-minha-parte",
                json={},
                content_type="application/json",
            )

        assert resp.status_code == 403

    def test_concluir_minha_parte_ultimo_dispara_notificacao_owner(self, client_logado_supervisor):
        """Quando último participante conclui (pode_concluir_global=True), notifica owner."""
        chamado_mock = _mock_chamado_obj(
            area="Manutencao",
            responsavel_id="outro_sup",
            participantes=[
                {
                    "supervisor_id": "sup_1",
                    "area": "Manutencao",
                    "status": "pendente",
                    "concluido_em": None,
                }
            ],
        )

        with (
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
            patch(
                "app.services.escalonamento_service.concluir_minha_parte",
                return_value={"sucesso": True, "dados": {"pode_concluir_global": True}},
            ),
            patch("app.routes.api_colaboracao.threading") as mock_threading,
        ):
            mock_chamado_cls.get_by_id.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/concluir-minha-parte",
                json={},
                content_type="application/json",
            )

        assert resp.status_code == 200
        mock_threading.Thread.assert_called()


# ── Notificação tripla ao incluir participante (Lacuna 2) ─────────────────────


class TestNotificacaoTriplaInclusao:
    def test_incluir_dispara_notificacao_tripla_participante(self, client_logado_supervisor):
        """Incluir participante → thread de notificação disparado (cobre e-mail + in-app + web push)."""
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

        with (
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
            patch(
                "app.services.escalonamento_service.incluir_participantes",
                return_value={
                    "sucesso": True,
                    "dados": {
                        "participantes": [
                            {
                                "supervisor_id": "id_dest",
                                "area": "Logistica",
                                "status": "pendente",
                                "concluido_em": None,
                            }
                        ],
                        "adicionados": [
                            {"supervisor_id": "id_dest", "area": "Logistica", "nome": "Dest Sup"}
                        ],
                    },
                },
            ),
            patch("app.routes.api_colaboracao.threading") as mock_threading,
        ):
            mock_chamado_cls.get_by_id.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/incluir-participantes",
                json={"participantes": [{"supervisor_id": "id_dest", "area": "Logistica"}]},
                content_type="application/json",
            )

        assert resp.status_code == 200
        # Thread de notificação iniciado (disparará e-mail + in-app + web push)
        mock_threading.Thread.assert_called_once()
        call_kwargs = mock_threading.Thread.call_args.kwargs
        assert call_kwargs.get("daemon") is True

    def test_incluir_sem_adicionados_nao_dispara_thread(self, client_logado_supervisor):
        """Quando todos participantes são duplicados, não dispara thread de notificação."""
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

        with (
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
            patch(
                "app.services.escalonamento_service.incluir_participantes",
                return_value={
                    "sucesso": False,
                    "erro": "Nenhum participante novo para incluir — todos já são participantes do chamado",
                },
            ),
            patch("app.routes.api_colaboracao.threading") as mock_threading,
        ):
            mock_chamado_cls.get_by_id.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/incluir-participantes",
                json={"participantes": [{"supervisor_id": "id_dest", "area": "Logistica"}]},
                content_type="application/json",
            )

        assert resp.status_code == 400
        mock_threading.Thread.assert_not_called()
