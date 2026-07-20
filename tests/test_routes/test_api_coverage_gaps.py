"""Testes direcionados a linhas descobertas em app/routes/api.py (gate de cobertura >= 85%).

Cobre: helpers de notificação em background (_dados_chamado_*_valido, _enviar_notificacao_*,
_notificar_escalonamento, _notificar_participante_incluido, _notificar_owner_todos_concluiram),
branches de erro/permissão em atualizar_status_ajax, api_editar_chamado, bulk_atualizar_status,
api_push_subscribe, api_chamados_paginar, carregar_mais, api_buscar_usuarios,
api_editar_solicitante/cancelar_solicitante/anexo_solicitante (gestor read-only),
api_transferir_area, api_escalonar_colega, api_incluir_participantes, api_concluir_minha_parte.

Segue padrão do projeto: patch('app.routes.api.db'), patch do serviço no módulo de origem,
fixtures client_logado_{solicitante,supervisor,admin,gestor}.
"""

from unittest.mock import MagicMock, patch


def _chamado_doc_mock(
    area="Manutencao",
    responsavel_id="sup_1",
    participantes=None,
    status="Em Atendimento",
    solicitante_id="sol_outro",
    confirmacao_solicitante=None,
):
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
        "solicitante_id": solicitante_id,
        "numero_chamado": "CHM-001",
        "confirmacao_solicitante": confirmacao_solicitante,
    }
    return doc


def _mock_chamado_obj(
    area="Manutencao",
    responsavel_id="sup_1",
    participantes=None,
    status="Em Atendimento",
    solicitante_id="sol_outro",
):
    c = MagicMock()
    c.id = "id_chamado_teste"
    c.area = area
    c.responsavel_id = responsavel_id
    c.solicitante_id = solicitante_id
    c.participantes = participantes or []
    c.supervisor_ids_com_acesso = [responsavel_id] if responsavel_id else []
    c.status = status
    c.numero_chamado = "CHM-001"
    return c


# ── _dados_chamado_reaberto_valido / _dados_chamado_confirmado_valido (unit) ──


def test_dados_chamado_reaberto_valido_retorna_none_quando_nao_existe():
    from app.routes.api import _dados_chamado_reaberto_valido

    doc = MagicMock()
    doc.exists = False
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        assert _dados_chamado_reaberto_valido("ch1") is None


def test_dados_chamado_reaberto_valido_retorna_none_quando_status_diferente():
    from app.routes.api import _dados_chamado_reaberto_valido

    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {"status": "Concluído", "confirmacao_solicitante": "reaberto"}
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        assert _dados_chamado_reaberto_valido("ch1") is None


def test_dados_chamado_reaberto_valido_retorna_dados_quando_valido():
    from app.routes.api import _dados_chamado_reaberto_valido

    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {"status": "Aberto", "confirmacao_solicitante": "reaberto"}
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        result = _dados_chamado_reaberto_valido("ch1")
    assert result is not None
    assert result["status"] == "Aberto"


def test_dados_chamado_confirmado_valido_retorna_none_quando_nao_confirmado():
    from app.routes.api import _dados_chamado_confirmado_valido

    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {"confirmacao_solicitante": "pendente"}
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        assert _dados_chamado_confirmado_valido("ch1") is None


def test_dados_chamado_confirmado_valido_retorna_dados_quando_confirmado():
    from app.routes.api import _dados_chamado_confirmado_valido

    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {"confirmacao_solicitante": "confirmado"}
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        result = _dados_chamado_confirmado_valido("ch1")
    assert result is not None


# ── _enviar_notificacao_reabrir / _enviar_notificacao_confirmar (thread body) ─


class _SyncThread:
    """Substitui threading.Thread para rodar o target sincronamente (sem daemon real)."""

    def __init__(self, target=None, daemon=None, **kwargs):
        self._target = target

    def start(self):
        if self._target:
            self._target()


def test_enviar_notificacao_reabrir_executa_e_notifica(app):
    from app.routes.api import _enviar_notificacao_reabrir

    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "status": "Aberto",
        "confirmacao_solicitante": "reaberto",
        "responsavel_id": "sup_1",
        "numero_chamado": "CHM-001",
        "categoria": "Manutencao",
    }

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.threading.Thread", _SyncThread),
        patch("app.routes.api.Usuario.get_by_id", return_value=MagicMock(nome="Sup")),
        patch("app.services.notifications.notificar_supervisor_chamado_reaberto") as mock_notif,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        _enviar_notificacao_reabrir(app, "ch1", {}, "motivo reabertura", "Fulano")

    mock_notif.assert_called_once()


def test_enviar_notificacao_reabrir_excecao_e_logada_sem_propagar(app):
    from app.routes.api import _enviar_notificacao_reabrir

    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "status": "Aberto",
        "confirmacao_solicitante": "reaberto",
        "responsavel_id": "sup_1",
    }

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.threading.Thread", _SyncThread),
        patch("app.routes.api.Usuario.get_by_id", side_effect=RuntimeError("falha usuario")),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        # Não deve levantar exceção — apenas logar e seguir
        _enviar_notificacao_reabrir(app, "ch1", {}, "motivo", "Fulano")


def test_enviar_notificacao_reabrir_chamado_invalido_nao_notifica(app):
    from app.routes.api import _enviar_notificacao_reabrir

    doc = MagicMock()
    doc.exists = False

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.threading.Thread", _SyncThread),
        patch("app.services.notifications.notificar_supervisor_chamado_reaberto") as mock_notif,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        _enviar_notificacao_reabrir(app, "ch1", {}, "motivo", "Fulano")

    mock_notif.assert_not_called()


def test_enviar_notificacao_confirmar_executa_e_notifica(app):
    from app.routes.api import _enviar_notificacao_confirmar

    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "confirmacao_solicitante": "confirmado",
        "responsavel_id": "sup_1",
        "numero_chamado": "CHM-001",
        "categoria": "Manutencao",
    }

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.threading.Thread", _SyncThread),
        patch("app.routes.api.Usuario.get_by_id", return_value=MagicMock(nome="Sup")),
        patch("app.services.notifications.notificar_responsavel_chamado_confirmado") as mock_notif,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        _enviar_notificacao_confirmar(app, "ch1", {}, "Fulano")

    mock_notif.assert_called_once()


def test_enviar_notificacao_confirmar_sem_responsavel_nao_notifica(app):
    from app.routes.api import _enviar_notificacao_confirmar

    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "confirmacao_solicitante": "confirmado",
        "responsavel_id": None,
        "numero_chamado": "CHM-001",
        "categoria": "Manutencao",
    }

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.threading.Thread", _SyncThread),
        patch("app.services.notifications.notificar_responsavel_chamado_confirmado") as mock_notif,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        _enviar_notificacao_confirmar(app, "ch1", {"responsavel_id": None}, "Fulano")

    mock_notif.assert_not_called()


def test_enviar_notificacao_confirmar_excecao_e_logada_sem_propagar(app):
    from app.routes.api import _enviar_notificacao_confirmar

    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "confirmacao_solicitante": "confirmado",
        "responsavel_id": "sup_1",
    }

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.threading.Thread", _SyncThread),
        patch("app.routes.api.Usuario.get_by_id", side_effect=RuntimeError("falha usuario")),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        _enviar_notificacao_confirmar(app, "ch1", {}, "Fulano")


def test_enviar_notificacao_confirmar_chamado_invalido_nao_notifica(app):
    from app.routes.api import _enviar_notificacao_confirmar

    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {"confirmacao_solicitante": "pendente"}

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.threading.Thread", _SyncThread),
        patch("app.services.notifications.notificar_responsavel_chamado_confirmado") as mock_notif,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        _enviar_notificacao_confirmar(app, "ch1", {}, "Fulano")

    mock_notif.assert_not_called()


# ── POST /api/atualizar-status: transição bloqueada (linha 303) ──────────────


def test_atualizar_status_ajax_transicao_bloqueada_retorna_403(client_logado_supervisor):
    doc = _chamado_doc_mock(status="Concluído", confirmacao_solicitante="confirmado")
    chamado_mock = _mock_chamado_obj(status="Concluído")

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
        patch("app.routes.api.verificar_permissao_mudanca_status", return_value=(True, None)),
        patch(
            "app.services.permission_validation.chamado_aceita_transicao_status",
            return_value=(False, "bloqueado"),
        ),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = chamado_mock

        resp = client_logado_supervisor.post(
            "/api/atualizar-status",
            json={"chamado_id": "ch1", "novo_status": "Em Atendimento"},
            content_type="application/json",
        )

    assert resp.status_code == 403
    assert resp.get_json()["sucesso"] is False


# ── POST /api/editar-chamado: fallback JSON para motivo_cancelamento/setores (360-361, 373) ──


def test_api_editar_chamado_motivo_e_setores_via_json_fallback(client_logado_supervisor):
    """Quando o form não traz motivo_cancelamento/setores_adicionais, cai no fallback de
    request.get_json() (linhas 360-361, 373). Content-Type real continua multipart (para
    popular request.form com chamado_id); get_json é forçado via patch na classe Request,
    já que Flask não parseia JSON e multipart no mesmo corpo."""
    from flask import Request as FlaskRequest

    def fake_get_json(self, *args, **kwargs):
        return {"motivo_cancelamento": "motivo via json", "setores_adicionais": ["TI"]}

    with (
        patch.object(FlaskRequest, "get_json", fake_get_json),
        patch(
            "app.services.edicao_chamado_service.processar_edicao_chamado",
            return_value={"sucesso": True, "mensagem": "Salvo"},
        ) as mock_proc,
    ):
        resp = client_logado_supervisor.post(
            "/api/editar-chamado",
            data={"chamado_id": "ch1", "novo_status": "Cancelado"},
            content_type="multipart/form-data",
        )

    assert resp.status_code == 200
    assert mock_proc.called
    kwargs = mock_proc.call_args.kwargs
    assert kwargs["motivo_cancelamento"] == "motivo via json"
    assert kwargs["setores_adicionais_lista"] == ["TI"]


def test_bulk_atualizar_status_json_vazio_retorna_400(client_logado_supervisor):
    resp = client_logado_supervisor.post(
        "/api/bulk-status", data="null", content_type="application/json"
    )
    assert resp.status_code == 400


# ── POST /api/bulk-atualizar-status: pode_trans False + resultado falho (449-452, 463) ──


def test_bulk_atualizar_status_transicao_bloqueada_adiciona_erro(client_logado_supervisor):
    doc = _chamado_doc_mock(status="Concluído", confirmacao_solicitante="confirmado")

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
        patch("app.routes.api.usuario_pode_ver_chamado", return_value=True),
        patch(
            "app.services.permission_validation.chamado_aceita_transicao_status",
            return_value=(False, "bloqueado"),
        ),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = _mock_chamado_obj(status="Concluído")

        resp = client_logado_supervisor.post(
            "/api/bulk-status",
            json={"chamado_ids": ["ch1"], "novo_status": "Em Atendimento"},
            content_type="application/json",
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["atualizados"] == 0
    assert len(data["erros"]) == 1


def test_bulk_atualizar_status_servico_retorna_erro_e_registra(client_logado_supervisor):
    doc = _chamado_doc_mock(status="Em Atendimento")

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
        patch("app.routes.api.usuario_pode_ver_chamado", return_value=True),
        patch(
            "app.services.permission_validation.chamado_aceita_transicao_status",
            return_value=(True, None),
        ),
        patch(
            "app.routes.api.atualizar_status_chamado",
            return_value={"sucesso": False, "erro": "Falha ao salvar"},
        ),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = _mock_chamado_obj(status="Em Atendimento")

        resp = client_logado_supervisor.post(
            "/api/bulk-status",
            json={"chamado_ids": ["ch1"], "novo_status": "Concluído"},
            content_type="application/json",
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["atualizados"] == 0
    assert data["erros"][0]["erro"] == "Falha ao salvar"


# ── POST /api/push-subscribe: sucesso (linha 575) ────────────────────────────


def test_api_push_subscribe_sucesso_retorna_200(client_logado_supervisor):
    with patch("app.routes.api_notificacoes.salvar_inscricao", return_value=True):
        resp = client_logado_supervisor.post(
            "/api/push-subscribe",
            json={"subscription": {"endpoint": "https://push.example/x"}},
            content_type="application/json",
        )
    assert resp.status_code == 200
    assert resp.get_json()["sucesso"] is True


# ── GET /api/chamados/paginar: limite fora do range é corrigido (linha 637) ──


def test_api_chamados_paginar_limite_invalido_usa_padrao(client_logado_admin):
    with (
        patch("app.routes.api.db"),
        patch(
            "app.routes.api.aplicar_filtros_dashboard_com_paginacao",
            return_value={"docs": [], "proximo_cursor": None, "tem_proxima": False},
        ),
    ):
        resp = client_logado_admin.get("/api/chamados/paginar?limite=9999")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["paginacao"]["limite"] == 50


# ── POST /api/carregar-mais: supervisor sem áreas retorna vazio (linha 703) ──


def test_carregar_mais_supervisor_sem_areas_retorna_vazio(client_logado_supervisor_sem_areas):
    resp = client_logado_supervisor_sem_areas.post(
        "/api/carregar-mais", json={}, content_type="application/json"
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["chamados"] == []
    assert data["tem_proxima"] is False


# ── GET /api/usuarios/buscar: exceção interna (923-925) ──────────────────────


def test_api_buscar_usuarios_excecao_retorna_500(client_logado_supervisor):
    with patch("app.routes.api.Usuario.buscar_ativos", side_effect=Exception("db down")):
        resp = client_logado_supervisor.get("/api/usuarios/buscar?q=ab")
    assert resp.status_code == 500
    assert resp.get_json()["sucesso"] is False


# ── Gestor read-only bloqueado nas rotas de self-service do solicitante ──────
# (943, 973, 997)


def test_api_editar_solicitante_gestor_only_retorna_403(client_logado_gestor):
    resp = client_logado_gestor.post(
        "/api/chamado/ch1/editar-solicitante",
        json={"descricao": "nova descrição válida"},
        content_type="application/json",
    )
    assert resp.status_code == 403
    assert resp.get_json()["sucesso"] is False


def test_api_cancelar_solicitante_gestor_only_retorna_403(client_logado_gestor):
    resp = client_logado_gestor.post(
        "/api/chamado/ch1/cancelar-solicitante",
        json={"motivo": "motivo com mais de dez caracteres"},
        content_type="application/json",
    )
    assert resp.status_code == 403
    assert resp.get_json()["sucesso"] is False


def test_api_anexo_solicitante_gestor_only_retorna_403(client_logado_gestor):
    resp = client_logado_gestor.post(
        "/api/chamado/ch1/anexo-solicitante",
        data={"motivo": "motivo com mais de dez caracteres"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 403
    assert resp.get_json()["sucesso"] is False


# ── POST /api/chamado/<id>/anexo-solicitante: tipo de arquivo não permitido (1012) ──


def test_api_anexo_solicitante_tipo_nao_permitido_retorna_400(client_logado_solicitante):
    import io

    with patch("app.routes.api.salvar_anexo", return_value=None):
        resp = client_logado_solicitante.post(
            "/api/chamado/ch1/anexo-solicitante",
            data={
                "motivo": "motivo com mais de dez caracteres",
                "anexo": (io.BytesIO(b"conteudo"), "arquivo.exe"),
            },
            content_type="multipart/form-data",
        )
    assert resp.status_code == 400
    assert "not allowed" in resp.get_json()["erro"]


# ── _notificar_escalonamento (thread body, 1036-1067) ────────────────────────


def test_notificar_escalonamento_transferencia_area_executa(app):
    from app.routes.api import _notificar_escalonamento

    with (
        patch("app.routes.api.threading.Thread", _SyncThread),
        patch("app.routes.api.Usuario.get_by_id", return_value=MagicMock(nome="Destino")),
        patch("app.services.notifications.notificar_supervisor_transferencia_area") as mock_notif,
    ):
        _notificar_escalonamento(
            app,
            "ch1",
            {"numero_chamado": "CHM-001", "area": "TI", "categoria": "Chamado"},
            "transferencia_area",
            "sup_dest",
        )

    mock_notif.assert_called_once()


def test_notificar_escalonamento_colega_executa(app):
    from app.routes.api import _notificar_escalonamento

    with (
        patch("app.routes.api.threading.Thread", _SyncThread),
        patch("app.routes.api.Usuario.get_by_id", return_value=MagicMock(nome="Destino")),
        patch("app.services.notifications.notificar_supervisor_escalonamento_colega") as mock_notif,
    ):
        _notificar_escalonamento(
            app,
            "ch1",
            {"numero_chamado": "CHM-001", "area": "TI", "categoria": "Chamado"},
            "escalonamento_colega",
            "sup_dest",
        )

    mock_notif.assert_called_once()


def test_notificar_escalonamento_excecao_e_logada_sem_propagar(app):
    from app.routes.api import _notificar_escalonamento

    with (
        patch("app.routes.api.threading.Thread", _SyncThread),
        patch("app.routes.api.Usuario.get_by_id", side_effect=RuntimeError("falha usuario")),
    ):
        _notificar_escalonamento(app, "ch1", {}, "transferencia_area", "sup_dest")


def test_notificar_escalonamento_destino_inexistente_nao_notifica(app):
    from app.routes.api import _notificar_escalonamento

    with (
        patch("app.routes.api.threading.Thread", _SyncThread),
        patch("app.routes.api.Usuario.get_by_id", return_value=None),
        patch("app.services.notifications.notificar_supervisor_transferencia_area") as mock_notif,
    ):
        _notificar_escalonamento(app, "ch1", {}, "transferencia_area", "sup_dest")

    mock_notif.assert_not_called()


# ── api_transferir_area: JSON vazio, área vazia, edição bloqueada, serviço falho, exceções ──


def test_api_transferir_area_json_vazio_retorna_400(client_logado_supervisor):
    resp = client_logado_supervisor.post(
        "/api/chamado/ch1/transferir-area", data="", content_type="application/json"
    )
    assert resp.status_code == 400


def test_api_transferir_area_sem_area_retorna_400(client_logado_supervisor):
    resp = client_logado_supervisor.post(
        "/api/chamado/ch1/transferir-area",
        json={"area": "", "supervisor_id": "id_dest", "motivo": "motivo"},
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_api_transferir_area_chamado_concluido_bloqueia_edicao(client_logado_supervisor):
    doc = _chamado_doc_mock(status="Concluído", confirmacao_solicitante="confirmado")
    chamado_mock = _mock_chamado_obj(status="Concluído")

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
        patch("app.routes.api.usuario_pode_ver_chamado", return_value=True),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = chamado_mock

        resp = client_logado_supervisor.post(
            "/api/chamado/ch1/transferir-area",
            json={"area": "TI", "supervisor_id": "id_dest", "motivo": "motivo válido"},
            content_type="application/json",
        )

    assert resp.status_code == 403


def test_api_transferir_area_servico_retorna_erro_400(client_logado_supervisor):
    doc = _chamado_doc_mock(area="Manutencao", responsavel_id="sup_1")
    chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
        patch("app.routes.api.usuario_pode_ver_chamado", return_value=True),
        patch(
            "app.services.escalonamento_service.transferir_area",
            return_value={"sucesso": False, "erro": "Área destino inválida"},
        ),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = chamado_mock

        resp = client_logado_supervisor.post(
            "/api/chamado/ch1/transferir-area",
            json={"area": "TI", "supervisor_id": "id_dest", "motivo": "motivo válido"},
            content_type="application/json",
        )

    assert resp.status_code == 400


def test_api_transferir_area_value_error_retorna_400(client_logado_supervisor):
    doc = _chamado_doc_mock(area="Manutencao", responsavel_id="sup_1")
    chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
        patch("app.routes.api.usuario_pode_ver_chamado", return_value=True),
        patch(
            "app.services.escalonamento_service.transferir_area",
            side_effect=ValueError("dado inválido"),
        ),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = chamado_mock

        resp = client_logado_supervisor.post(
            "/api/chamado/ch1/transferir-area",
            json={"area": "TI", "supervisor_id": "id_dest", "motivo": "motivo válido"},
            content_type="application/json",
        )

    assert resp.status_code == 400


def test_api_transferir_area_excecao_generica_retorna_500(client_logado_supervisor):
    doc = _chamado_doc_mock(area="Manutencao", responsavel_id="sup_1")
    chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
        patch("app.routes.api.usuario_pode_ver_chamado", return_value=True),
        patch(
            "app.services.escalonamento_service.transferir_area",
            side_effect=RuntimeError("falha inesperada"),
        ),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = chamado_mock

        resp = client_logado_supervisor.post(
            "/api/chamado/ch1/transferir-area",
            json={"area": "TI", "supervisor_id": "id_dest", "motivo": "motivo válido"},
            content_type="application/json",
        )

    assert resp.status_code == 500


# ── api_escalonar_colega: JSON vazio, não encontrado, edição bloqueada, exceções ──


def test_api_escalonar_colega_json_vazio_retorna_400(client_logado_supervisor):
    resp = client_logado_supervisor.post(
        "/api/chamado/ch1/escalonar-colega", data="", content_type="application/json"
    )
    assert resp.status_code == 400


def test_api_escalonar_colega_chamado_nao_encontrado_retorna_404(client_logado_supervisor):
    doc = MagicMock()
    doc.exists = False
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        resp = client_logado_supervisor.post(
            "/api/chamado/ch_inexistente/escalonar-colega",
            json={"supervisor_id": "id_colega", "motivo": "motivo válido"},
            content_type="application/json",
        )
    assert resp.status_code == 404


def test_api_escalonar_colega_chamado_concluido_bloqueia_edicao(client_logado_supervisor):
    doc = _chamado_doc_mock(status="Concluído", confirmacao_solicitante="confirmado")
    chamado_mock = _mock_chamado_obj(status="Concluído")

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
        patch("app.routes.api.usuario_pode_ver_chamado", return_value=True),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = chamado_mock

        resp = client_logado_supervisor.post(
            "/api/chamado/ch1/escalonar-colega",
            json={"supervisor_id": "id_colega", "motivo": "motivo válido"},
            content_type="application/json",
        )

    assert resp.status_code == 403


def test_api_escalonar_colega_value_error_retorna_400(client_logado_supervisor):
    doc = _chamado_doc_mock(area="Manutencao", responsavel_id="sup_1")
    chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
        patch("app.routes.api.usuario_pode_ver_chamado", return_value=True),
        patch(
            "app.services.escalonamento_service.escalonar_colega",
            side_effect=ValueError("dado inválido"),
        ),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = chamado_mock

        resp = client_logado_supervisor.post(
            "/api/chamado/ch1/escalonar-colega",
            json={"supervisor_id": "id_colega", "motivo": "motivo válido"},
            content_type="application/json",
        )

    assert resp.status_code == 400


def test_api_escalonar_colega_excecao_generica_retorna_500(client_logado_supervisor):
    doc = _chamado_doc_mock(area="Manutencao", responsavel_id="sup_1")
    chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
        patch("app.routes.api.usuario_pode_ver_chamado", return_value=True),
        patch(
            "app.services.escalonamento_service.escalonar_colega",
            side_effect=RuntimeError("falha inesperada"),
        ),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = chamado_mock

        resp = client_logado_supervisor.post(
            "/api/chamado/ch1/escalonar-colega",
            json={"supervisor_id": "id_colega", "motivo": "motivo válido"},
            content_type="application/json",
        )

    assert resp.status_code == 500


# ── _notificar_participante_incluido / _notificar_owner_todos_concluiram (thread body) ──


def test_notificar_participante_incluido_executa(app):
    from app.routes.api import _notificar_participante_incluido

    with (
        patch("app.routes.api.threading.Thread", _SyncThread),
        patch("app.routes.api.Usuario.get_by_id", return_value=MagicMock(nome="Sup Novo")),
        patch("app.services.notifications.notificar_participante_incluido") as mock_email,
        patch("app.services.notifications_inapp.criar_notificacao") as mock_inapp,
        patch("app.services.webpush_service.enviar_webpush_usuario") as mock_push,
    ):
        _notificar_participante_incluido(
            app,
            "ch1",
            {"numero_chamado": "CHM-001", "categoria": "Chamado"},
            [{"supervisor_id": "sup_novo", "area": "TI"}],
        )

    mock_email.assert_called_once()
    mock_inapp.assert_called_once()
    mock_push.assert_called_once()


def test_notificar_participante_incluido_pula_destino_inexistente(app):
    from app.routes.api import _notificar_participante_incluido

    with (
        patch("app.routes.api.threading.Thread", _SyncThread),
        patch("app.routes.api.Usuario.get_by_id", return_value=None),
        patch("app.services.notifications.notificar_participante_incluido") as mock_email,
    ):
        _notificar_participante_incluido(
            app, "ch1", {"numero_chamado": "CHM-001"}, [{"supervisor_id": "sumiu", "area": "TI"}]
        )

    mock_email.assert_not_called()


def test_notificar_participante_incluido_excecao_e_logada_sem_propagar(app):
    from app.routes.api import _notificar_participante_incluido

    with (
        patch("app.routes.api.threading.Thread", _SyncThread),
        patch("app.routes.api.Usuario.get_by_id", side_effect=RuntimeError("falha usuario")),
    ):
        _notificar_participante_incluido(
            app, "ch1", {"numero_chamado": "CHM-001"}, [{"supervisor_id": "s1", "area": "TI"}]
        )


def test_notificar_owner_todos_concluiram_executa(app):
    from app.routes.api import _notificar_owner_todos_concluiram

    with (
        patch("app.routes.api.threading.Thread", _SyncThread),
        patch("app.routes.api.Usuario.get_by_id", return_value=MagicMock(nome="Owner")),
        patch(
            "app.services.notifications.notificar_owner_todos_participantes_concluiram"
        ) as mock_email,
        patch("app.services.notifications_inapp.criar_notificacao") as mock_inapp,
        patch("app.services.webpush_service.enviar_webpush_usuario") as mock_push,
    ):
        _notificar_owner_todos_concluiram(
            app, "ch1", {"numero_chamado": "CHM-001", "categoria": "Chamado"}, "owner_1"
        )

    mock_email.assert_called_once()
    mock_inapp.assert_called_once()
    mock_push.assert_called_once()


def test_notificar_owner_todos_concluiram_excecao_e_logada_sem_propagar(app):
    from app.routes.api import _notificar_owner_todos_concluiram

    with (
        patch("app.routes.api.threading.Thread", _SyncThread),
        patch("app.routes.api.Usuario.get_by_id", side_effect=RuntimeError("falha usuario")),
    ):
        _notificar_owner_todos_concluiram(app, "ch1", {"numero_chamado": "CHM-001"}, "owner_1")


# ── api_incluir_participantes: não encontrado, edição bloqueada, exceções ────


def test_api_incluir_participantes_chamado_nao_encontrado_retorna_404(client_logado_supervisor):
    doc = MagicMock()
    doc.exists = False
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        resp = client_logado_supervisor.post(
            "/api/chamado/ch_inexistente/incluir-participantes",
            json={"participantes": [{"supervisor_id": "s1", "area": "TI"}]},
            content_type="application/json",
        )
    assert resp.status_code == 404


def test_api_incluir_participantes_chamado_concluido_retorna_403(client_logado_supervisor):
    doc = _chamado_doc_mock(status="Concluído", confirmacao_solicitante="confirmado")
    chamado_mock = _mock_chamado_obj(status="Concluído")

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
        patch("app.routes.api.usuario_pode_ver_chamado", return_value=True),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = chamado_mock

        resp = client_logado_supervisor.post(
            "/api/chamado/ch1/incluir-participantes",
            json={"participantes": [{"supervisor_id": "s1", "area": "TI"}]},
            content_type="application/json",
        )

    assert resp.status_code == 403


def test_api_incluir_participantes_value_error_retorna_400(client_logado_supervisor):
    doc = _chamado_doc_mock(area="Manutencao", responsavel_id="sup_1")
    chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
        patch("app.routes.api.usuario_pode_ver_chamado", return_value=True),
        patch(
            "app.services.escalonamento_service.incluir_participantes",
            side_effect=ValueError("dado inválido"),
        ),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = chamado_mock

        resp = client_logado_supervisor.post(
            "/api/chamado/ch1/incluir-participantes",
            json={"participantes": [{"supervisor_id": "s1", "area": "TI"}]},
            content_type="application/json",
        )

    assert resp.status_code == 400


def test_api_incluir_participantes_excecao_generica_retorna_500(client_logado_supervisor):
    doc = _chamado_doc_mock(area="Manutencao", responsavel_id="sup_1")
    chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
        patch("app.routes.api.usuario_pode_ver_chamado", return_value=True),
        patch(
            "app.services.escalonamento_service.incluir_participantes",
            side_effect=RuntimeError("falha inesperada"),
        ),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = chamado_mock

        resp = client_logado_supervisor.post(
            "/api/chamado/ch1/incluir-participantes",
            json={"participantes": [{"supervisor_id": "s1", "area": "TI"}]},
            content_type="application/json",
        )

    assert resp.status_code == 500


# ── api_concluir_minha_parte: não encontrado, já concluído, falho, exceção ───


def test_api_concluir_minha_parte_chamado_nao_encontrado_retorna_404(client_logado_supervisor):
    doc = MagicMock()
    doc.exists = False
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        resp = client_logado_supervisor.post(
            "/api/chamado/ch_inexistente/concluir-minha-parte",
            json={},
            content_type="application/json",
        )
    assert resp.status_code == 404


def test_api_concluir_minha_parte_chamado_ja_concluido_retorna_400(client_logado_supervisor):
    doc = _chamado_doc_mock(
        status="Concluído",
        participantes=[{"supervisor_id": "sup_1", "area": "TI", "status": "pendente"}],
    )
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = _mock_chamado_obj(
            status="Concluído",
            participantes=[{"supervisor_id": "sup_1", "area": "TI", "status": "pendente"}],
        )

        resp = client_logado_supervisor.post(
            "/api/chamado/ch1/concluir-minha-parte", json={}, content_type="application/json"
        )

    assert resp.status_code == 400


def test_api_concluir_minha_parte_servico_retorna_erro_400(client_logado_supervisor):
    doc = _chamado_doc_mock(
        status="Em Atendimento",
        participantes=[{"supervisor_id": "sup_1", "area": "TI", "status": "pendente"}],
    )

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
        patch(
            "app.services.escalonamento_service.concluir_minha_parte",
            return_value={"sucesso": False, "erro": "Já concluiu sua parte"},
        ),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = _mock_chamado_obj(
            status="Em Atendimento",
            participantes=[{"supervisor_id": "sup_1", "area": "TI", "status": "pendente"}],
        )

        resp = client_logado_supervisor.post(
            "/api/chamado/ch1/concluir-minha-parte", json={}, content_type="application/json"
        )

    assert resp.status_code == 400


def test_api_concluir_minha_parte_excecao_generica_retorna_500(client_logado_supervisor):
    doc = _chamado_doc_mock(
        status="Em Atendimento",
        participantes=[{"supervisor_id": "sup_1", "area": "TI", "status": "pendente"}],
    )

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
        patch(
            "app.services.escalonamento_service.concluir_minha_parte",
            side_effect=RuntimeError("falha inesperada"),
        ),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = _mock_chamado_obj(
            status="Em Atendimento",
            participantes=[{"supervisor_id": "sup_1", "area": "TI", "status": "pendente"}],
        )

        resp = client_logado_supervisor.post(
            "/api/chamado/ch1/concluir-minha-parte", json={}, content_type="application/json"
        )

    assert resp.status_code == 500
