"""
Testes do serviço de edição de chamados (processar_edicao_chamado).
Segue ciclo TDD: comportamento especificado antes de validar contra o código.
"""

from unittest.mock import MagicMock, patch


def _make_usuario(perfil="admin", uid="admin1", areas=None):
    u = MagicMock()
    u.id = uid
    u.nome = "Admin Teste"
    u.perfil = perfil
    u.areas = areas or ["Manutencao"]
    return u


def _make_doc(exists=True, data=None):
    doc = MagicMock()
    doc.exists = exists
    doc.to_dict.return_value = data or {
        "numero_chamado": "CHM-001",
        "status": "Aberto",
        "descricao": "Descrição original",
        "responsavel": "Resp Atual",
        "responsavel_id": "resp1",
        "area": "Manutencao",
        "sla_dias": None,
        "anexo": None,
        "anexos": [],
        "setores_adicionais": [],
        "categoria": "Manutencao",
        "tipo_solicitacao": "Corretiva",
        "solicitante_nome": "Sol Teste",
    }
    return doc


# ── Guardas de entrada ─────────────────────────────────────────────────────────


def test_processar_edicao_sem_chamado_id_retorna_erro(app):
    """processar_edicao_chamado com chamado_id vazio retorna sucesso=False."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    with app.app_context():
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivo_anexo=None,
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is False
    assert "obrigatório" in result.get("erro", "").lower()


def test_processar_edicao_chamado_nao_encontrado_retorna_404(app):
    """processar_edicao_chamado com chamado inexistente retorna sucesso=False e codigo 404."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    doc_nao_existe = _make_doc(exists=False)

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc_nao_existe
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch_inexistente",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivo_anexo=None,
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is False
    assert result.get("codigo") == 404


def test_processar_edicao_supervisor_sem_permissao_retorna_403(app):
    """processar_edicao_chamado com supervisor fora da área retorna sucesso=False e codigo 403."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    supervisor = _make_usuario(perfil="supervisor", uid="sup1", areas=["Qualidade"])
    doc = _make_doc()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.permissions.usuario_pode_ver_chamado", return_value=False),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = MagicMock()
        result = processar_edicao_chamado(
            usuario_atual=supervisor,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivo_anexo=None,
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is False
    assert result.get("codigo") == 403


# ── Sem alterações ─────────────────────────────────────────────────────────────


def test_processar_edicao_sem_alteracoes_retorna_sucesso(app):
    """processar_edicao_chamado sem alterações retorna sucesso=True e mensagem no_changes_made."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    doc = _make_doc()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = MagicMock()
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivo_anexo=None,
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is True


# ── Mudança de status ──────────────────────────────────────────────────────────


def test_processar_edicao_muda_status_com_sucesso(app):
    """processar_edicao_chamado altera status quando válido e diferente do atual."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    doc = _make_doc()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.atualizar_status_chamado") as mock_status,
        patch("app.services.edicao_chamado_service.execute_with_retry"),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_db.batch.return_value = MagicMock()
        mock_chamado_cls.from_dict.return_value = MagicMock()
        mock_status.return_value = {"sucesso": True, "mensagem": "Status atualizado"}
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="Em Atendimento",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivo_anexo=None,
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is True
    mock_status.assert_called_once()


def test_processar_edicao_cancelamento_sem_motivo_retorna_erro(app):
    """processar_edicao_chamado retorna erro ao cancelar sem motivo."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    doc = _make_doc()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = MagicMock()
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="Cancelado",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivo_anexo=None,
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is False
    assert (
        "motivo" in result.get("erro", "").lower()
        or "cancelamento" in result.get("erro", "").lower()
    )


def test_processar_edicao_cancelamento_com_motivo_chama_status(app):
    """processar_edicao_chamado cancela corretamente quando motivo é fornecido."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    doc = _make_doc()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.atualizar_status_chamado") as mock_status,
        patch("app.services.edicao_chamado_service.execute_with_retry"),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_db.batch.return_value = MagicMock()
        mock_chamado_cls.from_dict.return_value = MagicMock()
        mock_status.return_value = {"sucesso": True, "mensagem": "Cancelado"}
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="Cancelado",
            motivo_cancelamento="Duplicado",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivo_anexo=None,
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is True
    kwargs = mock_status.call_args.kwargs
    assert kwargs.get("motivo_cancelamento") == "Duplicado"


# ── SLA ───────────────────────────────────────────────────────────────────────


def test_processar_edicao_sla_invalido_retorna_erro(app):
    """processar_edicao_chamado retorna erro para SLA fora do range 1-365."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    doc = _make_doc()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = MagicMock()
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="999",
            arquivo_anexo=None,
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is False
    assert "sla" in result.get("erro", "").lower()


def test_processar_edicao_sla_zero_reseta_para_padrao(app):
    """processar_edicao_chamado com sla_str='0' remove o campo sla_dias."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    doc = _make_doc(data={**_make_doc().to_dict(), "sla_dias": 7})

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.execute_with_retry"),
        patch("firebase_admin.firestore") as mock_fs,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_db.batch.return_value = MagicMock()
        mock_chamado_cls.from_dict.return_value = MagicMock()
        mock_fs.DELETE_FIELD = "DELETE"
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="0",
            arquivo_anexo=None,
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is True


# ── Descrição ─────────────────────────────────────────────────────────────────


def test_processar_edicao_nova_descricao_diferente_salva(app):
    """processar_edicao_chamado com descrição diferente adiciona ao update_data."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    doc = _make_doc()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.execute_with_retry") as mock_retry,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_db.batch.return_value = MagicMock()
        mock_chamado_cls.from_dict.return_value = MagicMock()
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="Nova descrição completamente diferente",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivo_anexo=None,
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is True
    mock_retry.assert_called_once()
    update_data = mock_retry.call_args[0][1]
    assert "descricao" in update_data


# ── Responsável ───────────────────────────────────────────────────────────────


def test_processar_edicao_novo_responsavel_atualiza_dados(app):
    """processar_edicao_chamado com novo responsável válido atualiza responsavel e area."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    doc = _make_doc()
    novo_resp = MagicMock()
    novo_resp.id = "resp2"
    novo_resp.nome = "Novo Responsavel"
    novo_resp.areas = ["Elétrica"]
    novo_resp.area = "Elétrica"

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.Usuario") as mock_usuario_cls,
        patch("app.services.edicao_chamado_service.execute_with_retry") as mock_retry,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_db.batch.return_value = MagicMock()
        mock_chamado_cls.from_dict.return_value = MagicMock()
        mock_usuario_cls.get_by_id.return_value = novo_resp
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="resp2",
            novo_sla_str="",
            arquivo_anexo=None,
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is True
    update_data = mock_retry.call_args[0][1]
    assert update_data.get("responsavel") == "Novo Responsavel"


# ── Setores adicionais ────────────────────────────────────────────────────────


def test_processar_edicao_setores_adicionais_dispara_notificacao(app):
    """processar_edicao_chamado com novo setor adicional dispara thread de notificação."""

    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    doc = _make_doc()  # setores_adicionais = []

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.execute_with_retry"),
        patch("app.services.edicao_chamado_service.threading") as mock_threading,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_db.batch.return_value = MagicMock()
        mock_chamado_cls.from_dict.return_value = MagicMock()
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivo_anexo=None,
            setores_adicionais_lista=["Elétrica"],
        )
    assert result["sucesso"] is True
    assert mock_threading.Thread.call_count >= 1
